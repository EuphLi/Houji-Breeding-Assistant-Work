from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import OmicsBreedingAnalysisContext
from .evidence_adapters import build_omics_evidence_pack_from_context
from .evidence_pack import write_evidence_pack
from .tool_result_adapters import build_omics_evidence_pack_from_tool_results

import json
from .output_guard import run_dynamic_output_guard

from .citation_engine import build_citation_result
from .presentation import build_frontend_payload
from .literature_search import search_background_literature

'''
业务工作流编排层 / Evidence Pack 构建调度层 / LLM 与 renderer 上游
'''

"""
实现一条稳定的后端证据准备链路：
Context / 旧 Tool 结果
↓
Evidence Adapter / Tool Result Adapter
↓
Evidence Pack
↓
omics_evidence_pack.json
↓
summary / artifacts
"""

'''
workflow.py 的 Evidence Pack 准备层:
1. 调用 evidence_adapters 构建基础 Evidence Pack。
2. 调用 PubMed 背景文献检索。
3. 把 PubMed records 合并进 Evidence Pack。
4. 写出 omics_evidence_pack.json。
5. 生成 summary。
6. 生成 warnings。
'''
# 把完整 Evidence Pack 压缩成一个摘要
def summarize_evidence_pack(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    """生成 Evidence Pack 的轻量摘要，方便后续 graph、前端和测试使用。"""

    # 先拆 Evidence Pack 的几个核心区
    targets = evidence_pack.get("targets") or {}
    evidence = evidence_pack.get("evidence") or {}
    # Guard 需要遵守的边界，例如允许 DOI、是否需要群体验证建议。
    guard_requirements = evidence_pack.get("guard_requirements") or {}

    # 后拆证据文件数量统计的来源
    transcriptome_records = evidence.get("transcriptome") or []
    literature_records = evidence.get("literature") or []
    metabolome_context = evidence.get("metabolome_context") or []
    genome_context = evidence.get("genome_context") or []
    annotation_evidence = evidence.get("annotation") or []
    annotation_debug = ((evidence_pack.get("debug") or {}).get("annotation") or {})
    literature_debug = ((evidence_pack.get("debug") or {}).get("literature") or {})
    # 路径诊断的来源
    input_debug = ((evidence_pack.get("debug") or {}).get("inputs") or {})
    smoke_debug = ((evidence_pack.get("debug") or {}).get("smoke_context") or {})
    # PubMed 背景文献摘要来自这里，由这一层统计，再被下游 citation_engine.py 用进正文。
    background_literature_records = evidence_pack.get("background_literature_records") or []
    background_literature_search = evidence_pack.get("background_literature_search") or {}
    evidence_pack_path = str((evidence_pack.get("artifacts") or {}).get("evidence_pack_path") or "").strip()
    candidate_genes = [str(item).strip() for item in (targets.get("genes") or []) if str(item).strip()]
    evidence_level = input_debug.get("evidence_level", "")
    candidate_gene_fallback_used = bool(
        evidence_level == "default_smoke_data"
        and not candidate_genes
        and smoke_debug.get("primary_gene_id")
    )
    if candidate_genes and transcriptome_records:
        candidate_gene_source = (
            "default_smoke_data" if evidence_level == "default_smoke_data" else "current_run_deg"
        )
        candidate_gene_source_path = input_debug.get("transcriptome_result_path", "")
    elif candidate_gene_fallback_used:
        candidate_gene_source = "default_smoke_data"
        candidate_gene_source_path = smoke_debug.get("gene_ids_path", "")
    else:
        candidate_gene_source = "none"
        candidate_gene_source_path = ""

    return {
        "trait": (evidence_pack.get("task") or {}).get("trait") or input_debug.get("trait", ""),
        "question": (evidence_pack.get("task") or {}).get("question")
        or input_debug.get("question", ""),
        "data_source": input_debug.get("data_source", "") or input_debug.get("evidence_level", ""),
        "target_genes": targets.get("genes") or [],
        "candidate_genes": candidate_genes,
        "candidate_gene_source": candidate_gene_source,
        "candidate_gene_source_path": candidate_gene_source_path,
        "candidate_gene_fallback_used": candidate_gene_fallback_used,
        "trait_terms": targets.get("trait_terms") or [],
        "transcriptome_record_count": len(transcriptome_records),
        "literature_record_count": len(literature_records),
        "metabolome_context_count": len(metabolome_context),
        "genome_context_count": len(genome_context),
        "annotation_evidence_count": len(annotation_evidence),
        "data_dir": input_debug.get("data_dir", ""),
        "must_include_population_validation": bool(
            guard_requirements.get("must_include_population_validation")
        ),
        "allowed_doi_count": len(guard_requirements.get("allowed_dois") or []),
        "allowed_quoted_sentence_count": len(
            guard_requirements.get("allowed_quoted_sentences") or []
        ),
        "literature_evidence_path": literature_debug.get("literature_evidence_path", ""),
        "literature_path_exists": bool(literature_debug.get("literature_path_exists")),
        "literature_row_count": int(literature_debug.get("literature_row_count") or 0),
        "verified_row_count": int(literature_debug.get("verified_row_count") or 0),
        "usable_literature_count": int(
            literature_debug.get("usable_literature_count") or 0
        ),
        "filtered_reason_counts": literature_debug.get("filtered_reason_counts") or {},
        "transcriptome_result_path": input_debug.get("transcriptome_result_path", ""),
        "transcriptome_path_exists": bool(input_debug.get("transcriptome_path_exists")),
        "transcriptome_path_source": input_debug.get("transcriptome_path_source", ""),
        "transcriptome_input_status": input_debug.get("transcriptome_input_status", ""),
        "transcriptome_supporting_input_exists": bool(
            input_debug.get("transcriptome_supporting_input_exists")
        ),
        "transcriptome_supporting_input_count": int(
            input_debug.get("transcriptome_supporting_input_count") or 0
        ),
        "rnaseq_read_count": int(input_debug.get("rnaseq_read_count") or 0),
        "metabolome_path": input_debug.get("metabolome_path", ""),
        "metabolome_path_exists": bool(input_debug.get("metabolome_path_exists")),
        "metabolome_path_source": input_debug.get("metabolome_path_source", ""),
        "sample_map_path": input_debug.get("sample_map_path", ""),
        "sample_map_path_exists": bool(input_debug.get("sample_map_path_exists")),
        "reference_genome_path": input_debug.get("reference_genome_path", ""),
        "reference_genome_path_exists": bool(input_debug.get("reference_genome_path_exists")),
        "genome_gff_path": input_debug.get("genome_gff_path", ""),
        "genome_gff_path_exists": bool(input_debug.get("genome_gff_path_exists")),
        "annotation_path": input_debug.get("annotation_path", ""),
        "annotation_path_exists": bool(input_debug.get("annotation_path_exists")),
        "annotated_transcriptome_path": annotation_debug.get("annotated_transcriptome_path", "")
        or input_debug.get("annotated_transcriptome_path", ""),
        "annotation_merge_status": annotation_debug.get("annotation_merge_status", ""),
        "annotation_merge_warning": annotation_debug.get("annotation_merge_warning", ""),
        "annotation_merge_method": annotation_debug.get("annotation_merge_method", ""),
        "annotation_merge_total_count": int(
            annotation_debug.get("annotation_merge_total_count") or 0
        ),
        "annotation_merge_matched_count": int(
            annotation_debug.get("annotation_merge_matched_count") or 0
        ),
        "annotation_merge_unmatched_count": int(
            annotation_debug.get("annotation_merge_unmatched_count") or 0
        ),
        "annotation_merge_duplicate_count": int(
            annotation_debug.get("annotation_merge_duplicate_count") or 0
        ),
        "annotated_transcriptome_read_by_llm": bool(
            annotation_debug.get("annotated_transcriptome_read_by_llm")
        ),
        "annotation_gene_match_count": int(annotation_debug.get("annotation_gene_match_count") or 0),
        "annotation_unmatched_gene_count": int(
            annotation_debug.get("annotation_unmatched_gene_count") or 0
        ),
        "annotation_duplicate_gene_id_count": int(
            annotation_debug.get("annotation_duplicate_gene_id_count") or 0
        ),
        "annotation_isoform_count": int(annotation_debug.get("annotation_isoform_count") or 0),
        "annotation_candidate_gene_ids": annotation_debug.get("annotation_candidate_gene_ids") or [],
        "trait_relevant_annotation_gene_ids": annotation_debug.get("trait_relevant_annotation_gene_ids")
        or [],
        "pathway_summary": annotation_debug.get("pathway_summary") or [],
        "pathway_ids": annotation_debug.get("pathway_ids") or [],
        "ko_terms": annotation_debug.get("ko_terms") or [],
        "go_ids": annotation_debug.get("go_ids") or [],
        "pfam_ids": annotation_debug.get("pfam_ids") or [],
        "pubmed_query_terms": annotation_debug.get("pubmed_query_terms") or [],
        "pfam_literature_keywords": annotation_debug.get("pfam_literature_keywords") or [],
        "literature_query_plan_path": annotation_debug.get("literature_query_plan_path", ""),
        "literature_query_plan_count": int(
            annotation_debug.get("literature_query_plan_count") or 0
        ),
        "literature_query_plan_source": annotation_debug.get(
            "literature_query_plan_source", ""
        ),
        "literature_query_plan_used_for_background_search": bool(
            background_literature_search.get("used_query_plan")
        ),
        "background_query_plan_count": int(
            background_literature_search.get("query_plan_count") or 0
        ),
        "background_executed_query_count": int(
            background_literature_search.get("executed_query_count") or 0
        ),
        "background_unexecuted_query_count": int(
            background_literature_search.get("unexecuted_query_count") or 0
        ),
        "background_query_limit": int(background_literature_search.get("query_limit") or 0),
        "background_desired_record_count": int(
            background_literature_search.get("desired_record_count") or 0
        ),
        "background_per_query_result_limit": int(
            background_literature_search.get("per_query_result_limit") or 0
        ),
        "background_retained_record_limit": int(
            background_literature_search.get("retained_record_limit") or 0
        ),
        "background_fallback_executed": bool(
            background_literature_search.get("fallback_executed")
        ),
        "background_stop_reason": background_literature_search.get("stop_reason", ""),
        "background_priority_budgets": background_literature_search.get("priority_budgets") or {},
        "background_priority_execution_counts": background_literature_search.get(
            "priority_execution_counts"
        )
        or {},
        "metabolome_preview_available": bool(input_debug.get("metabolome_preview_available")),
        "metabolome_preview_row_count": int(
            input_debug.get("metabolome_preview_row_count") or 0
        ),
        "metabolome_preview_truncated": bool(input_debug.get("metabolome_preview_truncated")),
        "evidence_level": evidence_level,
        "smoke_context_primary_gene": smoke_debug.get("primary_gene_id", ""),
        "smoke_context_gene_count": int(smoke_debug.get("gene_count") or 0),
        "smoke_context_gene_ids_preview": smoke_debug.get("gene_ids_preview") or [],
        "background_literature_count": len(background_literature_records),
        "background_literature_record_count": len(background_literature_records),
        "background_literature_backend": background_literature_search.get("backend", ""),
        "background_literature_status": background_literature_search.get("status", ""),
        "background_literature_search_status": background_literature_search.get("status", ""),
        "background_literature_source": background_literature_search.get(
            "literature_source", ""
        ),
        "evidence_pack_path": evidence_pack_path,
        "omics_evidence_pack_path": evidence_pack_path,
        "evidence_pack_path_exists": bool(evidence_pack_path) and Path(evidence_pack_path).is_file(),
    }


# 证据完整性提示，仅检查 Evidence Pack 是否完整
def _build_warnings(evidence_pack: dict[str, Any]) -> list[str]:
    """根据 Evidence Pack 内容生成轻量 warning。

    这些 warning 不是 Guard 最终判定，只是提示当前证据是否完整。
    """

    summary = summarize_evidence_pack(evidence_pack)
    warnings: list[str] = []

    # 如果 Evidence Pack 里没有提取到 target genes，说明转录组证据没有提供可用候选基因。
    if not summary["target_genes"]:
        warnings.append("No target genes were extracted from transcriptome evidence.")

    # 转录组文件不可用时 warning
    if (
        summary.get("evidence_level") == "input_missing_or_filename_only"
        or (
            summary.get("transcriptome_result_path")
            and not summary.get("transcriptome_path_exists")
        )
    ):
        warnings.append("当前未读取到可用的转录组差异基因结果。")

    # 没有本地已验证文献时 warning，这里判断的是：literature_record_count，不等于 PubMed 背景文献数
    if summary["literature_record_count"] == 0 and summary["background_literature_count"] == 0:
        warnings.append(
            "当前输入中未提供可用的已验证文献证据记录，因此本次建议不包含 DOI 引用。"
        )

    if summary.get("annotation_path_exists") and summary.get("annotation_gene_match_count") == 0:
        warnings.append("已读取到功能注释文件，但未与当前 DEG 候选基因匹配到功能注释。")
    if (
        summary.get("annotation_path_exists")
        and summary.get("annotation_merge_status")
        and summary.get("annotation_merge_status") != "completed"
        and summary.get("annotation_merge_warning")
    ):
        warnings.append(summary["annotation_merge_warning"])

    return warnings


# Evidence Pack 准备入口。
# 该函数本身不直接解析 TSV，而是调用 evidence_adapters.build_omics_evidence_pack_from_context()
# 从 Context 中读取 transcriptome_result_path / metabolome_path / literature_evidence_path
# 并构建基础 Evidence Pack。
#
# 基础 Evidence Pack 构建完成后，再调用 search_background_literature()
# 根据 trait 和已提取的 target_genes 补充 PubMed 背景文献线索。
#
# 注意：
# - 本地 verified literature 与 PubMed background literature 是两类不同证据；
# - transcriptome_path_exists / metabolome_path_exists 来自 Evidence Pack debug.inputs；
# - warnings 只是证据完整性提醒，不等于 Guard 最终失败。
def prepare_omics_evidence_pack_from_context(
    context: OmicsBreedingAnalysisContext,
) -> dict[str, Any]:

    """从 Context 中的文件路径构建 Evidence Pack，并写入输出路径。"""
    # 这一步进入 evidence_adapters.py。它负责从 context 读取，然后生成基础 Evidence Pack
    evidence_pack = build_omics_evidence_pack_from_context(context)
    background_literature = search_background_literature(
        trait=context.trait,
        target_genes=evidence_pack.get("targets", {}).get("genes") or [],
        query_plan=evidence_pack.get("literature_query_plan") or [],
    )
    evidence_pack["background_literature_records"] = background_literature.get("records") or []
    evidence_pack["background_literature_search"] = {
        "status": background_literature.get("status", ""),
        "backend": background_literature.get("backend", ""),
        "literature_source": background_literature.get("literature_source", ""),
        "used_query_plan": bool(background_literature.get("used_query_plan")),
        "query_plan_count": int(background_literature.get("query_plan_count") or 0),
        "executed_query_count": int(background_literature.get("executed_query_count") or 0),
        "unexecuted_query_count": int(background_literature.get("unexecuted_query_count") or 0),
        "query_limit": int(background_literature.get("query_limit") or 0),
        "desired_record_count": int(background_literature.get("desired_record_count") or 0),
        "per_query_result_limit": int(background_literature.get("per_query_result_limit") or 0),
        "retained_record_limit": int(background_literature.get("retained_record_limit") or 0),
        "priority_budgets": background_literature.get("priority_budgets") or {},
        "priority_execution_counts": background_literature.get("priority_execution_counts") or {},
        "priority_plan_counts": background_literature.get("priority_plan_counts") or {},
        "executed_query_details": background_literature.get("executed_query_details") or [],
        "skipped_query_count": int(background_literature.get("skipped_query_count") or 0),
        "fallback_executed": bool(background_literature.get("fallback_executed")),
        "stop_reason": background_literature.get("stop_reason", ""),
        "queries": background_literature.get("queries") or [],
        "warning_count": len(background_literature.get("warnings") or []),
        "warnings": background_literature.get("warnings") or [],
    }
    guard_requirements = evidence_pack.setdefault("guard_requirements", {})
    background_records = evidence_pack["background_literature_records"]
    allowed_dois = list(guard_requirements.get("allowed_dois") or [])
    allowed_quotes = list(guard_requirements.get("allowed_quoted_sentences") or [])
    for record in background_records:
        doi = str(record.get("doi") or "").strip()
        quoted_sentence = str(record.get("quoted_sentence") or "").strip()
        if doi and doi not in allowed_dois:
            allowed_dois.append(doi)
        if quoted_sentence and quoted_sentence not in allowed_quotes:
            allowed_quotes.append(quoted_sentence)
    guard_requirements["allowed_dois"] = allowed_dois
    guard_requirements["allowed_quoted_sentences"] = allowed_quotes
    # 写出 omics_evidence_pack.json 到磁盘 总链路是：
    # chat_service.py 构造 output_dir
    #   ↓
    # omics_analysis.py 构造 evidence_pack_output_path
    #   ↓
    # workflow.py 写出 omics_evidence_pack.json
    output_path = Path(context.evidence_pack_output_path).expanduser().resolve()
    evidence_pack.setdefault("artifacts", {})["evidence_pack_path"] = str(output_path)
    write_evidence_pack(evidence_pack, output_path)
    # 生成 warnings
    warnings = _build_warnings(evidence_pack) # Evidence Pack 自身完整性 warning
    warnings.extend(background_literature.get("warnings") or []) # PubMed 背景检索 warning

    # 返回 Evidence Pack 结果，会继续传给总装函数 prepare_cited_guarded_omics_analysis_from_context()
    return {
        "status": "completed_with_warnings" if warnings else "completed",
        "evidence_pack_path": str(output_path),
        "evidence_pack": evidence_pack,
        "summary": summarize_evidence_pack(evidence_pack),
        "warnings": warnings,
        "artifacts": [str(output_path)],
    }


# 旧工具桥接入口 当前主线：
# Context 文件路径
# → build_omics_evidence_pack_from_context()
#
# 旧桥接：
# 旧 Tool 返回结果
# → build_omics_evidence_pack_from_tool_results()
def prepare_omics_evidence_pack_from_tool_results(
    *,
    context: OmicsBreedingAnalysisContext,
    transcriptome_tool_result: dict[str, Any] | None = None,
    literature_tool_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """从旧 Tool 返回结果构建 Evidence Pack，并写入输出路径。

    这是过渡层：
    - 可以复用旧 breeding_transcriptome_deg 的 significant_de_genes_path；
    - 可以复用旧 breeding_literature_evidence 的 entries；
    - 不复用旧 advice_generate 或 smoke 一键建议结果。
    """

    evidence_pack = build_omics_evidence_pack_from_tool_results(
        context=context,
        transcriptome_tool_result=transcriptome_tool_result,
        literature_tool_result=literature_tool_result,
    )
    output_path = Path(context.evidence_pack_output_path).expanduser().resolve()
    evidence_pack.setdefault("artifacts", {})["evidence_pack_path"] = str(output_path)
    write_evidence_pack(evidence_pack, output_path)
    warnings = _build_warnings(evidence_pack)

    return {
        "status": "completed_with_warnings" if warnings else "completed",
        "evidence_pack_path": str(output_path),
        "evidence_pack": evidence_pack,
        "summary": summarize_evidence_pack(evidence_pack),
        "warnings": warnings,
        "artifacts": [str(output_path)],
    }


# 通用 JSON 写出函数  dict --> json
def write_json_artifact(payload: dict[str, Any], output_path: str | Path) -> Path:
    """将结构化结果写入 JSON artifact。

    用于写出 guard_result.json、后续 citation_result.json 等结构化文件。
    """

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


# 这个函数是 Guard 的 workflow 入口
def guard_omics_answer(
    *,
    answer_markdown: str,
    evidence_pack: dict[str, Any],
    guard_result_path: str | Path,
) -> dict[str, Any]:
    """对多组学育种分析回答执行 Dynamic Guard，并写出 guard_result.json。

    这个函数只负责：
    - 调用 Dynamic Guard
    - 写出 guard_result.json
    - 返回统一结构

    它不负责：
    - 生成回答
    - 调用 LLM
    - 调用 Citation Engine
    """

    guard_result = run_dynamic_output_guard(answer_markdown, evidence_pack)
    guard_path = write_json_artifact(guard_result, guard_result_path)

    return {
        "status": "passed" if guard_result["passed"] else "failed_guard",  # Guard 是否通过
        "answer_markdown": answer_markdown,
        "guard_result": guard_result,
        "guard_result_path": str(guard_path),
        "artifacts": [str(guard_path)],
    }


# 把前面几层串起来：
# Context
# ↓
# prepare_omics_evidence_pack_from_context()
# ↓
# Evidence Pack
# ↓
# guard_omics_answer()
# ↓
# guard_result.json
def prepare_guarded_omics_answer_from_context(
    *,
    context: OmicsBreedingAnalysisContext,
    answer_markdown: str,
    guard_result_path: str | Path,
) -> dict[str, Any]:
    """从 Context 构建 Evidence Pack，然后对 answer_markdown 执行 Guard。

    这是临时衔接函数：
    - 当前阶段 answer_markdown 由测试或后续 LLM/Citation 层传入；
    - 本函数负责证据准备和 Guard；
    - 后续 LlamaIndex 接入后，可把 Citation Engine 生成的回答传入这里。
    """

    evidence_pack_result = prepare_omics_evidence_pack_from_context(context)
    guard_result = guard_omics_answer(
        answer_markdown=answer_markdown,
        evidence_pack=evidence_pack_result["evidence_pack"],
        guard_result_path=guard_result_path,
    )

    return {
        "status": guard_result["status"],
        "answer_markdown": answer_markdown,
        "evidence_pack": evidence_pack_result["evidence_pack"],
        "evidence_pack_path": evidence_pack_result["evidence_pack_path"],
        "guard_result": guard_result["guard_result"],
        "guard_result_path": guard_result["guard_result_path"],
        "summary": evidence_pack_result["summary"],
        "warnings": evidence_pack_result["warnings"],
        "artifacts": [
            *evidence_pack_result["artifacts"],
            *guard_result["artifacts"],
        ],
    }


# 当前新智能体的第一个“统一结果入口”，是后端 workflow 层的可测试总装函数。
# 它做了：
# 1. 生成 Evidence Pack
# 2. 生成 Citation Result
# 3. 执行 Dynamic Guard
# 4. 写出 final_result.json
# 把当前已有模块串了起来：
# Context
# ↓
# prepare_omics_evidence_pack_from_context()
# ↓
# build_citation_result()
# ↓
# guard_omics_answer()
# ↓
# final_result.json

# 函数在当前链路中的位置
# chat_service.py direct route
#   ↓
# omics_breeding_analysis_run.invoke({"input": tool_input})
#   ↓
# omics_analysis.py
#   ↓
# prepare_cited_guarded_omics_analysis_from_context()
#   ↓
# workflow.py 总装
def prepare_cited_guarded_omics_analysis_from_context(
    *,
    context: OmicsBreedingAnalysisContext,
    use_llamaindex: bool = False,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """构建带 citation、Dynamic Guard 和前端展示 payload 的多组学育种分析结果。

    流程：
    1. 根据 Context 构建 Evidence Pack；
    2. 基于 Evidence Pack 构建 citation result；
    3. 对 answer_markdown 执行 Dynamic Guard；
    4. 生成 frontend_payload；
    5. 写出 answer_markdown.md、citation_result.json、guard_result.json、
       frontend_payload.json、final_result.json；
    6. 返回前端可消费的统一结构。
    """

    # 负责把 Context 里的路径和输入变成统一证据包 Evidence Pack
    evidence_pack_result = prepare_omics_evidence_pack_from_context(context)
    evidence_pack = evidence_pack_result["evidence_pack"]

    # 确定输出目录  决定所有结果文件写到哪里
    base_output_dir = (
        Path(output_dir)
        if output_dir is not None
        else Path(context.evidence_pack_output_path).expanduser().resolve().parent
    )
    base_output_dir.mkdir(parents=True, exist_ok=True)

    # 构建 Citation Result，也就是 LLM 分析结果
    citation_result = build_citation_result(
        evidence_pack=evidence_pack,
        question=context.question,
        use_llamaindex=use_llamaindex,
        model_name=context.model,
    )

    answer_markdown = citation_result["answer_markdown"]

    # 确定几个输出文件路径
    answer_path = base_output_dir / "answer_markdown.md"
    citation_result_path = base_output_dir / "citation_result.json"
    guard_result_path = base_output_dir / "guard_result.json"
    frontend_payload_path = base_output_dir / "frontend_payload.json"
    final_result_path = base_output_dir / "final_result.json"

    # 写出 Markdown 和 citation_result
    # 这一步先把 LLM 生成的正文写成 Markdown 文件，再把 citation 结构化结果写成 JSON。
    # 这里还没有执行 Guard，也还没有生成 frontend_payload。
    answer_path.write_text(answer_markdown, encoding="utf-8")
    write_json_artifact(citation_result, citation_result_path)

    # 执行 Guard，对刚才生成的 answer_markdown 做动态边界检查
    guard_result = guard_omics_answer(
        answer_markdown=answer_markdown,
        evidence_pack=evidence_pack,
        guard_result_path=guard_result_path,
    )

    # 决定最终状态
    final_status = "completed" if guard_result["guard_result"]["passed"] else "failed_guard"

    # 合并 artifacts，把所有输出文件路径收集到一个列表，最终前端或诊断里能看到结构化输出文件，就是来自这里
    artifacts = [
        *evidence_pack_result["artifacts"],
        str(answer_path),
        str(citation_result_path),
        *guard_result["artifacts"],
        str(frontend_payload_path),
        str(final_result_path),
    ]
    literature_query_plan_path = str(
        (evidence_pack_result.get("summary") or {}).get("literature_query_plan_path") or ""
    ).strip()
    if literature_query_plan_path and literature_query_plan_path not in artifacts:
        artifacts.insert(2, literature_query_plan_path)
    annotated_transcriptome_path = str(
        (evidence_pack_result.get("summary") or {}).get("annotated_transcriptome_path") or ""
    ).strip()
    if annotated_transcriptome_path and annotated_transcriptome_path not in artifacts:
        artifacts.insert(1, annotated_transcriptome_path)

    raw_answer_backend = str(citation_result.get("raw_answer_backend") or "").strip()
    analysis_backend = "llm" if raw_answer_backend == "llm" else "rule_based"

    # 把 Evidence Pack 阶段的 summary 和 Citation 阶段的 backend 合并起来。
    # analysis_backend 表示综合分析文本来源；render_backend 表示最终 Markdown 渲染器。
    summary = {
        **evidence_pack_result["summary"],
        "evidence_pack_path": evidence_pack_result["evidence_pack_path"],
        "omics_evidence_pack_path": evidence_pack_result["evidence_pack_path"],
        "evidence_pack_path_exists": Path(evidence_pack_result["evidence_pack_path"]).is_file(),
        "background_literature_search_status": (
            (evidence_pack.get("background_literature_search") or {}).get("status", "")
        ),
        "background_literature_record_count": len(
            evidence_pack.get("background_literature_records") or []
        ),
        "literature_query_plan_count": len(evidence_pack.get("literature_query_plan") or []),
        "analysis_backend": analysis_backend,
        "render_backend": citation_result["backend"],
        "raw_answer_backend": raw_answer_backend,
        "citation_backend": citation_result.get("citation_backend", ""),
        "citation_disabled_reason": citation_result.get("disabled_reason", ""),
        "llamaindex_available": bool(citation_result.get("llamaindex_available")),
        "literature_card_count": len(citation_result["literature_cards"]),
        "annotated_transcriptome_read_by_llm": bool(
            (citation_result.get("analysis_prompt") or {}).get("annotated_transcriptome_read_by_llm")
        ),
    }

    # 组装 final_result，这是后端最终结果的主结构
    # 它会返回给：
    # omics_analysis.py
    #   ↓
    # chat_service.py tool_result
    #   ↓
    # _save_direct_breeding_workbench_tool_messages()
    #   ↓
    # 前端 history
    final_result = {
        "status": final_status,
        "backend": citation_result["backend"],
        "raw_answer_backend": citation_result.get("raw_answer_backend", ""),
        "llamaindex_available": citation_result["llamaindex_available"],
        "answer_markdown": answer_markdown,
        "canonical_answer_markdown": citation_result.get("canonical_answer_markdown", ""),
        "raw_llm_answer": citation_result.get("raw_llm_answer", ""),
        "citations": citation_result["citations"],
        "literature_cards": citation_result["literature_cards"],
        "claim_trace": citation_result["claim_trace"],
        "source_nodes": citation_result.get("source_nodes") or [],
        "analysis_prompt": citation_result.get("analysis_prompt") or {},
        "guard_result": guard_result["guard_result"],
        "evidence_pack": evidence_pack,
        "evidence_pack_path": evidence_pack_result["evidence_pack_path"],
        "citation_result_path": str(citation_result_path),
        "guard_result_path": guard_result["guard_result_path"],
        "answer_markdown_path": str(answer_path),
        "frontend_payload_path": str(frontend_payload_path),
        "summary": summary,
        "warnings": [
            *evidence_pack_result.get("warnings", []),
            *citation_result.get("warnings", []),
            *guard_result["guard_result"].get("warnings", []),
        ],
        "artifacts": artifacts,
    }

    # 生成 frontend_payload，是专门给前端消费的简化结构。
    frontend_payload = build_frontend_payload(final_result)
    # final_result 是后端完整结果，字段很多
    final_result["frontend_payload"] = frontend_payload

    # 写出 frontend_payload 和 final_result
    write_json_artifact(frontend_payload, frontend_payload_path)
    write_json_artifact(final_result, final_result_path)

    return final_result
