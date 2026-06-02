from __future__ import annotations

import re
from typing import Any

"""
输出边界控制层 / 反过度推断层 / 反编造层

基于 Evidence Pack 的 guard_requirements 检查最终回答是否越界
在数据流中的位置
raw answer / canonical answer
  ↓
output_guard.py
  ↓
guarded answer / guard_result
  ↓
workflow.py / presentation.py / 前端
"""

# 从回答中找DOI，若如果回答里出现 DOI，但不在 Evidence Pack 的 allowed_dois 中，就报错
DOI_PATTERN = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", re.IGNORECASE)

# 越界正则检查
POPULATION_VALIDATED_PATTERN = re.compile(
    r"(?:已完成|完成|completed|validated).{0,20}(?:群体|population).{0,20}(?:验证|validation)|"
    r"(?:群体|population).{0,20}(?:验证|validation).{0,20}(?:已完成|完成|completed|validated)",
    re.IGNORECASE,
)

WET_LAB_VALIDATED_PATTERN = re.compile(
    r"(?:已完成|完成|completed|validated).{0,20}(?:湿实验|wet[- ]?lab)|"
    r"(?:湿实验|wet[- ]?lab).{0,20}(?:已完成|完成|completed|validated)",
    re.IGNORECASE,
)

MARKER_COMPLETED_PATTERN = re.compile(
    r"(?:已完成|完成|completed|validated|developed).{0,20}(?:KASP|CAPS)|"
    r"(?:KASP|CAPS).{0,20}(?:已完成|完成|completed|validated|developed|开发完成)",
    re.IGNORECASE,
)

FINAL_BREEDING_CONCLUSION_PATTERN = re.compile(
    r"(?:最终育种结论|final breeding conclusion|最终结论).{0,20}(?:已明确|已确认|confirmed|validated|完成)",
    re.IGNORECASE,
)

ANNOTATION_VALIDATED_PATTERN = re.compile(
    r"(?:功能注释|annotation|A1).{0,30}(?:证明|证实|validated|confirmed).{0,30}(?:功能|调控|因果|trait|性状)|"
    r"(?:基因功能|调控目标性状|直接因果).{0,30}(?:已由|由).{0,20}(?:功能注释|annotation|A1).{0,20}(?:证明|证实)",
    re.IGNORECASE,
)

QUOTE_LINE_PATTERN = re.compile(r"引用原[文句][:：]\s*(.+)")


def _as_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _contains_any(text: str, terms: list[str]) -> bool:
    return any(term and term in text for term in terms)


def _is_negated_completion_match(answer: str, match: re.Match[str] | None) -> bool:
    if match is None:
        return False
    sentence_start = max(
        answer.rfind("\n", 0, match.start()),
        answer.rfind("。", 0, match.start()),
        answer.rfind("！", 0, match.start()),
        answer.rfind("?", 0, match.start()),
        answer.rfind("？", 0, match.start()),
    )
    prefix = answer[sentence_start + 1:match.start()]
    return any(
        token in prefix
        for token in ["不应", "不能", "不得", "不允许", "禁止", "不声称", "并非", "not "]
    )


def _has_positive_completion_claim(answer: str, pattern: re.Pattern[str]) -> bool:
    for match in pattern.finditer(answer):
        if not _is_negated_completion_match(answer, match):
            return True
    return False


# 专门提取回答里的：引用原文：xxxx
def _extract_reported_quotes(answer: str) -> list[str]:
    quotes: list[str] = []
    for match in QUOTE_LINE_PATTERN.finditer(answer):
        quote = match.group(1).strip()
        if quote and "待文献检索补充" not in quote:
            quotes.append(quote)
    return quotes


