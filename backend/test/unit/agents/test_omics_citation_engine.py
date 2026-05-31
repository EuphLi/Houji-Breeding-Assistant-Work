from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.citation_engine import (
    CitationSource,
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


# 测试验证 fallback citation result 能生成用户正文和结构化 citation 结果。
def test_build_citation_result_uses_rule_fallback_without_hardcoding(monkeypatch):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
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


def test_build_citation_result_keeps_supported_claims_for_background_and_metabolome():
    evidence_pack = _sample_evidence_pack()
    evidence_pack["evidence"]["metabolome_context"] = [
        {
            "evidence_id": "M1",
            "summary": "检测到代谢组结果文件，黄酮相关化合物存在分层差异。",
            "preview_text": "compound\tvalue\nflavonoid_a\t12.5",
            "source_file": "metabolome_raw_3372.tsv",
        }
    ]
    evidence_pack["background_literature_records"] = [
        {
            "citation_id": "BG1",
            "title": "Background flavonoid paper",
            "pmid": "123456",
            "doi": "10.5678/bg",
            "quoted_sentence": "Background evidence supports flavonoid accumulation differences.",
            "source": "PubMed",
            "query": "foxtail millet flavonoid",
            "quote_scope": "abstract",
            "relevance_level": "background",
        }
    ]
    evidence_pack["debug"] = {
        "inputs": {
            "transcriptome_path_exists": True,
            "metabolome_path_exists": True,
            "evidence_level": "user_provided_path",
        }
    }

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="根据数据给出候选验证方案",
        use_llamaindex=False,
        model_name="",
    )

    supported_ids = {
        citation_id
        for row in result["claim_trace"]
        for citation_id in row["citation_ids"]
    }

    assert {"T1", "L1", "M1", "BG1"}.issubset(supported_ids)
    assert any(row["source_status"] == "supported" for row in result["claim_trace"])


def test_build_claim_trace_skips_markdown_table_separators_and_headers():
    sources = [
        CitationSource(
            citation_id="M1",
            source_type="metabolome_context",
            text="metabolome",
            metadata={},
        )
    ]

    trace = build_claim_trace(
        answer_markdown="\n".join(
            [
                "# 标题",
                "## 文献依据",
                "| 列1 | 列2 |",
                "| --- | --- |",
                "- 黄酮相关化合物存在分层差异。[M1]",
            ]
        ),
        sources=sources,
    )

    assert len(trace) == 1
    assert trace[0]["citation_ids"] == ["M1"]


def test_build_citation_result_for_flavonoid_trait_keeps_trait_specific_acceptance_items(
    monkeypatch,
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    evidence_pack = {
        "task": {
            "trait": "黄酮相关",
            "question": "请给出一些育种建议",
        },
        "targets": {
            "genes": [],
            "trait_terms": ["黄酮相关"],
        },
        "evidence": {
            "transcriptome": [],
            "literature": [],
            "metabolome_context": [
                {
                    "evidence_id": "M1",
                    "summary": "黄酮相关化合物在不同材料间存在分层差异。",
                    "preview_text": "compound\tvalue\nflavonoid_a\t12.5",
                    "source_file": "metabolome_raw_3372.tsv",
                }
            ],
            "genome_context": [],
        },
        "background_literature_records": [
            {
                "citation_id": "BG1",
                "title": "Flavonoid pathway in foxtail millet",
                "pmid": "123456",
                "doi": "10.5678/bg",
                "quoted_sentence": "Flavonoid accumulation changed in millet leaves.",
                "source": "PubMed",
                "query": "Setaria italica flavonoid",
                "quote_scope": "abstract",
                "relevance_level": "background",
            }
        ],
        "debug": {
            "inputs": {
                "trait": "黄酮相关",
                "metabolome_path_exists": True,
                "transcriptome_path_exists": False,
                "evidence_level": "user_provided_path",
            }
        },
    }

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="请给出一些育种建议",
        use_llamaindex=False,
        model_name="",
    )

    assert "Si9g037800" in result["answer_markdown"]
    assert "群体" in result["answer_markdown"]
    assert "黄酮" in result["answer_markdown"]
    assert "10.5678/bg" not in result["answer_markdown"]
    assert "Flavonoid accumulation changed in millet leaves." not in result["answer_markdown"]
    assert result["literature_cards"][0]["doi"] == "10.5678/bg"
    assert (
        result["literature_cards"][0]["quoted_sentence"]
        == "Flavonoid accumulation changed in millet leaves."
    )


def test_build_citation_result_for_yield_trait_does_not_force_flavonoid_template():
    evidence_pack = _sample_evidence_pack()
    evidence_pack["task"]["trait"] = "高产相关"
    evidence_pack["targets"]["trait_terms"] = ["高产相关"]

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="围绕高产相关给出一些育种建议",
        use_llamaindex=False,
        model_name="",
    )

    assert "高产" in result["answer_markdown"] or "产量" in result["answer_markdown"]
    assert "群体" in result["answer_markdown"]
    assert "Si9g037800" not in result["answer_markdown"]
    assert "黄酮" not in result["answer_markdown"]
