from __future__ import annotations

import json

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.evidence_adapters import (
    build_omics_evidence_pack_from_context,
    collect_input_file_diagnostics,
    read_literature_records,
    read_transcriptome_records,
)

"""
这个测试文件专门保护 evidence_adapters.py
"""

# 测试证明
# 1. TSV 能被正确读取
# 2. gene_id 能被正确识别
# 3. 默认 evidence_id 是 T1、T2
# 4. logFC / pvalue / padj 能被标准化
def test_read_transcriptome_records_from_tsv(tmp_path):
    path = tmp_path / "significant_de_genes.tsv"
    path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "Si9g037800\t2.1\t0.001\t0.01\n"
        "GeneB\t-1.2\t0.02\t0.04\n",
        encoding="utf-8",
    )

    records = read_transcriptome_records(path)

    assert [item["gene_id"] for item in records] == ["Si9g037800", "GeneB"]
    assert records[0]["evidence_id"] == "T1"
    assert records[0]["logfc"] == "2.1"
    assert records[0]["pvalue"] == "0.001"
    assert records[0]["padj"] == "0.01"


# 确保只有真实、已验证、同时有 DOI 和 quoted_sentence 的文献才能进入 Evidence Pack。
def test_read_literature_records_filters_unverified_rows(tmp_path):
    path = tmp_path / "verified_literature_evidence.tsv"
    path.write_text(
        "evidence_id\tdoi\tquoted_sentence\tstatus\tis_demo\tsource\n"
        "L1\t10.1234/real\tVerified sentence.\tverified\tfalse\tPubMed\n"
        "L2\t10.9999/demo\tDemo sentence.\tverified\ttrue\tPubMedFixture\n"
        "L3\t10.8888/pending\tPending sentence.\tpending\tfalse\tPubMed\n"
        "L4\t\tMissing DOI sentence.\tverified\tfalse\tPubMed\n",
        encoding="utf-8",
    )

    records = read_literature_records(path)

    assert len(records) == 1
    assert records[0]["doi"] == "10.1234/real"
    assert records[0]["quoted_sentence"] == "Verified sentence."


# 最小集成测试
def test_build_omics_evidence_pack_from_context_uses_files(tmp_path):
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

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        literature_evidence_path=str(literature_path),
    )

    pack = build_omics_evidence_pack_from_context(context)

    assert pack["task"]["trait"] == "抗旱"
    assert pack["task"]["intent"] == "candidate_validation"
    assert pack["targets"]["genes"] == ["GeneA"]
    assert pack["guard_requirements"]["required_gene_ids"] == ["GeneA"]
    assert pack["guard_requirements"]["required_trait_terms"] == ["抗旱"]
    assert pack["guard_requirements"]["allowed_dois"] == ["10.1234/real"]
    assert pack["guard_requirements"]["allowed_quoted_sentences"] == ["Verified sentence."]


