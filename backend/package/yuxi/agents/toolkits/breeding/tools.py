from __future__ import annotations

"""这个文件实现的是基于 YuXi Tool Registry 的育种业务工具。
这些工具不是通用开源生信智能体，而是为当前项目封装的业务工具。
在 smoke 流程中，它们会检查 demo 输入、可选调用学长提供的 run_smoke_de_pipeline.sh、
读取 verified_literature_evidence.tsv 里的 DOI 和引用原句，并生成受 guard 约束的育种建议 Markdown。
"""

import csv
import json
import os
import re
import shlex
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from yuxi.agents.toolkits.registry import tool

"""
所属业务层次
育种工具实现层 / Tool 注册或包装层 / 固定流程工具集合
如果 omics_analysis.py 是“调度层”，那么 tools.py 就更接近“具体执行层”。
它负责把 Python 里的工具调用转成真实命令或脚本执行。

如果 omics_analysis.py 是 worker 调用的入口，那么 tools.py 可能承担两类职责之一：
1. 注册或暴露 breeding 相关工具。2. 提供具体底层函数，例如转录组 DEG 工具。

在数据流中的位置
omics_analysis.py
  ↓
tools.py 中的具体实现函数

也可能是：
tool registry
  ↓
tools.py 暴露工具定义
  ↓
worker / Tool service 找到 omics_breeding_analysis_run
"""

# FIXME 已完成 当前阶段：写死的是 smoke demo 的任务边界   或者是说目前的 tools 更准确地叫：谷子黄酮 smoke 任务专用 Tool
# TODO 已完成 未来阶段：可以抽象成多性状、多作物、多任务配置 任意作物任意性状通用育种 Tool  但是需要学长继续提供固定的 tool 流程

DEFAULT_DATA_DIR = "/mnt/yuxi-breeding-data/smoke_test_minimal"
DEFAULT_OUT_DIR = "/tmp/yuxi_runs/smoke_flavonoid_breeding_advice"
# TODO 已完成 待优化为可变或者直接删除核心候选基因初选定（即删除参考基因组 tool）
TARGET_GENE = "Si9g037800"  # 当前任务的核心候选基因，所有相关检查都围绕它：是否在 GFF 中出现 是否在功能注释中出现 是否在 significant_de_genes.tsv 中出现 最终回答是否包含 Si9g037800
# 人工核验文献证据表文件名 保存 DOI 文献标题 引用原句 证据等级 说明
VERIFIED_LITERATURE_EVIDENCE_FILE = "verified_literature_evidence.tsv"

# 统一管理 smoke 数据包中必须存在的文件名，只相当于复写配置表，做到文件名只写一遍
REQUIRED_FILES = {
    "genome_fa": "genome.fa",
    "genome_gff": "genome.gff",
    "annotation": "xiaomi_T2T_Annotation.smoke_genes.txt",
    "sample_map": "sampleName_clientId.txt",
    "metabolome": "metabolome_raw_3372.tsv",
    "pipeline_script": "run_smoke_de_pipeline.sh",
}

SAMPLE_MAP_HEADER_ALIASES = {
    "sample": ("sample", "sample_id", "samplename", "sample_name", "name"),
    "group": ("group", "treatment", "condition", "class"),
    "client_id": ("client_id", "clientid", "client", "label"),
}

'''正则表达式定义'''
# DOI快速匹配
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)
# 用来检查文本里有没有错误声称已经完成群体验证
POPULATION_VALIDATED_PATTERN = re.compile(
    r"(?:已完成|完成|completed|validated).{0,20}(?:群体|population).{0,20}(?:验证|validation)|"
    r"(?:群体|population).{0,20}(?:验证|validation).{0,20}(?:已完成|完成|completed|validated)",  # (?: ... ) 为“不捕获分组”，匹配其中任意一个词
    re.IGNORECASE,
)
# 同上述，湿实验验证越界检测
WET_LAB_VALIDATED_PATTERN = re.compile(
    r"(?:已完成|完成|completed|validated).{0,20}(?:湿实验|wet[- ]?lab)|"
    r"(?:湿实验|wet[- ]?lab).{0,20}(?:已完成|完成|completed|validated)",
    re.IGNORECASE,
)
# 生产级结论越界检测
PRODUCTION_CLAIM_PATTERN = re.compile(
    r"(?:生产级|production[- ]?grade|全基因组结论|whole[- ]?genome conclusion|可直接用于育种)",
    re.IGNORECASE,
)
# 当前阶段只能提出后续 KASP/CAPS 开发计划，不能声称开发已经完成。
MARKER_COMPLETED_PATTERN = re.compile(
    r"(?:已完成|完成|completed|validated|developed).{0,20}(?:KASP|CAPS)|"
    r"(?:KASP|CAPS).{0,20}(?:已完成|完成|completed|validated|developed|开发完成)",
    re.IGNORECASE,
)
# 当前阶段只能给出候选建议，不允许把 smoke 输出写成最终育种定论。
FINAL_BREEDING_CONCLUSION_PATTERN = re.compile(
    r"(?:最终育种结论|final breeding conclusion|最终结论).{0,20}(?:已|为|is|was)?",
    re.IGNORECASE,
)
# 黄铜关键词词组，作用是从代谢组文件或文本里查找黄酮相关内容
FLAVONOID_KEYWORDS = ("黄酮", "flavonoid", "flavone", "flavonol", "anthocyan", "isoflav")
ACCEPTED_LITERATURE_CURATION_STATUSES = {"verified", "curated", "accepted"}

# 转录组流程依赖的固定生信脚本（调用这些开源生信软件）
PIPELINE_DEPENDENCIES = ("hisat2-build", "hisat2", "samtools", "featureCounts", "Rscript")
PIPELINE_R_PACKAGES = ("limma", "optparse", "data.table")


"""输入合同层"""
# 这些输入模型主要服务于 YuXi Tool 调用时的参数约束和扩展管理展示。
# 可以把它们理解为定义“每个业务 Tool 对外公开的输入参数结构”。
# 这段所有的输入类都继承 BaseModel类,YuXi 可以根据它们生成参数 schema  以及其中大量的Field(...)进行字段定义
# 目前 Tool 整体是为 smoke demo 任务设计的
# TODO：后续 Agent 调用 Tool 时也可以传入不同参数，同时将对应的处理逻辑按照新的 tool 流程进行定义
# TODO：未来要通用化，应该把这些默认值抽到 TraitProfile 配置里。

# “smoke黄酮育种建议 Tool”的输入参数 对应 smoke_flavonoid_breeding_advice
class SmokeFlavonoidBreedingAdviceInput(BaseModel):
    # smoke数据目录 字段名：data_dir 字段类型：str 默认值：DEFAULT_DATA_DIR 说明：Smoke test data directory.
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Smoke test data directory.")
    # 当前性状分析
    trait: str = Field(default="黄酮相关", description="Trait focus for the breeding advice.")
    # 输出目录
    out_dir: str = Field(default=DEFAULT_OUT_DIR, description="Directory for run outputs and artifacts.")
    # 是否运行转录组工具执行固定生信脚本
    run_transcriptome: bool = Field(default=True, description="Whether to run run_smoke_de_pipeline.sh.")


# “参考基因组准备/检查 Tool”的输入参数 对应 breeding_reference_prepare
# 参考基因组Tool 是作为信息池 只检查这些文件是否存在，FIXME 并查找目标基因痕迹（目前应该删除）。
class BreedingReferencePrepareInput(BaseModel):
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Breeding data directory.")
    genome_fa: str = Field(default="genome.fa", description="Reference genome FASTA path relative to data_dir.")  # 相对路径
    genome_gff: str = Field(default="genome.gff", description="Reference genome GFF path relative to data_dir.")  # 相对路径
    annotation_txt: str = Field(
        default="xiaomi_T2T_Annotation.smoke_genes.txt",
        description="Annotation TXT path relative to data_dir.",
    )
    out_dir: str = Field(default="/tmp/yuxi_runs/breeding_reference_prepare", description="Output directory.")


# “转录组 DEG Tool”的输入参数 对应 breeding_transcriptome_deg  tool输出significant_de_genes.tsv
# 学长给出的固定生信流程：用 fq 文件、sample map、参考基因组、GFF，运行或读取转录组差异分析结果。
class BreedingTranscriptomeDegInput(BaseModel):
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Breeding data directory.")
    fq_dir: str = Field(default="fq", description="FASTQ directory relative to data_dir.")
    sample_map: str = Field(default="sampleName_clientId.txt", description="Sample map path relative to data_dir.")
    genome_fa: str = Field(default="genome.fa", description="Reference genome FASTA path relative to data_dir.")
    genome_gff: str = Field(default="genome.gff", description="Reference genome GFF path relative to data_dir.")
    out_dir: str = Field(default="/tmp/yuxi_runs/breeding_transcriptome_deg", description="Output directory.")
    threads: int = Field(default=8, description="Threads for the DEG pipeline.")
    # 默认会执行固定脚本 run_smoke_de_pipeline.sh。
    run_pipeline: bool = Field(default=True, description="Whether to execute run_smoke_de_pipeline.sh.")


# “代谢组信息读取 Tool”的输入参数 对应 breeding_metabolome_prepare
# FIXME 目前只是读取 metabolome_raw_3372.tsv、查找黄酮相关字段或关键词、作为后续智能体整合的背景证据
class BreedingMetabolomePrepareInput(BaseModel):
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Breeding data directory.")
    metabolome_tsv: str = Field(
        default="metabolome_raw_3372.tsv",
        description="Metabolome TSV path relative to data_dir.",
    )
    trait: str = Field(default="黄酮相关", description="Trait focus.")
    out_dir: str = Field(default="/tmp/yuxi_runs/breeding_metabolome_prepare", description="Output directory.")

# “文献证据读取 Tool”的输入参数 对应 breeding_literature_evidence
class BreedingLiteratureEvidenceInput(BaseModel):
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Breeding data directory.")
    # DOI 和引用原句来自 执行breeding_literature_evidence工具生成的verified_literature_evidence.tsv
    literature_evidence: str = Field(
        default=VERIFIED_LITERATURE_EVIDENCE_FILE,
        description="Literature evidence TSV path relative to data_dir.",
    )
    trait: str = Field(default="黄酮相关", description="Trait focus.")
    gene_id: str = Field(default=TARGET_GENE, description="Candidate gene id.")
    out_dir: str = Field(default="/tmp/yuxi_runs/breeding_literature_evidence", description="Output directory.")

# “育种建议生成 Tool”的输入参数 对应 breeding_advice_generate
# 这个 Tool 是整合型的，将前面每一步工具运行后留下的摘要/清单/证明文件整合成 breeding_advice.md
class BreedingAdviceGenerateInput(BaseModel):
    data_dir: str = Field(default=DEFAULT_DATA_DIR, description="Breeding data directory.")
    trait: str = Field(default="黄酮相关", description="Trait focus.")  # 性状方向
# TODO：各种工具输出的摘要，参数可选，如果用户不传，后端 Tool 会自己去默认路径找，或者重新执行轻量检查？
    reference_manifest: str = Field(default="", description="Optional reference_manifest.json path.")
    transcriptome_manifest: str = Field(default="", description="Optional transcriptome_manifest.json path.")
    metabolome_manifest: str = Field(default="", description="Optional metabolome_manifest.json path.")
    literature_manifest: str = Field(default="", description="Optional literature_manifest.json path.")
    significant_de_genes: str = Field(default="", description="Optional significant_de_genes.tsv path.")
    out_dir: str = Field(default="/tmp/yuxi_runs/breeding_advice_generate", description="Output directory.")


# “验证计划生成 Tool”的输入参数 对应 breeding_validation_plan
# 结合后续LLM分析，给用户输出后续的验证计划 TODO：梳理清楚如何给到LLM
class BreedingValidationPlanInput(BaseModel):
    trait: str = Field(default="黄酮相关", description="Trait focus.")
    gene_id: str = Field(default=TARGET_GENE, description="Candidate gene id.")
    marker_types: str = Field(default="SNP/InDel/KASP/CAPS", description="Marker types for follow-up planning.")
    out_dir: str = Field(default="/tmp/yuxi_runs/breeding_validation_plan", description="Output directory.")



"""
通用辅助函数层
1. 通常以下划线开头
2. 不直接暴露给 YuXi Agent
3. 不带 @tool 装饰器
4. 被后面的业务函数调用
5. 每个函数只做一个小动作
"""
# 把一个 Python 字典写成 JSON 文件
def _write_json(path: Path, payload: dict[str, Any]) -> None:
    #用UTF-8把字符串写入文件，要求： 直接保留中文  json缩进2个空格  key按字母排序
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _split_sample_map_row(line: str) -> list[str]:
    stripped = str(line or "").strip()
    if not stripped:
        return []
    if "\t" in stripped:
        return [part.strip() for part in stripped.split("\t")]
    return [part.strip() for part in re.split(r"\s+", stripped) if part.strip()]


def _sample_map_alias_index(headers: list[str], alias_group: str) -> int | None:
    aliases = SAMPLE_MAP_HEADER_ALIASES[alias_group]
    normalized_headers = [str(item or "").strip().lstrip("#").lower() for item in headers]
    for index, header in enumerate(normalized_headers):
        if header in aliases:
            return index
    return None


