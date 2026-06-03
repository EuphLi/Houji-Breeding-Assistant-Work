from __future__ import annotations

import csv
import gzip
import json
import logging
from pathlib import Path
from typing import Any

from .context import OmicsBreedingAnalysisContext
from .evidence_pack import build_omics_evidence_pack
from .merge_gene_annotation import merge_gene_annotation_files

"""
所属业务层次
证据读取层 / 文件适配层 / 原始结果转结构化证据层

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
TRAIT_RELATED_METABOLOME_KEYWORDS = (
    "黄酮",
    "flavonoid",
    "phenylpropanoid",
    "酚酸",
    "苯丙烷",
    "l-酪胺",
    "tyramine",
)

ANNOTATION_FILE_SUFFIXES = {".txt", ".tsv", ".csv", ".gz"}
ANNOTATION_FILENAME_KEYWORDS = (
    "annotation",
    "annot",
    "function",
    "functional",
)
GENE_ID_ALIASES = (
    "gene_id",
    "geneid",
    "gene",
    "gene_name",
    "locus_id",
    "locus",
    "id",
)
TRANSCRIPT_ID_ALIASES = (
    "mrna_id",
    "mRNA_id",
    "transcript_id",
    "transcript_ids",
    "isoform_id",
    "mrna",
    "transcript",
)
FUNCTION_FIELD_ALIASES = (
    "NR_annotation",
    "nr_annotation",
    "annotation",
    "description",
    "function",
    "functional_annotation",
    "SwissProt_annotation",
    "TrEMBL_annotation",
    "KOG_defination",
    "KOG_definition",
    "KO",
    "KEGG_gene_name",
    "KEGG_Pathway",
    "KeGG_Pathway",
    "Pathway_defination",
    "Pathway_definition",
    "GO_IDs",
    "GO_annotation",
    "Pfam_Description",
    "Pfam",
    "InterPro_Description",
    "InterPro",
    "TF_id",
)
FUNCTION_FIELD_KEYWORDS = (
    "annotation",
    "description",
    "function",
    "swissprot",
    "trembl",
    "kegg",
    "pathway",
    "go",
    "pfam",
    "interpro",
    "kog",
    "ko",
    "domain",
    "tf",
)
PATHWAY_FIELD_KEYWORDS = ("pathway", "kegg", "ko")
GO_FIELD_KEYWORDS = ("go",)
DOMAIN_FIELD_KEYWORDS = ("pfam", "interpro", "domain", "kog", "tf")
ANNOTATION_NOISE_SUBSTRINGS = (
    "http",
    "https",
    "www",
    "genome.jp",
    "dbget-bin",
    "www_bget",
    "url 片段",
)
ANNOTATION_NOISE_EXACT = {
    "[x]",
    "x",
    "-",
    "--",
    "na",
    "n/a",
    "none",
}
QUERY_PLAN_SPECIES_TERMS = ("Setaria italica", "foxtail millet")
PFAM_FIELD_PRIORITY = ("pfam", "Pfam_Description", "PFAM", "pfam_description")
TRAIT_SYNONYM_MAP = {
    "黄酮": ["flavonoid", "flavonoid biosynthesis", "chalcone", "chalcone isomerase", "phenylpropanoid"],
    "flavonoid": ["黄酮", "flavonoid biosynthesis", "chalcone", "chalcone isomerase", "phenylpropanoid"],
    "抗旱": ["drought", "abiotic stress", "water deficit", "dehydration"],
    "drought": ["抗旱", "abiotic stress", "water deficit", "dehydration"],
    "产量": ["yield", "grain yield", "grain weight", "panicle"],
    "高产": ["yield", "grain yield", "grain weight", "panicle"],
    "yield": ["产量", "高产", "grain yield", "grain weight", "panicle"],
}

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


def _normalize_header_key(value: str) -> str:
    text = str(value or "").replace("\ufeff", "").strip().lower()
    return "".join(ch for ch in text if ch.isalnum())


def _split_multi_value(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        return []
    parts = []
    for item in text.replace("；", ";").replace("，", ",").replace("|", ";").split(";"):
        for sub_item in item.split(","):
            normalized = sub_item.strip()
            if normalized:
                parts.append(normalized)
    return _deduplicate_strings(parts)


def _deduplicate_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _open_text(path: Path):
    if path.suffix.lower() == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", errors="replace")
    return path.open("r", encoding="utf-8-sig", errors="replace")


def _detect_delimiter(path: Path) -> str:
    if path.suffix.lower() == ".csv":
        return ","
    with _open_text(path) as handle:
        sample = handle.readline()
    return "," if sample.count(",") > sample.count("\t") else "\t"


def _read_delimited(path: str | Path) -> list[dict[str, str]]:
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return []
    delimiter = _detect_delimiter(file_path)
    with _open_text(file_path) as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        return [
            {str(key or "").replace("\ufeff", "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def _find_header_name(headers: list[str], aliases: tuple[str, ...]) -> str:
    normalized_aliases = {_normalize_header_key(alias) for alias in aliases}
    for header in headers:
        if _normalize_header_key(header) in normalized_aliases:
            return header
    for header in headers:
        normalized = _normalize_header_key(header)
        if any(alias and alias in normalized for alias in normalized_aliases):
            return header
    return ""


def _is_function_annotation_column(header: str) -> bool:
    normalized = _normalize_header_key(header)
    alias_keys = {_normalize_header_key(alias) for alias in FUNCTION_FIELD_ALIASES}
    return normalized in alias_keys or any(keyword in normalized for keyword in FUNCTION_FIELD_KEYWORDS)


def _classify_annotation_fields(headers: list[str]) -> list[str]:
    return [header for header in headers if _is_function_annotation_column(header)]


def _field_matches_keywords(header: str, keywords: tuple[str, ...]) -> bool:
    normalized = _normalize_header_key(header)
    return any(keyword in normalized for keyword in keywords)


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
    discovered["annotation_path"] = _discover_annotation_file(upload_files)
    discovered["rnaseq_read_paths"] = [
        str(path.resolve())
        for path in upload_files
        if path.name.lower().endswith((".fq", ".fastq", ".fq.gz", ".fastq.gz"))
    ]
    return discovered


def _has_supported_annotation_suffix(path: Path) -> bool:
    if path.suffix.lower() == ".gz":
        return Path(path.stem).suffix.lower() in {".txt", ".tsv", ".csv"} or path.suffix.lower() in ANNOTATION_FILE_SUFFIXES
    return path.suffix.lower() in ANNOTATION_FILE_SUFFIXES


def _looks_like_annotation_filename(path: Path) -> bool:
    name = path.name.lower()
    return any(keyword in name for keyword in ANNOTATION_FILENAME_KEYWORDS)


def _inspect_annotation_table(path: Path) -> dict[str, Any]:
    rows = _read_delimited(path)
    headers = list(rows[0].keys()) if rows else []
    gene_column = _find_header_name(headers, GENE_ID_ALIASES)
    transcript_column = _find_header_name(headers, TRANSCRIPT_ID_ALIASES)
    annotation_columns = _classify_annotation_fields(headers)
    return {
        "rows": rows,
        "headers": headers,
        "gene_column": gene_column,
        "transcript_column": transcript_column,
        "annotation_columns": annotation_columns,
    }


def _discover_annotation_file(upload_files: list[Path]) -> str:
    candidates = [
        path
        for path in upload_files
        if _has_supported_annotation_suffix(path) and _looks_like_annotation_filename(path)
    ]
    for path in candidates:
        try:
            inspection = _inspect_annotation_table(path)
        except Exception:  # noqa: BLE001
            continue
        if inspection["gene_column"] and inspection["annotation_columns"]:
            return str(path.resolve())
    return ""


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


def _find_header_index(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized_headers = [str(header or "").strip().lower() for header in headers]
    for alias in aliases:
        if alias in normalized_headers:
            return normalized_headers.index(alias)
    for index, header in enumerate(normalized_headers):
        if any(alias in header for alias in aliases):
            return index
    return None


def _is_significant_metabolite(row: dict[str, str]) -> bool:
    record_type = _first_present(row, ["type", "Type", "regulation", "direction", "sig"]).lower()
    if record_type in {"up", "down", "sig", "significant"}:
        return True

    fdr_raw = _first_present(row, ["fdr", "FDR", "padj", "qvalue", "q_value", "adj_p_val"])
    log2fc_raw = _first_present(row, ["log2fc", "Log2FC", "logFC", "fold_change"])
    if fdr_raw:
        try:
            fdr_value = float(fdr_raw)
            log2fc_value = abs(float(log2fc_raw)) if log2fc_raw else 0.0
            if fdr_value <= 0.05 and (log2fc_value >= 0.0):
                return True
        except ValueError:
            pass
    return False


def _metabolite_priority(row: dict[str, str]) -> tuple[int, int, float]:
    row_text = " ".join(str(value or "") for value in row.values()).lower()
    significant_rank = 0 if _is_significant_metabolite(row) else 1
    trait_rank = 0 if any(keyword in row_text for keyword in TRAIT_RELATED_METABOLOME_KEYWORDS) else 1
    fdr_value = 1.0
    raw = _first_present(row, ["fdr", "FDR", "padj", "qvalue", "q_value", "adj_p_val"])
    if raw:
        try:
            fdr_value = float(raw)
        except ValueError:
            pass
    return (significant_rank, trait_rank, fdr_value)


def _summarize_metabolome_preview(path: str | Path, preview_rows: list[str]) -> dict[str, Any]:
    file_rows = _read_tsv(path)
    total_records = len(file_rows)
    if not file_rows and preview_rows:
        headers = [cell.strip() for cell in preview_rows[0].split("\t")]
        parsed_rows = [
            [cell.strip() for cell in line.split("\t")]
            for line in preview_rows[1:]
            if str(line).strip()
        ]
        file_rows = [
            {headers[index]: row[index] if index < len(row) else "" for index in range(len(headers))}
            for row in parsed_rows
        ]
        total_records = len(file_rows)

    significant_records = [row for row in file_rows if _is_significant_metabolite(row)]
    ranked_rows = sorted(file_rows, key=_metabolite_priority)

    top_metabolites: list[dict[str, str]] = []
    if file_rows:
        sample_headers = list(file_rows[0].keys())
        id_index = _find_header_index(sample_headers, ("compound_id", "feature_id", "peak_id", "id"))
        name_index = _find_header_index(sample_headers, ("metabolite", "compound_name", "compound", "name"))
        class_index = _find_header_index(sample_headers, ("class", "subclass", "superclass", "category"))
        log2fc_index = _find_header_index(sample_headers, ("log2fc", "logfc", "fold_change"))
        fdr_index = _find_header_index(sample_headers, ("fdr", "padj", "qvalue", "adj_p_val"))
        type_index = _find_header_index(sample_headers, ("type", "regulation", "direction", "sig"))

        for row in ranked_rows[:5]:
            keys = sample_headers
            compound_id = row.get(keys[id_index], "") if id_index is not None and id_index < len(keys) else ""
            metabolite_name = row.get(keys[name_index], "") if name_index is not None and name_index < len(keys) else ""
            metabolite_class = row.get(keys[class_index], "") if class_index is not None and class_index < len(keys) else ""
            log2fc = row.get(keys[log2fc_index], "") if log2fc_index is not None and log2fc_index < len(keys) else ""
            fdr = row.get(keys[fdr_index], "") if fdr_index is not None and fdr_index < len(keys) else ""
            record_type = row.get(keys[type_index], "") if type_index is not None and type_index < len(keys) else ""
            top_metabolites.append(
                {
                    "compound_id": str(compound_id or "").strip(),
                    "name": str(metabolite_name or "").strip() or str(compound_id or "").strip(),
                    "class": str(metabolite_class or "").strip() or "未提供",
                    "log2fc": str(log2fc or "").strip() or "N/A",
                    "fdr": str(fdr or "").strip() or "N/A",
                    "type": str(record_type or "").strip() or "unknown",
                }
            )

    note = ""
    top_text = " ".join(
        f"{item.get('compound_id')} {item.get('name')} {item.get('class')}" for item in top_metabolites
    ).lower()
    if not any(keyword in top_text for keyword in TRAIT_RELATED_METABOLOME_KEYWORDS):
        note = "未检测到典型黄酮骨架代谢物显著差异；当前代谢组线索主要来自苯丙烷相关分支代谢物或其他相关代谢物。"

    return {
        "total_record_count": total_records,
        "significant_record_count": len(significant_records),
        "top_metabolites": top_metabolites,
        "trait_relevance_note": note,
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

        annotation = _first_present(
            row,
            [
                "annotation",
                "description",
                "functional_annotation",
                "gene_annotation",
                "product",
                "gene_product",
            ],
        )
        if annotation:
            record["annotation"] = annotation

        transcript_ids = _first_present(
            row,
            [
                "transcript_ids",
                "transcript_id",
                "mRNA_id",
                "mrna_id",
                "isoform_id",
                "mrna",
                "transcript",
            ],
        )
        if transcript_ids:
            record["transcript_ids"] = transcript_ids

        records.append(record)

    return records


def _trait_terms(trait: str) -> list[str]:
    terms = _split_multi_value(trait)
    normalized_trait = str(trait or "").lower()
    for key, synonyms in TRAIT_SYNONYM_MAP.items():
        if key.lower() in normalized_trait:
            terms.extend(synonyms)
    return _deduplicate_strings(terms)


def _extract_annotation_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        terms.extend(_split_multi_value(text))
        for token in re_split_annotation_text(text):
            if 3 <= len(token) <= 80:
                terms.append(token)
    cleaned_terms: list[str] = []
    for term in _deduplicate_strings(terms):
        cleaned = _clean_annotation_term(term)
        if cleaned:
            cleaned_terms.append(cleaned)
    return cleaned_terms[:30]


def _clean_annotation_term(term: Any) -> str:
    text = str(term or "").strip()
    if not text:
        return ""
    lower = text.lower()
    if lower in ANNOTATION_NOISE_EXACT:
        return ""
    if any(noise in lower for noise in ANNOTATION_NOISE_SUBSTRINGS):
        return ""
    if "unnamed protein" in lower or "uncharacterized protein" in lower:
        return ""
    return text


def _clean_pfam_keyword(term: Any) -> str:
    text = _clean_annotation_term(term)
    if not text:
        return ""
    lower = text.lower()
    if lower in {"na", "n/a", "none", "-", "--"}:
        return ""
    if text in {"[X]", "X"}:
        return ""
    if lower.startswith(("http://", "https://", "www.")) or "://" in lower:
        return ""
    return text


def re_split_annotation_text(text: str) -> list[str]:
    separators = [";", "|", ",", "/", "(", ")", "[", "]"]
    normalized = str(text or "")
    for separator in separators:
        normalized = normalized.replace(separator, "\t")
    return [item.strip() for item in normalized.split("\t") if item.strip()]


def _extract_keywords_from_cell(value: Any) -> list[str]:
    terms: list[str] = []
    for item in _split_multi_value(value):
        cleaned = _clean_pfam_keyword(item)
        if cleaned:
            terms.append(cleaned)
    for item in re_split_annotation_text(str(value or "")):
        cleaned = _clean_pfam_keyword(item)
        if cleaned:
            terms.append(cleaned)
    return _deduplicate_strings(terms)


def _query_trait_terms(trait: str) -> list[str]:
    terms = _trait_terms(trait)
    english_terms = [term for term in terms if any(ch.isascii() and ch.isalpha() for ch in term)]
    preferred = english_terms[:3] or terms[:3]
    if preferred:
        return _deduplicate_strings(preferred)
    raw = str(trait or "").strip()
    return [raw] if raw else []


def _score_trait_relevance(
    annotation_values: list[str],
    *,
    trait: str,
) -> tuple[list[str], int, str]:
    terms = _trait_terms(trait)
    haystack = " ".join(annotation_values).lower()
    matched = [term for term in terms if term and term.lower() in haystack]
    score = len(matched)
    if score >= 2:
        level = "high"
    elif score == 1:
        level = "medium"
    else:
        level = "none"
    return _deduplicate_strings(matched), score, level


def _annotation_output_path(transcriptome_path: str | Path, context: OmicsBreedingAnalysisContext) -> Path:
    path = Path(transcriptome_path)
    if path.name:
        return path.parent / "significant_de_genes.annotated.tsv"
    output_parent = Path(context.evidence_pack_output_path).expanduser().resolve().parent
    return output_parent / "transcriptome_deg" / "significant_de_genes.annotated.tsv"


def _query_plan_output_path(annotated_transcriptome_path: str | Path, context: OmicsBreedingAnalysisContext) -> Path:
    path = Path(annotated_transcriptome_path)
    if path.name:
        return path.parent / "literature_query_plan.jsonl"
    output_parent = Path(context.evidence_pack_output_path).expanduser().resolve().parent
    return output_parent / "transcriptome_deg" / "literature_query_plan.jsonl"


def _aggregate_annotation_records(
    rows: list[dict[str, str]],
    *,
    gene_column: str,
    transcript_column: str,
    annotation_columns: list[str],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        gene_id = str(row.get(gene_column) or "").strip()
        if not gene_id:
            continue
        entry = grouped.setdefault(
            gene_id,
            {
                "gene_id": gene_id,
                "transcript_ids": [],
                "records": [],
                "annotation_fields": {column: [] for column in annotation_columns},
            },
        )
        transcript_id = str(row.get(transcript_column) or "").strip() if transcript_column else ""
        if transcript_id:
            entry["transcript_ids"].extend(_split_multi_value(transcript_id))
        entry["records"].append(row)
        for column in annotation_columns:
            value = str(row.get(column) or "").strip()
            if value:
                entry["annotation_fields"].setdefault(column, []).append(value)

    for entry in grouped.values():
        entry["transcript_ids"] = _deduplicate_strings(entry["transcript_ids"])
        entry["annotation_fields"] = {
            column: _deduplicate_strings(values)
            for column, values in entry["annotation_fields"].items()
            if values
        }
    return grouped


def _matched_by(deg_record: dict[str, Any], annotation_entry: dict[str, Any]) -> tuple[str, int]:
    deg_transcripts = set(_split_multi_value(deg_record.get("transcript_ids")))
    annotation_transcripts = set(annotation_entry.get("transcript_ids") or [])
    matched_transcripts = deg_transcripts.intersection(annotation_transcripts)
    if deg_transcripts and annotation_transcripts and matched_transcripts:
        return "gene_id_and_transcript_id", len(matched_transcripts)
    return "gene_id", 0


def _build_candidate_annotation(
    deg_record: dict[str, Any],
    annotation_entry: dict[str, Any],
    *,
    trait: str,
) -> dict[str, Any]:
    annotation_fields = {
        column: " | ".join(values)
        for column, values in (annotation_entry.get("annotation_fields") or {}).items()
    }
    all_values = list(annotation_fields.values())
    pathway_terms = _extract_annotation_terms(
        [
            value
            for column, value in annotation_fields.items()
            if _field_matches_keywords(column, PATHWAY_FIELD_KEYWORDS)
        ]
    )
    go_terms = _extract_annotation_terms(
        [
            value
            for column, value in annotation_fields.items()
            if _field_matches_keywords(column, GO_FIELD_KEYWORDS)
        ]
    )
    domain_terms = _extract_annotation_terms(
        [
            value
            for column, value in annotation_fields.items()
            if _field_matches_keywords(column, DOMAIN_FIELD_KEYWORDS)
        ]
    )
    normalized_function_terms = _extract_annotation_terms(all_values)
    trait_relevance_terms, trait_relevance_score, trait_relevance_level = _score_trait_relevance(
        all_values,
        trait=trait,
    )
    matched_by, matched_transcript_count = _matched_by(deg_record, annotation_entry)
    gene_id = str(deg_record.get("gene_id") or "").strip()
    query_terms = _deduplicate_strings(
        [
            gene_id,
            trait,
            "Setaria italica",
            *trait_relevance_terms,
            *pathway_terms[:8],
            *go_terms[:8],
            *domain_terms[:8],
            *normalized_function_terms[:8],
        ]
    )
    return {
        "gene_id": gene_id,
        "transcript_ids": annotation_entry.get("transcript_ids") or [],
        "matched_by": matched_by,
        "annotation_fields": annotation_fields,
        "normalized_function_terms": normalized_function_terms,
        "pathway_terms": pathway_terms,
        "go_terms": go_terms,
        "domain_terms": domain_terms,
        "trait_relevance_terms": trait_relevance_terms,
        "trait_relevance_score": trait_relevance_score,
        "trait_relevance_level": trait_relevance_level,
        "matched_transcript_count": matched_transcript_count,
        "gene_level_terms": _deduplicate_strings([gene_id, *normalized_function_terms[:8]]),
        "trait_terms": _trait_terms(trait),
        "pubmed_query_terms": query_terms,
    }


def _write_annotated_transcriptome(
    transcriptome_path: str | Path,
    output_path: Path,
    *,
    annotation_columns: list[str],
    candidate_annotations_by_gene: dict[str, dict[str, Any]],
) -> str:
    rows = _read_delimited(transcriptome_path)
    if not rows:
        return ""
    fieldnames = list(rows[0].keys())
    append_columns = [column for column in annotation_columns if column not in fieldnames]
    if "annotation_matched_by" not in fieldnames:
        append_columns.append("annotation_matched_by")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*fieldnames, *append_columns], delimiter="\t")
        writer.writeheader()
        for row in rows:
            gene_id = _infer_gene_id(row)
            candidate = candidate_annotations_by_gene.get(gene_id) or {}
            merged = dict(row)
            annotation_fields = candidate.get("annotation_fields") or {}
            for column in annotation_columns:
                if column not in fieldnames:
                    merged[column] = str(annotation_fields.get(column) or "")
            merged["annotation_matched_by"] = str(candidate.get("matched_by") or "unmatched")
            writer.writerow(merged)
    return str(output_path)


def _extract_pfam_keywords_from_annotated_rows(
    rows: list[dict[str, str]],
    *,
    candidate_annotations: list[dict[str, Any]],
) -> tuple[list[str], dict[str, list[str]]]:
    pfam_keywords_by_gene: dict[str, list[str]] = {}
    for row in rows:
        gene_id = _infer_gene_id(row)
        if not gene_id:
            continue
        pfam_terms: list[str] = []
        for field_name in PFAM_FIELD_PRIORITY:
            if field_name not in row:
                continue
            pfam_terms = _extract_keywords_from_cell(row.get(field_name))
            if pfam_terms:
                break
        if not pfam_terms and "domain_terms" in row:
            pfam_terms = _extract_keywords_from_cell(row.get("domain_terms"))
        if pfam_terms:
            pfam_keywords_by_gene.setdefault(gene_id, []).extend(pfam_terms)

    if not pfam_keywords_by_gene:
        for candidate in candidate_annotations:
            gene_id = str(candidate.get("gene_id") or "").strip()
            if not gene_id:
                continue
            annotation_fields = candidate.get("annotation_fields") or {}
            pfam_terms: list[str] = []
            if isinstance(annotation_fields, dict):
                for field_name in PFAM_FIELD_PRIORITY:
                    if field_name not in annotation_fields:
                        continue
                    pfam_terms = _extract_keywords_from_cell(annotation_fields.get(field_name))
                    if pfam_terms:
                        break
            if not pfam_terms:
                pfam_terms = _deduplicate_strings(
                    [
                        cleaned
                        for item in (candidate.get("domain_terms") or [])
                        for cleaned in _extract_keywords_from_cell(item)
                    ]
                )
            if pfam_terms:
                pfam_keywords_by_gene.setdefault(gene_id, []).extend(pfam_terms)

    normalized = {
        gene_id: _deduplicate_strings(
            [_clean_pfam_keyword(term) for term in values if _clean_pfam_keyword(term)]
        )
        for gene_id, values in pfam_keywords_by_gene.items()
    }
    normalized = {gene_id: values for gene_id, values in normalized.items() if values}
    return (
        _deduplicate_strings([term for values in normalized.values() for term in values]),
        normalized,
    )


def _build_literature_query_plan(
    *,
    trait: str,
    candidate_gene_ids: list[str],
    pfam_keywords_by_gene: dict[str, list[str]],
    pathway_terms: list[str],
) -> list[dict[str, Any]]:
    query_entries: list[dict[str, Any]] = []
    seen_queries: set[str] = set()
    counters = {"high": 0, "medium": 0, "low": 0, "fallback": 0}
    trait_terms = _query_trait_terms(trait)

    def add_entry(
        *,
        query_type: str,
        priority: str,
        query: str,
        gene_id: str = "",
        pfam_keyword: str = "",
        old_keywords: list[str] | None = None,
    ) -> None:
        normalized_query = " ".join(str(query or "").split())
        if not normalized_query or normalized_query in seen_queries:
            return
        seen_queries.add(normalized_query)
        counters[priority] = counters.get(priority, 0) + 1
        prefix = {
            "high": "PFAM_HIGH",
            "medium": "PFAM_MED",
            "low": "PFAM_LOW",
            "fallback": "PFAM_FALLBACK",
        }[priority]
        query_entries.append(
            {
                "query_id": f"{prefix}_{counters[priority]:03d}",
                "query_type": query_type,
                "priority": priority,
                "gene_id": gene_id,
                "pfam_keyword": pfam_keyword,
                "old_keywords": old_keywords or [],
                "query": normalized_query,
                "source": "annotated_transcriptome_pfam",
                "is_evidence": False,
            }
        )

    for gene_id in candidate_gene_ids:
        for pfam_keyword in pfam_keywords_by_gene.get(gene_id) or []:
            for species in QUERY_PLAN_SPECIES_TERMS:
                for trait_term in trait_terms[:2]:
                    add_entry(
                        query_type="species_pfam_trait",
                        priority="high",
                        gene_id=gene_id,
                        pfam_keyword=pfam_keyword,
                        old_keywords=[species, trait_term],
                        query=f'{species} "{pfam_keyword}" {trait_term}',
                    )
                for pathway_term in pathway_terms[:4]:
                    add_entry(
                        query_type="species_pfam_pathway",
                        priority="high",
                        gene_id=gene_id,
                        pfam_keyword=pfam_keyword,
                        old_keywords=[species, pathway_term],
                        query=f'{species} "{pfam_keyword}" "{pathway_term}"',
                    )
                add_entry(
                    query_type="species_pfam",
                    priority="medium",
                    gene_id=gene_id,
                    pfam_keyword=pfam_keyword,
                    old_keywords=[species],
                    query=f'{species} "{pfam_keyword}"',
                )
            for trait_term in trait_terms[:2]:
                add_entry(
                    query_type="pfam_trait",
                    priority="medium",
                    gene_id=gene_id,
                    pfam_keyword=pfam_keyword,
                    old_keywords=[trait_term],
                    query=f'"{pfam_keyword}" {trait_term}',
                )
            add_entry(
                query_type="gene_pfam",
                priority="low",
                gene_id=gene_id,
                pfam_keyword=pfam_keyword,
                old_keywords=[gene_id],
                query=f'{gene_id} "{pfam_keyword}"',
            )

    for trait_term in trait_terms[:2]:
        add_entry(
            query_type="trait_only",
            priority="fallback",
            old_keywords=[trait_term],
            query=trait_term,
        )
        for gene_id in candidate_gene_ids[:6]:
            add_entry(
                query_type="target_gene_trait",
                priority="fallback",
                gene_id=gene_id,
                old_keywords=[gene_id, trait_term],
                query=f"{gene_id} {trait_term}",
            )
        for species in QUERY_PLAN_SPECIES_TERMS:
            add_entry(
                query_type="species_trait",
                priority="fallback",
                old_keywords=[species, trait_term],
                query=f"{species} {trait_term}",
            )

    return query_entries


def _write_query_plan_jsonl(path: Path, query_plan: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for entry in query_plan:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return str(path)


def collect_annotation_evidence(
    *,
    context: OmicsBreedingAnalysisContext,
    transcriptome_records: list[dict[str, Any]],
    input_diagnostics: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    annotation_path = input_diagnostics.get("annotation_path", "")
    annotation_exists = bool(input_diagnostics.get("annotation_path_exists"))
    transcriptome_path = input_diagnostics.get("transcriptome_result_path", "")
    transcriptome_exists = bool(transcriptome_path) and Path(transcriptome_path).is_file()
    base_metadata = {
        "annotation_file": annotation_path,
        "annotation_file_name": Path(annotation_path).name if annotation_path else "",
        "annotation_path_exists": annotation_exists,
        "annotated_transcriptome_path": "",
        "annotation_merge_status": "skipped_missing_annotation",
        "annotation_merge_warning": "",
        "annotation_merge_method": "按 gene_id 将 DEG 结果与功能注释文件对映",
        "annotation_merge_total_count": 0,
        "annotation_merge_matched_count": 0,
        "annotation_merge_unmatched_count": 0,
        "annotation_merge_duplicate_count": 0,
        "annotated_transcriptome_read_by_llm": False,
        "pfam_literature_keywords": [],
        "literature_query_plan_path": "",
        "literature_query_plan_count": 0,
        "literature_query_plan_source": "annotated_transcriptome_pfam",
        "literature_query_plan_preview": [],
        "annotation_gene_match_count": 0,
        "annotation_unmatched_gene_count": len(transcriptome_records),
        "annotation_duplicate_gene_id_count": 0,
        "annotation_isoform_count": 0,
        "annotation_candidate_gene_ids": [],
        "trait_relevant_annotation_gene_ids": [],
        "candidate_annotations": [],
        "pathway_summary": [],
        "pubmed_query_terms": [],
        "recognized_columns": {},
    }

    if annotation_exists and transcriptome_exists:
        merge_result = merge_gene_annotation_files(
            transcriptome_path,
            annotation_path,
            _annotation_output_path(transcriptome_path, context),
        )
        base_metadata.update(
            {
                "annotated_transcriptome_path": str(merge_result.get("output_file") or ""),
                "annotation_merge_status": str(merge_result.get("status") or ""),
                "annotation_merge_warning": str(merge_result.get("warning") or ""),
                "annotation_merge_total_count": int(merge_result.get("total_count") or 0),
                "annotation_merge_matched_count": int(merge_result.get("matched_count") or 0),
                "annotation_merge_unmatched_count": int(merge_result.get("unmatched_count") or 0),
                "annotation_merge_duplicate_count": int(merge_result.get("duplicate_count") or 0),
            }
        )
    elif annotation_exists:
        base_metadata["annotation_merge_status"] = "skipped_missing_transcriptome"
        base_metadata["annotation_merge_warning"] = "Transcriptome DEG file is unavailable for annotation merge."

    if base_metadata["annotation_merge_status"] in {
        "annotation_missing_gene_id",
        "transcriptome_missing_gene_id",
        "annotation_empty",
        "transcriptome_empty",
    }:
        return [], base_metadata

    if not annotation_exists or not transcriptome_records:
        return [], base_metadata

    inspection = _inspect_annotation_table(Path(annotation_path))
    rows = inspection["rows"]
    gene_column = inspection["gene_column"]
    transcript_column = inspection["transcript_column"]
    annotation_columns = inspection["annotation_columns"]
    base_metadata["recognized_columns"] = {
        "gene_id": gene_column,
        "transcript_id": transcript_column,
        "annotation_fields": annotation_columns,
    }
    if not rows or not gene_column or not annotation_columns:
        return [], base_metadata

    grouped = _aggregate_annotation_records(
        rows,
        gene_column=gene_column,
        transcript_column=transcript_column,
        annotation_columns=annotation_columns,
    )
    duplicate_gene_id_count = sum(1 for entry in grouped.values() if len(entry.get("records") or []) > 1)
    isoform_count = sum(len(entry.get("transcript_ids") or []) for entry in grouped.values())
    candidate_annotations: list[dict[str, Any]] = []
    unmatched_gene_ids: list[str] = []
    matched_transcript_count = 0
    for deg_record in transcriptome_records:
        gene_id = str(deg_record.get("gene_id") or "").strip()
        annotation_entry = grouped.get(gene_id)
        if not annotation_entry:
            unmatched_gene_ids.append(gene_id)
            continue
        candidate = _build_candidate_annotation(
            deg_record,
            annotation_entry,
            trait=context.trait,
        )
        matched_transcript_count += int(candidate.get("matched_transcript_count") or 0)
        candidate_annotations.append(candidate)

    pathway_summary = _deduplicate_strings(
        [
            term
            for item in candidate_annotations
            for term in (item.get("pathway_terms") or [])
        ]
    )[:30]
    pubmed_query_terms = _deduplicate_strings(
        [
            term
            for item in candidate_annotations
            for term in (item.get("pubmed_query_terms") or [])
        ]
    )[:80]
    trait_relevant_gene_ids = [
        item["gene_id"]
        for item in candidate_annotations
        if int(item.get("trait_relevance_score") or 0) > 0
    ]
    query_plan_path = ""
    query_plan: list[dict[str, Any]] = []
    pfam_literature_keywords: list[str] = []
    annotated_path = str(base_metadata.get("annotated_transcriptome_path") or "").strip()
    if annotated_path and Path(annotated_path).is_file():
        pfam_literature_keywords, pfam_keywords_by_gene = _extract_pfam_keywords_from_annotated_rows(
            _read_delimited(annotated_path),
            candidate_annotations=candidate_annotations,
        )
        query_plan = _build_literature_query_plan(
            trait=context.trait,
            candidate_gene_ids=[item["gene_id"] for item in candidate_annotations],
            pfam_keywords_by_gene=pfam_keywords_by_gene,
            pathway_terms=pathway_summary,
        )
        if query_plan:
            query_plan_path = _write_query_plan_jsonl(
                _query_plan_output_path(annotated_path, context),
                query_plan,
            )
    metadata = {
        **base_metadata,
        "annotation_gene_match_count": len(candidate_annotations),
        "annotation_unmatched_gene_count": len(unmatched_gene_ids),
        "annotation_duplicate_gene_id_count": duplicate_gene_id_count,
        "annotation_isoform_count": isoform_count,
        "annotation_matched_transcript_count": matched_transcript_count,
        "annotation_candidate_gene_ids": [item["gene_id"] for item in candidate_annotations],
        "annotation_unmatched_gene_ids": unmatched_gene_ids,
        "trait_relevant_annotation_gene_ids": trait_relevant_gene_ids,
        "candidate_annotations": candidate_annotations,
        "pathway_summary": pathway_summary,
        "pubmed_query_terms": pubmed_query_terms,
        "pfam_literature_keywords": pfam_literature_keywords,
        "literature_query_plan_path": query_plan_path,
        "literature_query_plan_count": len(query_plan),
        "literature_query_plan_source": "annotated_transcriptome_pfam",
        "literature_query_plan_preview": [item["query"] for item in query_plan[:8]],
    }
    if not candidate_annotations:
        return [], metadata
    evidence = [
        {
            "evidence_id": "A1",
            "source_file": annotation_path,
            "summary": (
                f"用户上传功能注释文件按 gene_id 与 DEG 结果关联，"
                f"生成 merged annotated DEG 文件 {Path(metadata['annotated_transcriptome_path']).name or 'N/A'}，"
                f"merge total={metadata['annotation_merge_total_count']} matched={metadata['annotation_merge_matched_count']} "
                f"unmatched={metadata['annotation_merge_unmatched_count']} duplicate={metadata['annotation_merge_duplicate_count']}；"
                f"候选基因匹配 {len(candidate_annotations)} 个，未匹配 {len(unmatched_gene_ids)} 个；"
                f"已生成 Pfam 文献检索计划 {metadata['literature_query_plan_count']} 条。"
            ),
            "metadata": metadata,
        }
    ]
    return evidence, metadata


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
    annotation_evidence, annotation_metadata = collect_annotation_evidence(
        context=context,
        transcriptome_records=transcriptome_records,
        input_diagnostics=input_diagnostics,
    )
    if annotation_metadata.get("annotated_transcriptome_path"):
        input_diagnostics["annotated_transcriptome_path"] = annotation_metadata[
            "annotated_transcriptome_path"
        ]
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
        metabolome_summary = _summarize_metabolome_preview(
            input_diagnostics["metabolome_path"],
            metabolome_preview["preview_rows"],
        )
        metabolome_context.append(
            {
                "evidence_id": "M1",
                "summary": (
                    f"检测到代谢组结果文件：{input_diagnostics['metabolome_path']}。"
                    "当前仅保留代谢组摘要和 Top 关键代谢物，不展示整张原始 TSV。"
                ),
                "source_file": input_diagnostics["metabolome_path"],
                "preview_text": metabolome_preview["preview_text"],
                "preview_rows": metabolome_preview["preview_rows"],
                "preview_row_count": metabolome_preview["row_count"],
                "truncated": metabolome_preview["truncated"],
                "total_record_count": metabolome_summary["total_record_count"],
                "significant_record_count": metabolome_summary["significant_record_count"],
                "top_metabolites": metabolome_summary["top_metabolites"],
                "trait_relevance_note": metabolome_summary["trait_relevance_note"],
                "note": "metabolome summary supplied to canonical renderer",
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
    smoke_primary_gene = ""
    if input_diagnostics["evidence_level"] == "default_smoke_data" and smoke_gene_ids:
        smoke_primary_gene = smoke_gene_ids[0]
        preview = ", ".join(smoke_gene_ids[:6])
        genome_context.append(
            {
                "evidence_id": "G1",
                "summary": (
                    "当前默认 smoke 数据包围绕局部基因区域开展演示，"
                    f"包含 {smoke_primary_gene} 在内的 {len(smoke_gene_ids)} 个基因。"
                    "该信息仅作为上下文线索，不代表已经读取到真实 DEG 结果。"
                ),
                "source_file": str(smoke_gene_ids_path),
                "primary_gene_id": smoke_primary_gene,
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
        annotation_evidence=annotation_evidence,
    )
    # 写入 debug 信息
    evidence_pack["debug"] = {
        "inputs": input_diagnostics,
        "literature": {
            key: value
            for key, value in literature_diagnostics.items()
            if key != "records"
        },
        "annotation": annotation_metadata,
        "smoke_context": {
            "gene_ids_path": str(smoke_gene_ids_path),
            "gene_count": len(smoke_gene_ids),
            "primary_gene_id": smoke_primary_gene,
            "gene_ids_preview": smoke_gene_ids[:12],
        },
    }
    return evidence_pack
