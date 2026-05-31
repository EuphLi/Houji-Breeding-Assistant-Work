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
2. fallback citation 可用
3. answer_markdown 包含 GeneA / 抗旱，但不展开 DOI / quoted_sentence 技术明细
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
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "GeneA\t1.8\t0.003\t0.02\n",
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
    assert result["backend"] == "rule_fallback"
    assert result["guard_result"]["passed"] is True

    assert "GeneA" in result["answer_markdown"]
    assert "抗旱" in result["answer_markdown"]
    assert "10.1234/real" not in result["answer_markdown"]
    assert "Verified sentence." not in result["answer_markdown"]

    assert result["citations"][0]["citation_id"] == "T1"
    assert result["citations"][1]["citation_id"] == "L1"
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
    assert loaded["summary"]["analysis_backend"] == "rule_fallback"