def _infer_pipeline_group_label(group_value: str) -> str:
    normalized = str(group_value or "").strip()
    upper = normalized.upper()
    tokens = [token for token in re.split(r"[^A-Z0-9]+", upper) if token]
    token_set = set(tokens)
    if "LM" in token_set or "LH" in token_set or "CK" in token_set or "CONTROL" in token_set or "REFERENCE" in token_set:
        return "LM"
    if "JM" in token_set or "JH" in token_set or "TREATED" in token_set or "TREATMENT" in token_set or "CASE" in token_set:
        return "JM"
    if upper in {"C", "CTRL"}:
        return "LM"
    if upper in {"T", "TRT"}:
        return "JM"
    return ""


def _normalize_sample_map(
    *,
    sample_map_path: Path,
    out_dir: Path,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pending",
        "original_path": str(sample_map_path),
        "normalized_path": "",
        "compatible_path": "",
        "preview": [],
        "columns": [],
        "row_count": 0,
        "bad_rows": [],
        "parse_error": "",
        "has_header": False,
        "original_group_values": [],
        "group_mapping": {},
        "pipeline_group_mode": "unknown",
    }

    if not sample_map_path.exists() or not sample_map_path.is_file():
        result["status"] = "missing"
        result["parse_error"] = "sample_map_missing"
        return result

    rows = [_split_sample_map_row(line) for line in sample_map_path.read_text(encoding="utf-8").splitlines()]
    rows = [row for row in rows if row]
    if not rows:
        result["status"] = "failed"
        result["parse_error"] = "sample_map_empty"
        return result

    header = rows[0]
    sample_index = _sample_map_alias_index(header, "sample")
    group_index = _sample_map_alias_index(header, "group")
    client_index = _sample_map_alias_index(header, "client_id")
    has_header = sample_index is not None and (group_index is not None or client_index is not None)
    result["has_header"] = has_header
    result["columns"] = header if has_header else []

    if has_header:
        second_index = group_index if group_index is not None else client_index
        data_rows = rows[1:]
    else:
        if len(header) < 2:
            result["status"] = "failed"
            result["parse_error"] = "sample_map_requires_at_least_two_columns"
            result["columns"] = header
            return result
        sample_index = 0
        second_index = 1
        data_rows = rows

    normalized_lines: list[str] = []
    compatible_lines: list[str] = []
    observed_group_values: list[str] = []
    ordered_unique_groups: list[str] = []
    explicit_group_values: list[str] = []
    for row_number, row in enumerate(data_rows, start=2 if has_header else 1):
        if sample_index is None or second_index is None or len(row) <= max(sample_index, second_index):
            result["bad_rows"].append({"row_number": row_number, "row": row, "reason": "missing_required_columns"})
            continue
        sample_id = str(row[sample_index]).strip()
        group_value = str(row[second_index]).strip()
        if not sample_id or not group_value:
            result["bad_rows"].append({"row_number": row_number, "row": row, "reason": "empty_sample_or_group"})
            continue
        normalized_lines.append(f"{sample_id}\t{group_value}")
        observed_group_values.append(group_value)
        if group_index is not None:
            explicit_group_values.append(group_value)
            if group_value not in ordered_unique_groups:
                ordered_unique_groups.append(group_value)
        compatible_lines.append(f"{sample_id}\t{group_value}")

    result["row_count"] = len(normalized_lines)
    result["original_group_values"] = ordered_unique_groups

    if not normalized_lines:
        result["status"] = "failed"
        result["parse_error"] = "sample_map_contains_no_valid_rows"
        return result

    pipeline_group_mode = "client_id_passthrough"
    group_mapping: dict[str, str] = {}
    if group_index is not None:
        pipeline_group_mode = "explicit_group_mapped_to_jm_lm"
        inferred_labels: dict[str, str] = {}
        for group_value in ordered_unique_groups:
            inferred = _infer_pipeline_group_label(group_value)
            if inferred:
                inferred_labels[group_value] = inferred
        unresolved_groups = [group_value for group_value in ordered_unique_groups if group_value not in inferred_labels]
        available_labels = [label for label in ("LM", "JM") if label not in set(inferred_labels.values())]
        for group_value in unresolved_groups:
            if available_labels:
                inferred_labels[group_value] = available_labels.pop(0)
        if len(set(inferred_labels.values())) < 2 and len(ordered_unique_groups) >= 2:
            first_group, second_group = ordered_unique_groups[:2]
            inferred_labels[first_group] = "LM"
            inferred_labels[second_group] = "JM"
        if len(ordered_unique_groups) < 2:
            result["status"] = "failed"
            result["parse_error"] = "explicit_group_requires_two_distinct_groups"
            result["group_mapping"] = inferred_labels
            result["pipeline_group_mode"] = pipeline_group_mode
            return result
        unresolved_after_assignment = [
            group_value for group_value in ordered_unique_groups if not inferred_labels.get(group_value)
        ]
        unique_labels = {label for label in inferred_labels.values() if label}
        if unresolved_after_assignment or len(unique_labels) != 2 or not unique_labels.issubset({"LM", "JM"}):
            result["status"] = "failed"
            result["parse_error"] = "explicit_group_cannot_be_mapped_to_jm_lm"
            result["group_mapping"] = inferred_labels
            result["pipeline_group_mode"] = pipeline_group_mode
            return result
        group_mapping = inferred_labels
        compatible_lines = []
        valid_index = 0
        for row_number, row in enumerate(data_rows, start=2 if has_header else 1):
            if sample_index is None or second_index is None or len(row) <= max(sample_index, second_index):
                continue
            sample_id = str(row[sample_index]).strip()
            group_value = str(row[second_index]).strip()
            if not sample_id or not group_value:
                continue
            mapped_group = group_mapping[group_value]
            compatible_lines.append(f"{sample_id}\t{sample_id}_{mapped_group}")
            valid_index += 1
    result["group_mapping"] = group_mapping
    result["pipeline_group_mode"] = pipeline_group_mode
    result["preview"] = compatible_lines[:6]

    out_dir.mkdir(parents=True, exist_ok=True)
    normalized_path = out_dir / "normalized_sampleName_clientId.txt"
    normalized_path.write_text("\n".join(normalized_lines) + "\n", encoding="utf-8")
    compatible_path = out_dir / "compatible_sampleName_clientId.txt"
    compatible_path.write_text("\n".join(compatible_lines) + "\n", encoding="utf-8")
    result["normalized_path"] = str(normalized_path)
    result["compatible_path"] = str(compatible_path)
    result["status"] = "completed"
    return result


# 检查当前数据目录里，smoke 数据包必需文件是否涵盖齐全
def _required_smoke_files(data_dir: Path) -> tuple[dict[str, Path], list[str]]:
    paths = {name: data_dir / rel for name, rel in REQUIRED_FILES.items()}  # 根据前面定义的 REQUIRED_FILES 生成绝对路径表
    missing = [str(path) for path in paths.values() if not path.exists()]  # 把不存在的文件加入 missing 列表
    # 这个函数在检查 smoke 数据是否齐全时被调用。
    # 输入是数据目录；输出是已解析路径表和缺失文件列表。
    # 它属于“文件合同检查”步骤，不属于智能体推理。

    # 先去 data_dir/fq/下面找所有的*.fq.gz文件
    fq_dir = data_dir / "fq"
    fastqs = []
    if fq_dir.exists():
        for pattern in ("*.fq.gz", "*.fastq.gz", "*.fq", "*.fastq"):
            fastqs.extend(sorted(fq_dir.glob(pattern)))
    if not fastqs:
        for pattern in ("*.fq.gz", "*.fastq.gz", "*.fq", "*.fastq"):
            fastqs.extend(sorted(data_dir.glob(pattern)))  # 没找到则退一步去根目录 data_dir 寻找
    if not fastqs:
        missing.append(str(fq_dir / "*.fq.gz"))  # 若还没找到就认为缺少 RNA-seq reads

    paths["fq_dir"] = fq_dir
    return paths, missing  #返回 paths即每个关键文件对应的完整路径  missing即缺失的文件路径列表


# 自动定位真正的 smoke 数据目录  FIXME：是否只能处理一层的间接目录？
def _resolve_smoke_data_dir(data_dir: Path) -> Path:
    # 这个函数在所有育种 Tool 刚拿到 data_dir 时被间接调用。
    # 输入是用户给出的目录；输出是最终应当读取的 smoke 数据目录。
    # 它只做目录定位，不做任何智能分析。
    # 这样可以兼容“外层目录下只有一个 smoke_case 子目录”的演示数据摆放方式。可理解为如果用户传的是外层目录，我帮他自动找到里面真正的数据目录。
    # 即解决：用户传入的 data_dir 不一定就是最终包含 genome.fa、fq/、metabolome_raw_3372.tsv 的直接父目录

    if _required_smoke_files(data_dir)[1] == []:  # 取出missing列表为空，说明没有缺失文件，当前目录就是正确目录
        return data_dir
    if not data_dir.exists():  # 若目录不存在，也直接返回，由之后的_ensure_data_dir()负责处理报错
        return data_dir

    # 如果当前目录下面只有一个子目录，就检查子目录
    child_dirs = [path for path in data_dir.iterdir() if path.is_dir()]
    if len(child_dirs) != 1:
        return data_dir  # 如有且只有一个子目录，不返回，继续

    child = child_dirs[0]
    if _required_smoke_files(child)[1] == []:
        return child  # 如果这个子目录是完整的 smoke 数据目录，就返回子目录
    return data_dir  # 否则返回原目录


# 统一检查输入数据目录
def _ensure_data_dir(data_dir: str) -> tuple[Path | None, dict[str, Any] | None]:
    # 所有对外 Tool 在真正读取文件数据前都会经过这里，是 “第一道门”。
    # 输入是字符串形式的 data_dir；输出是标准化 Path 或错误结果。
    # 它的作用是把“路径不存在”这种基础问题尽早变成统一错误返回。

    # 将字符串形式路径转为Path  支持 ~/xxx 形式的路径  转为绝对路径
    data_path = Path(data_dir).expanduser().resolve()
    # 如果路径不存在或者该路径不是正确目录，就返回错误  返回结构是 （正常路径，错误对象）
    if not data_path.exists() or not data_path.is_dir():
        # 错误返回 ：（None，错误对象{}）
        return None, {
            "status": "error",
            "error": f"data_dir does not exist or is not a directory: {data_path}",
            "artifacts": [],
        }
    # 正确返回：（最终数据目录，None）
    return _resolve_smoke_data_dir(data_path), None

# 统一检查/创建输出目录  和 _ensure_data_dir() 类似，不过它处理的是输出目录
def _ensure_out_dir(out_dir: str) -> tuple[Path | None, str | None]:
    # 所有 Tool 在写 manifest、log、advice 前都会经过这里。
    # 输入是输出目录字符串；输出是可写目录或错误信息。

    # 将字符串形式路径转为Path  支持 ~/xxx 形式的路径  转为绝对路径
    out_path = Path(out_dir).expanduser().resolve()
    try:    # 只处理两种正确情况
        out_path.mkdir(parents=True, exist_ok=True)  # 父目录不存在也一起创建  目录已存在也不报错（即如果目标路径已经是一个目录，就当作成功）
    except Exception as exc:  # noqa: BLE001
        return None, f"Cannot create out_dir {out_path}: {exc}"  # 失败返回
    return out_path, None  # 成功返回


# 在文本中查目标基因  比如：_lookup_gene_in_text(genome_gff_path, "Si9g037800") 它会逐行读取 genome.gff，如果某一行包含 Si9g037800，就保存下来
def _lookup_gene_in_text(path: Path, gene_id: str) -> dict[str, Any]:
    # 这个函数在参考信息检查和 DEG 回退检查时被调用。
    # 输入是文本文件路径和目标基因；输出是是否找到基因以及命中的原始行片段。
    # 它只做“按文本检索证据” 即 字符串检索，不做基因功能推断。
    matches: list[str] = []
    if not path.exists():
        return {"found": False, "matches": matches}
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if gene_id in line:
                matches.append(line.rstrip("\n")[:500])  # 去掉行尾换行符，只保留前 500 个字符，避免某一行太长。
                if len(matches) >= 5:  # 最多只保存5条命中记录
                    break
    return {"found": bool(matches), "matches": matches}


# 检查代谢组表中是否有代谢组关键词，如黄酮
def _inspect_metabolome(path: Path) -> dict[str, Any]:
    # 这个函数在代谢组 Tool 和建议生成阶段被调用。
    # 输入是 metabolome_raw_3372.tsv；输出是表头、样例行和黄酮关键词命中情况。
    # 这里的结果来自文件读取，不是 LLM 推理。
    # 当前 smoke 范式下，代谢组被当作“已打捞到的信息”，只做轻量检查。
    if not path.exists():
        return {
            "exists": False,
            "columns": [],
            "sample_rows": [],
            "row_count_sampled": 0,
            "flavonoid_related": False,
            "matched_terms": [],
        }

    matched_terms: set[str] = set()
    columns: list[str] = []
    sample_rows: list[list[str]] = []
    sampled_rows = 0
    # 如果文件存在，就读取 TSV
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        # 先读表头，将其拼接成字符串，转小写
        try:
            columns = next(reader)
        except StopIteration:
            columns = []
        header_text = "\t".join(columns).lower()
        # 检查表头是否有黄酮关键词 TODO：后续应该更改为泛化代谢组
        for keyword in FLAVONOID_KEYWORDS:
            if keyword.lower() in header_text:
                matched_terms.add(keyword)
        # 最多读取20行，每行只保留前8列，再检查每一行是否有黄酮关键词
        for row in reader:
            sampled_rows += 1
            sample_rows.append(row[:8])
            row_text = "\t".join(row).lower()
            for keyword in FLAVONOID_KEYWORDS:
                if keyword.lower() in row_text:
                    matched_terms.add(keyword)
            if sampled_rows >= 20:
                break
    # 成功返回
    return {
        "exists": True,
        "columns": columns,
        "sample_rows": sample_rows,
        "row_count_sampled": sampled_rows,
        "flavonoid_related": bool(matched_terms),
        "matched_terms": sorted(matched_terms),
    }


