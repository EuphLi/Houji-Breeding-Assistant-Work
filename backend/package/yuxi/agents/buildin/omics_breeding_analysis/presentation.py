from __future__ import annotations

from pathlib import Path
from typing import Any

"""
最终报告渲染层 / Markdown 组装层 / 来源索引生成层
负责“把这些关系写成用户看到的 Markdown”

在数据流中的位置
Evidence Pack + citations + claim_trace
  ↓
presentation.py
  ↓
answer_markdown / source index / literature cards / trace table

"""



def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]

# 用文件后缀判断 artifact 类型，后续前端可以据此决定是按 JSON、Markdown、表格还是普通文件展示
def _artifact_type(path: str) -> str:
    suffix = Path(path).suffix.lower()

    if suffix == ".json":
        return "json"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    if suffix in {".tsv", ".csv"}:
        return "table"

    return "file"


def _build_debug_evidence_context(citations: list[Any]) -> dict[str, Any]:
    """Build a compact evidence context mirror for debugging LLM inputs.

    This intentionally keeps only candidate-level summaries. It must not expose
    the full uploaded annotation table.
    """

    annotation_items: list[dict[str, Any]] = []
    literature_items: list[dict[str, Any]] = []
    for item in citations:
        if not isinstance(item, dict):
            continue
        if item.get("source_type") in {"literature", "background_literature"}:
            metadata = item.get("metadata") or {}
            literature_items.append(
                {
                    "citation_id": item.get("citation_id", ""),
                    "source_type": item.get("source_type", ""),
                    "title": metadata.get("title", ""),
                    "doi": metadata.get("doi", ""),
                    "pmid": metadata.get("pmid", ""),
                    "quoted_sentence": metadata.get("quoted_sentence", ""),
                    "abstract_sentence": metadata.get("abstract_sentence", ""),
                    "query_id": metadata.get("query_id", ""),
                    "query_type": metadata.get("query_type", ""),
                    "query_priority": metadata.get("query_priority", ""),
                    "query": metadata.get("query", ""),
                    "evidence_role": metadata.get("evidence_role", ""),
                    "evidence_boundary": metadata.get("evidence_boundary", ""),
                }
            )
            continue
        if item.get("source_type") != "annotation":
            continue
        metadata = item.get("metadata") or {}
        annotation_items.append(
            {
                "citation_id": item.get("citation_id", ""),
                "annotation_file": metadata.get("annotation_file", ""),
                "annotation_file_name": metadata.get("annotation_file_name", ""),
                "annotation_path_exists": bool(metadata.get("annotation_path_exists")),
                "annotation_gene_match_count": int(
                    metadata.get("annotation_gene_match_count") or 0
                ),
                "annotation_unmatched_gene_count": int(
                    metadata.get("annotation_unmatched_gene_count") or 0
                ),
                "annotation_candidate_gene_ids": metadata.get(
                    "annotation_candidate_gene_ids"
                )
                or [],
                "candidate_annotations": metadata.get("candidate_annotations") or [],
                "pathway_summary": metadata.get("pathway_summary") or [],
                "evidence_role": metadata.get("evidence_role", "")
                or "功能注释线索，不等同于功能验证",
            }
        )

    return {
        "annotation": annotation_items,
        "literature": literature_items,
    }


