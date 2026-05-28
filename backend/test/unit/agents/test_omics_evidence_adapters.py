from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.context import (
    OmicsBreedingAnalysisContext,
)
from yuxi.agents.buildin.omics_breeding_analysis.evidence_adapters import (
    build_omics_evidence_pack_from_context,
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