# 核心函数
def run_dynamic_output_guard(
    answer: str,
    evidence_pack: dict[str, Any],
) -> dict[str, Any]:
    """根据 Evidence Pack 动态检查最终回答。

    这个 Guard 不写死具体基因、性状或任务词。
    它只读取 evidence_pack["guard_requirements"] 中的动态要求。

    检查范围：
    - 目标基因是否覆盖
    - 目标性状是否覆盖
    - 需要群体验证建议时，是否提到群体层面的后续验证
    - DOI 是否来自 allowed_dois
    - quoted_sentence 是否来自 allowed_quoted_sentences
    - 是否出现已完成群体验证、湿实验、最终 KASP/CAPS、最终育种结论等越界表述
    """

    answer = answer or ""
    guard_requirements = evidence_pack.get("guard_requirements") or {}

    required_gene_ids = _as_list(guard_requirements.get("required_gene_ids"))
    required_trait_terms = _as_list(guard_requirements.get("required_trait_terms"))
    allowed_dois = set(_as_list(guard_requirements.get("allowed_dois")))
    allowed_quoted_sentences = set(
        _as_list(guard_requirements.get("allowed_quoted_sentences"))
    )
    must_include_population_validation = bool(
        guard_requirements.get("must_include_population_validation")
    )

    doi_matches = DOI_PATTERN.findall(answer)
    unsupported_dois = [doi for doi in doi_matches if doi not in allowed_dois]

    reported_quotes = _extract_reported_quotes(answer)
    unsupported_quotes = [
        quote for quote in reported_quotes if quote not in allowed_quoted_sentences
    ]

    checks = {
        "required_gene_ids": required_gene_ids,
        "required_trait_terms": required_trait_terms,
        "contains_required_gene_ids": all(gene_id in answer for gene_id in required_gene_ids),
        "contains_required_trait_terms": all(term in answer for term in required_trait_terms),
        "must_include_population_validation": must_include_population_validation,
        "contains_population_validation_plan": (
            not must_include_population_validation
            or _contains_any(answer, ["群体", "population", "群体验证", "验证群体"])
        ),
        "has_unsupported_doi": bool(unsupported_dois),
        "has_unsupported_quoted_sentence": bool(unsupported_quotes),
        "claims_population_validation_completed": _has_positive_completion_claim(
            answer, POPULATION_VALIDATED_PATTERN
        ),
        "claims_wet_lab_completed": _has_positive_completion_claim(
            answer, WET_LAB_VALIDATED_PATTERN
        ),
        "claims_marker_development_completed": _has_positive_completion_claim(
            answer, MARKER_COMPLETED_PATTERN
        ),
        "claims_final_breeding_conclusion": _has_positive_completion_claim(
            answer, FINAL_BREEDING_CONCLUSION_PATTERN
        ),
        "claims_annotation_as_validation": _has_positive_completion_claim(
            answer, ANNOTATION_VALIDATED_PATTERN
        ),
    }

    errors: list[str] = []
    warnings: list[str] = []

    if required_gene_ids and not checks["contains_required_gene_ids"]:
        errors.append(f"Answer must mention required target genes: {required_gene_ids}.")

    if required_trait_terms and not checks["contains_required_trait_terms"]:
        errors.append(f"Answer must mention required trait terms: {required_trait_terms}.")

    if not checks["contains_population_validation_plan"]:
        errors.append("Answer must include a population-level follow-up validation plan.")

    if unsupported_dois:
        errors.append(f"Answer contains DOI not present in Evidence Pack: {unsupported_dois}.")

    if unsupported_quotes:
        errors.append(
            "Answer contains quoted_sentence not present in Evidence Pack: "
            f"{unsupported_quotes}."
        )

    if checks["claims_population_validation_completed"]:
        errors.append("Answer appears to claim completed population validation.")

    if checks["claims_wet_lab_completed"]:
        errors.append("Answer appears to claim completed wet-lab validation.")

    if checks["claims_marker_development_completed"]:
        errors.append("Answer appears to claim completed KASP/CAPS marker development.")

    if checks["claims_final_breeding_conclusion"]:
        errors.append("Answer appears to claim a final breeding conclusion.")

    if checks["claims_annotation_as_validation"]:
        errors.append("Answer appears to treat functional annotation as validation or causal proof.")

    if not doi_matches and allowed_dois:
        warnings.append("Evidence Pack contains DOI evidence, but answer does not cite DOI.")

    return {
        "passed": not errors,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "unsupported_dois": unsupported_dois,
        "unsupported_quoted_sentences": unsupported_quotes,
    }
