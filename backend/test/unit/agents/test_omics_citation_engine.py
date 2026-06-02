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
                    "annotation": "chalcone--flavonone isomerase",
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

    assert [source.citation_id for source in sources] == ["T1", "L1", "Guard"]
    assert sources[0].source_type == "transcriptome"
    assert "GeneA" in sources[0].text
    assert sources[0].metadata["annotation"] == "chalcone--flavonone isomerase"
    assert sources[1].source_type == "literature"
    assert sources[1].metadata["doi"] == "10.1234/real"
    assert sources[1].metadata["quoted_sentence"] == "Verified sentence."
    assert sources[2].source_type == "guard_rule"


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

    assert result["backend"] == "canonical_renderer"
    assert result["raw_answer_backend"] == "rule_fallback"
    assert "GeneA" in result["answer_markdown"]
    assert "抗旱" in result["answer_markdown"]
    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "10.1234/real" not in body
    assert "Verified sentence." not in body
    assert "DOI：10.1234/real" in source_index
    assert "引用原句：Verified sentence." in source_index
    assert result["literature_cards"][0]["doi"] == "10.1234/real"
    assert result["citations"][0]["citation_id"] == "T1"
    assert result["citations"][1]["citation_id"] == "L1"
    assert result["citations"][2]["citation_id"] == "Guard"
    assert result["answer_markdown"].count("## ") >= 6
    assert "当前未命中可用的在线 LLM 分析" not in result["answer_markdown"]


def test_build_citation_result_includes_a1_annotation_source_and_claim_trace(monkeypatch):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    evidence_pack = _sample_evidence_pack()
    evidence_pack["task"]["trait"] = "黄酮相关"
    evidence_pack["targets"]["trait_terms"] = ["黄酮相关"]
    evidence_pack["evidence"]["annotation"] = [
        {
            "evidence_id": "A1",
            "source_file": "/tmp/uploaded_gene_function_table.tsv",
            "summary": "用户上传功能注释文件按 gene_id 与 DEG 结果关联。",
            "metadata": {
                "annotation_file": "/tmp/uploaded_gene_function_table.tsv",
                "annotation_file_name": "uploaded_gene_function_table.tsv",
                "annotation_path_exists": True,
                "annotated_transcriptome_path": "/tmp/transcriptome_deg/significant_de_genes.annotated.tsv",
                "annotation_gene_match_count": 1,
                "annotation_unmatched_gene_count": 0,
                "annotation_duplicate_gene_id_count": 1,
                "annotation_isoform_count": 2,
                "annotation_candidate_gene_ids": ["GeneA"],
                "trait_relevant_annotation_gene_ids": ["GeneA"],
                "candidate_annotations": [
                    {
                        "gene_id": "GeneA",
                        "transcript_ids": ["GeneA.t1", "GeneA.t2"],
                        "matched_by": "gene_id_and_transcript_id",
                        "annotation_fields": {
                            "SwissProt_annotation": "chalcone isomerase",
                            "KEGG_Pathway": "flavonoid biosynthesis",
                        },
                        "normalized_function_terms": ["chalcone isomerase"],
                        "pathway_terms": ["flavonoid biosynthesis"],
                        "go_terms": ["flavonoid biosynthetic process"],
                        "domain_terms": ["PF02431"],
                        "trait_relevance_terms": ["flavonoid", "chalcone"],
                        "trait_relevance_score": 2,
                        "trait_relevance_level": "high",
                        "pubmed_query_terms": [
                            "GeneA",
                            "黄酮相关",
                            "Setaria italica",
                            "chalcone isomerase",
                            "flavonoid biosynthesis",
                        ],
                    }
                ],
                "pathway_summary": ["flavonoid biosynthesis"],
                "pubmed_query_terms": ["GeneA", "Setaria italica", "chalcone isomerase"],
            },
        }
    ]

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="请给出一些育种建议",
        use_llamaindex=False,
        model_name="",
    )

    citation_ids = [item["citation_id"] for item in result["citations"]]
    assert "A1" in citation_ids
    assert "已从用户上传功能注释文件生成 A1 功能注释证据" in result["answer_markdown"]
    assert "[A1] [Guard]" in result["answer_markdown"]
    _, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "[A1] 基因功能注释证据" in source_index
    assert "uploaded_gene_function_table.tsv" in source_index
    assert "flavonoid biosynthesis" in source_index
    assert "chalcone isomerase" in source_index
    assert any("A1" in row["citation_ids"] for row in result["claim_trace"])
    assert "GeneID\tmRNA_id" not in result["answer_markdown"]