def test_annotation_evidence_adapter_parses_custom_uploaded_annotation_and_writes_artifact(tmp_path):
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\ttranscript_ids\tlogFC\tpvalue\tpadj\n"
        "GeneA\tGeneA.t1;GeneA.t2\t1.8\t0.003\t0.02\n"
        "GeneB\tGeneB.t1\t-1.2\t0.02\t0.04\n",
        encoding="utf-8",
    )
    annotation = tmp_path / "uploaded_gene_function_table.tsv"
    annotation.write_text(
        "GeneID\tmRNA_id\tSwissProt_annotation\tKEGG_Pathway\tGO_IDs\tPfam_Description\n"
        "GeneA\tGeneA.t1\tchalcone isomerase\tflavonoid biosynthesis\tflavonoid biosynthetic process\tChalcone domain\n"
        "GeneA\tGeneA.t2\tchalcone-flavanone isomerase\tphenylpropanoid biosynthesis\tGO:0009813\tPF02431\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    pack = build_omics_evidence_pack_from_context(context)

    annotation_records = pack["evidence"]["annotation"]
    assert len(annotation_records) == 1
    metadata = annotation_records[0]["metadata"]
    assert metadata["annotation_file_name"] == "uploaded_gene_function_table.tsv"
    assert metadata["annotation_merge_status"] == "completed"
    assert metadata["annotation_merge_total_count"] == 2
    assert metadata["annotation_merge_matched_count"] == 1
    assert metadata["annotation_merge_unmatched_count"] == 1
    assert metadata["annotation_merge_duplicate_count"] == 1
    assert "Chalcone domain" in metadata["pfam_literature_keywords"]
    assert metadata["literature_query_plan_count"] > 0
    assert metadata["literature_query_plan_source"] == "annotated_transcriptome_pfam"
    assert metadata["annotation_gene_match_count"] == 1
    assert metadata["annotation_unmatched_gene_count"] == 1
    assert metadata["annotation_duplicate_gene_id_count"] == 1
    assert metadata["annotation_isoform_count"] == 2
    assert metadata["annotation_matched_transcript_count"] == 2
    assert metadata["annotation_candidate_gene_ids"] == ["GeneA"]
    candidate = metadata["candidate_annotations"][0]
    assert candidate["matched_by"] == "gene_id_and_transcript_id"
    assert "chalcone isomerase" in candidate["annotation_fields"]["SwissProt_annotation"]
    assert "flavonoid biosynthesis" in candidate["pathway_terms"]
    assert "chalcone" in " ".join(candidate["trait_relevance_terms"]).lower()
    assert "chalcone isomerase" in candidate["pubmed_query_terms"]
    assert "Setaria italica" in candidate["pubmed_query_terms"]
    annotated_path = deg_dir / "significant_de_genes.annotated.tsv"
    assert metadata["annotated_transcriptome_path"] == str(annotated_path)
    assert annotated_path.exists()
    query_plan_path = deg_dir / "literature_query_plan.jsonl"
    assert metadata["literature_query_plan_path"] == str(query_plan_path)
    assert query_plan_path.exists()
    query_plan_entries = [
        json.loads(line)
        for line in query_plan_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert any(item["query_type"] == "species_pfam_trait" for item in query_plan_entries)
    assert any(item["query_type"] == "species_pfam_pathway" for item in query_plan_entries)
    assert any(item["query_type"] == "gene_pfam" for item in query_plan_entries)
    assert any(
        item["query"] == 'Setaria italica "Chalcone domain" flavonoid'
        for item in query_plan_entries
    )
    assert deg_path.read_text(encoding="utf-8").startswith("gene_id\ttranscript_ids\tlogFC")
    annotated_text = annotated_path.read_text(encoding="utf-8")
    assert annotated_text.splitlines()[0] == (
        "gene_id\ttranscript_ids\tlogFC\tpvalue\tpadj\tGeneID\tmRNA_id\tSwissProt_annotation\tKEGG_Pathway\tGO_IDs\tPfam_Description"
    )
    assert "GeneA\tGeneA.t1;GeneA.t2\t1.8\t0.003\t0.02\tGeneA\tGeneA.t1\tchalcone isomerase\tflavonoid biosynthesis\tflavonoid biosynthetic process\tChalcone domain" in annotated_text
    assert "GeneB\tGeneB.t1\t-1.2\t0.02\t0.04\t\t\t\t\t\t" in annotated_text


def test_annotation_evidence_adapter_uses_smoke_fixture_as_normal_annotation_path(tmp_path):
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "Si9g037800\t2.0\t0.001\t0.01\n",
        encoding="utf-8",
    )
    annotation = tmp_path / "xiaomi_T2T_Annotation.smoke_genes.txt"
    annotation.write_text(
        "gene_id\tmRNA_id\tKEGG_Pathway\tSwissProt_annotation\n"
        "Si9g037800\tSi9g037800.1\tflavonoid biosynthesis\tchalcone isomerase\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    pack = build_omics_evidence_pack_from_context(context)
    metadata = pack["evidence"]["annotation"][0]["metadata"]

    assert metadata["annotation_candidate_gene_ids"] == ["Si9g037800"]
    assert "flavonoid biosynthesis" in metadata["pubmed_query_terms"]
    assert "chalcone isomerase" in metadata["pubmed_query_terms"]


def test_annotation_evidence_adapter_filters_dirty_tokens_from_summary_terms(tmp_path):
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\n"
        "GeneA\t1.8\t0.003\t0.02\n",
        encoding="utf-8",
    )
    annotation = tmp_path / "uploaded_gene_function_table.tsv"
    annotation.write_text(
        "GeneID\tNR_annotation\tKEGG_Pathway\tGO_IDs\tPfam_Description\tInterPro_Description\n"
        "GeneA\tnaringenin-chalcone synthase\thttp://www.genome.jp/dbget-bin/www_bget?ko:K01859|ko00941|Flavonoid biosynthesis\tGO:0009813|URL 片段\t[X]|Chalcone N-terminal domain\tUncharacterized protein|Chalcone/stilbene synthase, conserved site\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation),
        evidence_pack_output_path=str(tmp_path / "omics_evidence_pack.json"),
    )

    pack = build_omics_evidence_pack_from_context(context)
    metadata = pack["evidence"]["annotation"][0]["metadata"]
    summary_text = " ".join(metadata["pathway_summary"])

    assert "ko00941" in summary_text
    assert "Flavonoid biosynthesis" in summary_text
    assert "GO:0009813" in " ".join(metadata["candidate_annotations"][0]["go_terms"])
    assert "dbget-bin" not in summary_text
    assert "www_bget" not in summary_text
    assert "URL 片段" not in summary_text
    assert "[X]" not in summary_text
    assert "Uncharacterized protein" not in summary_text


def test_annotation_evidence_adapter_degrades_without_annotation_file(tmp_path):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\nGeneA\t1.0\t0.01\t0.02\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="给出一些育种建议",
        transcriptome_result_path=str(deg_path),
        annotation_path="",
    )

    pack = build_omics_evidence_pack_from_context(context)

    assert pack["evidence"]["annotation"] == []
    assert pack["debug"]["annotation"]["annotation_path_exists"] is False
    assert pack["debug"]["annotation"]["annotation_merge_status"] == "skipped_missing_annotation"
    assert pack["debug"]["annotation"]["annotated_transcriptome_path"] == ""
    assert pack["debug"]["annotation"]["literature_query_plan_count"] == 0
    assert pack["debug"]["annotation"]["candidate_annotations"] == []


