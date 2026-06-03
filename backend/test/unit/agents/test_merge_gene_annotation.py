from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.merge_gene_annotation import (
    merge_gene_annotation_files,
)


def test_merge_gene_annotation_files_writes_annotated_output(tmp_path):
    transcriptome = tmp_path / "significant_de_genes.tsv"
    transcriptome.write_text(
        "gene_id\tlogFC\tpadj\n"
        "GeneA\t1.8\t0.02\n"
        "GeneB\t-1.2\t0.04\n",
        encoding="utf-8",
    )
    annotation = tmp_path / "annotation.tsv"
    annotation.write_text(
        "gene_id\tdescription\n"
        "GeneA\tchalcone isomerase\n"
        "GeneA\tduplicate row ignored\n",
        encoding="utf-8",
    )
    output = tmp_path / "significant_de_genes.annotated.tsv"

    result = merge_gene_annotation_files(transcriptome, annotation, output)

    assert result["status"] == "completed"
    assert result["total_count"] == 2
    assert result["matched_count"] == 1
    assert result["unmatched_count"] == 1
    assert result["duplicate_count"] == 1
    assert output.exists()

    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "gene_id\tlogFC\tpadj\tgene_id\tdescription"
    assert lines[1] == "GeneA\t1.8\t0.02\tGeneA\tchalcone isomerase"
    assert lines[2] == "GeneB\t-1.2\t0.04\t\t"


def test_merge_gene_annotation_files_returns_warning_when_annotation_lacks_gene_id(tmp_path):
    transcriptome = tmp_path / "significant_de_genes.tsv"
    transcriptome.write_text("gene_id\tlogFC\nGeneA\t1.8\n", encoding="utf-8")
    annotation = tmp_path / "annotation.tsv"
    annotation.write_text("description\nchalcone isomerase\n", encoding="utf-8")

    result = merge_gene_annotation_files(
        transcriptome,
        annotation,
        tmp_path / "significant_de_genes.annotated.tsv",
    )

    assert result["status"] == "annotation_missing_gene_id"
    assert "gene_id column was not found" in result["warning"]
    assert result["output_file"] == ""
