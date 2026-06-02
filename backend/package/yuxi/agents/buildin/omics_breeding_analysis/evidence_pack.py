from __future__ import annotations

import json
from pathlib import Path
from typing import Any

"""
证据数据结构层 / Evidence Pack schema 层 / 证据统一组织层
当前多组学育种分析智能体的 证据标准化层
把已经拿到的多组学证据、文献证据、用户任务信息整理成统一 JSON 结构：
trait + question
+ transcriptome_records
+ literature_records
+ metabolome_context
+ genome_context
↓
omics_evidence_pack.json
它是后续 Citation、Guard、前端溯源展示的共同输入
在数据流中的位置
evidence_adapters.py
  ↓
evidence_pack.py 定义的数据结构
  ↓
citation_engine.py / presentation.py
"""

# 表示哪些任务类型需要后续 群体层面 的验证建议，后续需要在群体中结合基因型和性状数据验证
BREEDING_VALIDATION_INTENTS = {
    "breeding_advice",
    "marker_recommendation",
    "candidate_validation",
}

# FIXME:后续需要由 LLM 判断
def infer_task_intent(question: str) -> str:
    """根据用户问题粗略判断任务类型。

    第一版只做规则判断，后续可交给 LLM 或 TaskFrameBuilder 增强。
    """

    text = question or ""

    if any(keyword in text for keyword in ["标记", "KASP", "CAPS", "SNP", "InDel"]):
        return "marker_recommendation"

    if any(keyword in text for keyword in ["验证", "候选", "关联"]):
        return "candidate_validation"

    if any(keyword in text for keyword in ["育种建议", "建议", "改良", "选育"]):
        return "breeding_advice"

    return "general_analysis"


# 去重 去空值
def _deduplicate_preserve_order(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


# FIXME：从转录组证据里提取目标基因
def extract_target_genes(transcriptome_records: list[dict[str, Any]]) -> list[str]:
    """从转录组证据中提取目标基因。

    注意：
    - 这里不写死任何基因 ID。
    - 当前 smoke 数据可能得到 Si9g037800。
    - 换成其他数据时，应返回其他 gene_id。
    """

    candidates: list[str] = []

    for record in transcriptome_records:
        # 支持三种字段名
        gene_id = record.get("gene_id") or record.get("target_gene") or record.get("id")
        if gene_id:
            candidates.append(str(gene_id))

    return _deduplicate_preserve_order(candidates)


# 构建动态 Guard 要求
def build_guard_requirements(
    *,
    trait: str,
    question: str,
    target_genes: list[str],
    literature_records: list[dict[str, Any]],
    annotation_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建动态 Guard 要求。

    固定的是检查结构，不固定具体基因、性状或关键词。
    """

    # 根据用户问题推断任务类型
    intent = infer_task_intent(question)
    # 没有写死“群体”一定每次都出现，而是根据任务类型动态决定
    requires_population_validation = intent in BREEDING_VALIDATION_INTENTS

    # 告诉后续 Guard 哪些 DOI 是允许的
    allowed_dois = _deduplicate_preserve_order(
        [str(record.get("doi") or "") for record in literature_records]
    )
    # 哪些 quoted_sentence 是允许的
    allowed_quotes = _deduplicate_preserve_order(
        [str(record.get("quoted_sentence") or "") for record in literature_records]
    )

    # 把当前 trait 作为动态性状词
    trait_terms = _deduplicate_preserve_order([trait])
    annotation_gene_ids: list[str] = []
    if annotation_evidence:
        for record in annotation_evidence:
            metadata = record.get("metadata") or {}
            annotation_gene_ids.extend(metadata.get("annotation_candidate_gene_ids") or [])

    # 返回结构 即后续Guard的输入规范，后续按这些规则检查回答
    return {
        "intent": intent,
        "must_mention_target_genes": bool(target_genes),
        "required_gene_ids": target_genes,
        "must_mention_trait": bool(trait_terms),
        "required_trait_terms": trait_terms,
        "must_include_population_validation": requires_population_validation,
        "allowed_dois": allowed_dois,
        "allowed_quoted_sentences": allowed_quotes,
        "annotation_candidate_gene_ids": _deduplicate_preserve_order(annotation_gene_ids),
        "forbidden_claim_types": [
            "fabricated_doi",
            "fabricated_quoted_sentence",
            "completed_population_validation",
            "completed_wet_lab_validation",
            "final_kasp_caps_marker_developed",
            "final_breeding_conclusion_confirmed",
            "annotation_as_wet_lab_validation",
            "annotation_as_direct_causal_evidence",
        ],
    }


# 核心函数，输入是已经整理好的证据列表，负责把已经传进来的数据标准化
def build_omics_evidence_pack(
    *,
    trait: str,
    question: str,
    transcriptome_records: list[dict[str, Any]] | None = None,
    literature_records: list[dict[str, Any]] | None = None,
    metabolome_context: list[dict[str, Any]] | None = None,
    genome_context: list[dict[str, Any]] | None = None,
    annotation_evidence: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建多组学育种分析 Evidence Pack。

    该函数只做标准化，不做 LLM 推理，不做最终育种结论。
    """

    # 默认空列表处理
    transcriptome_records = transcriptome_records or []
    literature_records = literature_records or []
    metabolome_context = metabolome_context or []
    genome_context = genome_context or []
    annotation_evidence = annotation_evidence or []

    # 提取目标基因
    target_genes = extract_target_genes(transcriptome_records)
    # 判断任务类型
    intent = infer_task_intent(question)

    # Evidence Pack 最终结构
    evidence_pack = {
        "schema_version": "omics_evidence_pack.v1",
        "task": {  # 用户任务
            "trait": trait,
            "question": question,
            "intent": intent,
        },
        "targets": {  # 动态目标
            "genes": target_genes,
            "trait_terms": _deduplicate_preserve_order([trait]),
        },
        "evidence": {  # 多组学证据和文献证据
            "transcriptome": transcriptome_records,
            "literature": literature_records,
            "metabolome_context": metabolome_context,
            "genome_context": genome_context,
            "annotation": annotation_evidence,
        },
        "guard_requirements": build_guard_requirements(  # 后续 Guard 的动态检查要求
            trait=trait,
            question=question,
            target_genes=target_genes,
            literature_records=literature_records,
            annotation_evidence=annotation_evidence,
        ),
    }

    # Evidence Pack 最终结构可以直接给 Citation Engine、Guard、前端 claim_trace 展示、文献卡片展示 使用
    return evidence_pack


# 把 Evidence Pack 写成 JSON 文件
def write_evidence_pack(evidence_pack: dict[str, Any], output_path: str | Path) -> Path:
    """将 Evidence Pack 写入 JSON 文件。"""

    path = Path(output_path)  # 字符串路径转换成 Path 对象
    path.parent.mkdir(parents=True, exist_ok=True)  # 确保输出目录存在
    path.write_text(json.dumps(evidence_pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