def test_annotation_evidence_adapter_returns_merge_warning_when_deg_lacks_gene_id(tmp_path):
    deg_dir = tmp_path / "transcriptome_deg"
    deg_dir.mkdir()
    deg_path = deg_dir / "significant_de_genes.tsv"
    deg_path.write_text(
        "feature_id\tlogFC\tpadj\n"
        "GeneA\t1.8\t0.02\n",
        encoding="utf-8",
    )
    annotation = tmp_path / "annotation.tsv"
    annotation.write_text(
        "gene_id\tdescription\n"
        "GeneA\tchalcone isomerase\n",
        encoding="utf-8",
    )

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        annotation_path=str(annotation),
    )

    pack = build_omics_evidence_pack_from_context(context)

    assert pack["evidence"]["annotation"] == []
    assert pack["debug"]["annotation"]["annotation_merge_status"] == "transcriptome_missing_gene_id"
    assert "gene_id column was not found" in pack["debug"]["annotation"]["annotation_merge_warning"]


def test_collect_input_file_diagnostics_marks_uploaded_fastq_without_deg_as_present(tmp_path):
    genome_fa = tmp_path / "genome.fa"
    genome_fa.write_text(">chr1\nACGT\n", encoding="utf-8")
    genome_gff = tmp_path / "genome.gff"
    genome_gff.write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    annotation = tmp_path / "xiaomi_T2T_Annotation.smoke_genes.txt"
    annotation.write_text("GeneA\tannotation\n", encoding="utf-8")
    sample_map = tmp_path / "sampleName_clientId.txt"
    sample_map.write_text("sample1\tclient1\n", encoding="utf-8")
    fastq = tmp_path / "sample1_R1.fq.gz"
    fastq.write_text("fake fastq bytes\n", encoding="utf-8")

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path=str(genome_fa),
        genome_gff_path=str(genome_gff),
        annotation_path=str(annotation),
        sample_map_path=str(sample_map),
        rnaseq_read_paths=[str(fastq)],
        upload_root=str(tmp_path),
    )

    diagnostics = collect_input_file_diagnostics(context)

    assert diagnostics["transcriptome_path_exists"] is False
    assert diagnostics["transcriptome_supporting_input_exists"] is True
    assert diagnostics["transcriptome_input_status"] == "fastq_uploaded"
    assert diagnostics["rnaseq_read_count"] == 1
    assert diagnostics["evidence_level"] == "user_provided_path"