def test_build_breeding_analysis_prompt_includes_annotation_summary_not_raw_table():
    evidence_pack = _sample_evidence_pack()
    evidence_pack["evidence"]["annotation"] = [
        {
            "evidence_id": "A1",
            "metadata": {
                "annotation_file_name": "custom_function_annotation.tsv",
                "annotation_gene_match_count": 1,
                "annotation_unmatched_gene_count": 0,
                "candidate_annotations": [
                    {
                        "gene_id": "GeneA",
                        "normalized_function_terms": ["drought response protein"],
                        "pathway_terms": ["ABA signaling"],
                        "domain_terms": ["InterPro IPR0001"],
                        "trait_relevance_level": "medium",
                    }
                ],
                "pathway_summary": ["ABA signaling"],
                "pubmed_query_terms": ["GeneA", "drought response protein"],
            },
        }
    ]

    prompt = build_breeding_analysis_prompt(
        evidence_pack=evidence_pack,
        question="根据数据给出候选验证方案",
        sources=build_citation_sources(evidence_pack),
    )

    assert "custom_function_annotation.tsv" in prompt["user_prompt"]
    assert "drought response protein" in prompt["user_prompt"]
    assert "GeneID\tmRNA_id" not in prompt["user_prompt"]


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

    assert result["backend"] == "canonical_renderer"
    assert result["raw_answer_backend"] == "llm"
    assert "抗旱相关性状" in result["raw_llm_answer"]
    assert "# 育种建议报告" in result["answer_markdown"]
    assert "当前分析围绕抗旱相关性状展开。" not in result["answer_markdown"]


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
    assert trace[1]["source_status"] == "background"
    assert trace[2]["citation_ids"] == []
    assert trace[2]["source_status"] == "needs_citation"


