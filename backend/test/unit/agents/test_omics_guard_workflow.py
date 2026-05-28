from __future__ import annotations

import json

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.workflow import (
    guard_omics_answer,
    prepare_guarded_omics_answer_from_context,
)


# 验证合法回答：
# 包含 GeneA、包含 抗旱、包含 群体后续验证建议
# DOI 来自 allowed_dois、引用原句来自 allowed_quoted_sentences
# 所以 Guard 通过，并写出 guard_result.json
def test_guard_omics_answer_writes_guard_result(tmp_path):
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
            "GeneA 可作为当前证据支持的候选目标基因。",
            "建议后续在群体中结合基因型和抗旱表型开展关联验证。",
            "真实 DOI：10.1234/real",
            "引用原文：Verified sentence.",
        ]
    )

    guard_path = tmp_path / "guard_result.json"

    result = guard_omics_answer(
        answer_markdown=answer,
        evidence_pack=evidence_pack,
        guard_result_path=guard_path,
    )

    assert result["status"] == "passed"
    assert result["guard_result"]["passed"] is True
    assert result["guard_result_path"] == str(guard_path)
    assert result["artifacts"] == [str(guard_path)]

    loaded = json.loads(guard_path.read_text(encoding="utf-8"))
    assert loaded["passed"] is True


# 验证越界回答：
# 我们已经完成群体验证，这会被 Dynamic Guard 拦截，返回：failed_guard
def test_guard_omics_answer_returns_failed_guard_for_overclaim(tmp_path):
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
        ]
    )

    result = guard_omics_answer(
        answer_markdown=answer,
        evidence_pack=evidence_pack,
        guard_result_path=tmp_path / "guard_result.json",
    )

    assert result["status"] == "failed_guard"
    assert result["guard_result"]["passed"] is False
    assert any(
        "completed population validation" in error
        for error in result["guard_result"]["errors"]
    )


# 验证完整小链路：
# Context
# ↓
# 读取 DEG / literature TSV
# ↓
# 写 omics_evidence_pack.json
# ↓
# 执行 Guard
# ↓
# 写 guard_result.json
# 这一步通过后，说明 Evidence Pack 与 Dynamic Guard 已经能在 workflow 层连起来
def test_prepare_guarded_omics_answer_from_context_writes_evidence_and_guard(tmp_path):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "GeneA\t1.8\t0.003\t0.02\n",
        encoding="utf-8",
    )

    literature_path = tmp_path / "verified_literature_evidence.tsv"
    literature_path.write_text(
        "evidence_id\tdoi\tquoted_sentence\tstatus\tis_demo\tsource\n"
        "L1\t10.1234/real\tVerified sentence.\tverified\tfalse\tPubMed\n",
        encoding="utf-8",
    )

    evidence_pack_path = tmp_path / "omics_evidence_pack.json"
    guard_path = tmp_path / "guard_result.json"

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        literature_evidence_path=str(literature_path),
        evidence_pack_output_path=str(evidence_pack_path),
    )

    answer = "\n".join(
        [
            "本轮分析围绕抗旱性状展开。",
            "GeneA 可作为当前证据支持的候选目标基因。",
            "建议后续在群体中结合基因型和抗旱表型开展关联验证。",
            "真实 DOI：10.1234/real",
            "引用原文：Verified sentence.",
        ]
    )

    result = prepare_guarded_omics_answer_from_context(
        context=context,
        answer_markdown=answer,
        guard_result_path=guard_path,
    )

    assert result["status"] == "passed"
    assert result["summary"]["target_genes"] == ["GeneA"]
    assert result["guard_result"]["passed"] is True
    assert str(evidence_pack_path) in result["artifacts"]
    assert str(guard_path) in result["artifacts"]
    assert evidence_pack_path.exists()
    assert guard_path.exists()