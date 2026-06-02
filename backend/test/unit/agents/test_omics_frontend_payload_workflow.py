from __future__ import annotations

import json

import pytest

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
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
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

    assert payload["citation_panel"]["citation_count"] == 3
    assert any(
        item["citation_id"] == "Guard"
        for item in payload["citation_panel"]["citations"]
    )
    assert payload["literature_panel"]["card_count"] == 1
    assert payload["guard_panel"]["passed"] is True
    assert payload["claim_trace_panel"]["row_count"] >= 1
    assert payload["artifact_panel"]["artifact_count"] >= 5

    frontend_payload_path = tmp_path / "frontend_payload.json"
    final_result_path = tmp_path / "final_result.json"

    assert frontend_payload_path.exists()
    assert final_result_path.exists()

    loaded_payload = json.loads(frontend_payload_path.read_text(encoding="utf-8"))
    assert loaded_payload["schema_version"] == "omics_frontend_payload.v1"
    assert loaded_payload["literature_panel"]["cards"][0]["doi"] == "10.1234/real"

    loaded_final = json.loads(final_result_path.read_text(encoding="utf-8"))
    assert loaded_final["frontend_payload"]["schema_version"] == "omics_frontend_payload.v1"
    assert loaded_final["frontend_payload_path"] == str(frontend_payload_path)