# 检查 DEG 结果是否支持目标基因
def _inspect_de_support(path: Path | None, gene_id: str) -> dict[str, Any]:
    # 这个函数在转录组和建议生成阶段被调用。
    # 输入是 significant_de_genes.tsv 路径和目标基因；输出是目标基因是否出现在 DEG 结果里。
    # 这属于生信结果回收，不属于智能体整合。

    # 如果没有文件
    if path is None or not path.exists():
        return {"available": False, "supports_target_gene": False, "matches": []}

    # 如果有文件，就按 TSV 字典格式读取
    matches: list[dict[str, str]] = []
    with path.open(encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")  # 每一行会变成一个字典 比如原表头是：gene_id logFC P.Value，会变成 {"gene_id": "Si9g037800","logFC": "2.1","P.Value": "0.001"}
        if reader.fieldnames:
            for row in reader:
                # 把这一行所有字段值拼成一个字符串，只要里面包含目标基因，就认为命中
                if gene_id in "\t".join(str(v) for v in row.values()):
                    # 命中后保存整行
                    matches.append({k: str(v) for k, v in row.items()})
                    if len(matches) >= 5:
                        break
    # 回退逻辑：如果TSV表格方式没找到，就按普通文本再查一次
    if not matches:
        text_matches = _lookup_gene_in_text(path, gene_id)["matches"]
        matches = [{"line": line} for line in text_matches]
    # supports_target_gene 只是说明：目标基因出现在显著差异表达结果中
    return {"available": True, "supports_target_gene": bool(matches), "matches": matches}


# 在多个可能位置找 DEG 结果文件
def _find_significant_de_genes(data_dir: Path, out_dir: Path, preferred: Path | None = None) -> Path | None:
    # 这个函数在转录组 Tool 结束后被调用。
    # 输入是数据目录、输出目录和优先候选路径；输出是实际找到的 DEG 结果文件路径。
    # 它的作用是兼容脚本可能把结果写在不同目录层级。如 run_smoke_de_pipeline.sh 或不同运行方式可能把 significant_de_genes.tsv 放在不同位置

    candidates: list[Path] = []
    # 候选路径包括：
    # preferred
    # data_dir/significant_de_genes.tsv
    # out_dir/significant_de_genes.tsv
    if preferred is not None:
        candidates.append(preferred)
    candidates.extend([data_dir / "significant_de_genes.tsv", out_dir / "significant_de_genes.tsv"])
    # rglob 递归查找
    for base in (data_dir, out_dir):
        if base.exists():
            candidates.extend(sorted(base.rglob("significant_de_genes.tsv")))
    # seen 对递归查找结果进行去重
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        # 如果文件存在且是普通文件，返回对应路径
        if resolved.exists() and resolved.is_file():
            return resolved
    return None


# 把 DEG 结果复制到统一位置  当前 out_dir/significant_de_genes.tsv
def _copy_significant_de_genes(significant_de_path: Path | None, out_path: Path) -> Path | None:
    # 这个函数在找到 DEG 结果后被调用。
    # 输入是原始结果路径和当前 Tool 的输出目录；输出是统一复制后的结果路径。
    # 这样前端和后续 Tool 可以稳定地从当前 out_dir 下取到 `significant_de_genes.tsv`。

    # 没有找到 DEG 文件
    if significant_de_path is None:
        return None
    # 目标复制路径
    copied = out_path / "significant_de_genes.tsv"
    # 如果源文件已在，目标位置，不用复制，直接返回
    if significant_de_path.resolve() == copied.resolve():
        return significant_de_path
    # 否则复制，copy2 会保留文件元信息
    shutil.copy2(significant_de_path, copied)
    # 返回复制后的路径
    return copied


def _copy_optional_pipeline_table(
    *,
    filename: str,
    data_dir: Path,
    out_dir: Path,
) -> Path | None:
    candidates: list[Path] = [data_dir / filename, out_dir / filename]
    for base in (data_dir, out_dir):
        if base.exists():
            candidates.extend(sorted(base.rglob(filename)))

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and resolved.is_file():
            copied = out_dir / filename
            if copied.resolve() != resolved:
                shutil.copy2(resolved, copied)
            return copied
    return None


def _normalize_literature_evidence_level(raw_level: str) -> str:
    # 旧逻辑的问题：
    # TSV 中的 evidence_level 可能混用 crop_trait_background、pathway_background、gene_specific 等内部写法。
    # 直接把这些值泄露到最终输出，读者容易误把“证据等级”理解成实验已经完成。
    #
    # 新逻辑统一成 high / medium / background 三档。
    # 这三档只表示文献与当前任务的相关性和支持强弱，不代表群体验证、湿实验或最终 KASP/CAPS 已完成。
    normalized = (raw_level or "").strip().lower()
    if normalized in {"high", "direct", "gene_specific"}:
        return "high"
    if normalized in {"medium", "moderate", "candidate"}:
        return "medium"
    return "background"


# 取真实文献 DOI 和引用原句：负责从 verified_literature_evidence.tsv 读取真实文献数据
'''其中的 verified_literature_evidence.tsv 可以理解为是给 育种Tools 准备的一张“已核验真实文献数据表”
其来源链路为：PubMed / Web of Science / Google Scholar / 论文 PDF / 学长提供文献 ——》筛选与黄酮、谷子、Si9g037800 或相关机制有关的文献
——》 确认 DOI 真实存在 ——》从论文原文中摘出可以引用的原句 ——》整理成 verified_literature_evidence.tsv '''
def _load_verified_literature_evidence(
    data_dir: Path,
    trait: str,
    *,  # * 代表后面的参数（literature_filename 和 gene_id）必须用关键字传参，避免参数顺序传错
    literature_filename: str = VERIFIED_LITERATURE_EVIDENCE_FILE,
    gene_id: str = TARGET_GENE,
) -> tuple[list[dict[str, str]], Path]:
    # DOI 和引用原句不来自大模型生成，而是从整理的 TSV 中读取。
    # 这里先做最小过滤，保证后续 advice 只能引用“已落盘、可追溯”的文献字段。
    # 先确定证据文件 TSV 的路径
    evidence_path = data_dir / literature_filename
    # 文件不存在
    if not evidence_path.exists():
        return [], evidence_path
    # 文件存在，用 csv.DictReader 按 TSV 读取：
    entries: list[dict[str, str]] = []
    with evidence_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        # 旧逻辑保留供学习对照：
        # old:
        # 只按 gene_id / trait / doi / quoted_sentence 做基础过滤。
        #
        # 旧逻辑的问题：
        # 1. 没有读取 curation_status，pending / rejected / demo 行也可能被当成真实证据；
        # 2. evidence_level 没有统一归一化，后续很难在汇报里稳定解释；
        # 3. 没有把“无 curation_status 时仍需人工确认”这条边界显式写出来。
        field_names = {name.strip() for name in (reader.fieldnames or []) if name}
        has_curation_status = "curation_status" in field_names
        # 每一行取字段
        for row in reader:
            row_gene_id = (row.get("gene_id") or "").strip()
            trait_value = (row.get("trait") or "").strip()
            doi = (row.get("doi") or "").strip()
            quoted_sentence = (row.get("quoted_sentence") or "").strip()
            curation_status = (row.get("curation_status") or "").strip().lower()
            # 逐步过滤
            if row_gene_id != gene_id:  # 必须是当前基因
                continue
            if "黄酮" not in trait_value and "黄酮" not in trait:  # FIXME：必须是黄酮相关
                continue
            if not DOI_PATTERN.fullmatch(doi):  # DOI 格式
                continue
            if not quoted_sentence:  # 必须有引用原句
                continue
            # 学长要求：如果 TSV 里有 curation_status，就只允许 verified / curated / accepted 进入真实文献证据。
            if has_curation_status and curation_status not in ACCEPTED_LITERATURE_CURATION_STATUSES:
                continue
            # 全部通过后加入 entries
            entries.append(
                {
                    "gene_id": row_gene_id,
                    "trait": trait_value,
                    "doi": doi,
                    "title": (row.get("title") or "").strip(),
                    "quoted_sentence": quoted_sentence,
                    "source": (row.get("source") or "").strip(),
                    "evidence_level": _normalize_literature_evidence_level(row.get("evidence_level") or ""),
                    "note": (row.get("note") or "").strip(),
                    "curation_status": curation_status,
                    # 如果 TSV 暂时没有 curation_status，本轮允许读取 DOI 和引用原句，
                    # 但正式汇报前仍需人工核对原始论文与整理表，不能把它误写成“自动确认过”的最终证据。
                    "curation_note": (
                        ""
                        if has_curation_status
                        else "TSV 未提供 curation_status；正式汇报前需人工确认 DOI 与引用原句。"
                    ),
                }
            )
    # 成功返回
    return entries, evidence_path


# 读取上游工具生成的 manifest JSON
def _load_json_if_present(path_value: str) -> dict[str, Any] | None:
    # 这个函数在 advice_generate 读取上游 manifest 时被调用。 比如：reference_manifest.json transcriptome_manifest.json等等
    # 输入是 manifest 路径字符串；输出是 JSON 内容或 null。
    # 它允许建议生成阶段复用上游结果，而不是重复跑同样的轻量检查。
    # 作用是如果前面步骤已经运行过，就直接复用 manifest；
    # 如果没有，就返回 None，让后面的 advice_generate 自己回退执行轻量检查。
    if not path_value:
        return None
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _transcriptome_pipeline_runner() -> str:
    return str(os.environ.get("TRANSCRIPTOME_PIPELINE_RUNNER") or "").strip()


def _resolve_pipeline_runner() -> dict[str, Any]:
    runner = _transcriptome_pipeline_runner()
    if not runner:
        return {
            "raw": "",
            "args": [],
            "resolved_args": [],
            "resolved_executable": "",
            "resolution_attempts": [],
            "executable_not_found": "",
        }

    runner_args = shlex.split(runner)
    if not runner_args:
        return {
            "raw": runner,
            "args": [],
            "resolved_args": [],
            "resolved_executable": "",
            "resolution_attempts": [],
            "executable_not_found": "",
        }

    executable = runner_args[0]
    resolution_attempts: list[str] = []
    resolved_executable = ""
    executable_path = Path(executable).expanduser()
    if executable_path.is_absolute():
        resolution_attempts.append(str(executable_path))
        resolved_executable = str(executable_path)
    else:
        which_result = shutil.which(executable)
        if which_result:
            resolution_attempts.append(which_result)
            resolved_executable = which_result
        else:
            home = Path.home()
            for candidate in [
                home / ".local" / "bin" / executable,
                home / "micromamba" / "bin" / executable,
                Path("/home/li/.local/bin") / executable,
                Path("/home/li/micromamba/bin") / executable,
            ]:
                candidate_text = str(candidate.expanduser())
                resolution_attempts.append(candidate_text)
                if candidate.exists():
                    resolved_executable = candidate_text
                    break

    resolved_args = list(runner_args)
    if resolved_executable:
        resolved_args[0] = resolved_executable

    return {
        "raw": runner,
        "args": runner_args,
        "resolved_args": resolved_args,
        "resolved_executable": resolved_executable,
        "resolution_attempts": resolution_attempts,
        "executable_not_found": executable if runner_args and not resolved_executable else "",
    }


def _with_pipeline_runner(command: list[str], *, runner_info: dict[str, Any] | None = None) -> list[str]:
    info = runner_info or _resolve_pipeline_runner()
    resolved_args = list(info.get("resolved_args") or [])
    if not resolved_args:
        return command
    return [*resolved_args, *command]


def _tail_text(text: str, *, max_chars: int = 2000) -> str:
    return str(text or "")[-max_chars:]


def _run_dependency_probe(
    tool: str,
    command: list[str],
    *,
    cwd: Path,
    runner_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runner_info = runner_info or _resolve_pipeline_runner()
    full_command = _with_pipeline_runner(command, runner_info=runner_info)
    result = {
        "tool": tool,
        "command_list": full_command,
        "command_display": " ".join(full_command),
        "command": full_command,
        "runner_raw": runner_info.get("raw") or "",
        "resolved_pipeline_runner_args": list(runner_info.get("resolved_args") or []),
        "resolved_pipeline_runner_executable": runner_info.get("resolved_executable") or "",
        "runner_resolution_attempts": list(runner_info.get("resolution_attempts") or []),
        "returncode": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "exception": "",
        "runner_executable_not_found": runner_info.get("executable_not_found") or "",
        "available": False,
        "ok": False,
    }
    if runner_info.get("executable_not_found"):
        result["stderr_tail"] = f"Runner executable not found: {runner_info['executable_not_found']}"
        result["exception"] = f"FileNotFoundError(2, 'No such file or directory: {runner_info['executable_not_found']}')"
        return result
    try:
        completed = subprocess.run(
            full_command,
            cwd=str(cwd),
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
        result["returncode"] = completed.returncode
        result["stdout_tail"] = _tail_text(completed.stdout)
        result["stderr_tail"] = _tail_text(completed.stderr)
        result["available"] = completed.returncode == 0
        result["ok"] = result["available"]
    except FileNotFoundError as exc:
        result["exception"] = repr(exc)
        result["stderr_tail"] = str(exc)
        result["runner_executable_not_found"] = full_command[0] if full_command else ""
    except Exception as exc:  # noqa: BLE001
        result["exception"] = repr(exc)
        result["stderr_tail"] = str(exc)
    return result


def _check_pipeline_dependencies(*, data_dir: Path) -> dict[str, Any]:
    runner_info = _resolve_pipeline_runner()
    dependency_commands = {
        "hisat2-build": ["hisat2-build", "--version"],
        "hisat2": ["hisat2", "--version"],
        "samtools": ["samtools", "--version"],
        "featureCounts": ["featureCounts", "-v"],
        "Rscript": ["Rscript", "--version"],
    }
    dependency_checks = {
        name: _run_dependency_probe(name, command, cwd=data_dir, runner_info=runner_info)
        for name, command in dependency_commands.items()
    }
    missing_tools = [name for name, check in dependency_checks.items() if not check["available"]]

    r_package_checks: dict[str, dict[str, Any]] = {}
    missing_r_packages: list[str] = []
    if "Rscript" not in missing_tools:
        for package_name in PIPELINE_R_PACKAGES:
            check = _run_dependency_probe(
                f"Rpackage:{package_name}",
                ["Rscript", "-e", f'q(status=if (requireNamespace("{package_name}", quietly=TRUE)) 0 else 1)'],
                cwd=data_dir,
                runner_info=runner_info,
            )
            r_package_checks[package_name] = check
            if not check["available"]:
                missing_r_packages.append(package_name)

    return {
        "runner": runner_info.get("raw") or "",
        "mode": "runner" if runner_info.get("raw") else "current_path",
        "runner_info": runner_info,
        "checks": dependency_checks,
        "missing_tools": missing_tools,
        "r_package_checks": r_package_checks,
        "missing_r_packages": missing_r_packages,
    }


def _resolve_transcriptome_pipeline_script(data_dir: Path) -> tuple[Path | None, str | None]:
    local_tool_dir = Path(__file__).resolve().parent
    candidates = [
        data_dir / REQUIRED_FILES["pipeline_script"],
        local_tool_dir / REQUIRED_FILES["pipeline_script"],
        local_tool_dir / "scripts" / REQUIRED_FILES["pipeline_script"],
    ]
    default_root = Path(DEFAULT_DATA_DIR).expanduser()
    candidates.append(default_root / REQUIRED_FILES["pipeline_script"])
    if default_root.exists():
        candidates.extend(sorted(default_root.rglob(REQUIRED_FILES["pipeline_script"])))

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists() and resolved.is_file():
            return resolved, str(resolved)
    return None, None


"""
固定流程执行层：目前只有转录组接入了固定的生信分析脚本
"""
def _run_transcriptome_pipeline(
    data_dir: Path,
    out_dir: Path,
    threads: int,
    run_log: Path,
    *,
    fq_dir: str,
    sample_map: str,
    genome_fa: str,
    genome_gff: str,
) -> dict[str, Any]:
    # 真正的转录组执行不是 YuXi 原生能力，而是调用学长给定的固定脚本 run_smoke_de_pipeline.sh 。
    # 该脚本底层依赖 hisat2、samtools、featureCounts、Rscript 等开源生信软件。

    # 找到脚本路径
    script, resolved_script_path = _resolve_transcriptome_pipeline_script(data_dir)
    if script is None:
        run_log.write_text("Pipeline script not found: run_smoke_de_pipeline.sh\n", encoding="utf-8")
        return {
            "attempted": False,
            "returncode": None,
            "command": [],
            "stdout_tail": "",
            "stderr_tail": "",
            "error": "pipeline_script_missing",
            "resolved_script_path": "",
        }
    # 设置转录组输出目录
    de_out_dir = out_dir / "de_pipeline_out"
    # 组装命令 本质是拼接 Linux 命令  subprocess.run() 用列表形式相比于字符串执行时更安全
    command = [
        "bash",
        str(script),
        "--fa",
        genome_fa,
        "--gff",
        genome_gff,
        "--fq-dir",
        fq_dir,
        "--sample-map",
        sample_map,
        "--outdir",
        str(de_out_dir),
        "--threads",
        str(threads),
    ]
    runner_info = _resolve_pipeline_runner()
    final_command = _with_pipeline_runner(command, runner_info=runner_info)
    # 初始化结果字典，函数返回给上层的执行结果摘要
    result: dict[str, Any] = {
        "attempted": True,  # 是否尝试执行脚本
        "returncode": None,  # 脚本返回码  正常执行为0
        "command": final_command,  # 实际执行命令
        "stdout_tail": "",  # 标准输出最后 4000 个字符
        "stderr_tail": "",  # 错误输出最后 4000 个字符
        "error": "",  # python 调用阶段的异常
        "resolved_script_path": resolved_script_path or "",
        "runner": runner_info.get("raw") or "",
        "resolved_pipeline_runner_args": list(runner_info.get("resolved_args") or []),
        "resolved_pipeline_runner_executable": runner_info.get("resolved_executable") or "",
        "runner_resolution_attempts": list(runner_info.get("resolution_attempts") or []),
        "runner_executable_not_found": runner_info.get("executable_not_found") or "",
    }
    if runner_info.get("executable_not_found"):
        result["attempted"] = False
        result["error"] = "pipeline_runner_executable_not_found"
        result["stderr_tail"] = f"Runner executable not found: {runner_info['executable_not_found']}"
        return result
    # 真正执行脚本
    try:
        completed = subprocess.run(
            final_command,  # 要执行的命令列表
            cwd=str(data_dir),  # 在数据目录下执行脚本，使脚本找到传来的data_dir相对路径下的文件
            text=True,  # 输出按字符串处理而不是字节
            capture_output=True,  # 捕获 stdout 和 stderr
            timeout=1800,  # 最长运行时间
            check=False,  # 即使命令返回非 0，也不让 Python 直接抛异常
        )
        # 保存执行结果
        result["returncode"] = completed.returncode
        result["stdout_tail"] = completed.stdout[-4000:]  # 只保存后4000个字符，避免日志过大
        result["stderr_tail"] = completed.stderr[-4000:]
        # 编写运行日志，生成一个 run.log
        run_log.write_text(
            "\n".join([
                f"command: {' '.join(final_command)}",
                f"cwd: {data_dir}",
                f"returncode: {completed.returncode}",
                "",
                "=== stdout ===",
                completed.stdout,
                "",
                "=== stderr ===",
                completed.stderr,
            ]),
            encoding="utf-8",
        )
    # python 调用脚本时出错处理  把错误写入 result["error"] 和 run.log
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
        run_log.write_text(f"Pipeline execution failed before completion: {exc}\n", encoding="utf-8")
    return result



"""
建议文本生成与守卫层：
_render_literature_lines
_build_advice_markdown
_guard_advice
"""

# 文献证据渲染层
def _render_literature_lines(literature_evidence: list[dict[str, str]]) -> list[str]:
    # 这个函数在生成最终 markdown 时被调用。
    # 输入是已验证文献证据，即 _load_verified_literature_evidence() 读取出的文献列表；输出是“文献证据”小节的 markdown 行。
    # 这里展示的 DOI 和引用原句必须来自 TSV 证据，不能让大模型自由编造。

    # 标题
    lines = ["## 文献证据"]
    # 文献证据列表为空
    if not literature_evidence:
        lines.extend(["真实 DOI：待文献检索补充", "引用原文：待文献检索补充"])
        return lines
    # 逐行遍历，且从 1 开始编号
    for index, evidence in enumerate(literature_evidence, start=1):
        # 逐条生成 md
        lines.append(f"### 证据 {index}")
        lines.append(f"真实 DOI：{evidence['doi']}")
        lines.append(f"引用原文：{evidence['quoted_sentence']}")
        # 可选字段
        if evidence.get("title"):
            lines.append(f"文献标题：{evidence['title']}")
        if evidence.get("source"):  # 这条 DOI 和引用原句是通过什么渠道获得、整理或核验的？
            lines.append(f"证据来源：{evidence['source']}")
        # TODO：后续应该增加字段，让证据分级来源判断过程更加明确，也可删掉这个字段，让用户自行判断
        # 证据等级不是由样本自动算出的，而是由“文献内容与当前组学发现、育种目标之间的匹配程度”判断出来的。
        # 例如：如果转录组结果显示：Si9g037800 显著差异表达  代谢组结果显示：黄酮相关代谢物显著变化  同时文献又说：某类基因或某条通路参与黄酮积累
        # 那么这条文献对当前项目的支持力度就更高。
        if evidence.get("evidence_level"):  # 表示这条文献和当前育种建议之间的支持强度
            lines.append(f"证据等级：{evidence['evidence_level']}")
        if evidence.get("curation_note"):
            lines.append(f"人工确认说明：{evidence['curation_note']}")
        if evidence.get("note"):
            lines.append(f"备注：{evidence['note']}")
    return lines


# 育种建议 Markdown 生成层  把前面各种文件解析结果，拼成一篇 Markdown 育种建议
def _build_advice_markdown(
    *,  # 表示后面的参数必须用关键字传入，不能靠位置传入
    trait: str,  # FIXME：来源于用户输入的 当前性状，比如“黄酮相关”
    significant_de_path: Path | None,  # DEG结果路径 来源于转录组流程
    de_support: dict[str, Any],  # DEG 是否支持目标基因
    gff_hit: dict[str, Any],  # GFF 是否找到目标基因
    annotation_hit: dict[str, Any],  # 功能注释是否找到目标基因
    metabolome_summary: dict[str, Any],  # 代谢组是否有代谢组关键词（如黄酮）
    literature_evidence: list[dict[str, str]],  # DOI 和 引用原句
) -> str:
    # 这里负责把“文件解析得到的证据”组织成可展示的育种建议。
    # 它生成的是建议文本，不是实验结论；所有表述都必须保留 smoke demo 边界。

    # 构造转录组证据句子  TODO：之后可以进行多组学的泛式编排优化
    # 如果在 significant_de_genes.tsv 中检出目标基因
    if de_support.get("supports_target_gene"):
        de_sentence = (
            f"转录组结果文件 `{significant_de_path}` 中检出 {TARGET_GENE}，"
            "可作为 smoke 范式下的候选转录组证据。"   # 这里措辞是“候选转录组证据”，不是“已证明功能”。
        )
    # 如果 DEG 文件存在但没有检出目标基因
    elif de_support.get("available"):
        de_sentence = (
            f"当前 `significant_de_genes.tsv` 未检出 {TARGET_GENE}；"
            "建议仍需如实标记为待进一步验证的候选线索。"
        )
    # DEG 文件不存在
    else:
        de_sentence = "当前尚未获得 `significant_de_genes.tsv`，不能判断转录组是否支持 Si9g037800。"

    # 构造参考信息句子  定位：参考基因组是信息池，只做文件检索，不做智能分析。
    ref_sentences = []
    # 检查 GFF 是否找到了目标基因
    if gff_hit.get("found"):
        ref_sentences.append(f"`genome.gff` 中找到 {TARGET_GENE} 相关记录。")
    else:
        ref_sentences.append(f"`genome.gff` 中未找到 {TARGET_GENE}，不能编造基因位置。")
    # 检查功能注释
    if annotation_hit.get("found"):
        ref_sentences.append(f"`xiaomi_T2T_Annotation.smoke_genes.txt` 中找到 {TARGET_GENE} 相关注释记录。")
    else:
        ref_sentences.append(f"`xiaomi_T2T_Annotation.smoke_genes.txt` 中未找到 {TARGET_GENE}，不能编造功能注释。")

    # 构造代谢组证据句子
    # FIXME：如果代谢组里有黄酮关键词  （后续应泛化）
    if metabolome_summary.get("flavonoid_related"):
        metabolome_sentence = (
            "代谢组原始表中出现黄酮相关字段或名称，可作为黄酮相关背景证据，"
            "但不能证明 Si9g037800 到代谢物变化的因果关系。"
        )
    else:
        metabolome_sentence = (
            "代谢组原始表暂未在表头或前 20 行样本中识别到明确黄酮关键词；"
            "仍只能作为待解析的背景输入。"
        )

    # 旧逻辑保留供学习对照：
    # old:
    # background_only = literature_evidence and all(
    #     evidence.get("evidence_level") != "gene_specific" for evidence in literature_evidence
    # )
    #
    # 旧逻辑的问题：
    # advice 组装层仍然依赖 gene_specific 这个旧标签，
    # 但本轮已经把 evidence_level 统一成 high / medium / background。
    # 如果这里不一起收口，就会把 high / medium 也误判成 background_only。
    #
    # 新逻辑：
    # 只有当所有文献条目都被归一化为 background 时，才补“当前文献证据均为背景证据”的边界句。
    background_only = literature_evidence and all(
        evidence.get("evidence_level") == "background" for evidence in literature_evidence
    )

    # 组装完整 MarkDown  用列表按行存放 md  TODO：后续是否进行泛化优化？
    advice_lines = [
        "# 黄酮相关育种建议",
        "",
        "## 性状目标",
        f"当前性状输入为：{trait}。本轮建议围绕黄酮相关性状展开，且仅代表 smoke 测试范式下的初步建议。",
        "",
        "## 候选基因与参考信息",
        f"核心关注基因：{TARGET_GENE}。",
        *[f"- {line}" for line in ref_sentences],
        "",
        "## 转录组证据",
        de_sentence,
        "",
        "## 代谢组证据",
        metabolome_sentence,
        "代谢组证据只能作为黄酮相关背景证据，不能写成湿实验验证或因果验证。",
        "",
        *_render_literature_lines(literature_evidence),  # _render_literature_lines 返回的多行文献证据插入到完整的md
        "",
        "## 育种建议",   # FIXME：智能体建议的模板化表达
        f"- 将 {TARGET_GENE} 作为黄酮相关候选基因线索之一，但根据转录组和注释证据强弱动态调整优先级。",
        "- 构建或扩大群体，系统采集基因型数据和黄酮含量表型。",
        "- 在群体中开展候选基因/候选位点与黄酮含量的关联分析。",
        "- 在获得可靠候选变异后，再开展 KASP/CAPS 或其他标记转化与验证设计。",
        "",
        "## 边界",
        "本结果来自 smoke 测试流程，不是生产级全基因组结论。",
        "当前只提出群体构建、表型测定、关联分析和标记验证计划，这些验证仍待后续执行。",
    ]
    # 对照上面的判断文献是否只是背景证据
    if background_only:
        advice_lines.append("当前文献证据均为背景证据，不是 Si9g037800 直接功能验证。")
    # 最后，将列表按换行符拼成完整的 md 字符串
    return "\n".join(advice_lines)

# 最终审核守卫层
def _guard_advice(advice: str, *, known_dois: set[str] | None = None) -> dict[str, Any]:
    # 这是最终输出守卫：不让 Agent 文本越过当前 demo 能力边界。
    # 重点检查目标基因、群体、黄酮、DOI 真实性，以及是否误称验证已经完成。

    # 已验证文献证据中的DOI集合
    known_dois = known_dois or set()
    # 检查是否有生产级表述  会匹配 生产级、production-grade、全基因组结论、可直接用于育种等过度描述
    production_wording = bool(PRODUCTION_CLAIM_PATTERN.search(advice))
    # 允许表述
    explicit_smoke_boundary = (
        "不是生产级全基因组结论" in advice
        or "非生产级" in advice
        or "not production-grade" in advice.lower()
    )
    # 检查关键字段  最终文本是否包含：候选基因、群体、黄酮等要求的硬性输出字段   TODO：后续需对此进行泛化
    checks = {
        "contains_target_gene": TARGET_GENE in advice,
        "contains_population": "群体" in advice,
        "contains_flavonoid": "黄酮" in advice,
        "has_literature_placeholder": (
            "真实 DOI：待文献检索补充" in advice and "引用原文：待文献检索补充" in advice
        ),
        # 检查是否误称已完成验证  防止声称完成：群体验证、湿实验验证   当前项目只能说“建议后续验证操作”
        "claims_population_validation_completed": bool(POPULATION_VALIDATED_PATTERN.search(advice)),
        "claims_wet_lab_completed": bool(WET_LAB_VALIDATED_PATTERN.search(advice)),
        "claims_marker_development_completed": bool(MARKER_COMPLETED_PATTERN.search(advice)),
        "claims_final_breeding_conclusion": bool(FINAL_BREEDING_CONCLUSION_PATTERN.search(advice)),
        # 有生产级相关词，并且没有明确否定，才算越界。
        "claims_production_grade": production_wording and not explicit_smoke_boundary,
    }

    # 检查 DOI 是否有证据支持  先找出 advice 中所有的DOI，然后检查这些DOI是否都在 known_dois 已验证的文献证据中
    doi_matches = DOI_PATTERN.findall(advice)
    unsupported_dois = [doi for doi in doi_matches if doi not in known_dois]
    checks["has_unsupported_doi"] = bool(unsupported_dois)  # 如果有 unsupported DOI，后面会报错

    # 生成 errors 和 warnings
    errors: list[str] = []
    warnings: list[str] = []
    if not checks["contains_target_gene"]:
        errors.append(f"Advice must contain {TARGET_GENE}.")
    if not checks["contains_population"]:
        errors.append("Advice must contain 群体.")
    if not checks["contains_flavonoid"]:
        errors.append("Advice must contain 黄酮.")
    if checks["has_unsupported_doi"]:
        errors.append(f"Advice contains DOI not backed by retrieved literature: {unsupported_dois}.")
    if checks["claims_population_validation_completed"]:
        errors.append("Advice appears to claim completed population validation.")
    if checks["claims_wet_lab_completed"]:
        errors.append("Advice appears to claim completed wet-lab validation.")
    if checks["claims_marker_development_completed"]:
        errors.append("Advice appears to claim completed KASP/CAPS marker development.")
    if checks["claims_final_breeding_conclusion"]:
        errors.append("Advice appears to claim a final breeding conclusion.")
    if checks["claims_production_grade"]:
        warnings.append("Advice contains production-grade wording; smoke results must remain preliminary.")
    if not checks["has_literature_placeholder"] and not doi_matches:
        warnings.append("No real DOI found; placeholder should be shown.")

    # 返回 guard 结果，写入 guard_result.json
    return {
        "passed": not errors,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "unsupported_dois": unsupported_dois,
    }



"""
业务执行编排层
_run_reference_prepare_impl
_run_transcriptome_deg_impl
_run_metabolome_prepare_impl
_run_literature_evidence_impl
_run_breeding_advice_generate_impl
_run_validation_plan_impl
"""

# 参考信息业务执行层 是 breeding_reference_prepare 这个 Tool 的内部实现
def _run_reference_prepare_impl(
    *,
    data_dir: str,
    genome_fa: str,
    genome_gff: str,
    annotation_txt: str,
    out_dir: str,
) -> dict[str, Any]:
    # FIXME： 参考信息阶段是在准备“信息池/标准”，只做“文件存在性 + 目标基因痕迹检查”。
    # 这里不做 LLM 智能分析，避免把参考信息池和后续整合建议混在一起。

    # 检查数据目录
    data_path, error = _ensure_data_dir(data_dir)
    if error:
        return error

    # 检查输出目录
    out_path, out_error = _ensure_out_dir(out_dir)
    if out_error:
        return {"status": "error", "error": out_error, "artifacts": []}

    # 拼接参考文件路径
    genome_fa_path = data_path / genome_fa
    genome_gff_path = data_path / genome_gff
    annotation_path = data_path / annotation_txt
    # 检查是否缺文件
    missing_inputs = [str(path) for path in (genome_fa_path, genome_gff_path, annotation_path) if not path.exists()]

    # 在 GFF 和 注释文件中 字符串检索目标基因
    gff_hit = _lookup_gene_in_text(genome_gff_path, TARGET_GENE)
    annotation_hit = _lookup_gene_in_text(annotation_path, TARGET_GENE)
    # 写 reference_manifest.Jjson，即记录运行步骤
    manifest_path = out_path / "reference_manifest.json"
    manifest = {
        "tool": "breeding_reference_prepare",  # 记录使用了哪个tool
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "completed" if not missing_inputs else "error",
        "data_dir": str(data_path),
        "genome_fa": str(genome_fa_path),
        "genome_gff": str(genome_gff_path),
        "annotation_txt": str(annotation_path),
        "gene_id": TARGET_GENE,
        "gene_found_in_gff": gff_hit["found"],  # 是否在gff中找到目标基因
        "gene_found_in_annotation": annotation_hit["found"],
        "missing_inputs": missing_inputs,
    }
    _write_json(manifest_path, manifest)
    # 返回结构化结果 给 agent 或 后续工具使用
    return {
        "status": manifest["status"],
        "manifest": str(manifest_path),
        "gene_found_in_gff": gff_hit["found"],
        "gene_found_in_annotation": annotation_hit["found"],
        "gff_matches": gff_hit["matches"],
        "annotation_matches": annotation_hit["matches"],
        "missing_inputs": missing_inputs,
        "artifacts": [str(manifest_path)],
    }


# 转录组业务执行层 是转录组tool的核心
def _run_transcriptome_deg_impl(
    *,
    data_dir: str,
    fq_dir: str,
    sample_map: str,
    genome_fa: str,
    genome_gff: str,
    out_dir: str,
    threads: int,
    run_pipeline: bool,
) -> dict[str, Any]:
    # 这一段是转录组 Tool 的核心编排：
    # 1. 检查输入文件和外部软件
    # 2. 需要时调用固定脚本
    # 3. 回收 significant_de_genes.tsv 并检查目标基因是否出现
    #
    # - fq 文件只是转录组打捞流程的输入工具；
    # - 真正的“信息打捞”由固定脚本和 hisat2/samtools/featureCounts/Rscript 完成；
    # - LLM 不能替代这条固定生信流程。

    out_path, out_error = _ensure_out_dir(out_dir)
    if out_error:
        return {"status": "error", "error": out_error, "artifacts": []}
    run_log = out_path / "run.log"
    # 检查目录
    data_path, error = _ensure_data_dir(data_dir)
    if error:
        run_log.write_text(
            "\n".join(
                [
                    f"timestamp: {datetime.now(timezone.utc).isoformat()}",
                    f"data_dir: {Path(data_dir).expanduser()}",
                    "final_status: error",
                    f"error: {error['error']}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            **error,
            "pipeline_log_path": str(run_log),
            "artifacts": [str(run_log)],
        }

    fq_path = data_path / fq_dir
    sample_map_path = data_path / sample_map
    genome_fa_path = data_path / genome_fa
    genome_gff_path = data_path / genome_gff
    script_path, resolved_script_path = _resolve_transcriptome_pipeline_script(data_path)
    sample_map_normalization = _normalize_sample_map(
        sample_map_path=sample_map_path,
        out_dir=out_path,
    )
    normalized_sample_map_path = str(sample_map_normalization.get("normalized_path") or "")
    compatible_sample_map_path = str(sample_map_normalization.get("compatible_path") or "")
    pipeline_sample_map_path = compatible_sample_map_path or normalized_sample_map_path
    pipeline_sample_map_arg = ""
    if pipeline_sample_map_path:
        try:
            pipeline_sample_map_arg = str(Path(pipeline_sample_map_path).relative_to(data_path))
        except ValueError:
            pipeline_sample_map_arg = pipeline_sample_map_path

    missing_inputs = [str(path) for path in (sample_map_path, genome_fa_path, genome_gff_path) if not path.exists()]
    fastq_files: list[Path] = []
    if fq_path.exists():
        for pattern in ("*.fq.gz", "*.fastq.gz", "*.fq", "*.fastq"):
            fastq_files.extend(sorted(fq_path.glob(pattern)))
    if not fastq_files:
        missing_inputs.append(str(fq_path / "*.fq.gz"))

    pipeline_result = {
        "attempted": False,
        "returncode": None,
        "stdout_tail": "",
        "stderr_tail": "",
        "error": "",
        "resolved_script_path": resolved_script_path or "",
        "command": [],
    }
    missing_tools: list[str] = []
    missing_r_packages: list[str] = []
    dependency_diagnostics: dict[str, Any] = {
        "runner": _transcriptome_pipeline_runner(),
        "mode": "runner" if _transcriptome_pipeline_runner() else "current_path",
        "runner_info": _resolve_pipeline_runner(),
        "checks": {},
        "r_package_checks": {},
    }
    transcriptome_pipeline_status = "not_enough_inputs"
    transcriptome_pipeline_decision_reason = "missing_required_inputs" if missing_inputs else ""
    sample_map_parse_error = str(sample_map_normalization.get("parse_error") or "").strip()

    def _write_pipeline_log(final_status: str) -> None:
        if (dependency_diagnostics.get("runner_info") or {}).get("executable_not_found"):
            next_step_hint = (
                'Use an absolute micromamba path, e.g. export TRANSCRIPTOME_PIPELINE_RUNNER="$(command -v micromamba) run -n rnaseq_deg"'
            )
        elif missing_tools or missing_r_packages:
            next_step_hint = (
                "Install required bioinformatics tools in the configured runner environment, "
                "for example rnaseq_deg, or set TRANSCRIPTOME_PIPELINE_RUNNER to a valid environment."
            )
        else:
            next_step_hint = "Review final_command, stdout/stderr, and the fixed pipeline script output."
        dependency_check_commands = [
            check.get("command_display") or " ".join(check.get("command") or [])
            for check in dependency_diagnostics.get("checks", {}).values()
        ]
        dependency_check_results_lines: list[str] = []
        for check in dependency_diagnostics.get("checks", {}).values():
            dependency_check_results_lines.extend(
                [
                    f"  - tool: {check.get('tool')}",
                    f"    command: {check.get('command_display') or ''}",
                    f"    returncode: {check.get('returncode')}",
                    f"    available: {str(bool(check.get('available'))).lower()}",
                    f"    stdout_tail: {check.get('stdout_tail') or ''}",
                    f"    stderr_tail: {check.get('stderr_tail') or ''}",
                    f"    exception: {check.get('exception') or ''}",
                    f"    runner_executable_not_found: {check.get('runner_executable_not_found') or ''}",
                ]
            )
        if dependency_diagnostics.get("r_package_checks"):
            for package_name, check in dependency_diagnostics["r_package_checks"].items():
                dependency_check_commands.append(
                    check.get("command_display") or " ".join(check.get("command") or [])
                )
                dependency_check_results_lines.extend(
                    [
                        f"  - tool: Rpackage:{package_name}",
                        f"    command: {check.get('command_display') or ''}",
                        f"    returncode: {check.get('returncode')}",
                        f"    available: {str(bool(check.get('available'))).lower()}",
                        f"    stdout_tail: {check.get('stdout_tail') or ''}",
                        f"    stderr_tail: {check.get('stderr_tail') or ''}",
                        f"    exception: {check.get('exception') or ''}",
                        f"    runner_executable_not_found: {check.get('runner_executable_not_found') or ''}",
                    ]
                )
        run_log.write_text(
            "\n".join(
                [
                    f"timestamp: {datetime.now(timezone.utc).isoformat()}",
                    f"data_dir: {data_path}",
                    f"upload_root: {data_path}",
                    f"discovered_fastq_count: {len(fastq_files)}",
                    f"discovered_sample_map_path: {sample_map_path}",
                    f"sample_map_original_path: {sample_map_path}",
                    f"normalized_sample_map_path: {normalized_sample_map_path}",
                    f"compatible_sample_map_path: {compatible_sample_map_path}",
                    f"normalized_sample_map_preview: {json.dumps(sample_map_normalization.get('preview') or [], ensure_ascii=False)}",
                    f"sample_map_normalization_status: {sample_map_normalization.get('status') or ''}",
                    f"sample_map_columns: {json.dumps(sample_map_normalization.get('columns') or [], ensure_ascii=False)}",
                    f"sample_map_rows: {int(sample_map_normalization.get('row_count') or 0)}",
                    f"bad_sample_map_rows: {json.dumps(sample_map_normalization.get('bad_rows') or [], ensure_ascii=False)}",
                    f"original_group_values: {json.dumps(sample_map_normalization.get('original_group_values') or [], ensure_ascii=False)}",
                    f"group_mapping: {json.dumps(sample_map_normalization.get('group_mapping') or {}, ensure_ascii=False)}",
                    f"pipeline_group_mode: {sample_map_normalization.get('pipeline_group_mode') or ''}",
                    f"sample_map_parse_error: {sample_map_parse_error}",
                    f"discovered_reference_genome_path: {genome_fa_path}",
                    f"discovered_genome_gff_path: {genome_gff_path}",
                    f"transcriptome_pipeline_runner: {dependency_diagnostics.get('runner') or ''}",
                    f"resolved_pipeline_runner_args: {json.dumps((dependency_diagnostics.get('runner_info') or {}).get('resolved_args') or [], ensure_ascii=False)}",
                    f"resolved_pipeline_runner_executable: {(dependency_diagnostics.get('runner_info') or {}).get('resolved_executable') or ''}",
                    f"runner_resolution_attempts: {json.dumps((dependency_diagnostics.get('runner_info') or {}).get('resolution_attempts') or [], ensure_ascii=False)}",
                    f"runner_executable_not_found: {(dependency_diagnostics.get('runner_info') or {}).get('executable_not_found') or ''}",
                    f"dependency_check_mode: {dependency_diagnostics.get('mode') or 'current_path'}",
                    f"dependency_check_commands: {json.dumps(dependency_check_commands, ensure_ascii=False)}",
                    f"resolved_pipeline_script_path: {resolved_script_path or ''}",
                    f"missing_inputs: {', '.join(missing_inputs)}",
                    f"missing_tools: {', '.join(missing_tools)}",
                    f"missing_r_packages: {', '.join(missing_r_packages)}",
                    f"command: {' '.join(pipeline_result.get('command') or [])}",
                    f"final_command: {' '.join(pipeline_result.get('command') or [])}",
                    f"returncode: {pipeline_result.get('returncode')}",
                    f"transcriptome_pipeline_status: {transcriptome_pipeline_status}",
                    f"transcriptome_pipeline_decision_reason: {transcriptome_pipeline_decision_reason}",
                    f"final_status: {final_status}",
                    f"next_step_hint: {next_step_hint}",
                    "",
                    "=== stdout_tail ===",
                    str(pipeline_result.get("stdout_tail") or ""),
                    "",
                    "=== stderr_tail ===",
                    str(pipeline_result.get("stderr_tail") or ""),
                    "",
                    "=== pipeline_error ===",
                    str(pipeline_result.get("error") or ""),
                    "",
                    "dependency_check_results:",
                    *dependency_check_results_lines,
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    # 运行固定脚本判断
    if run_pipeline and not missing_inputs:
        if script_path is None:
            transcriptome_pipeline_status = "failed"
            transcriptome_pipeline_decision_reason = "pipeline_script_not_found"
            pipeline_result["error"] = "pipeline_script_missing"
        elif sample_map_normalization.get("status") != "completed":
            transcriptome_pipeline_status = "failed"
            transcriptome_pipeline_decision_reason = "sample_map_parse_error"
            pipeline_result["error"] = sample_map_parse_error or "sample_map_parse_error"
        else:
            dependency_diagnostics = _check_pipeline_dependencies(data_dir=data_path)
            missing_tools = list(dependency_diagnostics.get("missing_tools") or [])
            missing_r_packages = list(dependency_diagnostics.get("missing_r_packages") or [])
            if missing_tools or missing_r_packages:
                transcriptome_pipeline_status = "failed"
                transcriptome_pipeline_decision_reason = "pipeline_dependencies_missing"
            else:
                pipeline_result = _run_transcriptome_pipeline(
                    data_path,
                    out_path,
                    threads,
                    run_log,
                    fq_dir=fq_dir,
                    sample_map=pipeline_sample_map_arg,
                    genome_fa=genome_fa,
                    genome_gff=genome_gff,
                )
                resolved_script_path = str(
                    pipeline_result.get("resolved_script_path") or resolved_script_path or ""
                )
                transcriptome_pipeline_status = (
                    "completed" if pipeline_result.get("returncode") == 0 else "failed"
                )
                transcriptome_pipeline_decision_reason = "pipeline_executed"
    elif not run_pipeline:
        transcriptome_pipeline_status = "skipped_existing_deg_request"
        transcriptome_pipeline_decision_reason = "run_pipeline_disabled"

    # 查找 DEG 文件
    preferred = out_path / "de_pipeline_out" / "04_de" / "significant_de_genes.tsv"
    significant_de_path = _find_significant_de_genes(data_path, out_path, preferred=preferred)
    # 复制 DEG 文件
    copied_de_path = _copy_significant_de_genes(significant_de_path, out_path)
    copied_all_genes_path = _copy_optional_pipeline_table(
        filename="all_genes.tsv",
        data_dir=data_path,
        out_dir=out_path,
    )
    # 检查目标基因是否出现
    de_support = _inspect_de_support(copied_de_path or significant_de_path, TARGET_GENE)

    # 判断状态
    if copied_de_path or significant_de_path:  # 找到DEG文件
        status = "completed"
        transcriptome_pipeline_status = "completed"
    elif missing_inputs:  # 缺输入文件
        status = "error"
    elif run_pipeline and script_path is None:
        status = "error"
    elif run_pipeline and (missing_tools or missing_r_packages):  # 缺生信软件工具（hisat2/samtools等）
        status = "error"
    elif run_pipeline and pipeline_result.get("returncode") not in {0, None}:  # 脚本返回非0
        status = "error"
    else:  # 其余情况
        status = "error"
        if not transcriptome_pipeline_decision_reason:
            transcriptome_pipeline_decision_reason = "deg_not_generated"

    # 写对应json日志
    manifest_path = out_path / "transcriptome_manifest.json"
    manifest = {
        "tool": "breeding_transcriptome_deg",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "transcriptome_pipeline_status": transcriptome_pipeline_status,
        "transcriptome_pipeline_decision_reason": transcriptome_pipeline_decision_reason,
        "data_dir": str(data_path),
        "fq_dir": str(fq_path),
        "sample_map": str(sample_map_path),
        "sample_map_original_path": str(sample_map_path),
        "normalized_sample_map_path": normalized_sample_map_path,
        "compatible_sample_map_path": compatible_sample_map_path,
        "normalized_sample_map_preview": sample_map_normalization.get("preview") or [],
        "sample_map_normalization_status": sample_map_normalization.get("status") or "",
        "sample_map_columns": sample_map_normalization.get("columns") or [],
        "sample_map_rows": int(sample_map_normalization.get("row_count") or 0),
        "bad_sample_map_rows": sample_map_normalization.get("bad_rows") or [],
        "original_group_values": sample_map_normalization.get("original_group_values") or [],
        "group_mapping": sample_map_normalization.get("group_mapping") or {},
        "pipeline_group_mode": sample_map_normalization.get("pipeline_group_mode") or "",
        "sample_map_parse_error": sample_map_parse_error,
        "genome_fa": str(genome_fa_path),
        "genome_gff": str(genome_gff_path),
        "resolved_pipeline_script_path": resolved_script_path or "",
        "run_pipeline": run_pipeline,
        "threads": threads,
        "missing_inputs": missing_inputs,
        "missing_tools": missing_tools,
        "missing_r_packages": missing_r_packages,
        "transcriptome_pipeline_runner": dependency_diagnostics.get("runner") or "",
        "dependency_check_mode": dependency_diagnostics.get("mode") or "current_path",
        "dependency_diagnostics": dependency_diagnostics,
        "pipeline_result": pipeline_result,
        "significant_de_genes_path": str(copied_de_path or significant_de_path or ""),
        "all_genes_path": str(copied_all_genes_path or ""),
        "target_gene_found": de_support["supports_target_gene"],
        "target_gene_matches": de_support["matches"],
    }
    _write_pipeline_log(status)
    _write_json(manifest_path, manifest)
    _write_json(out_path / "manifest.json", manifest)

    artifacts = [str(manifest_path), str(out_path / "manifest.json"), str(run_log)]
    if copied_de_path or significant_de_path:
        artifacts.insert(0, str(copied_de_path or significant_de_path))
    if copied_all_genes_path:
        artifacts.insert(1, str(copied_all_genes_path))

    return {
        "status": status,
        "manifest": str(manifest_path),
        "significant_de_genes_path": str(copied_de_path or significant_de_path or ""),
        "all_genes_path": str(copied_all_genes_path or ""),
        "target_gene_found": de_support["supports_target_gene"],
        "matches": de_support["matches"],
        "missing_inputs": missing_inputs,
        "missing_tools": missing_tools,
        "missing_r_packages": missing_r_packages,
        "pipeline_result": pipeline_result,
        "pipeline_log_path": str(run_log),
        "transcriptome_pipeline_status": transcriptome_pipeline_status,
        "transcriptome_pipeline_decision_reason": transcriptome_pipeline_decision_reason,
        "resolved_pipeline_script_path": resolved_script_path or "",
        "transcriptome_pipeline_runner": dependency_diagnostics.get("runner") or "",
        "dependency_check_mode": dependency_diagnostics.get("mode") or "current_path",
        "dependency_diagnostics": dependency_diagnostics,
        "sample_map_original_path": str(sample_map_path),
        "normalized_sample_map_path": normalized_sample_map_path,
        "compatible_sample_map_path": compatible_sample_map_path,
        "normalized_sample_map_preview": sample_map_normalization.get("preview") or [],
        "sample_map_normalization_status": sample_map_normalization.get("status") or "",
        "sample_map_columns": sample_map_normalization.get("columns") or [],
        "sample_map_rows": int(sample_map_normalization.get("row_count") or 0),
        "bad_sample_map_rows": sample_map_normalization.get("bad_rows") or [],
        "original_group_values": sample_map_normalization.get("original_group_values") or [],
        "group_mapping": sample_map_normalization.get("group_mapping") or {},
        "pipeline_group_mode": sample_map_normalization.get("pipeline_group_mode") or "",
        "sample_map_parse_error": sample_map_parse_error,
        "artifacts": artifacts,
    }


# 代谢组业务执行层
def _run_metabolome_prepare_impl(*, data_dir: str, metabolome_tsv: str, trait: str, out_dir: str) -> dict[str, Any]:
    # FIXME：代谢组阶段当前只做轻量读取，定位黄酮相关字段或名称，作为背景证据。
    # 它不产生因果证明，也不直接证明 Si9g037800 的功能。

    # 检查目录
    data_path, error = _ensure_data_dir(data_dir)
    if error:
        return error

    out_path, out_error = _ensure_out_dir(out_dir)
    if out_error:
        return {"status": "error", "error": out_error, "artifacts": []}

    # 拼接输入文件路径
    metabolome_path = data_path / metabolome_tsv
    summary = _inspect_metabolome(metabolome_path)
    status = "completed" if summary["exists"] else "error"

    # 写日志
    manifest_path = out_path / "metabolome_manifest.json"
    manifest = {
        "tool": "breeding_metabolome_prepare",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "data_dir": str(data_path),
        "trait": trait,
        "metabolome_tsv": str(metabolome_path),
        "flavonoid_related": summary["flavonoid_related"],
        "matched_terms": summary["matched_terms"],
        "columns": summary["columns"],
        "sample_rows": summary["sample_rows"],
        # 防止把代谢组背景证据说成因果验证
        "note": "代谢组信号只能作为黄酮相关背景证据，不能证明 Si9g037800 的因果关系。",
    }
    _write_json(manifest_path, manifest)
    return {
        "status": status,
        "manifest": str(manifest_path),
        "metabolome_tsv": str(metabolome_path),
        "flavonoid_related": summary["flavonoid_related"],
        "matched_terms": summary["matched_terms"],
        "columns": summary["columns"],
        "sample_rows": summary["sample_rows"],
        "artifacts": [str(manifest_path)],
    }


# 文献证据业务执行层
def _run_literature_evidence_impl(
    *,
    data_dir: str,
    literature_evidence: str,
    trait: str,
    gene_id: str,
    out_dir: str,
) -> dict[str, Any]:
    # 文献阶段的价值在于给前端和最终回答提供“可追溯 DOI + 原句”。
    # 当前 smoke 数据里的证据是背景证据，不应被解释成 Si9g037800 已直接功能验证。

    # 检查目录
    data_path, error = _ensure_data_dir(data_dir)
    if error:
        return error

    out_path, out_error = _ensure_out_dir(out_dir)
    if out_error:
        return {"status": "error", "error": out_error, "artifacts": []}

    # 关键调用
    evidence_entries, evidence_path = _load_verified_literature_evidence(
        data_path,
        trait,
        literature_filename=literature_evidence,
        gene_id=gene_id,
    )
    # FIXME：统计证据等级
    evidence_level_counts: dict[str, int] = {}
    for entry in evidence_entries:
        level = entry.get("evidence_level") or "unknown"
        evidence_level_counts[level] = evidence_level_counts.get(level, 0) + 1

    # 旧逻辑保留供学习对照：
    # old:
    # background_only = evidence_entries and all(entry.get("evidence_level") != "gene_specific" for entry in evidence_entries)
    #
    # 旧逻辑的问题：
    # 旧代码依赖 gene_specific 这种内部写法，和本轮统一的 high / medium / background 三档不一致。
    # 新逻辑直接基于归一化后的 evidence_level 判断“是否全部为背景证据”，便于前端和组会统一解释。
    background_only = evidence_entries and all(
        entry.get("evidence_level") == "background" for entry in evidence_entries
    )
    status = "completed" if evidence_entries else "pending_literature"
    manifest_path = out_path / "literature_manifest.json"
    manifest = {
        "tool": "breeding_literature_evidence",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "data_dir": str(data_path),
        "literature_evidence_path": str(evidence_path),
        "gene_id": gene_id,
        "trait": trait,
        "evidence_count": len(evidence_entries),
        "evidence_level_counts": evidence_level_counts,
        "background_only": background_only,
        "note": (
            "当前文献证据均为背景证据，不是 Si9g037800 直接功能验证。"  # 当文献证据均被判断为背景证据
            if background_only
            else "若后续补入更强文献证据，再更新 direct evidence 判断。"
        ),
        "entries": evidence_entries,
    }
    _write_json(manifest_path, manifest)
    return {
        "status": status,
        "manifest": str(manifest_path),
        "literature_evidence_path": str(evidence_path),
        "entries": evidence_entries,
        "evidence_level_counts": evidence_level_counts,
        "background_only": background_only,
        "artifacts": [str(manifest_path)],
    }


# 最终建议总封装层，是多组学整合和建议生成的总装函数。
# 它把参考信息、转录组、代谢组、文献证据汇总，生成 advice，再用 guard 检查边界。
# FIXME：是最接近“智能体整合”的后端实现部分。
def _run_breeding_advice_generate_impl(
    *,
    data_dir: str,
    trait: str,
    reference_manifest: str,
    transcriptome_manifest: str,
    metabolome_manifest: str,
    literature_manifest: str,
    significant_de_genes: str,
    out_dir: str,
) -> dict[str, Any]:
    # 建议生成阶段是总装配：
    # - 读取前面各步骤的 manifest 或直接回退执行轻量检查
    # - 汇总文件证据
    # - 生成建议 markdown
    # - 再经过 guard，防止输出越界
    #
    # 真正需要 Agent/LLM 参与的是“如何整合这些已打捞到的信息并组织建议”。
    # 但即使进入建议阶段，也不能编造 DOI、引用原句或已完成验证的结论。

    # 检查目录
    data_path, error = _ensure_data_dir(data_dir)
    if error:
        return {
            **error,
            "advice_markdown": "",
            "guard_result": {"passed": False, "errors": ["missing data_dir"]},
        }

    out_path, out_error = _ensure_out_dir(out_dir)
    if out_error:
        return {
            "status": "error",
            "error": out_error,
            "advice_markdown": "",
            "guard_result": {"passed": False, "errors": ["cannot create out_dir"]},
            "artifacts": [],
        }

    # 读取 或 回退生成reference_payload执行上游模块
    # 如果用户传了 reference_manifest，并且能读取，就复用它；
    # 否则就现场执行 _run_reference_prepare_impl。
    reference_payload = _load_json_if_present(reference_manifest) or _run_reference_prepare_impl(
        data_dir=str(data_path),
        genome_fa=REQUIRED_FILES["genome_fa"],
        genome_gff=REQUIRED_FILES["genome_gff"],
        annotation_txt=REQUIRED_FILES["annotation"],
        out_dir=str(out_path / "reference_prepare"),
    )
    # 读取 或 回退生成transcriptome_payload执行上游模块
    transcriptome_payload = _load_json_if_present(transcriptome_manifest) or _run_transcriptome_deg_impl(
        data_dir=str(data_path),
        fq_dir="fq",
        sample_map=REQUIRED_FILES["sample_map"],
        genome_fa=REQUIRED_FILES["genome_fa"],
        genome_gff=REQUIRED_FILES["genome_gff"],
        out_dir=str(out_path / "transcriptome_deg"),
        threads=8,
        run_pipeline=False,
    )
    # 读取或回退
    metabolome_payload = _load_json_if_present(metabolome_manifest) or _run_metabolome_prepare_impl(
        data_dir=str(data_path),
        metabolome_tsv=REQUIRED_FILES["metabolome"],
        trait=trait,
        out_dir=str(out_path / "metabolome_prepare"),
    )
    # 读取或回退
    literature_payload = _load_json_if_present(literature_manifest) or _run_literature_evidence_impl(
        data_dir=str(data_path),
        literature_evidence=VERIFIED_LITERATURE_EVIDENCE_FILE,
        trait=trait,
        gene_id=TARGET_GENE,
        out_dir=str(out_path / "literature_evidence"),
    )

    # 取出关键文件路径  将上游结果转为实际路径和文献条目
    genome_gff_path = Path(reference_payload.get("genome_gff", data_path / REQUIRED_FILES["genome_gff"]))
    annotation_path = Path(reference_payload.get("annotation_txt", data_path / REQUIRED_FILES["annotation"]))
    metabolome_path = Path(metabolome_payload.get("metabolome_tsv", data_path / REQUIRED_FILES["metabolome"]))
    literature_evidence_entries = literature_payload.get("entries", [])

    # 确定 DEG 文件路径
    # 如果用户显式传了 significant_de_genes，就用用户传的；
    # 否则，如果 transcriptome_payload 里有 significant_de_genes_path，就用它；
    # 否则就是 None。
    significant_de_path = (
        Path(significant_de_genes).expanduser().resolve()
        if significant_de_genes
        else Path(transcriptome_payload["significant_de_genes_path"]).expanduser().resolve()
        if transcriptome_payload.get("significant_de_genes_path")
        else None
    )
    # 虽然前面 payload 里可能已经有部分结果  再次检查提取证据  确保最终advice使用的是实际文件内容
    de_support = _inspect_de_support(significant_de_path, TARGET_GENE)
    gff_hit = _lookup_gene_in_text(genome_gff_path, TARGET_GENE)
    annotation_hit = _lookup_gene_in_text(annotation_path, TARGET_GENE)
    metabolome_summary = _inspect_metabolome(metabolome_path)
    # 生成建议md
    advice = _build_advice_markdown(
        trait=trait,
        significant_de_path=significant_de_path,
        de_support=de_support,
        gff_hit=gff_hit,
        annotation_hit=annotation_hit,
        metabolome_summary=metabolome_summary,
        literature_evidence=literature_evidence_entries,
    )
    # guard 检查，确保把文献TSV中真实存在的DOI传给guard
    known_dois = {entry["doi"] for entry in literature_evidence_entries}
    guard_result = _guard_advice(advice, known_dois=known_dois)

    # 判断最终状态
    status = "completed"
    if not (significant_de_path and significant_de_path.exists()):
        status = "error"  # 没有 DEG 文件
    if not guard_result["passed"]:
        status = "failed_guard" if status == "completed" else status
    elif guard_result.get("warnings"):
        status = "completed_with_warnings"

    # 写三个最终核心输出
    advice_path = out_path / "breeding_advice.md"
    guard_path = out_path / "guard_result.json"
    manifest_path = out_path / "run_manifest.json"
    advice_path.write_text(advice, encoding="utf-8")
    _write_json(guard_path, guard_result)

    copied_de_path = _copy_significant_de_genes(significant_de_path, out_path)
    artifacts = [
        str(path)
        for path in [copied_de_path or significant_de_path, advice_path, guard_path, manifest_path]
        if path is not None
    ]
    manifest = {
        "tool": "breeding_advice_generate",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "data_dir": str(data_path),
        "trait": trait,
        "reference_manifest": reference_payload.get("manifest", reference_manifest),
        "transcriptome_manifest": transcriptome_payload.get("manifest", transcriptome_manifest),
        "metabolome_manifest": metabolome_payload.get("manifest", metabolome_manifest),
        "literature_manifest": literature_payload.get("manifest", literature_manifest),
        "significant_de_genes_path": str(copied_de_path or significant_de_path or ""),
        "artifacts": artifacts,
    }
    _write_json(manifest_path, manifest)

    return {
        "status": status,
        "manifest": str(manifest_path),
        "advice_markdown": advice,
        "significant_de_genes_path": str(copied_de_path or significant_de_path or ""),
        "guard_result": guard_result,
        "artifacts": artifacts,
    }


# 验证计划生成层
def _run_validation_plan_impl(*, trait: str, gene_id: str, marker_types: str, out_dir: str) -> dict[str, Any]:
    # 这里输出的是“下一步验证计划”，不是已完成结果。
    out_path, out_error = _ensure_out_dir(out_dir)
    if out_error:
        return {"status": "error", "error": out_error, "artifacts": []}

    # FIXME：拼接验证计划 md   后续需进行泛化
    plan = "\n".join([
        "# 黄酮相关验证计划",
        "",
        f"- 目标基因：{gene_id}",
        f"- 性状：{trait}",
        f"- 标记类型：{marker_types}",
        "",
        "## 计划步骤",
        "- 构建或扩大群体，覆盖目标基因位点附近的遗传变异。",
        "- 对群体开展基因型检测，优先关注 SNP/InDel/KASP/CAPS 相关候选位点。",
        "- 对群体同步开展黄酮含量表型测定。",
        "- 将基因型与黄酮表型做关联分析，评估候选位点稳定性。",
        "- 对显著候选变异开展进一步确认，决定是否进入后续转化。",
        "- 在确认候选变异后，再推进 KASP/CAPS 标记的后续转化设计。",
        "",
        "## 边界",
        "以上内容是验证计划，不是已完成的群体验证、湿实验验证或最终 KASP/CAPS 标记开发结果。",
    ])
    # 写文件  输出两个计划文件
    plan_path = out_path / "validation_plan.md"
    manifest_path = out_path / "validation_manifest.json"
    plan_path.write_text(plan, encoding="utf-8")
    _write_json(
        manifest_path,
        {
            "tool": "breeding_validation_plan",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
            "trait": trait,
            "gene_id": gene_id,
            "marker_types": marker_types,
            "plan_path": str(plan_path),
        },
    )
    return {
        "status": "completed",
        "manifest": str(manifest_path),
        "validation_plan": plan,
        "artifacts": [str(plan_path), str(manifest_path)],
    }


"""""
YuXi 工具注册入口层
这一层是“对外接口层”：负责把内部能力注册给 YuXi，不负责从零实现全部业务。
用 @tool 把前面已经实现好的内部业务函数 _run_xxx_impl() 包装成 YuXi Agent 可以识别、可以调用、可以在扩展管理页面展示的 Tool
如果以后要改业务逻辑，主要改 _run_xxx_impl()；如果要改前端展示、工具名称、标签、输入 schema，主要改 @tool(...) 这一层。
"""""


'''@tool(...) 是 YuXi 的工具注册装饰器。它告诉 YuXi： 定义函数 + 注册函数 + 描述函数参数 + 告诉前端如何展示
下面这个函数是一个 Tool。
它属于 breeding 分类。
它有“育种、黄酮、参考基因组”这些标签。
它在前端显示名称叫“参考基因组准备”。
它的输入参数结构由 BreedingReferencePrepareInput 定义。
'''
# 参考基因组准备Tool
# FIXME：只是文件检查和文本检索，属于参考信息池检查工具，参考基因组是“信息池/标准”，不能让 LLM 去自由分析或改写。
@tool(
    category="breeding",
    tags=["育种", "黄酮", "参考基因组"],
    display_name="参考基因组准备",
    args_schema=BreedingReferencePrepareInput,
)
def breeding_reference_prepare(
    # 输入
    data_dir: str = DEFAULT_DATA_DIR,
    genome_fa: str = "genome.fa",
    genome_gff: str = "genome.gff",
    annotation_txt: str = "xiaomi_T2T_Annotation.smoke_genes.txt",
    out_dir: str = "/tmp/yuxi_runs/breeding_reference_prepare",
) -> dict[str, Any]:
    """Validate breeding reference files and locate Si9g037800 in the reference annotations.

    什么时候调用：Agent 需要先确认参考信息池里是否存在目标基因痕迹时。
    输入：参考基因组、GFF、注释文本和输出目录。
    输出：reference_manifest，以及目标基因是否在参考注释中出现。
    链路位置：固定信息池准备阶段，不属于智能体整合建议。
    """
    # 实际调用 _run_reference_prepare_impl
    # 告诉后续流程：参考信息池是否齐全？目标基因是否在参考注释中能找到痕迹？
    return _run_reference_prepare_impl(
        data_dir=data_dir,
        genome_fa=genome_fa,
        genome_gff=genome_gff,
        annotation_txt=annotation_txt,
        out_dir=out_dir,
    )


# 转录组差异分析 Tool，固定转录组生信流程封装工具
@tool(
    category="breeding",
    tags=["育种", "黄酮", "转录组"],
    display_name="转录组差异分析",
    args_schema=BreedingTranscriptomeDegInput,
)
def breeding_transcriptome_deg(
    data_dir: str = DEFAULT_DATA_DIR,
    fq_dir: str = "fq",
    sample_map: str = "sampleName_clientId.txt",
    genome_fa: str = "genome.fa",
    genome_gff: str = "genome.gff",
    out_dir: str = "/tmp/yuxi_runs/breeding_transcriptome_deg",
    threads: int = 8,
    run_pipeline: bool = True,
) -> dict[str, Any]:
    """Run or inspect the smoke DEG workflow and summarize whether Si9g037800 is significant.

    什么时候调用：Agent 需要取得转录组 DEG 证据时。
    输入：fq 目录、sample map、参考文件、线程数和是否执行固定脚本。
    输出：transcriptome_manifest、DEG 结果路径、目标基因是否出现在 DEG 中。
    链路位置：固定生信流程阶段；底层结果来自脚本和开源软件，不来自 LLM。
    """
    return _run_transcriptome_deg_impl(
        data_dir=data_dir,
        fq_dir=fq_dir,
        sample_map=sample_map,
        genome_fa=genome_fa,
        genome_gff=genome_gff,
        out_dir=out_dir,
        threads=threads,
        run_pipeline=run_pipeline,
    )


# 代谢组准备 Tool，FIXME：代谢组信息读取工具，当前代谢组视为已经获得的信息，直接读取 metabolome_raw_3372.tsv 即可。
# FIXME：业务意义是说明代谢组中是否出现黄酮相关背景信息。  需泛化
@tool(
    category="breeding",
    tags=["育种", "黄酮", "代谢组"],
    display_name="代谢组准备",
    args_schema=BreedingMetabolomePrepareInput,
)
def breeding_metabolome_prepare(
    data_dir: str = DEFAULT_DATA_DIR,
    metabolome_tsv: str = "metabolome_raw_3372.tsv",
    trait: str = "黄酮相关",
    out_dir: str = "/tmp/yuxi_runs/breeding_metabolome_prepare",
) -> dict[str, Any]:
    """Inspect metabolome input and summarize flavonoid-related background signals.

    什么时候调用：Agent 需要读取代谢组背景输入时。
    输入：代谢组 TSV、性状和输出目录。
    输出：metabolome_manifest、关键词命中情况、样例行。
    链路位置：文件读取阶段；这里只确认黄酮相关背景，不宣称因果验证。
    """
    return _run_metabolome_prepare_impl(
        data_dir=data_dir,
        metabolome_tsv=metabolome_tsv,
        trait=trait,
        out_dir=out_dir,
    )


# 文献证据读取 Tool，已验证文献证据读取工具
@tool(
    category="breeding",
    tags=["育种", "黄酮", "文献"],
    display_name="文献证据读取",
    args_schema=BreedingLiteratureEvidenceInput,
)
def breeding_literature_evidence(
    data_dir: str = DEFAULT_DATA_DIR,
    literature_evidence: str = VERIFIED_LITERATURE_EVIDENCE_FILE,
    trait: str = "黄酮相关",
    gene_id: str = TARGET_GENE,
    out_dir: str = "/tmp/yuxi_runs/breeding_literature_evidence",
) -> dict[str, Any]:
    """Read verified literature evidence and keep background evidence separate from direct gene validation.

    什么时候调用：Agent 需要真实 DOI 和引用原句作为可追溯文献证据时。
    输入：文献 TSV、性状、基因 ID 和输出目录。
    输出：literature_manifest、文献条目列表、背景证据标记。
    链路位置：证据读取阶段；DOI 与原句来自 TSV，不允许大模型编造。
    """
    return _run_literature_evidence_impl(
        data_dir=data_dir,
        literature_evidence=literature_evidence,
        trait=trait,
        gene_id=gene_id,
        out_dir=out_dir,
    )

# 育种建议生成 Tool，多组学证据整合与建议生成工具
@tool(
    category="breeding",
    tags=["育种", "黄酮", "建议"],
    display_name="育种建议生成",
    args_schema=BreedingAdviceGenerateInput,
)
def breeding_advice_generate(
    data_dir: str = DEFAULT_DATA_DIR,
    trait: str = "黄酮相关",
    reference_manifest: str = "",
    transcriptome_manifest: str = "",
    metabolome_manifest: str = "",
    literature_manifest: str = "",
    significant_de_genes: str = "",
    out_dir: str = "/tmp/yuxi_runs/breeding_advice_generate",
) -> dict[str, Any]:
    """Aggregate reference, transcriptome, metabolome and literature results into guarded breeding advice.

    什么时候调用：Agent 已经拿到参考、转录组、代谢组和文献证据，准备生成最终建议时。
    输入：上游 manifest 或直接文件路径、性状和输出目录。
    输出：breeding_advice.md、guard_result.json、run_manifest.json。
    链路位置：多组学信息整合与建议生成阶段；这是最接近“智能体发挥作用”的部分。
    """
    return _run_breeding_advice_generate_impl(
        data_dir=data_dir,
        trait=trait,
        reference_manifest=reference_manifest,
        transcriptome_manifest=transcriptome_manifest,
        metabolome_manifest=metabolome_manifest,
        literature_manifest=literature_manifest,
        significant_de_genes=significant_de_genes,
        out_dir=out_dir,
    )


# 验证计划生成 Tool，后续验证计划生成工具  FIXME：需泛化
@tool(
    category="breeding",
    tags=["育种", "黄酮", "验证计划"],
    display_name="验证计划生成",
    args_schema=BreedingValidationPlanInput,
)
def breeding_validation_plan(
    trait: str = "黄酮相关",
    gene_id: str = TARGET_GENE,
    marker_types: str = "SNP/InDel/KASP/CAPS",
    out_dir: str = "/tmp/yuxi_runs/breeding_validation_plan",
) -> dict[str, Any]:
    """Generate a validation plan for the flavonoid breeding workflow without claiming finished experiments.

    什么时候调用：Agent 需要给出后续验证路线图时。
    输入：性状、基因 ID、标记类型和输出目录。
    输出：validation_plan.md 和 manifest。
    链路位置：最终建议的延伸步骤；只输出计划，不允许写成已完成结果。
    """
    return _run_validation_plan_impl(
        trait=trait,
        gene_id=gene_id,
        marker_types=marker_types,
        out_dir=out_dir,
    )


# FIXME：需优化 交给 Agent 真正调度多个 Tool，支持 Agent 按模块化 Tool 自主规划
# 用户提问
# → Agent 判断需要调用哪些 Tool
# → 调用 reference Tool
# → 调用 transcriptome Tool
# → 调用 metabolome Tool
# → 调用 literature Tool
# → 调用 advice Tool
# → 输出结果

# 一键 smoke 黄酮育种建议 Tool，一键演示包装层 / smoke demo 总入口  FIXME：需泛化
# 当前育种工作台最关键的 Tool，把前面几个业务模块串起来。它显式执行转录组业务层，再调用建议生成业务层。
# 建议生成业务层在缺少上游 manifest 时，会内部回退执行参考信息检查、代谢组读取、文献证据读取等业务层逻辑。
#
# 学习型边界说明：
# 1. 它不是长期主链路，只是组会演示和 smoke test 的一键包装层；
# 2. 它不是完全自主的多工具编排，内部仍然是固定顺序地串联模块；
# 3. 长期方向仍然是把前面的 7 个模块化 Tool 交给受控 Agent 逐步调度。
@tool(
    category="breeding",
    tags=["育种", "黄酮", "smoke"],
    display_name="Smoke 黄酮育种建议",
    args_schema=SmokeFlavonoidBreedingAdviceInput,
)
def smoke_flavonoid_breeding_advice(
    data_dir: str = DEFAULT_DATA_DIR,
    trait: str = "黄酮相关",
    out_dir: str = DEFAULT_OUT_DIR,
    run_transcriptome: bool = True,
) -> dict[str, Any]:
    """Keep the one-click smoke entrypoint while reusing modular flavonoid breeding tools.

    什么时候调用：工作台强制优先调用的一键 smoke 入口。
    输入：data_dir、trait、out_dir 和是否执行转录组固定脚本。
    输出：最终 advice markdown、DEG 路径、代谢组路径和 guard 结果。
    链路位置：模块化 Tool 的包装层，方便 Agent 一次拿到完整黄酮育种建议。
    """
    # 这个 Tool 是当前工作台最重要的一键入口。
    # 理解为“先跑转录组/读取结果，再汇总成最终建议”的包装层。

    # 第一步：先跑或读取转录组 DEG ，调用内部转录组流程
    # 如果 run_transcriptome=True，会尝试跑固定脚本
    # 如果 run_transcriptome=False，通常就是读取已有 significant_de_genes.tsv
    transcriptome_payload = _run_transcriptome_deg_impl(
        data_dir=data_dir,
        fq_dir="fq",
        sample_map=REQUIRED_FILES["sample_map"],
        genome_fa=REQUIRED_FILES["genome_fa"],
        genome_gff=REQUIRED_FILES["genome_gff"],
        out_dir=out_dir,
        threads=8,
        run_pipeline=run_transcriptome,
    )

    # 第二步：如果转录组前置错误，直接返回错误，避免后面继续生成假建议
    if transcriptome_payload.get("status") == "error" and transcriptome_payload.get("error"):
        return {
            "status": "error",
            "error": transcriptome_payload["error"],
            "advice_markdown": "",
            "significant_de_genes_path": "",
            "metabolome_path": "",
            "guard_result": {"passed": False, "errors": ["missing data_dir"]},
            "artifacts": [],
        }

    # 第三步：调用建议生成模块，最终 advice 仍然依赖后续 guard；即使前面文件都在，也不能绕过边界约束。
    # 这里把转录组 manifest 和 DEG 路径传给 advice 生成函数。
    # 其他 manifest 传空字符串，表示：如果没有现成 manifest，advice_generate 内部会自己回退执行轻量检查。
    # 比如它会再去做：参考信息检查、代谢组读取、文献证据读取
    advice_payload = _run_breeding_advice_generate_impl(
        data_dir=data_dir,
        trait=trait,
        reference_manifest="",
        transcriptome_manifest=transcriptome_payload.get("manifest", ""),
        metabolome_manifest="",
        literature_manifest="",
        significant_de_genes=transcriptome_payload.get("significant_de_genes_path", ""),
        out_dir=out_dir,
    )
    data_path, _ = _ensure_data_dir(data_dir)
    metabolome_path = data_path / REQUIRED_FILES["metabolome"] if data_path is not None else Path("")

    # 第四步：整理返回给 Agent / 前端的结果
    result = {
        "status": advice_payload["status"],  # 运行状态
        "advice_markdown": advice_payload["advice_markdown"],  # 最终育种建议
        "significant_de_genes_path": advice_payload["significant_de_genes_path"],  # DEG 文件路径
        "metabolome_path": str(metabolome_path),  # 代谢组文件路径
        "guard_result": advice_payload["guard_result"],  # 输出 guard 结果
        "artifacts": advice_payload["artifacts"],  # 产物文件路径
    }
    # 如果缺底层 hisat2、samtools 等工具，就把状态标成带警告。
    if transcriptome_payload.get("missing_tools"):
        result["missing_tools"] = transcriptome_payload["missing_tools"]
        if result["status"] == "completed":
            result["status"] = "completed_with_warnings"
    return result
