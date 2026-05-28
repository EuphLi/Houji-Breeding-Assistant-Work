from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.tool_result_adapters import (
    build_omics_evidence_pack_from_tool_results,
    extract_literature_records_from_tool_result,
    extract_transcriptome_records_from_tool_result,
)

# 测试验证：防止旧 smoke 硬编码污染新 Evidence Pack
def test_extract_transcriptome_records_from_legacy_tool_result_uses_result_file(tmp_path):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "GeneA\t1.5\t0.01\t0.02\n",
        encoding="utf-8",
    )

    legacy_result = {
        "status": "completed",
        "significant_de_genes_path": str(deg_path),
        "target_gene_found": True,
        "matches": [{"gene_id": "Si9g037800"}],
    }

    records = extract_transcriptome_records_from_tool_result(legacy_result)

    assert records[0]["gene_id"] == "GeneA"
    assert records[0]["logfc"] == "1.5"


# 验证：PubMedFixture 会被过滤。只留下真实来源：PubMed
def test_extract_literature_records_from_legacy_tool_result_filters_fixture_entries():
    legacy_result = {
        "entries": [
            {
                "evidence_id": "L1",
                "doi": "10.1234/real",
                "quoted_sentence": "Verified sentence.",
                "source": "PubMed",
            },
            {
                "evidence_id": "L2",
                "doi": "10.9999/demo",
                "quoted_sentence": "Demo sentence.",
                "source": "PubMedFixture",
            },
        ]
    }

    records = extract_literature_records_from_tool_result(legacy_result)

    assert len(records) == 1
    assert records[0]["doi"] == "10.1234/real"
    assert records[0]["quoted_sentence"] == "Verified sentence."


# 验证完整桥接链路：
# Context + 旧转录组工具结果 + 旧文献工具结果
# ↓
# Evidence Pack
# 并确认：trait 是 抗旱、gene 是 GeneA。不是 黄酮 / Si9g037800
def test_build_omics_evidence_pack_from_tool_results_keeps_dynamic_trait_and_gene(tmp_path):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "GeneA\t1.5\t0.01\t0.02\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
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
                "doi": "10.1234/real",
                "quoted_sentence": "Verified sentence.",
                "source": "PubMed",
            }
        ]
    }

    pack = build_omics_evidence_pack_from_tool_results(
        context=context,
        transcriptome_tool_result=transcriptome_tool_result,
        literature_tool_result=literature_tool_result,
    )

    assert pack["task"]["trait"] == "抗旱"
    assert pack["task"]["intent"] == "candidate_validation"
    assert pack["targets"]["genes"] == ["GeneA"]
    assert pack["guard_requirements"]["required_gene_ids"] == ["GeneA"]
    assert pack["guard_requirements"]["allowed_dois"] == ["10.1234/real"]