# 展示适配层。它不生成新结论，只整理已有 final_result
# 这样后续 Vue 页面只需要读这些 panel，不需要自己理解后端内部结构
def build_frontend_payload(final_result: dict[str, Any]) -> dict[str, Any]:
    """将 final_result 转换为前端方案 5 需要的展示结构。

    这个函数不做业务推理，不修改 Guard 结果，不重新生成 citation。
    它只做展示层字段整理，方便后续 Vue 页面或 API 直接消费。
    """

    guard_result = final_result.get("guard_result") or {}
    citations = _as_list(final_result.get("citations"))
    literature_cards = _as_list(final_result.get("literature_cards"))
    claim_trace = _as_list(final_result.get("claim_trace"))
    artifacts = _as_list(final_result.get("artifacts"))
    summary = final_result.get("summary") or {}
    evidence_pack_path = str(
        final_result.get("evidence_pack_path")
        or summary.get("evidence_pack_path")
        or summary.get("omics_evidence_pack_path")
        or ""
    ).strip()

    # citation_index 的作用是把 [T1] / [L1] 这种 citation id 映射回完整来源信息。
    # 这样 claim_trace_rows 里每一条 claim 都可以带上对应 source
    citation_index = {
        item.get("citation_id"): {
            "citation_id": item.get("citation_id", ""),
            "source_type": item.get("source_type", ""),
            "text": item.get("text", ""),
            "metadata": item.get("metadata") or {},
        }
        for item in citations
        if isinstance(item, dict) and item.get("citation_id")
    }

    claim_trace_rows = []
    for item in claim_trace:
        if not isinstance(item, dict):
            continue

        citation_ids = _as_list(item.get("citation_ids"))
        source_status = item.get("source_status", "needs_citation")
        claim_trace_rows.append(
            {
                "claim_id": item.get("claim_id", ""),
                "text": item.get("text", ""),
                "citation_ids": citation_ids,
                "source_status": source_status,
                "explanation": item.get("explanation", ""),
                "sources": [
                    citation_index[citation_id]
                    for citation_id in citation_ids
                    if citation_id in citation_index
                ],
            }
        )

    artifact_links = []
    for path in artifacts:
        path_text = str(path)
        artifact_links.append(
            {
                "name": Path(path_text).name,
                "path": path_text,
                "type": _artifact_type(path_text),
            }
        )

    return {
        "schema_version": "omics_frontend_payload.v1",
        "status": final_result.get("status", ""),
        "backend": final_result.get("backend", ""),
        "raw_answer_backend": final_result.get("raw_answer_backend", ""),
        "llamaindex_available": bool(final_result.get("llamaindex_available")),
        "answer_markdown": final_result.get("answer_markdown", ""),
        "raw_llm_answer": final_result.get("raw_llm_answer", ""),
        "summary": summary,
        "warnings": _as_list(final_result.get("warnings")),
        "literature_cards": literature_cards,
        "citation_panel": {
            "citations": list(citation_index.values()),
            "citation_count": len(citation_index),
        },
        "literature_panel": {
            "cards": literature_cards,
            "card_count": len(literature_cards),
        },
        "claim_trace_panel": {
            "rows": claim_trace_rows,
            "row_count": len(claim_trace_rows),
            "supported_count": sum(
                1 for row in claim_trace_rows if row["source_status"] == "supported"
            ),
            "background_count": sum(
                1 for row in claim_trace_rows if row["source_status"] == "background"
            ),
            "guard_count": sum(
                1 for row in claim_trace_rows if row["source_status"] == "guard"
            ),
            "needs_citation_count": sum(
                1 for row in claim_trace_rows if row["source_status"] == "needs_citation"
            ),
        },
        "guard_panel": {
            "passed": bool(guard_result.get("passed")),
            "errors": _as_list(guard_result.get("errors")),
            "warnings": _as_list(guard_result.get("warnings")),
            "unsupported_dois": _as_list(guard_result.get("unsupported_dois")),
            "unsupported_quoted_sentences": _as_list(
                guard_result.get("unsupported_quoted_sentences")
            ),
        },
        "artifact_panel": {
            "artifacts": artifact_links,
            "artifact_count": len(artifact_links),
        },
        "debug_panel": {
            "raw_llm_answer": final_result.get("raw_llm_answer", ""),
            "analysis_prompt": final_result.get("analysis_prompt") or {},
            "evidence_pack_path": evidence_pack_path,
            "omics_evidence_pack_path": evidence_pack_path,
            "evidence_pack_path_exists": bool(evidence_pack_path) and Path(evidence_pack_path).is_file(),
            "query_plan_count": int(summary.get("background_query_plan_count") or 0),
            "executed_query_count": int(summary.get("background_executed_query_count") or 0),
            "unexecuted_query_count": int(summary.get("background_unexecuted_query_count") or 0),
            "fallback_executed": bool(summary.get("background_fallback_executed")),
            "priority_budgets": summary.get("background_priority_budgets") or {},
            "background_literature_record_count": int(
                summary.get("background_literature_record_count") or 0
            ),
            "stop_reason": summary.get("background_stop_reason", ""),
            "evidence_context": _build_debug_evidence_context(citations),
        },
    }
