from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.presentation import (
    build_frontend_payload,
)


# 测试模拟一个通过 Guard 的 final_result，确认它能被整理成前端方案 5 的展示结构：
# citation_panel
# literature_panel
# claim_trace_panel
# guard_panel
# artifact_panel
def test_build_frontend_payload_groups_final_result_for_display():
    final_result = {
        "status": "completed",
        "backend": "canonical_renderer",
        "raw_answer_backend": "llm",
        "llamaindex_available": False,
        "answer_markdown": "GeneA 是候选基因。[T1]",
        "raw_llm_answer": "raw llm body",
        "summary": {
            "target_genes": ["GeneA"],
            "trait_terms": ["抗旱"],
        },
        "warnings": [],
        "citations": [
            {
                "citation_id": "T1",
                "source_type": "transcriptome",
                "text": "GeneA transcriptome evidence.",
                "metadata": {"gene_id": "GeneA"},
            },
            {
                "citation_id": "L1",
                "source_type": "literature",
                "text": "Literature evidence.",
                "metadata": {"doi": "10.1234/real"},
            },
            {
                "citation_id": "BG1",
                "source_type": "background_literature",
                "text": "Background evidence.",
                "metadata": {
                    "title": "Background flavonoid paper",
                    "pmid": "123456",
                    "doi": "10.5678/bg",
                    "abstract_sentence": "Background evidence supports flavonoid accumulation differences.",
                    "query_id": "PFAM_HIGH_001",
                    "query_type": "species_pfam_trait",
                    "query_priority": "high",
                    "query": 'Setaria italica "chalcone isomerase" flavonoid',
                    "evidence_role": "background_literature",
                    "evidence_boundary": "背景文献，不是当前实验直接验证",
                },
            },
        ],
        "literature_cards": [
            {
                "citation_id": "L1",
                "doi": "10.1234/real",
                "quoted_sentence": "Verified sentence.",
                "title": "Verified Paper",
            },
            {
                "citation_id": "BG1",
                "pmid": "123456",
                "doi": "10.5678/bg",
                "title": "Background flavonoid paper",
                "abstract_sentence": "Background evidence supports flavonoid accumulation differences.",
                "query_id": "PFAM_HIGH_001",
                "query_type": "species_pfam_trait",
                "query_priority": "high",
                "query": 'Setaria italica "chalcone isomerase" flavonoid',
                "evidence_role": "background_literature",
                "evidence_boundary": "背景文献，不是当前实验直接验证",
            },
        ],
        "claim_trace": [
            {
                "claim_id": "C1",
                "text": "GeneA 是候选基因 [T1]",
                "citation_ids": ["T1", "BG1"],
                "source_status": "supported",
            },
            {
                "claim_id": "C2",
                "text": "这是一条无 citation 的说明",
                "citation_ids": [],
                "source_status": "needs_citation",
                "explanation": "关键结论句缺少 citation id。",
            },
        ],
        "guard_result": {
            "passed": True,
            "errors": [],
            "warnings": [],
            "unsupported_dois": [],
            "unsupported_quoted_sentences": [],
        },
        "artifacts": [
            "/tmp/omics_evidence_pack.json",
            "/tmp/answer_markdown.md",
            "/tmp/final_result.json",
        ],
    }

    payload = build_frontend_payload(final_result)

    assert payload["schema_version"] == "omics_frontend_payload.v1"
    assert payload["status"] == "completed"
    assert payload["answer_markdown"] == "GeneA 是候选基因。[T1]"
    assert payload["raw_llm_answer"] == "raw llm body"

    assert payload["citation_panel"]["citation_count"] == 3
    assert payload["literature_panel"]["card_count"] == 2

    assert payload["claim_trace_panel"]["row_count"] == 2
    assert payload["claim_trace_panel"]["supported_count"] == 1
    assert payload["claim_trace_panel"]["needs_citation_count"] == 1
    assert payload["claim_trace_panel"]["rows"][0]["sources"][0]["citation_id"] == "T1"
    assert payload["claim_trace_panel"]["rows"][0]["sources"][1]["citation_id"] == "BG1"
    assert (
        payload["claim_trace_panel"]["rows"][0]["sources"][1]["metadata"]["query_id"]
        == "PFAM_HIGH_001"
    )
    assert payload["claim_trace_panel"]["rows"][1]["explanation"] == "关键结论句缺少 citation id。"
    assert payload["literature_panel"]["cards"][1]["query_priority"] == "high"
    assert payload["literature_panel"]["cards"][1]["evidence_boundary"] == "背景文献，不是当前实验直接验证"
    assert payload["citation_panel"]["citations"][2]["metadata"]["query_type"] == "species_pfam_trait"

    assert payload["guard_panel"]["passed"] is True

    assert payload["artifact_panel"]["artifact_count"] == 3
    assert payload["artifact_panel"]["artifacts"][0]["type"] == "json"
    assert payload["artifact_panel"]["artifacts"][1]["type"] == "markdown"
    assert payload["debug_panel"]["raw_llm_answer"] == "raw llm body"


# 测试模拟一个 Guard 失败的 final_result，确认错误信息、伪造 DOI、伪造引用原句不会丢失
def test_build_frontend_payload_preserves_guard_errors():
    final_result = {
        "status": "failed_guard",
        "answer_markdown": "GeneA 是候选基因。",
        "guard_result": {
            "passed": False,
            "errors": ["Answer must include a population-level follow-up validation plan."],
            "warnings": [],
            "unsupported_dois": ["10.9999/fake"],
            "unsupported_quoted_sentences": ["Fake quote."],
        },
        "citations": [],
        "literature_cards": [],
        "claim_trace": [],
        "artifacts": [],
    }

    payload = build_frontend_payload(final_result)

    assert payload["status"] == "failed_guard"
    assert payload["guard_panel"]["passed"] is False
    assert payload["guard_panel"]["errors"] == [
        "Answer must include a population-level follow-up validation plan."
    ]
    assert payload["guard_panel"]["unsupported_dois"] == ["10.9999/fake"]
    assert payload["guard_panel"]["unsupported_quoted_sentences"] == ["Fake quote."]
