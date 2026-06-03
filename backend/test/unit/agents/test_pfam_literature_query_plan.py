from __future__ import annotations

import json

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.evidence_adapters import (
    build_omics_evidence_pack_from_context,
)


def test_pfam_literature_query_plan_extracts_pfam_and_generates_prioritized_queries(tmp_path):
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "Si9g037800\t2.1\t0.001\t0.01\n",
        encoding="utf-8",
    )
    annotation_path = tmp_path / "annotation.tsv"
    annotation_path.write_text(
        "gene_id\tpfam\tKEGG_Pathway\tGO_IDs\tPfam_Description\tInterPro_Description\n"
        "Si9g037800\tChalcone-flavanone isomerase\tFlavonoid biosynthesis|ko00941|K01859|LSE1451|E5.5.1.6\tGO:0016872|chalcone isomerase activity\tPF02431\tChalcone isomerase-like domain\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation_path),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    pack = build_omics_evidence_pack_from_context(context)
    metadata = pack["evidence"]["annotation"][0]["metadata"]

    assert metadata["pfam_literature_keywords"] == ["Chalcone-flavanone isomerase"]
    assert metadata["literature_query_plan_count"] > 0
    assert metadata["literature_query_plan_source"] == "annotated_transcriptome_pfam"
    assert "Flavonoid biosynthesis" in metadata["pathway_summary"]
    assert "ko00941" not in metadata["pathway_summary"]
    assert "K01859" in metadata["ko_terms"]
    assert "ko00941" in metadata["ko_terms"]
    assert "GO:0016872" in metadata["go_ids"]
    assert "PF02431" in metadata["pfam_ids"]
    assert "LSE1451" in metadata["pathway_ids"]
    assert "E5.5.1.6" in metadata["pathway_ids"]

    query_plan_path = deg_dir / "literature_query_plan.jsonl"
    entries = [
        json.loads(line)
        for line in query_plan_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert any(
        entry["query_type"] == "species_pfam_trait"
        and entry["priority"] == "high"
        and entry["query"] == 'Setaria italica "Chalcone-flavanone isomerase" flavonoid'
        for entry in entries
    )
    assert any(
        entry["query_type"] == "species_pfam_pathway"
        and entry["priority"] == "high"
        and entry["query"] == 'Setaria italica "Chalcone-flavanone isomerase" "Flavonoid biosynthesis"'
        for entry in entries
    )
    assert any(
        entry["query_type"] == "species_pfam_pathway"
        and entry["priority"] == "high"
        and entry["query"] == 'Setaria italica "Chalcone-flavanone isomerase" "chalcone isomerase activity"'
        for entry in entries
    )
    assert any(
        entry["query_type"] == "gene_pfam"
        and entry["priority"] == "low"
        and entry["query"] == 'Si9g037800 "Chalcone-flavanone isomerase"'
        for entry in entries
    )
    assert all(entry["is_evidence"] is False for entry in entries)
    high_entries = [entry for entry in entries if entry["priority"] == "high"]
    assert len(high_entries) <= 8
    assert len([entry for entry in entries if entry["priority"] == "medium"]) <= 4
    assert len([entry for entry in entries if entry["priority"] == "low"]) <= 2
    assert len([entry for entry in entries if entry["priority"] == "fallback"]) <= 4
    assert len(entries) <= 18
    assert not any(
        entry["query_type"] == "species_pfam_pathway"
        and entry["priority"] == "high"
        and any(token in (entry["old_keywords"] or []) for token in ["LSE1451", "K01859", "ko00941", "E5.5.1.6"])
        for entry in entries
    )
    assert not any(
        any(token in entry["query"] for token in ["LSE1451", "K01859", "ko00941", "E5.5.1.6"])
        and entry["query_type"] == "species_pfam_pathway"
        and entry["priority"] == "high"
        for entry in entries
    )
