from __future__ import annotations

import json

import pytest

from yuxi.agents.buildin.omics_breeding_analysis import citation_engine as omics_citation_engine
from yuxi.agents.buildin.omics_breeding_analysis import workflow as omics_workflow
from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.workflow import (
    prepare_cited_guarded_omics_analysis_from_context,
)


# 这个测试覆盖：
# Context
# → Evidence Pack
# → Citation Result
# → Guard
# → frontend_payload
# → frontend_payload.json
# → final_result.json
# 它确认后端最终结果里不仅有 final_result，还包含前端可直接消费的 frontend_payload。
def test_final_workflow_writes_frontend_payload(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "queries": [],
            "records": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        omics_citation_engine,
        "load_chat_model",
        lambda fully_specified_name: type(
            "FakeModel",
            (),
            {
                "invoke": lambda self, messages: type(
                    "Response",
                    (),
                    {
                        "content": "# 多组学育种分析结果\n\n当前分析围绕抗旱相关性状展开，GeneA 可作为后续重点关注基因。\n\n建议后续开展群体验证，并在自然群体或分离群体中结合 GeneA 基因型与抗旱表型开展关联验证。"
                    },
                )()
            },
        )(),
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

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        literature_evidence_path=str(literature_path),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=False,
        output_dir=tmp_path,
    )

    assert result["status"] == "completed"
    assert result["guard_result"]["passed"] is True

    payload = result["frontend_payload"]

    assert payload["schema_version"] == "omics_frontend_payload.v1"
    assert payload["status"] == "completed"
    assert payload["answer_markdown"]
    assert payload["summary"]["analysis_backend"] == "llm"
    assert payload["summary"]["render_backend"] == "canonical_renderer"
    assert payload["summary"]["evidence_pack_path"] == str(tmp_path / "omics_evidence_pack.json")
    assert payload["summary"]["evidence_pack_path_exists"] is True

    assert payload["citation_panel"]["citation_count"] == 3
    assert any(
        item["citation_id"] == "Guard"
        for item in payload["citation_panel"]["citations"]
    )
    assert payload["literature_panel"]["card_count"] == 1
    assert payload["guard_panel"]["passed"] is True
    assert payload["claim_trace_panel"]["row_count"] >= 1
    assert payload["artifact_panel"]["artifact_count"] >= 5
    assert payload["debug_panel"]["evidence_pack_path"] == str(tmp_path / "omics_evidence_pack.json")
    assert payload["debug_panel"]["omics_evidence_pack_path"] == str(
        tmp_path / "omics_evidence_pack.json"
    )
    assert payload["debug_panel"]["evidence_pack_path_exists"] is True
    assert payload["debug_panel"]["query_plan_count"] == 0
    assert payload["debug_panel"]["executed_query_count"] == 0
    assert payload["debug_panel"]["unexecuted_query_count"] == 0
    assert payload["debug_panel"]["fallback_executed"] is False
    assert payload["debug_panel"]["priority_budgets"] == {}
    assert payload["debug_panel"]["background_literature_record_count"] == 0
    assert payload["debug_panel"]["stop_reason"] == ""

    frontend_payload_path = tmp_path / "frontend_payload.json"
    final_result_path = tmp_path / "final_result.json"

    assert frontend_payload_path.exists()
    assert final_result_path.exists()

    loaded_payload = json.loads(frontend_payload_path.read_text(encoding="utf-8"))
    assert loaded_payload["schema_version"] == "omics_frontend_payload.v1"
    assert loaded_payload["literature_panel"]["cards"][0]["doi"] == "10.1234/real"
    assert loaded_payload["debug_panel"]["evidence_pack_path"] == str(
        tmp_path / "omics_evidence_pack.json"
    )

    loaded_final = json.loads(final_result_path.read_text(encoding="utf-8"))
    assert loaded_final["frontend_payload"]["schema_version"] == "omics_frontend_payload.v1"
    assert loaded_final["frontend_payload_path"] == str(frontend_payload_path)


def test_frontend_payload_keeps_background_query_provenance(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "completed",
            "backend": "mock_pubmed",
            "literature_source": "pubmed_search_with_query_plan",
            "used_query_plan": True,
            "query_plan_count": 1,
            "executed_query_count": 1,
            "unexecuted_query_count": 0,
            "query_limit": 9,
            "desired_record_count": 5,
            "per_query_result_limit": 2,
            "retained_record_limit": 5,
            "priority_budgets": {"high": 4, "medium": 2, "low": 1, "fallback": 2},
            "priority_execution_counts": {"high": 1, "medium": 0, "low": 0, "fallback": 0},
            "priority_plan_counts": {"high": 1, "medium": 0, "low": 0, "fallback": 0},
            "executed_query_details": [
                {
                    "query_id": "PFAM_HIGH_001",
                    "query_type": "species_pfam_trait",
                    "priority": "high",
                    "query": 'Setaria italica "chalcone isomerase" flavonoid',
                    "status": "completed",
                    "raw_result_count": 1,
                    "retained_new_record_count": 1,
                }
            ],
            "skipped_query_count": 0,
            "fallback_executed": False,
            "stop_reason": "all_queries_exhausted",
            "queries": ['Setaria italica "chalcone isomerase" flavonoid'],
            "records": [
                {
                    "citation_id": "BG1",
                    "title": "Background flavonoid paper",
                    "pmid": "123456",
                    "doi": "10.5678/bg",
                    "abstract_sentence": "Background evidence supports flavonoid accumulation differences.",
                    "source": "PubMed",
                    "query_id": "PFAM_HIGH_001",
                    "query_type": "species_pfam_trait",
                    "query_priority": "high",
                    "query": 'Setaria italica "chalcone isomerase" flavonoid',
                    "evidence_role": "background_literature",
                    "relevance_level": "background",
                }
            ],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        omics_citation_engine,
        "load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )

    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\tannotation\n"
        "GeneA\t1.8\t0.003\t0.02\tchalcone isomerase\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    result = prepare_cited_guarded_omics_analysis_from_context(
        context=context,
        use_llamaindex=False,
        output_dir=tmp_path,
    )

    payload = result["frontend_payload"]
    assert payload["literature_panel"]["cards"][0]["query_id"] == "PFAM_HIGH_001"
    assert payload["literature_panel"]["cards"][0]["query_type"] == "species_pfam_trait"
    assert payload["literature_panel"]["cards"][0]["query_priority"] == "high"
    assert payload["literature_panel"]["cards"][0]["query"] == 'Setaria italica "chalcone isomerase" flavonoid'
    bg_row = next(row for row in payload["claim_trace_panel"]["rows"] if "BG1" in row["citation_ids"])
    bg_source = next(source for source in bg_row["sources"] if source["citation_id"] == "BG1")
    assert bg_source["metadata"]["query_id"] == "PFAM_HIGH_001"
    assert bg_source["metadata"]["query_type"] == "species_pfam_trait"
    assert bg_source["metadata"]["query_priority"] == "high"
    assert bg_source["metadata"]["evidence_boundary"] == "背景文献，不是当前实验直接验证"
    assert payload["debug_panel"]["query_plan_count"] == 1
    assert payload["debug_panel"]["executed_query_count"] == 1
    assert payload["debug_panel"]["unexecuted_query_count"] == 0
    assert payload["debug_panel"]["fallback_executed"] is False
    assert payload["debug_panel"]["priority_budgets"] == {
        "high": 4,
        "medium": 2,
        "low": 1,
        "fallback": 2,
    }
    assert payload["debug_panel"]["stop_reason"] == "all_queries_exhausted"
