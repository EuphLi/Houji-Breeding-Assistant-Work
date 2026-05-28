from __future__ import annotations

import json

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.workflow import (
    prepare_omics_evidence_pack_from_context,
    prepare_omics_evidence_pack_from_tool_results,
    summarize_evidence_pack,
)


# 验证：Context 文件路径
# ↓
# 读取 TSV
# ↓
# 构建 Evidence Pack
# ↓
# 写出 omics_evidence_pack.json
def test_prepare_omics_evidence_pack_from_context_writes_json(tmp_path):
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

    output_path = tmp_path / "omics_evidence_pack.json"

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        literature_evidence_path=str(literature_path),
        evidence_pack_output_path=str(output_path),
    )

    result = prepare_omics_evidence_pack_from_context(context)

    assert result["status"] == "completed_with_warnings"
    assert result["evidence_pack_path"] == str(output_path)
    assert result["artifacts"] == [str(output_path)]
    assert result["summary"]["target_genes"] == ["GeneA"]
    assert result["summary"]["allowed_doi_count"] == 1
    assert result["summary"]["literature_path_exists"] is True
    assert result["summary"]["usable_literature_count"] == 1

    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["task"]["trait"] == "抗旱"
    assert loaded["targets"]["genes"] == ["GeneA"]


# 验证：旧 Tool 返回结果
# ↓
# 桥接层
# ↓
# 写出 Evidence Pack
def test_prepare_omics_evidence_pack_from_tool_results_uses_legacy_outputs(tmp_path):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "GeneB\t2.0\t0.001\t0.01\n",
        encoding="utf-8",
    )

    output_path = tmp_path / "omics_evidence_pack.json"

    context = OmicsBreedingAnalysisContext(
        trait="产量",
        question="请给出一些育种建议",
        evidence_pack_output_path=str(output_path),
    )

    transcriptome_tool_result = {
        "status": "completed",
        "significant_de_genes_path": str(deg_path),
        "target_gene_found": True,
        "matches": [{"gene_id": "Si9g037800"}],
    }

    literature_tool_result = {
        "entries": [
            {
                "evidence_id": "L1",
                "doi": "10.5678/real",
                "quoted_sentence": "Verified literature sentence.",
                "source": "PubMed",
            }
        ]
    }

    result = prepare_omics_evidence_pack_from_tool_results(
        context=context,
        transcriptome_tool_result=transcriptome_tool_result,
        literature_tool_result=literature_tool_result,
    )

    assert result["status"] == "completed"
    assert result["summary"]["target_genes"] == ["GeneB"]
    assert result["summary"]["allowed_doi_count"] == 1

    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["task"]["trait"] == "产量"
    assert loaded["targets"]["genes"] == ["GeneB"]


# 验证：summary 统计逻辑
def test_summarize_evidence_pack_reports_counts():
    evidence_pack = {
        "targets": {
            "genes": ["GeneA", "GeneB"],
            "trait_terms": ["抗旱"],
        },
        "evidence": {
            "transcriptome": [{"gene_id": "GeneA"}, {"gene_id": "GeneB"}],
            "literature": [{"doi": "10.1234/real"}],
            "metabolome_context": [],
            "genome_context": [],
        },
        "guard_requirements": {
            "must_include_population_validation": True,
            "allowed_dois": ["10.1234/real"],
            "allowed_quoted_sentences": ["Verified sentence."],
        },
    }

    summary = summarize_evidence_pack(evidence_pack)

    assert summary["target_genes"] == ["GeneA", "GeneB"]
    assert summary["trait_terms"] == ["抗旱"]
    assert summary["transcriptome_record_count"] == 2
    assert summary["literature_record_count"] == 1
    assert summary["must_include_population_validation"] is True
    assert summary["allowed_doi_count"] == 1
    assert summary["allowed_quoted_sentence_count"] == 1


def test_prepare_omics_evidence_pack_marks_missing_inputs(tmp_path):
    output_path = tmp_path / "omics_evidence_pack.json"
    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="significant_de_genes.tsv",
        metabolome_path="metabolome_raw_3372.tsv",
        literature_evidence_path="",
        evidence_pack_output_path=str(output_path),
    )

    result = prepare_omics_evidence_pack_from_context(context)

    assert result["summary"]["transcriptome_path_exists"] is False
    assert result["summary"]["metabolome_path_exists"] is False
    assert result["summary"]["evidence_level"] == "input_missing_or_filename_only"
