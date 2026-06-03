from __future__ import annotations

import json

import pytest

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.workflow import (
    prepare_cited_guarded_omics_analysis_from_context,
)

"""
测试覆盖完整链路：

临时 DEG TSV
临时 verified_literature_evidence.tsv
↓
OmicsBreedingAnalysisContext
↓
Evidence Pack
↓
Citation Result
↓
Dynamic Guard
↓
final_result.json

它确认：

1. 最终状态是 completed
2. canonical citation renderer 可用
3. answer_markdown 主正文包含 GeneA / 抗旱，DOI / quoted_sentence 只出现在来源索引
4. guard_result 通过
5. citations / literature_cards / claim_trace 都存在
6. 所有关键 artifact 文件都写出
"""

def test_prepare_cited_guarded_omics_analysis_from_context_writes_final_result(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.workflow.search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "queries": [],
            "records": [],
            "warnings": [],
        },
    )
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\tannotation\n"
        "GeneA\t1.8\t0.003\t0.02\tchalcone--flavonone isomerase\n",
        encoding="utf-8",
    )

    literature_path = tmp_path / "verified_literature_evidence.tsv"
    literature_path.write_text(
        "evidence_id\tdoi\tquoted_sentence\tstatus\tis_demo\tsource\ttitle\trelevance_level\n"
        "L1\t10.1234/real\tVerified sentence.\tverified\tfalse\tPubMed\tVerified Paper\tbackground\n",
        encoding="utf-8",
    )

    evidence_pack_path = tmp_path / "omics_evidence_pack.json"

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        literature_evidence_path=str(literature_path),
        evidence_pack_output_path=str(evidence_pack_path),
    )

    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=False,
        output_dir=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["backend"] == "canonical_renderer"
    assert result["raw_answer_backend"] == "rule_fallback"
    assert result["guard_result"]["passed"] is True

    assert "GeneA" in result["answer_markdown"]
    assert "抗旱" in result["answer_markdown"]
    assert "## 来源索引" in result["answer_markdown"]
    assert "## 当前输入与证据状态" in result["answer_markdown"]
    assert "## 候选基因与候选通路" in result["answer_markdown"]
    assert "## 育种建议" in result["answer_markdown"]
    assert "## 后续验证建议" in result["answer_markdown"]
    assert "## 边界说明" in result["answer_markdown"]
    assert len([line for line in result["answer_markdown"].splitlines() if line.strip()]) >= 24
    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "10.1234/real" not in body
    assert "Verified sentence." not in body
    assert "DOI：10.1234/real" in source_index
    assert "引用原句：Verified sentence." in source_index
    assert "注释：chalcone--flavonone isomerase" in source_index

    assert result["citations"][0]["citation_id"] == "T1"
    assert result["citations"][1]["citation_id"] == "L1"
    assert result["citations"][-1]["citation_id"] == "Guard"
    assert result["literature_cards"][0]["doi"] == "10.1234/real"
    assert result["summary"]["literature_path_exists"] is True
    assert result["summary"]["usable_literature_count"] == 1

    assert result["claim_trace"]
    assert any(item["citation_ids"] for item in result["claim_trace"])

    assert (tmp_path / "omics_evidence_pack.json").exists()
    assert (tmp_path / "answer_markdown.md").exists()
    assert (tmp_path / "citation_result.json").exists()
    assert (tmp_path / "guard_result.json").exists()
    assert (tmp_path / "final_result.json").exists()

    loaded = json.loads((tmp_path / "final_result.json").read_text(encoding="utf-8"))
    assert loaded["status"] == "completed"
    assert loaded["guard_result"]["passed"] is True
    assert loaded["summary"]["target_genes"] == ["GeneA"]
    assert loaded["summary"]["analysis_backend"] == "rule_based"
    assert loaded["summary"]["render_backend"] == "canonical_renderer"
    assert loaded["summary"]["raw_answer_backend"] == "rule_fallback"


