from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.citation_engine import (
    build_breeding_analysis_prompt,
    build_citation_result,
    build_citation_sources,
    build_claim_trace,
    build_literature_cards,
)


# _sample_evidence_pack() 构造一个动态任务：性状是“抗旱”，
# 目标基因是 GeneA，文献 DOI 是 10.1234/real。它故意不用 Si9g037800 / 黄酮，继续防止 smoke 任务硬编码
def _sample_evidence_pack():
    return {
        "task": {
            "trait": "抗旱",
            "question": "根据数据给出候选验证方案",
            "intent": "candidate_validation",
        },
        "targets": {
            "genes": ["GeneA"],
            "trait_terms": ["抗旱"],
        },
        "evidence": {
            "transcriptome": [
                {
                    "evidence_id": "T1",
                    "gene_id": "GeneA",
                    "logfc": "1.8",
                    "pvalue": "0.003",
                    "padj": "0.02",
                    "source_file": "significant_de_genes.tsv",
                }
            ],
            "literature": [
                {
                    "evidence_id": "L1",
                    "doi": "10.1234/real",
                    "quoted_sentence": "Verified sentence.",
                    "title": "Verified Paper",
                    "relevance_level": "background",
                    "source_file": "verified_literature_evidence.tsv",
                }
            ],
            "metabolome_context": [],
            "genome_context": [],
        },
        "guard_requirements": {
            "required_gene_ids": ["GeneA"],
            "required_trait_terms": ["抗旱"],
            "must_include_population_validation": True,
            "allowed_dois": ["10.1234/real"],
            "allowed_quoted_sentences": ["Verified sentence."],
        },
    }


# 测试验证 Evidence Pack 能转为 citation source
def test_build_citation_sources_from_evidence_pack():
    sources = build_citation_sources(_sample_evidence_pack())

    assert [source.citation_id for source in sources] == ["T1", "L1"]
    assert sources[0].source_type == "transcriptome"
    assert "GeneA" in sources[0].text
    assert sources[1].source_type == "literature"
    assert sources[1].metadata["doi"] == "10.1234/real"
    assert sources[1].metadata["quoted_sentence"] == "Verified sentence."


# 测试验证 literature source 能转成前端文献卡片
def test_build_literature_cards_from_sources():
    sources = build_citation_sources(_sample_evidence_pack())
    cards = build_literature_cards(sources)

    assert len(cards) == 1
    assert cards[0]["citation_id"] == "L1"
    assert cards[0]["doi"] == "10.1234/real"
    assert cards[0]["quoted_sentence"] == "Verified sentence."


# 测试验证 fallback citation result 能生成用户正文和结构化 citation 结果，且 DOI/quoted_sentence 只保留在 JSON。
def test_build_citation_result_uses_rule_fallback_without_hardcoding():
    result = build_citation_result(
        evidence_pack=_sample_evidence_pack(),
        question="根据数据给出候选验证方案",
        use_llamaindex=False,
        model_name="",
    )

    assert result["backend"] == "rule_fallback"
    assert "GeneA" in result["answer_markdown"]
    assert "抗旱" in result["answer_markdown"]
    assert "10.1234/real" not in result["answer_markdown"]
    assert "Verified sentence." not in result["answer_markdown"]
    assert result["literature_cards"][0]["doi"] == "10.1234/real"
    assert result["citations"][0]["citation_id"] == "T1"
    assert result["citations"][1]["citation_id"] == "L1"


def test_build_breeding_analysis_prompt_changes_with_trait():
    drought_prompt = build_breeding_analysis_prompt(
        evidence_pack=_sample_evidence_pack(),
        question="根据数据给出候选验证方案",
        sources=build_citation_sources(_sample_evidence_pack()),
    )
    flavonoid_pack = _sample_evidence_pack()
    flavonoid_pack["task"]["trait"] = "黄酮相关"
    flavonoid_pack["targets"]["trait_terms"] = ["黄酮相关"]
    flavonoid_prompt = build_breeding_analysis_prompt(
        evidence_pack=flavonoid_pack,
        question="给出一些育种建议",
        sources=build_citation_sources(flavonoid_pack),
    )

    assert "abiotic stress" in drought_prompt["user_prompt"] or "抗旱" in drought_prompt["user_prompt"]
    assert "flavonoid" in flavonoid_prompt["user_prompt"].lower() or "黄酮" in flavonoid_prompt["user_prompt"]


def test_build_citation_result_prefers_llm_when_model_invocation_succeeds(monkeypatch):
    class FakeModel:
        def invoke(self, messages):
            joined = "\n".join(str(item.content) for item in messages)
            assert "抗旱" in joined
            return type("Response", (), {"content": "# 多组学育种分析结果\n\n当前分析围绕抗旱相关性状展开。"})

    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda fully_specified_name: FakeModel(),
    )

    result = build_citation_result(
        evidence_pack=_sample_evidence_pack(),
        question="根据数据给出候选验证方案",
        use_llamaindex=False,
        model_name="provider:model",
    )

    assert result["backend"] == "llm"
    assert "抗旱相关性状" in result["answer_markdown"]


# 测试验证 claim_trace 能标记哪些句子有 citation，哪些句子没有 citation
def test_build_claim_trace_marks_cited_and_uncited_segments():
    answer = "\n".join(
        [
            "GeneA 是候选基因。[T1]",
            "已验证文献可作为背景支持。[L1]",
            "这是一条没有 citation 的说明。",
        ]
    )
    sources = build_citation_sources(_sample_evidence_pack())

    trace = build_claim_trace(answer_markdown=answer, sources=sources)

    assert trace[0]["citation_ids"] == ["T1"]
    assert trace[0]["source_status"] == "supported"
    assert trace[1]["citation_ids"] == ["L1"]
    assert trace[1]["source_status"] == "supported"
    assert trace[2]["citation_ids"] == []
    assert trace[2]["source_status"] == "uncited"
