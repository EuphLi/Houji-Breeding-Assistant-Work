from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

from .context import OmicsBreedingAnalysisContext
from .evidence_pack import build_omics_evidence_pack

"""
此文件是 Evidence Pack 的文件适配层，完成把“文件路径和 TSV 内容”转成“标准 records”。
完整链路是：
chat_service.py
  构造 tool_input
    ↓
omics_analysis.py
  构造 OmicsBreedingAnalysisContext
    ↓
workflow.py
  prepare_omics_evidence_pack_from_context()
    ↓
evidence_adapters.py
  读取 transcriptome / literature / metabolome 路径
    ↓
evidence_pack.py
  build_omics_evidence_pack()

上一阶段的 evidence_pack.py 做的是：
已经有 transcriptome_records / literature_records
↓
构建 Evidence Pack

但它不负责读真实文件。
这一步新增的 evidence_adapters.py 负责：
significant_de_genes.tsv
verified_literature_evidence.tsv
↓
读取和字段标准化
↓
transcriptome_records / literature_records
↓
build_omics_evidence_pack()

所以它的位置是：
Context 文件路径
↓
evidence_adapters.py 读取 TSV
↓
evidence_pack.py 构建统一证据包

实现了链路:
OmicsBreedingAnalysisContext
  ↓
evidence_adapters.py
  - read_transcriptome_records()
  - read_literature_records()
  ↓
evidence_pack.py
  - build_omics_evidence_pack()
  ↓
omics_evidence_pack.json 结构
"""

logger = logging.getLogger(__name__)


DEFAULT_SMOKE_DATA_MARKER = "/smoke_test_minimal/"
MAX_METABOLOME_PREVIEW_ROWS = 30
MAX_METABOLOME_PREVIEW_CHARS = 10000

# 负责读取 TSV 文件
def _read_tsv(path: str | Path) -> list[dict[str, str]]:
    """读取 TSV 文件为字典列表。

    文件不存在时返回空列表，避免第一版因为缺少可选证据直接崩溃。
    """
    # 接收字符串路径或Path对象
    file_path = Path(path)
    # 若文件不存在，返回空列表
    if not file_path.exists() or not file_path.is_file():
        return []
    # 文件存在，用 csv.DictReader 按制表符读取
    with file_path.open("r", encoding="utf-8") as handle:
        # 每一行转成 dict
        reader = csv.DictReader(handle, delimiter="\t")
        return [dict(row) for row in reader]