def test_prepare_cited_guarded_omics_analysis_from_context_adds_annotation_a1(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.workflow.search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "queries": [],
            "records": [],
            "warnings": [],
        },
    )
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\ttranscript_ids\tlogFC\tpvalue\tpadj\n"
        "GeneA\tGeneA.t1\t1.8\t0.003\t0.02\n",
        encoding="utf-8",
    )
    annotation_path = tmp_path / "custom_function_annotation.tsv"
    annotation_path.write_text(
        "gene_id\ttranscript_id\tKEGG_Pathway\tInterPro_Description\n"
        "GeneA\tGeneA.t1\tflavonoid biosynthesis\tchalcone isomerase domain\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation_path),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=False,
        output_dir=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["summary"]["annotation_evidence_count"] == 1
    assert result["summary"]["annotation_merge_status"] == "completed"
    assert result["summary"]["annotation_merge_matched_count"] == 1
    assert result["summary"]["annotation_merge_unmatched_count"] == 0
    assert result["summary"]["annotation_merge_duplicate_count"] == 0
    assert result["summary"]["annotation_gene_match_count"] == 1
    assert result["summary"]["annotation_isoform_count"] == 1
    assert result["summary"]["pfam_literature_keywords"] == ["chalcone isomerase domain"]
    assert result["summary"]["literature_query_plan_count"] > 0
    assert result["summary"]["literature_query_plan_source"] == "annotated_transcriptome_pfam"
    assert result["summary"]["pathway_ids"] == []
    assert result["summary"]["ko_terms"] == []
    assert result["summary"]["annotated_transcriptome_path"].endswith(
        "transcriptome_deg/significant_de_genes.annotated.tsv"
    )
    assert result["summary"]["annotated_transcriptome_read_by_llm"] is True
    assert result["summary"]["background_literature_count"] == 0
    assert result["summary"]["background_literature_status"] == "disabled_for_unit_test"
    assert result["summary"]["literature_query_plan_used_for_background_search"] is False
    assert "A1" in {item["citation_id"] for item in result["citations"]}
    assert "[A1] 基因功能注释证据" in result["answer_markdown"]
    assert "系统已将转录组 DEG 结果与用户上传功能注释文件按 gene_id 合并" in result["answer_markdown"]
    assert "flavonoid biosynthesis" in result["answer_markdown"]
    assert any("A1" in row["citation_ids"] for row in result["claim_trace"])
    assert result["summary"]["annotated_transcriptome_path"] in result["artifacts"]
    assert result["summary"]["literature_query_plan_path"] in result["artifacts"]
    assert result["evidence_pack"]["evidence"]["annotation"][0]["evidence_id"] == "A1"
    assert (
        result["evidence_pack"]["evidence"]["annotation"][0]["metadata"]["annotated_transcriptome_path"]
        == result["summary"]["annotated_transcriptome_path"]
    )
    prompt_text = result["analysis_prompt"]["user_prompt"]
    assert "## 转录组-功能注释合并文件全文" in prompt_text
    assert "significant_de_genes.annotated.tsv" in prompt_text
    assert "gene_id\ttranscript_ids\tlogFC\tpvalue\tpadj\tgene_id\ttranscript_id\tKEGG_Pathway\tInterPro_Description" in prompt_text
    assert "GeneA\tGeneA.t1\t1.8\t0.003\t0.02\tGeneA\tGeneA.t1\tflavonoid biosynthesis\tchalcone isomerase domain" in prompt_text
    assert "literature_query_plan_role=待检索计划，不等同于 PubMed 文献证据" in prompt_text
    debug_annotation = result["frontend_payload"]["debug_panel"]["evidence_context"][
        "annotation"
    ][0]
    assert debug_annotation["citation_id"] == "A1"
    assert debug_annotation["annotation_gene_match_count"] == 1
    assert debug_annotation["candidate_annotations"][0]["gene_id"] == "GeneA"


def test_prepare_cited_guarded_omics_analysis_from_context_uses_query_plan_for_background_pubmed(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )

    def fake_background_search(**kwargs):
        query_plan = kwargs.get("query_plan") or []
        assert query_plan
        assert query_plan[0]["query_type"] == "species_pfam_trait"
        return {
            "status": "completed",
            "backend": "mock_pubmed",
            "literature_source": "pubmed_search_with_query_plan",
            "used_query_plan": True,
            "query_plan_count": len(query_plan),
            "executed_query_count": 1,
            "query_limit": 8,
            "per_query_result_limit": 2,
            "retained_record_limit": 5,
            "queries": [query_plan[0]["query"]],
            "records": [
                {
                    "title": "Foxtail millet chalcone isomerase background",
                    "pmid": "123456",
                    "abstract_sentence": "Background evidence supports chalcone isomerase related flavonoid accumulation.",
                    "source": "PubMed",
                    "query_id": query_plan[0]["query_id"],
                    "query_type": query_plan[0]["query_type"],
                    "query_priority": query_plan[0]["priority"],
                    "query": query_plan[0]["query"],
                    "gene_id": query_plan[0]["gene_id"],
                    "pfam_keyword": query_plan[0]["pfam_keyword"],
                    "evidence_role": "background_literature",
                    "relevance_level": "background",
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.workflow.search_background_literature",
        fake_background_search,
    )
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "Si9g037800\t1.8\t0.003\t0.02\n",
        encoding="utf-8",
    )
    annotation_path = tmp_path / "annotation.tsv"
    annotation_path.write_text(
        "gene_id\tpfam\tKEGG_Pathway\n"
        "Si9g037800\tChalcone-flavanone isomerase\tFlavonoid biosynthesis\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation_path),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=False,
        output_dir=tmp_path,
    )

    assert result["summary"]["background_literature_count"] == 1
    assert result["summary"]["background_literature_status"] == "completed"
    assert result["summary"]["literature_query_plan_used_for_background_search"] is True
    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "[BG1]" in body
    assert "[BG1] PubMed 背景文献" in source_index
    assert "query_id：" in source_index
    assert "query_type：" in source_index


def test_prepare_cited_guarded_omics_analysis_from_context_without_deg_does_not_emit_t1_or_smoke_gene(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.workflow.search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "queries": [],
            "records": [],
            "warnings": [],
        },
    )

    evidence_pack_path = tmp_path / "omics_evidence_pack.json"
    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="根据当前输入给出建议",
        transcriptome_result_path=str(tmp_path / "missing_significant_de_genes.tsv"),
        evidence_pack_output_path=str(evidence_pack_path),
    )

    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=False,
        output_dir=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["summary"]["target_genes"] == []
    assert result["summary"]["candidate_genes"] == []
    assert result["summary"]["candidate_gene_source"] == "none"
    assert result["summary"]["candidate_gene_fallback_used"] is False
    assert "Si9g037800" not in result["answer_markdown"]
    assert "[T1]" not in result["answer_markdown"]
    assert "[T1] 转录组 DEG" not in result["answer_markdown"]
    assert all("T1" not in item["citation_ids"] for item in result["claim_trace"])
