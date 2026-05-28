from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.output_guard import (
    run_dynamic_output_guard,
)

"""
测试文件说明

这四个测试分别覆盖：

1. 合法回答可以通过
2. 缺少动态目标基因 / 性状 / 群体验证建议会失败
3. 编造 DOI 和 quoted_sentence 会失败
4. 声称已完成群体验证或 KASP/CAPS 开发会失败

这正是 Dynamic Guard 第一版的核心边界。
"""


def test_dynamic_output_guard_passes_supported_answer():
    evidence_pack = {
        "guard_requirements": {
            "required_gene_ids": ["GeneA"],
            "required_trait_terms": ["抗旱"],
            "must_include_population_validation": True,
            "allowed_dois": ["10.1234/real"],
            "allowed_quoted_sentences": ["Verified sentence."],
        }
    }

    answer = "\n".join(
        [
            "本轮分析围绕抗旱性状展开。",
            "GeneA 可作为当前数据支持的候选目标基因。",
            "建议后续在群体中结合基因型和抗旱表型开展关联验证。",
            "真实 DOI：10.1234/real",
            "引用原文：Verified sentence.",
        ]
    )

    result = run_dynamic_output_guard(answer, evidence_pack)

    assert result["passed"] is True
    assert result["errors"] == []


def test_dynamic_output_guard_rejects_missing_dynamic_terms():
    evidence_pack = {
        "guard_requirements": {
            "required_gene_ids": ["GeneA"],
            "required_trait_terms": ["抗旱"],
            "must_include_population_validation": True,
            "allowed_dois": [],
            "allowed_quoted_sentences": [],
        }
    }

    answer = "本轮结果显示候选基因值得进一步关注。"

    result = run_dynamic_output_guard(answer, evidence_pack)

    assert result["passed"] is False
    assert any("required target genes" in error for error in result["errors"])
    assert any("required trait terms" in error for error in result["errors"])
    assert any("population-level" in error for error in result["errors"])


def test_dynamic_output_guard_rejects_unsupported_doi_and_quote():
    evidence_pack = {
        "guard_requirements": {
            "required_gene_ids": ["GeneA"],
            "required_trait_terms": ["抗旱"],
            "must_include_population_validation": False,
            "allowed_dois": ["10.1234/real"],
            "allowed_quoted_sentences": ["Verified sentence."],
        }
    }

    answer = "\n".join(
        [
            "GeneA 与抗旱相关。",
            "真实 DOI：10.9999/fake",
            "引用原文：Fabricated sentence.",
        ]
    )

    result = run_dynamic_output_guard(answer, evidence_pack)

    assert result["passed"] is False
    assert result["unsupported_dois"] == ["10.9999/fake"]
    assert result["unsupported_quoted_sentences"] == ["Fabricated sentence."]


def test_dynamic_output_guard_rejects_overclaims():
    evidence_pack = {
        "guard_requirements": {
            "required_gene_ids": ["GeneA"],
            "required_trait_terms": ["抗旱"],
            "must_include_population_validation": True,
            "allowed_dois": [],
            "allowed_quoted_sentences": [],
        }
    }

    answer = "\n".join(
        [
            "GeneA 是抗旱相关候选基因。",
            "我们已经完成群体验证。",
            "KASP 标记已经开发完成。",
        ]
    )

    result = run_dynamic_output_guard(answer, evidence_pack)

    assert result["passed"] is False
    assert any("completed population validation" in error for error in result["errors"])
    assert any("KASP/CAPS marker development" in error for error in result["errors"])