def _normalized_row_lookup(row: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in (row or {}).items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        normalized.setdefault(key_text.lower(), value)
    return normalized


# 从一组候选字段名里，取第一个存在且非空的值
# 因为不同工具或不同 TSV 的列名可能不统一，增强兼容性，避免代码只认一种固定列名
# 如 _first_present(row, ["gene_id", "GeneID", "gene"]) 会返回对应的基因ID
def _first_present(row: dict[str, Any], candidates: list[str]) -> str:
    normalized_row = _normalized_row_lookup(row)
    for key in candidates:
        value = row.get(key)
        if value is None:
            value = normalized_row.get(str(key or "").strip().lower())
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _infer_gene_id(row: dict[str, Any]) -> str:
    gene_id = _first_present(
        row,
        [
            "gene_id",
            "geneid",
            "gene_id(s)",
            "gene",
            "gene_name",
            "target_gene",
            "feature_id",
            "locus_id",
            "locus",
            "id",
        ],
    )
    if gene_id:
        return gene_id

    normalized_row = _normalized_row_lookup(row)
    for key, value in normalized_row.items():
        if ("gene" in key or key.endswith("_id") or key == "id") and str(value or "").strip():
            return str(value).strip()

    for value in (row or {}).values():
        text = str(value or "").strip()
        if text:
            return text

    return ""


# 判断路径来源
def _infer_input_source(path: str | Path) -> str:
    normalized = str(path or "").strip()
    if not normalized:
        return "input_missing_or_filename_only"
    if DEFAULT_SMOKE_DATA_MARKER in normalized:
        return "default_smoke_data"
    return "user_provided_path"


def _context_data_dir(context: OmicsBreedingAnalysisContext) -> str:
    upload_root = str(context.upload_root or "").strip()
    if upload_root:
        return upload_root
    for value in [
        context.transcriptome_result_path,
        context.metabolome_path,
        context.literature_evidence_path,
    ]:
        normalized = str(value or "").strip()
        if not normalized:
            continue
        path = Path(normalized)
        if path.name and "." in path.name:
            return str(path.parent)
        return str(path)
    return ""


def _candidate_context_roots(context: OmicsBreedingAnalysisContext) -> list[Path]:
    roots: list[Path] = []
    for raw in [
        context.upload_root,
        _context_data_dir(context),
    ]:
        normalized = str(raw or "").strip()
        if not normalized:
            continue
        path = Path(normalized).expanduser()
        candidate_root = path if path.is_dir() else path.parent
        if candidate_root in roots:
            continue
        roots.append(candidate_root)
    return roots


def _resolve_context_file_path(
    path_value: str | Path,
    *,
    context: OmicsBreedingAnalysisContext,
) -> str:
    normalized = str(path_value or "").strip()
    if not normalized:
        return ""

    explicit = Path(normalized).expanduser()
    candidates = [explicit]
    for root in _candidate_context_roots(context):
        candidates.append(root / normalized)
        candidates.append(root / explicit.name)

    seen: set[str] = set()
    for candidate in candidates:
        candidate_text = str(candidate)
        if candidate_text in seen:
            continue
        seen.add(candidate_text)
        if candidate.is_file():
            return str(candidate.resolve())

    if explicit.is_absolute():
        return str(explicit)
    return normalized


def _list_upload_root_files(context: OmicsBreedingAnalysisContext) -> list[Path]:
    upload_root = str(context.upload_root or "").strip()
    if not upload_root:
        return []
    root_path = Path(upload_root).expanduser()
    if not root_path.exists() or not root_path.is_dir():
        return []
    return [path for path in root_path.rglob("*") if path.is_file()]


def _discover_context_input_paths(context: OmicsBreedingAnalysisContext) -> dict[str, Any]:
    upload_files = _list_upload_root_files(context)
    discovered: dict[str, Any] = {
        "transcriptome_result_path": "",
        "metabolome_path": "",
        "literature_evidence_path": "",
        "sample_map_path": "",
        "reference_genome_path": "",
        "genome_gff_path": "",
        "annotation_path": "",
        "rnaseq_read_paths": [],
    }
    if not upload_files:
        return discovered

    def _pick_first(predicate) -> str:
        for path in upload_files:
            if predicate(path):
                return str(path.resolve())
        return ""

    discovered["transcriptome_result_path"] = _pick_first(
        lambda path: path.name == "significant_de_genes.tsv"
        and "transcriptome_deg" in {part.lower() for part in path.parts}
    )
    discovered["metabolome_path"] = _pick_first(
        lambda path: path.name == "metabolome_raw_3372.tsv"
        or ("metabolome" in path.name.lower() and path.suffix.lower() == ".tsv")
    )
    discovered["literature_evidence_path"] = _pick_first(
        lambda path: path.name == "verified_literature_evidence.tsv"
    )
    discovered["sample_map_path"] = _pick_first(
        lambda path: path.name == "sampleName_clientId.txt"
    )
    discovered["reference_genome_path"] = _pick_first(
        lambda path: path.name in {"genome.fa", "genome.fasta"}
    )
    discovered["genome_gff_path"] = _pick_first(
        lambda path: path.name in {"genome.gff", "genome.gff3"}
    )
    discovered["annotation_path"] = _pick_first(
        lambda path: (
            "annotation" in path.name.lower()
            or path.name in {"smoke_gene_ids.txt", "xiaomi_T2T_Annotation.smoke_genes.txt"}
        )
        and path.suffix.lower() in {".txt", ".tsv"}
    )
    discovered["rnaseq_read_paths"] = [
        str(path.resolve())
        for path in upload_files
        if path.name.lower().endswith((".fq", ".fastq", ".fq.gz", ".fastq.gz"))
    ]
    return discovered


def discover_context_input_paths(context: OmicsBreedingAnalysisContext) -> dict[str, Any]:
    return _discover_context_input_paths(context)


def _read_smoke_gene_ids(path: str | Path) -> list[str]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return []

    gene_ids: list[str] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        gene_id = str(line or "").strip()
        if gene_id:
            gene_ids.append(gene_id)
    return gene_ids


def _read_text_preview(
    path: str | Path,
    *,
    max_rows: int,
    max_chars: int,
) -> dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return {
            "preview_text": "",
            "preview_rows": [],
            "row_count": 0,
            "truncated": False,
        }

    preview_rows: list[str] = []
    preview_text_parts: list[str] = []
    total_chars = 0
    truncated = False

    with file_path.open("r", encoding="utf-8", errors="replace") as handle:
        for index, line in enumerate(handle):
            if index >= max_rows:
                truncated = True
                break
            normalized = line.rstrip("\n")
            preview_rows.append(normalized)
            total_chars += len(normalized) + 1
            preview_text_parts.append(normalized)
            if total_chars >= max_chars:
                truncated = True
                break

    preview_text = "\n".join(preview_text_parts)
    if len(preview_text) > max_chars:
        preview_text = preview_text[:max_chars]
        truncated = True

    return {
        "preview_text": preview_text,
        "preview_rows": preview_rows,
        "row_count": len(preview_rows),
        "truncated": truncated,
    }


# 输入路径诊断
def collect_input_file_diagnostics(context: OmicsBreedingAnalysisContext) -> dict[str, Any]:
    discovered_paths = discover_context_input_paths(context)
    # 读取：
    transcriptome_path = _resolve_context_file_path(
        context.transcriptome_result_path or discovered_paths["transcriptome_result_path"],
        context=context,
    )
    metabolome_path = _resolve_context_file_path(
        context.metabolome_path or discovered_paths["metabolome_path"],
        context=context,
    )
    literature_path = _resolve_context_file_path(
        context.literature_evidence_path or discovered_paths["literature_evidence_path"],
        context=context,
    )
    sample_map_path = _resolve_context_file_path(
        context.sample_map_path or discovered_paths["sample_map_path"],
        context=context,
    )
    reference_genome_path = _resolve_context_file_path(
        context.reference_genome_path or discovered_paths["reference_genome_path"],
        context=context,
    )
    genome_gff_path = _resolve_context_file_path(
        context.genome_gff_path or discovered_paths["genome_gff_path"],
        context=context,
    )
    annotation_path = _resolve_context_file_path(
        context.annotation_path or discovered_paths["annotation_path"],
        context=context,
    )
    rnaseq_read_paths = [
        _resolve_context_file_path(path, context=context)
        for path in ((context.rnaseq_read_paths or []) or discovered_paths["rnaseq_read_paths"])
        if str(path or "").strip()
    ]
    # 判断：
    transcriptome_exists = bool(transcriptome_path) and Path(transcriptome_path).is_file()
    metabolome_exists = bool(metabolome_path) and Path(metabolome_path).is_file()
    literature_exists = bool(literature_path) and Path(literature_path).is_file()
    sample_map_exists = bool(sample_map_path) and Path(sample_map_path).is_file()
    reference_genome_exists = bool(reference_genome_path) and Path(reference_genome_path).is_file()
    genome_gff_exists = bool(genome_gff_path) and Path(genome_gff_path).is_file()
    annotation_exists = bool(annotation_path) and Path(annotation_path).is_file()
    existing_rnaseq_read_paths = [path for path in rnaseq_read_paths if Path(path).is_file()]
    transcriptome_supporting_input_count = len(existing_rnaseq_read_paths) + sum(
        [
            sample_map_exists,
            reference_genome_exists,
            genome_gff_exists,
            annotation_exists,
        ]
    )
    transcriptome_supporting_input_exists = transcriptome_supporting_input_count > 0
    if transcriptome_exists:
        transcriptome_input_status = "deg_available"
    elif existing_rnaseq_read_paths:
        transcriptome_input_status = "fastq_uploaded"
    elif transcriptome_supporting_input_exists:
        transcriptome_input_status = "supporting_files_uploaded"
    else:
        transcriptome_input_status = "missing"

    effective_paths = [
        transcriptome_path,
        metabolome_path,
        literature_path,
        sample_map_path,
        reference_genome_path,
        genome_gff_path,
        annotation_path,
        *existing_rnaseq_read_paths,
    ]
    any_existing_inputs = (
        transcriptome_exists
        or metabolome_exists
        or literature_exists
        or transcriptome_supporting_input_exists
    )

    if any_existing_inputs:
        if any(_infer_input_source(path) == "default_smoke_data" for path in effective_paths):
            evidence_level = "default_smoke_data"
        else:
            evidence_level = "user_provided_path"
    else:
        evidence_level = "input_missing_or_filename_only"

    return {
        "trait": str(context.trait or "").strip(),
        "question": str(context.question or "").strip(),
        "data_dir": _context_data_dir(context),
        "transcriptome_result_path": transcriptome_path,
        "transcriptome_path_exists": transcriptome_exists,
        "transcriptome_path_source": _infer_input_source(transcriptome_path),
        "transcriptome_input_status": transcriptome_input_status,
        "transcriptome_supporting_input_exists": transcriptome_supporting_input_exists,
        "transcriptome_supporting_input_count": transcriptome_supporting_input_count,
        "metabolome_path": metabolome_path,
        "metabolome_path_exists": metabolome_exists,
        "metabolome_path_source": _infer_input_source(metabolome_path),
        "literature_evidence_path": literature_path,
        "literature_path_exists": literature_exists,
        "sample_map_path": sample_map_path,
        "sample_map_path_exists": sample_map_exists,
        "reference_genome_path": reference_genome_path,
        "reference_genome_path_exists": reference_genome_exists,
        "genome_gff_path": genome_gff_path,
        "genome_gff_path_exists": genome_gff_exists,
        "annotation_path": annotation_path,
        "annotation_path_exists": annotation_exists,
        "rnaseq_read_paths": existing_rnaseq_read_paths,
        "rnaseq_read_count": len(existing_rnaseq_read_paths),
        "discovered_upload_files": {
            "transcriptome_result_path": discovered_paths["transcriptome_result_path"],
            "metabolome_path": discovered_paths["metabolome_path"],
            "sample_map_path": discovered_paths["sample_map_path"],
            "reference_genome_path": discovered_paths["reference_genome_path"],
            "genome_gff_path": discovered_paths["genome_gff_path"],
            "annotation_path": discovered_paths["annotation_path"],
            "rnaseq_read_paths": discovered_paths["rnaseq_read_paths"],
        },
        "evidence_level": evidence_level,
        "data_source": evidence_level,
    }


# 读取 significant_de_genes.tsv，并把它转成 Evidence Pack 需要的 transcriptome_records
def read_transcriptome_records(path: str | Path) -> list[dict[str, Any]]:
    """从 significant_de_genes.tsv 读取转录组证据。

    当前只做轻量字段标准化：
    - 不在这里判断最终候选基因
    - 不写死具体 gene_id
    - 不生成最终育种结论
    """

    rows = _read_tsv(path)
    records: list[dict[str, Any]] = []

    # 这里会从每行提取 gene_id。如果某行没有基因 ID，就跳过。
    # 然后构建标准记录
    for index, row in enumerate(rows, start=1):
        gene_id = _infer_gene_id(row)
        if not gene_id:
            continue

        record = {
            "evidence_id": row.get("evidence_id") or f"T{index}",  # 证据编号，默认 T1、T2...
            "gene_id": gene_id,  # 目标基因ID
            "source_file": str(path),  # 证据来源文件路径
        }

        # 尝试提取统计值，表示它支持多种 DEG 结果列名
        for source_key, target_key in [
            ("logFC", "logfc"),
            ("log2FoldChange", "logfc"),
            ("log2fc", "logfc"),
            ("fold_change", "logfc"),
            ("pvalue", "pvalue"),
            ("p_value", "pvalue"),
            ("p.value", "pvalue"),
            ("padj", "padj"),
            ("adj.P.Val", "padj"),
            ("adj_p_val", "padj"),
            ("FDR", "padj"),
        ]:
            value = _first_present(row, [source_key])
            if value:
                record[target_key] = str(value).strip()

        records.append(record)

    return records


# 判断一条文献记录是否应该被过滤掉
def _is_rejected_or_demo_literature_row(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or row.get("evidence_status") or "").strip().lower()
    source = str(row.get("source") or "").strip().lower()
    is_demo = str(row.get("is_demo") or "").strip().lower()

    if status in {"pending", "rejected", "demo", "invalid"}:
        return True

    if is_demo in {"1", "true", "yes", "y"}:
        return True

    # 如果来源是 PubMedFixture 固定样例数据之类，也过滤
    if "fixture" in source:
        return True

    return False


def _literature_status(row: dict[str, Any]) -> str:
    return str(
        row.get("status") or row.get("evidence_status") or row.get("evidence_level") or ""
    ).strip().lower()


def _is_verified_like_literature_row(row: dict[str, Any]) -> bool:
    return _literature_status(row) in {"verified", "curated", "accepted"}


# 本地文献 TSV 诊断，这个函数的定位是：
# 读取本地 verified_literature_evidence.tsv
# 统计过滤原因
# 返回可用文献 records
def collect_literature_evidence_diagnostics(
    path: str | Path,
    *,
    trait: str = "",
) -> dict[str, Any]:
    """收集文献证据文件的诊断信息，并返回可用记录。

    当前不联网搜索，只诊断本地 verified_literature_evidence.tsv 的可用性。
    """

    file_path = Path(path)
    # 如果路径为空，直接返回
    if not str(path or "").strip():
        return {
            "literature_evidence_path": str(path),
            "literature_path_exists": False,
            "literature_row_count": 0,
            "verified_row_count": 0,
            "usable_literature_count": 0,
            "filtered_reason_counts": {
                "missing_doi": 0,
                "missing_quote": 0,
                "demo": 0,
                "non_verified": 0,
                "trait_mismatch": 0,
            },
            "records": [],
        }

    rows = _read_tsv(file_path)
    filtered_reason_counts = {
        "missing_doi": 0,
        "missing_quote": 0,
        "demo": 0,
        "non_verified": 0,
        "trait_mismatch": 0,
    }
    records: list[dict[str, Any]] = []
    verified_row_count = 0
    normalized_trait = trait.strip().lower()

    for index, row in enumerate(rows, start=1):
        if _is_rejected_or_demo_literature_row(row):
            status = _literature_status(row)
            if status in {"demo"} or str(row.get("is_demo") or "").strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
            }:
                filtered_reason_counts["demo"] += 1
            else:
                filtered_reason_counts["non_verified"] += 1
            continue
        # DOI读取和引用原句读取
        doi = _first_present(row, ["doi", "DOI"])
        quoted_sentence = _first_present(
            row,
            ["quoted_sentence", "quote", "original_sentence", "sentence"],
        )

        if not doi:
            filtered_reason_counts["missing_doi"] += 1
            continue
        if not quoted_sentence:
            filtered_reason_counts["missing_quote"] += 1
            continue

        verified_row_count += 1

        # 即使 trait 不完全匹配，只要 DOI 和 quoted_sentence 存在，当前仍然会加入 records。
        row_trait = _first_present(row, ["trait", "target_trait"]).lower()
        if normalized_trait and row_trait and normalized_trait not in row_trait:
            filtered_reason_counts["trait_mismatch"] += 1

        records.append(
            {
                "evidence_id": row.get("evidence_id") or f"L{index}",
                "doi": doi,
                "quoted_sentence": quoted_sentence,
                "trait": _first_present(row, ["trait", "target_trait"]),
                "gene_id": _first_present(row, ["gene_id", "target_gene", "gene"]),
                "title": _first_present(row, ["title", "paper_title"]),
                "source_file": str(path),
                "relevance_level": _first_present(row, ["relevance_level", "relevance"]),
            }
        )

    diagnostics = {
        "literature_evidence_path": str(path),
        "literature_path_exists": file_path.exists() and file_path.is_file(),
        "literature_row_count": len(rows),
        "verified_row_count": verified_row_count,
        "usable_literature_count": len(records),
        "filtered_reason_counts": filtered_reason_counts,
        "records": records,
    }
    logger.info(
        "Literature evidence diagnostics: path=%s exists=%s rows=%s verified=%s usable=%s filtered=%s",
        diagnostics["literature_evidence_path"],
        diagnostics["literature_path_exists"],
        diagnostics["literature_row_count"],
        diagnostics["verified_row_count"],
        diagnostics["usable_literature_count"],
        diagnostics["filtered_reason_counts"],
    )
    return diagnostics