def test_build_citation_result_keeps_supported_claims_for_background_and_metabolome():
    evidence_pack = _sample_evidence_pack()
    evidence_pack["evidence"]["metabolome_context"] = [
        {
            "evidence_id": "M1",
            "summary": "检测到代谢组结果文件，黄酮相关化合物存在分层差异。",
            "top_metabolites": [
                {
                    "compound_id": "pme1002",
                    "name": "L-酪胺",
                    "class": "phenylpropanoid amine",
                    "log2fc": "1.11",
                    "fdr": "0.0029",
                    "type": "up",
                },
                {
                    "compound_id": "pme2001",
                    "name": "对香豆酸",
                    "class": "phenolic acid",
                    "log2fc": "0.88",
                    "fdr": "0.0042",
                    "type": "up",
                },
            ],
            "total_record_count": 128,
            "significant_record_count": 12,
            "trait_relevance_note": "未检测到典型黄酮骨架代谢物显著差异；当前代谢组线索主要来自苯丙烷相关分支代谢物或其他相关代谢物。",
            "preview_rows": [
                "compound_id\tmetabolite\tLog2FC\tFDR\tType",
                "pme1002\tL-酪胺\t1.11\t0.0029\tup",
            ],
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

    assert {"T1", "M1", "BG1", "Guard"}.issubset(supported_ids)
    assert any(row["source_status"] == "supported" for row in result["claim_trace"])
    assert "Top 关键代谢物：" in result["answer_markdown"]
    assert "pme1002 / L-酪胺 / Class=phenylpropanoid amine / Log2FC=1.11 / FDR=0.0029 / Type=up" in result["answer_markdown"]
    assert "总记录数：128" in result["answer_markdown"]
    assert "显著差异代谢物数：12" in result["answer_markdown"]
    assert "compound\tvalue" not in result["answer_markdown"]
    assert "N/A / L-酪胺" not in result["answer_markdown"]


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

    assert "Si9g037800" not in result["answer_markdown"]
    assert "群体" in result["answer_markdown"]
    assert "黄酮" in result["answer_markdown"]
    assert "[T1]" not in result["answer_markdown"]
    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "10.5678/bg" not in body
    assert "Flavonoid accumulation changed in millet leaves." not in body
    assert "DOI：10.5678/bg" in source_index
    assert "引用原句：Flavonoid accumulation changed in millet leaves." in source_index
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


def test_canonical_answer_body_uses_sentence_end_citations_and_hides_doi_before_source_index(
    monkeypatch,
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    evidence_pack = _sample_evidence_pack()
    evidence_pack["task"]["trait"] = "黄酮相关"
    evidence_pack["targets"]["genes"] = ["Si9g037800"]
    evidence_pack["targets"]["trait_terms"] = ["黄酮相关"]
    evidence_pack["evidence"]["metabolome_context"] = [
        {
            "evidence_id": "M1",
            "summary": "检测到黄酮相关代谢线索。",
            "preview_text": "compound_id\tmetabolite\tLog2FC\tFDR\tType\npme1002\tL-酪胺\t1.11\t0.0029\tup",
            "preview_rows": [
                "compound_id\tmetabolite\tLog2FC\tFDR\tType",
                "pme1002\tL-酪胺\t1.11\t0.0029\tup",
            ],
            "preview_row_count": 1,
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
        }
    ]

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="请给出一些育种建议",
        use_llamaindex=False,
        model_name="",
    )

    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "Si9g037800 是当前 DEG 结果支持的核心候选基因。[T1]" in body
    assert "代谢组结果提示黄酮相关代谢分支可能发生扰动" in body
    assert "[M1] [Guard]" in body
    assert "PubMed 文献仅作为背景线索" in body
    assert "[BG1]" in body
    assert "已完成湿实验验证、群体验证或最终 KASP/CAPS 标记开发。[Guard]" in body
    assert "DOI：" not in body
    assert "PMID：" not in body
    assert "引用原句：" not in body
    assert "[T1] 转录组 DEG" in source_index
    assert "[M1] 代谢组" in source_index
    assert "[BG1] PubMed 背景文献" in source_index
    assert "DOI：10.5678/bg" in source_index
    assert "引用原句：Background evidence supports flavonoid accumulation differences." in source_index
    assert "logFC=1.8" in source_index
    assert "padj=0.02" in source_index
    assert "注释：chalcone--flavonone isomerase" in source_index


def test_claim_trace_excludes_source_index_and_only_tracks_real_claims():
    sources = build_citation_sources(_sample_evidence_pack())
    answer = "\n".join(
        [
            "# 育种建议报告",
            "",
            "## 当前输入与证据状态",
            "- 目标性状：黄酮相关",
            "- GeneA 是当前 DEG 结果支持的核心候选基因。[T1]",
            "- PubMed 文献仅作为背景线索，不等同于当前实验直接验证。[Guard]",
            "",
            "---",
            "",
            "## 来源索引",
            "",
            "[T1] 转录组 DEG",
            "DOI：10.1234/real",
            "引用原句：Verified sentence.",
        ]
    )

    trace = build_claim_trace(answer_markdown=answer, sources=sources)

    assert [row["text"] for row in trace] == [
        "GeneA 是当前 DEG 结果支持的核心候选基因。[T1]",
        "PubMed 文献仅作为背景线索，不等同于当前实验直接验证。[Guard]",
    ]


def test_empty_background_literature_does_not_emit_bg_citations(monkeypatch):
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

    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "当前未检索到可用 PubMed 背景文献。[Guard]" in body
    assert "[BG1]" not in body
    assert "[BG2]" not in body
    assert "[BG1]" not in source_index
    assert "[BG2]" not in source_index
    assert all("BG" not in " ".join(row["citation_ids"]) for row in result["claim_trace"])


def test_background_literature_without_quote_is_not_treated_as_bg_evidence(monkeypatch):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    evidence_pack = _sample_evidence_pack()
    evidence_pack["background_literature_records"] = [
        {
            "citation_id": "BG1",
            "title": "429 fallback record",
            "pmid": "123456",
            "quoted_sentence": "",
            "source": "PubMed",
        }
    ]

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="根据数据给出候选验证方案",
        use_llamaindex=False,
        model_name="",
    )

    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "当前未检索到可用 PubMed 背景文献。[Guard]" in body
    assert "[BG1]" not in body
    assert "[BG1]" not in source_index


def test_a1_source_index_prefers_nr_function_and_cleans_dirty_tokens(monkeypatch):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    evidence_pack = _sample_evidence_pack()
    evidence_pack["evidence"]["annotation"] = [
        {
            "evidence_id": "A1",
            "source_file": "/tmp/uploaded_gene_function_table.tsv",
            "metadata": {
                "annotation_file": "/tmp/uploaded_gene_function_table.tsv",
                "annotation_gene_match_count": 1,
                "annotation_unmatched_gene_count": 0,
                "candidate_annotations": [
                    {
                        "gene_id": "GeneA",
                        "annotation_fields": {
                            "NR_annotation": "naringenin-chalcone synthase",
                            "SwissProt_annotation": "chalcone synthase [Hordeum vulgare]",
                            "KO": "ko:K01859",
                            "KEGG_gene_name": "E5.5.1.6",
                            "KEGG_Pathway": "ko00941",
                            "Pathway_definition": "Flavonoid biosynthesis",
                            "GO_IDs": "GO:0009813",
                            "Pfam_Description": "Chalcone and stilbene synthases, N-terminal domain",
                            "InterPro_Description": "Chalcone/stilbene synthase, conserved site",
                        },
                        "normalized_function_terms": ["naringenin-chalcone synthase"],
                        "pathway_terms": ["ko00941", "dbget-bin", "www_bget?ko:K01859"],
                        "go_terms": ["GO:0009813", "URL 片段"],
                        "domain_terms": ["Chalcone and stilbene synthases, N-terminal domain", "[X]"],
                    }
                ],
                "pathway_summary": [
                    "dbget-bin",
                    "www_bget?ko:K01859",
                    "URL 片段",
                    "[X]",
                    "Unnamed protein",
                    "ko00941",
                    "Flavonoid biosynthesis",
                    "GO:0009813",
                    "Chalcone and stilbene synthases, N-terminal domain",
                    "Chalcone/stilbene synthase, conserved site",
                ],
            },
        }
    ]

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="请给出一些育种建议",
        use_llamaindex=False,
        model_name="",
    )

    _, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "功能：naringenin-chalcone synthase" in source_index
    assert "SwissProt/同源注释：chalcone synthase [Hordeum vulgare]" in source_index
    assert "KO：K01859" in source_index
    assert "KEGG gene：E5.5.1.6" in source_index
    assert "KEGG Pathway：ko00941; Flavonoid biosynthesis" in source_index
    assert "GO：GO:0009813" in source_index
    assert "Pfam：Chalcone and stilbene synthases, N-terminal domain" in source_index
    assert "InterPro：Chalcone/stilbene synthase, conserved site" in source_index
    assert "dbget-bin" not in source_index
    assert "www_bget" not in source_index
    assert "URL 片段" not in source_index
    assert "[X]" not in source_index
    assert "Unnamed protein" not in source_index


def test_metabolome_summary_counts_type_and_significant_rows_without_na_prefix(monkeypatch):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    evidence_pack = _sample_evidence_pack()
    evidence_pack["task"]["trait"] = "黄酮相关"
    evidence_pack["evidence"]["metabolome_context"] = [
        {
            "evidence_id": "M1",
            "summary": "代谢组摘要。",
            "total_record_count": 4,
            "significant_record_count": 2,
            "top_metabolites": [
                {
                    "compound_id": "",
                    "name": "Tyramine",
                    "class": "phenylpropanoid amine",
                    "log2fc": "1.11",
                    "fdr": "0.0029",
                    "type": "up",
                }
            ],
            "source_file": "metabolome_raw_3372.tsv",
        }
    ]

    result = build_citation_result(
        evidence_pack=evidence_pack,
        question="请给出一些育种建议",
        use_llamaindex=False,
        model_name="",
    )

    _, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "显著差异代谢物数：2" in source_index
    assert "Tyramine / Class=phenylpropanoid amine / Log2FC=1.11 / FDR=0.0029 / Type=up" in source_index
    assert "N/A / Tyramine" not in source_index
