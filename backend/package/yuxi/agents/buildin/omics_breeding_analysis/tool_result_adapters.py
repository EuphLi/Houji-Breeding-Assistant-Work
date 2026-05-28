from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import OmicsBreedingAnalysisContext
from .evidence_adapters import read_literature_records, read_transcriptome_records
from .evidence_pack import build_omics_evidence_pack

"""
负责：从旧 tool_result 中找到可信的文件路径或文献 entries
复用的是：
1. 旧转录组工具产出的 significant_de_genes.tsv 文件路径
2. 旧文献工具产出的 entries
3. 旧文献工具可能提供的 literature_evidence_path
"""

'''
处于目前项目中的作用
1. 兼容旧工具输出
2. 单元测试
3. 未来如果重新启用“先跑旧工具，再构建 Evidence Pack”的链路
'''


# 把任意输入安全转成字符串
def _as_non_empty_str(value: Any) -> str:
    text = str(value or "").strip()
    return text

# 转录组旧工具结果适配
def extract_transcriptome_records_from_tool_result(
    tool_result: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """从旧转录组 Tool 返回结果中提取 transcriptome_records。

    只信任 significant_de_genes_path 指向的文件内容。

    不使用旧工具里的 target_gene_found / matches 字段，因为这些字段当前仍可能围绕
    smoke 任务中的固定 TARGET_GENE。
    """

    if not isinstance(tool_result, dict):
        return []

    # 只读取信任的一个字段：ignificant_de_genes_path，旧转录组工具生成的差异基因结果文件路径
    significant_de_path = _as_non_empty_str(tool_result.get("significant_de_genes_path"))
    if not significant_de_path:
        return []

    # 再交给 read_transcriptome_records()去真正的读文件
    return read_transcriptome_records(Path(significant_de_path))


# 过滤函数，不让测试数据、演示数据、未确认数据进入正式 Evidence Pack。
def _is_demo_or_unverified_literature_entry(entry: dict[str, Any]) -> bool:
    status = _as_non_empty_str(
        entry.get("status") or entry.get("evidence_status") or entry.get("curation_status")
    ).lower()
    source = _as_non_empty_str(entry.get("source")).lower()
    is_demo = _as_non_empty_str(entry.get("is_demo")).lower()

    if status in {"pending", "rejected", "demo", "invalid"}:
        return True

    if is_demo in {"1", "true", "yes", "y"}:
        return True

    if "fixture" in source:
        return True

    return False


# 文献旧工具结果适配
def extract_literature_records_from_tool_result(
    tool_result: dict[str, Any] | None,
    *,
    fallback_path: str = "",
) -> list[dict[str, Any]]:
    """从旧文献 Tool 返回结果中提取 literature_records。

    优先使用 tool_result["entries"]。
    如果 entries 不存在，并且提供了 fallback_path，则回退读取 TSV 文件。

    这里仍会重新过滤 demo / fixture / pending / rejected 记录。
    """

    # 优先用旧工具返回 entries
    # 如果没有 entries，就读 fallback_path 指向的 verified_literature_evidence.tsv
    if not isinstance(tool_result, dict):
        return read_literature_records(fallback_path) if fallback_path else []

    # 如果没有 entries，也回退读 TSV
    entries = tool_result.get("entries")
    if not isinstance(entries, list):
        return read_literature_records(fallback_path) if fallback_path else []

    records: list[dict[str, Any]] = []

    # 遍历 entries，只处理字典格式
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            continue

        # 过滤不可用文献数据
        if _is_demo_or_unverified_literature_entry(entry):
            continue

        # 确保 DOI 和 quoted_sentence 必须同时存在
        doi = _as_non_empty_str(entry.get("doi"))
        quoted_sentence = _as_non_empty_str(entry.get("quoted_sentence"))

        if not doi or not quoted_sentence:
            continue

        # 标准化文献记录
        records.append(
            {
                "evidence_id": _as_non_empty_str(entry.get("evidence_id")) or f"L{index}",
                "doi": doi,
                "quoted_sentence": quoted_sentence,
                "trait": _as_non_empty_str(entry.get("trait")),
                "gene_id": _as_non_empty_str(entry.get("gene_id")),
                "title": _as_non_empty_str(entry.get("title")),
                "source_file": _as_non_empty_str(
                    entry.get("source_file") or tool_result.get("literature_evidence_path")
                ),
                "relevance_level": _as_non_empty_str(
                    entry.get("relevance_level") or entry.get("evidence_level")
                ),
            }
        )

    return records


# 总入口
def build_omics_evidence_pack_from_tool_results(
    *,
    context: OmicsBreedingAnalysisContext,
    transcriptome_tool_result: dict[str, Any] | None = None,
    literature_tool_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """根据旧工具返回结果构建新的 Evidence Pack。

    该函数是临时桥接层：
    - 允许复用旧 breeding_transcriptome_deg 的输出文件；
    - 允许复用旧 breeding_literature_evidence 的 entries；
    - 不复用旧 advice_generate / smoke 一键包装的最终 Markdown；
    - 不使用旧工具中的硬编码 target_gene_found 作为新任务目标。
    """

    # 从旧转录组结果提取转录组记录
    transcriptome_records = extract_transcriptome_records_from_tool_result(
        transcriptome_tool_result
    )

    # 从旧文献结果提取文献记录
    literature_records = extract_literature_records_from_tool_result(
        literature_tool_result,
        fallback_path=context.literature_evidence_path,
    )

    # 构建新的 Evidence Pack
    return build_omics_evidence_pack(
        trait=context.trait,
        question=context.question,
        transcriptome_records=transcriptome_records,
        literature_records=literature_records,
        metabolome_context=[],
        genome_context=[],
    )