def test_collect_input_file_diagnostics_discovers_uploaded_files_from_upload_root(tmp_path):
    fq_dir = tmp_path / "fq"
    fq_dir.mkdir()
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    metabolome = tmp_path / "metabolome_raw_3372.tsv"
    metabolome.write_text("compound\tvalue\nflavonoid_a\t1.0\n", encoding="utf-8")
    sample_map = tmp_path / "sampleName_clientId.txt"
    sample_map.write_text("sample1\tclient1\n", encoding="utf-8")
    genome_fa = tmp_path / "genome.fa"
    genome_fa.write_text(">chr1\nACGT\n", encoding="utf-8")
    genome_gff = tmp_path / "genome.gff"
    genome_gff.write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")

    context = OmicsBreedingAnalysisContext(
        trait="高产相关",
        question="给出一些育种建议",
        upload_root=str(tmp_path),
        transcriptome_result_path="",
        metabolome_path="",
        sample_map_path="",
        reference_genome_path="",
        genome_gff_path="",
        rnaseq_read_paths=[],
    )

    diagnostics = collect_input_file_diagnostics(context)

    assert diagnostics["metabolome_path_exists"] is True
    assert diagnostics["metabolome_path"] == str(metabolome)
    assert diagnostics["sample_map_path_exists"] is True
    assert diagnostics["reference_genome_path_exists"] is True
    assert diagnostics["genome_gff_path_exists"] is True
    assert diagnostics["rnaseq_read_count"] == 1
    assert diagnostics["transcriptome_input_status"] == "fastq_uploaded"
    assert diagnostics["data_source"] == "user_provided_path"


def test_collect_input_file_diagnostics_does_not_treat_user_uploaded_deg_as_pipeline_output(tmp_path):
    (tmp_path / "significant_de_genes.tsv").write_text(
        "gene_id\tlogFC\tpvalue\tpadj\nGeneA\t1.0\t0.01\t0.02\n",
        encoding="utf-8",
    )
    fq_dir = tmp_path / "fq"
    fq_dir.mkdir()
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (tmp_path / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (tmp_path / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (tmp_path / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")

    context = OmicsBreedingAnalysisContext(
        trait="抗旱相关",
        question="给出一些育种建议",
        upload_root=str(tmp_path),
        transcriptome_result_path="",
    )

    diagnostics = collect_input_file_diagnostics(context)

    assert diagnostics["transcriptome_path_exists"] is False
    assert diagnostics["transcriptome_result_path"] == ""
    assert diagnostics["transcriptome_input_status"] == "fastq_uploaded"


def test_collect_input_file_diagnostics_discovers_alternate_upload_names(tmp_path):
    fq_dir = tmp_path / "fq"
    fq_dir.mkdir()
    (fq_dir / "sample1_R1.fastq.gz").write_text("fake fastq\n", encoding="utf-8")
    (tmp_path / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    genome_fa = tmp_path / "genome.fasta"
    genome_fa.write_text(">chr1\nACGT\n", encoding="utf-8")
    genome_gff = tmp_path / "genome.gff3"
    genome_gff.write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    annotation = tmp_path / "custom_function_annotation.tsv"
    annotation.write_text("gene_id\tannotation\nGeneA\tstress response\n", encoding="utf-8")

    context = OmicsBreedingAnalysisContext(
        trait="籽粒性状",
        question="给出一些育种建议",
        upload_root=str(tmp_path),
        transcriptome_result_path="",
    )

    diagnostics = collect_input_file_diagnostics(context)

    assert diagnostics["reference_genome_path"] == str(genome_fa)
    assert diagnostics["genome_gff_path"] == str(genome_gff)
    assert diagnostics["annotation_path"] == str(annotation)
    assert diagnostics["rnaseq_read_count"] == 1