# 读取 verified_literature_evidence.tsv，并把它转成 Evidence Pack 需要的 literature_records
def read_literature_records(path: str | Path) -> list[dict[str, Any]]:
    """从 verified_literature_evidence.tsv 读取已验证文献证据。

    只保留同时具备 DOI 和 quoted_sentence 的记录。
    demo / pending / rejected 记录不会进入 Evidence Pack。
    """

    return collect_literature_evidence_diagnostics(path)["records"]


# 把 Context 和 Evidence Pack 连接起来 这一阶段最重要的函数
# 它把 Context 变成 Evidence Pack。
def build_omics_evidence_pack_from_context(
    context: OmicsBreedingAnalysisContext,
) -> dict[str, Any]:
    """根据 Context 中的路径读取证据，并构建 Evidence Pack。"""
    input_diagnostics = collect_input_file_diagnostics(context)
    transcriptome_path = input_diagnostics["transcriptome_result_path"]
    literature_path = input_diagnostics["literature_evidence_path"]
    metabolome_path = input_diagnostics["metabolome_path"]

    # 从 Context 读取转录组文件路径
    transcriptome_records = read_transcriptome_records(transcriptome_path)
    # 从 Context 读取文献证据文件路径
    literature_diagnostics = collect_literature_evidence_diagnostics(
        literature_path,
        trait=context.trait,
    )
    literature_records = literature_diagnostics["records"]
    smoke_gene_ids_path = Path(input_diagnostics["data_dir"]) / "smoke_gene_ids.txt"
    smoke_gene_ids = _read_smoke_gene_ids(smoke_gene_ids_path)
    # 代谢组目前只做“文件存在性摘要”
    metabolome_context: list[dict[str, Any]] = []
    if input_diagnostics["metabolome_path_exists"]:
        metabolome_preview = _read_text_preview(
            input_diagnostics["metabolome_path"],
            max_rows=MAX_METABOLOME_PREVIEW_ROWS,
            max_chars=MAX_METABOLOME_PREVIEW_CHARS,
        )
        metabolome_context.append(
            {
                "evidence_id": "M1",
                "summary": (
                    f"检测到代谢组结果文件：{input_diagnostics['metabolome_path']}。"
                    "以下为提供给 LLM 的表格预览，属于输入上下文，不代表已完成专业代谢组统计分析。"
                ),
                "source_file": input_diagnostics["metabolome_path"],
                "preview_text": metabolome_preview["preview_text"],
                "preview_rows": metabolome_preview["preview_rows"],
                "preview_row_count": metabolome_preview["row_count"],
                "truncated": metabolome_preview["truncated"],
                "note": "metabolome table preview supplied to LLM for analysis",
            }
        )
        input_diagnostics["metabolome_preview_available"] = bool(
            metabolome_preview["preview_text"]
        )
        input_diagnostics["metabolome_preview_row_count"] = metabolome_preview["row_count"]
        input_diagnostics["metabolome_preview_truncated"] = metabolome_preview["truncated"]
    else:
        input_diagnostics["metabolome_preview_available"] = False
        input_diagnostics["metabolome_preview_row_count"] = 0
        input_diagnostics["metabolome_preview_truncated"] = False

    genome_context: list[dict[str, Any]] = []
    if input_diagnostics["evidence_level"] == "default_smoke_data" and smoke_gene_ids:
        primary_gene = (
            "Si9g037800"
            if "Si9g037800" in smoke_gene_ids
            else smoke_gene_ids[0]
        )
        preview = ", ".join(smoke_gene_ids[:6])
        genome_context.append(
            {
                "evidence_id": "G1",
                "summary": (
                    "当前默认 smoke 数据包围绕局部基因区域开展演示，"
                    f"包含 {primary_gene} 在内的 {len(smoke_gene_ids)} 个基因。"
                    "该信息仅作为上下文线索，不代表已经读取到真实 DEG 结果。"
                ),
                "source_file": str(smoke_gene_ids_path),
                "primary_gene_id": primary_gene,
                "gene_ids_preview": preview,
            }
        )

    # 构建 Evidence Pack
    evidence_pack = build_omics_evidence_pack(
        trait=context.trait,
        question=context.question,
        transcriptome_records=transcriptome_records,
        literature_records=literature_records,
        metabolome_context=metabolome_context,
        genome_context=genome_context,
    )
    # 写入 debug 信息
    evidence_pack["debug"] = {
        "inputs": input_diagnostics,
        "literature": {
            key: value
            for key, value in literature_diagnostics.items()
            if key != "records"
        },
        "smoke_context": {
            "gene_ids_path": str(smoke_gene_ids_path),
            "gene_count": len(smoke_gene_ids),
            "primary_gene_id": (
                "Si9g037800"
                if "Si9g037800" in smoke_gene_ids
                else (smoke_gene_ids[0] if smoke_gene_ids else "")
            ),
            "gene_ids_preview": smoke_gene_ids[:12],
        },
    }
    return evidence_pack
