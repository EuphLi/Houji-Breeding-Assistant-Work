from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from yuxi.services.tool_service import get_tool_metadata
from yuxi.agents.buildin.omics_breeding_analysis.literature_search import (
    build_literature_queries,
    search_background_literature,
)
from yuxi.agents.buildin.omics_breeding_analysis import workflow as omics_workflow
from yuxi.agents.toolkits.breeding.omics_analysis import (
    _run_omics_breeding_analysis_impl,
    omics_breeding_analysis_run,
)
from yuxi.agents.toolkits.buildin.pubmed import pubmed_search


# 测试不通过 Tool Registry，而是直接测 _run_omics_breeding_analysis_impl()。这样能稳定验证：
# TSV 输入
# → 新 workflow
# → final_result.json
def test_omics_breeding_analysis_tool_impl_writes_final_result(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\tannotation\n"
        "GeneA\t1.8\t0.003\t0.02\tchalcone--flavonone isomerase\n",
        encoding="utf-8",
    )

    literature_path = tmp_path / "verified_literature_evidence.tsv"
    literature_path.write_text(
        "evidence_id\tdoi\tquoted_sentence\tstatus\tis_demo\tsource\ttitle\trelevance_level\n"
        "L1\t10.1234/real\tVerified sentence.\tverified\tfalse\tPubMed\tVerified Paper\tbackground\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "omics_run"

    result = _run_omics_breeding_analysis_impl(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        metabolome_path="",
        literature_evidence_path=str(literature_path),
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["status"] == "completed"
    assert result["backend"] == "canonical_renderer"
    assert result["raw_answer_backend"] == "rule_fallback"
    assert result["guard_result"]["passed"] is True
    assert result["summary"]["target_genes"] == ["GeneA"]

    assert "GeneA" in result["answer_markdown"]
    assert "抗旱" in result["answer_markdown"]
    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "10.1234/real" not in body
    assert "Verified sentence." not in body
    assert "DOI：10.1234/real" in source_index
    assert "引用原句：Verified sentence." in source_index
    assert "注释：chalcone--flavonone isomerase" in source_index
    assert result["summary"]["literature_path_exists"] is True
    assert result["summary"]["usable_literature_count"] == 1

    assert (output_dir / "omics_evidence_pack.json").exists()
    assert (output_dir / "answer_markdown.md").exists()
    assert (output_dir / "citation_result.json").exists()
    assert (output_dir / "guard_result.json").exists()
    assert (output_dir / "final_result.json").exists()

    loaded = json.loads((output_dir / "final_result.json").read_text(encoding="utf-8"))
    assert loaded["status"] == "completed"
    assert loaded["summary"]["target_genes"] == ["GeneA"]

    assert result["frontend_payload"]["schema_version"] == "omics_frontend_payload.v1"
    assert result["frontend_payload"]["guard_panel"]["passed"] is True
    assert result["frontend_payload"]["literature_panel"]["card_count"] == 1
    assert result["frontend_payload"]["claim_trace_panel"]["needs_citation_count"] == 0
    assert result["frontend_payload_path"]
    assert (output_dir / "frontend_payload.json").exists()


# 测试验证 breeding/__init__.py 已经导入新模块，使 @tool 注册逻辑生效
def test_omics_breeding_analysis_tool_is_imported_by_breeding_package():
    from yuxi.agents.toolkits import breeding  # noqa: F401
    from yuxi.agents.toolkits.registry import get_all_tool_instances

    tools = get_all_tool_instances()
    tool_names = {getattr(item, "name", "") for item in tools}

    assert "omics_breeding_analysis_run" in tool_names


def test_pubmed_search_is_registered_in_tool_registry():
    from yuxi.agents.toolkits import buildin  # noqa: F401
    from yuxi.agents.toolkits.registry import get_all_tool_instances

    tools = get_all_tool_instances()
    tool_names = {getattr(item, "name", "") for item in tools}

    assert "pubmed_search" in tool_names


def test_pubmed_search_is_exposed_in_tool_metadata():
    tools = get_tool_metadata()
    pubmed_tool = next(item for item in tools if item["id"] == "pubmed_search")

    assert pubmed_tool["name"] == "PubMed 搜索"
    assert pubmed_tool["category"] == "buildin"
    assert "搜索" in pubmed_tool["tags"]


def test_omics_breeding_analysis_tool_invoke_accepts_input_wrapper(monkeypatch):
    captured: dict[str, object] = {}

    def fake_impl(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "summary": {"ok": True}, "artifacts": []}

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.omics_analysis._run_omics_breeding_analysis_impl",
        fake_impl,
    )

    payload = {
        "trait": "黄酮相关",
        "question": "给出一些育种建议",
        "transcriptome_result_path": "",
        "metabolome_path": "",
        "literature_evidence_path": "",
        "evidence_pack_output_path": "",
        "output_dir": "/tmp/yuxi_runs/omics_breeding_analysis_debug",
        "use_llamaindex": False,
        "model": "",
    }

    result = omics_breeding_analysis_run.invoke({"input": payload})

    assert result["status"] == "completed"
    assert captured["trait"] == "黄酮相关"
    assert captured["question"] == "给出一些育种建议"


def test_omics_breeding_analysis_tool_invoke_without_input_wrapper_raises_validation_error():
    with pytest.raises(Exception, match="input"):
        omics_breeding_analysis_run.invoke({"trait": "黄酮相关", "question": "给出一些育种建议"})


def test_pubmed_search_parses_pubmed_xml_without_xmltodict(monkeypatch):
    esearch_payload = json.dumps(
        {"esearchresult": {"idlist": ["11111111"]}},
        ensure_ascii=False,
    ).encode("utf-8")
    efetch_payload = """\
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>11111111</PMID>
      <Article>
        <ArticleTitle>Foxtail millet flavonoid regulation</ArticleTitle>
        <Abstract>
          <AbstractText>Flavonoid accumulation changed in millet leaves.</AbstractText>
        </Abstract>
        <ELocationID EIdType="doi">10.1000/example</ELocationID>
      </Article>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="doi">10.1000/example</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
""".encode("utf-8")

    class FakeResponse:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        assert timeout == 10
        url = request.full_url
        parsed = urllib.parse.urlparse(url)
        params = urllib.parse.parse_qs(parsed.query)
        if parsed.path.endswith("esearch.fcgi"):
            assert params["retmax"] == ["2"]
            return FakeResponse(esearch_payload)
        if parsed.path.endswith("efetch.fcgi"):
            assert params["id"] == ["11111111"]
            return FakeResponse(efetch_payload)
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    result = pubmed_search.invoke({"query": "Setaria italica flavonoid", "max_results": 2})

    assert result["status"] == "completed"
    assert result["records"][0]["title"] == "Foxtail millet flavonoid regulation"
    assert result["records"][0]["doi"] == "10.1000/example"
    assert result["records"][0]["pmid"] == "11111111"
    assert result["records"][0]["abstract"] == "Flavonoid accumulation changed in millet leaves."
    assert result["records"][0]["url"] == "https://pubmed.ncbi.nlm.nih.gov/11111111/"


def test_search_background_literature_returns_unavailable_when_pubmed_fails(monkeypatch):
    class FakePubMedTool:
        @staticmethod
        def invoke(payload):
            raise TimeoutError(f"request timeout for {payload['query']}")

    monkeypatch.setattr(
        "yuxi.agents.toolkits.buildin.pubmed.pubmed_search",
        FakePubMedTool(),
    )

    result = search_background_literature(
        trait="黄酮相关",
        target_genes=["GeneA", "GeneB", "GeneC"],
        max_results=9,
    )

    assert result["status"] == "dynamic_search_unavailable"
    assert result["literature_source"] == "dynamic_search_unavailable"
    assert result["backend"] == "pubmed_search"
    assert result["records"] == []
    assert len(result["queries"]) == 3
    assert "PubMed query failed" in result["warnings"][0]


def test_omics_breeding_analysis_tool_impl_handles_empty_literature_path(tmp_path):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\tannotation\n"
        "GeneA\t1.8\t0.003\t0.02\tchalcone--flavonone isomerase\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "omics_run"

    result = _run_omics_breeding_analysis_impl(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        metabolome_path="",
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["status"] == "completed"
    assert result["summary"]["literature_path_exists"] is False
    assert result["summary"]["usable_literature_count"] == 0
    body, source_index = result["answer_markdown"].split("## 来源索引", maxsplit=1)
    assert "当前未检索到可用 PubMed 背景文献。[Guard]" in body
    assert "[BG1]" not in body
    assert "[BG2]" not in body
    assert "DOI：" not in body
    assert "当前未检索到可用 PubMed 背景文献" in body
    assert "DOI：" not in source_index
    assert "[BG1]" not in source_index
    assert "[BG2]" not in source_index
    assert all("BG" not in " ".join(row["citation_ids"]) for row in result["claim_trace"])


def test_omics_breeding_analysis_tool_impl_merges_background_literature_records(
    monkeypatch, tmp_path
):
    deg_path = tmp_path / "significant_de_genes.tsv"
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\tannotation\n"
        "GeneA\t1.8\t0.003\t0.02\tchalcone--flavonone isomerase\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "omics_run"

    def fake_background_search(**kwargs):
        assert kwargs["trait"] == "黄酮"
        assert kwargs["target_genes"] == ["GeneA"]
        return {
            "status": "completed",
            "backend": "pubmed_search",
            "literature_source": "pubmed_search",
            "queries": ["Setaria italica 黄酮", "GeneA Setaria italica"],
            "records": [
                {
                    "query": "Setaria italica 黄酮",
                    "title": "Flavonoid pathway in foxtail millet",
                    "doi": "10.1000/example",
                    "pmid": "123456",
                    "abstract": "Flavonoid accumulation changed in millet leaves.",
                    "quoted_sentence": "Flavonoid accumulation changed in millet leaves.",
                    "quote_scope": "abstract",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/123456/",
                    "source": "PubMed",
                }
            ],
            "warnings": [],
        }

    monkeypatch.setattr(omics_workflow, "search_background_literature", fake_background_search)

    result = _run_omics_breeding_analysis_impl(
        trait="黄酮",
        question="根据数据给出候选验证方案",
        transcriptome_result_path=str(deg_path),
        metabolome_path="",
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["status"] == "completed"
    assert result["summary"]["background_literature_count"] == 1
    assert result["summary"]["background_literature_backend"] == "pubmed_search"
    assert result["summary"]["background_literature_status"] == "completed"
    assert result["summary"]["background_literature_source"] == "pubmed_search"
    assert result["literature_cards"][0]["doi"] == "10.1000/example"
    assert result["literature_cards"][0]["quote_scope"] == "abstract"

    evidence_pack = json.loads((output_dir / "omics_evidence_pack.json").read_text(encoding="utf-8"))
    assert evidence_pack["background_literature_records"][0]["doi"] == "10.1000/example"
    assert (
        evidence_pack["background_literature_records"][0]["quoted_sentence"]
        == "Flavonoid accumulation changed in millet leaves."
    )


def test_build_literature_queries_adds_trait_specific_pubmed_terms():
    flavonoid_queries = build_literature_queries("黄酮相关", ["GeneA"])
    drought_queries = build_literature_queries("抗旱相关", ["GeneA"])
    yield_queries = build_literature_queries("高产相关", ["GeneA"])

    assert any("flavonoid" in item.lower() for item in flavonoid_queries)
    assert any("drought" in item.lower() or "abiotic stress" in item.lower() for item in drought_queries)
    assert any("yield" in item.lower() for item in yield_queries)


def test_omics_breeding_analysis_tool_marks_fastq_pipeline_failure_without_missing_input(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    (upload_root / "metabolome_raw_3372.tsv").write_text("compound\tvalue\nflavonoid_a\t12.5\n", encoding="utf-8")

    class FakeTranscriptomeTool:
        @staticmethod
        def invoke(payload):
            out_dir = Path(payload["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            run_log = out_dir / "run.log"
            run_log.write_text("pipeline failed\n", encoding="utf-8")
            return {
                "status": "error",
                "significant_de_genes_path": "",
                "missing_inputs": [],
                "missing_tools": [],
                "pipeline_result": {"attempted": True, "returncode": 1},
                "artifacts": [str(out_dir / "transcriptome_manifest.json"), str(run_log)],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools.breeding_transcriptome_deg",
        FakeTranscriptomeTool(),
    )

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path=str(upload_root / "metabolome_raw_3372.tsv"),
        reference_genome_path=str(upload_root / "genome.fa"),
        genome_gff_path=str(upload_root / "genome.gff"),
        annotation_path="",
        sample_map_path=str(upload_root / "sampleName_clientId.txt"),
        rnaseq_read_paths=[str(fq_dir / "sample1_R1.fq.gz")],
        upload_root=str(upload_root),
        uploaded_file_count=5,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["summary"]["transcriptome_input_status"] == "fastq_uploaded"
    assert result["summary"]["transcriptome_pipeline_status"] == "failed"
    assert result["summary"]["pipeline_log_path"].endswith("run.log")
    assert result["summary"]["pipeline_log_path"].startswith(str(upload_root / "transcriptome_deg"))
    assert result["summary"]["data_source"] == "user_provided_path"
    assert result["summary"]["metabolome_path_exists"] is True


def test_omics_breeding_analysis_tool_runs_fixed_pipeline_into_upload_root(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    (upload_root / "metabolome_raw_3372.tsv").write_text("compound\tvalue\ntrait_a\t12.5\n", encoding="utf-8")

    class FakeTranscriptomeTool:
        @staticmethod
        def invoke(payload):
            out_dir = Path(payload["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            deg_path = out_dir / "significant_de_genes.tsv"
            deg_path.write_text(
                "gene_id\tlogFC\tpvalue\tpadj\nGeneA\t1.5\t0.01\t0.03\n",
                encoding="utf-8",
            )
            run_log = out_dir / "run.log"
            run_log.write_text("pipeline completed\n", encoding="utf-8")
            manifest = out_dir / "manifest.json"
            manifest.write_text("{\"status\":\"completed\"}\n", encoding="utf-8")
            return {
                "status": "completed",
                "significant_de_genes_path": str(deg_path),
                "pipeline_result": {"attempted": True, "returncode": 0},
                "artifacts": [str(deg_path), str(manifest), str(run_log)],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools.breeding_transcriptome_deg",
        FakeTranscriptomeTool(),
    )

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="高产相关",
        question="围绕高产相关给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path=str(upload_root / "metabolome_raw_3372.tsv"),
        reference_genome_path=str(upload_root / "genome.fa"),
        genome_gff_path=str(upload_root / "genome.gff"),
        annotation_path="",
        sample_map_path=str(upload_root / "sampleName_clientId.txt"),
        rnaseq_read_paths=[str(fq_dir / "sample1_R1.fq.gz")],
        upload_root=str(upload_root),
        uploaded_file_count=5,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    expected_deg = upload_root / "transcriptome_deg" / "significant_de_genes.tsv"
    assert result["summary"]["transcriptome_pipeline_status"] == "completed"
    assert result["summary"]["transcriptome_input_status"] == "deg_generated_from_fastq"
    assert result["summary"]["transcriptome_path_exists"] is True
    assert result["summary"]["transcriptome_result_path"] == str(expected_deg)
    assert result["summary"]["pipeline_log_path"] == str(upload_root / "transcriptome_deg" / "run.log")
    assert result["summary"]["data_source"] == "omics_pipeline_generated"
    assert result["summary"]["metabolome_path_exists"] is True


def test_omics_breeding_analysis_tool_emits_transcriptome_progress_snapshots(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")

    class FakeTranscriptomeTool:
        @staticmethod
        def invoke(payload):
            out_dir = Path(payload["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            deg_path = out_dir / "significant_de_genes.tsv"
            deg_path.write_text("gene_id\tlogFC\tpvalue\tpadj\nGeneA\t1.5\t0.01\t0.03\n", encoding="utf-8")
            run_log = out_dir / "run.log"
            run_log.write_text("pipeline completed\n", encoding="utf-8")
            return {
                "status": "completed",
                "significant_de_genes_path": str(deg_path),
                "pipeline_result": {"attempted": True, "returncode": 0},
                "artifacts": [str(deg_path), str(run_log)],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools.breeding_transcriptome_deg",
        FakeTranscriptomeTool(),
    )

    progress_updates: list[dict[str, object]] = []
    output_dir = tmp_path / "omics_run"
    _run_omics_breeding_analysis_impl(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path=str(upload_root / "genome.fa"),
        genome_gff_path=str(upload_root / "genome.gff"),
        annotation_path="",
        sample_map_path=str(upload_root / "sampleName_clientId.txt"),
        rnaseq_read_paths=[str(fq_dir / "sample1_R1.fq.gz")],
        upload_root=str(upload_root),
        uploaded_file_count=4,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
        progress_callback=progress_updates.append,
    )

    assert [item["transcriptome_pipeline_status"] for item in progress_updates] == [
        "running",
        "completed",
    ]
    assert progress_updates[0]["transcriptome_pipeline_attempted"] is True
    assert progress_updates[1]["transcriptome_path_exists"] is True
    assert str(progress_updates[1]["transcriptome_result_path"]).endswith("significant_de_genes.tsv")


def test_omics_breeding_analysis_tool_emits_failed_transcriptome_progress_snapshot(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")

    class FakeTranscriptomeTool:
        @staticmethod
        def invoke(payload):
            out_dir = Path(payload["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            run_log = out_dir / "run.log"
            run_log.write_text("pipeline failed\n", encoding="utf-8")
            return {
                "status": "error",
                "significant_de_genes_path": "",
                "missing_inputs": [],
                "missing_tools": [],
                "pipeline_result": {"attempted": True, "returncode": 1},
                "artifacts": [str(run_log)],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools.breeding_transcriptome_deg",
        FakeTranscriptomeTool(),
    )

    progress_updates: list[dict[str, object]] = []
    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path=str(upload_root / "genome.fa"),
        genome_gff_path=str(upload_root / "genome.gff"),
        annotation_path="",
        sample_map_path=str(upload_root / "sampleName_clientId.txt"),
        rnaseq_read_paths=[str(fq_dir / "sample1_R1.fq.gz")],
        upload_root=str(upload_root),
        uploaded_file_count=4,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
        progress_callback=progress_updates.append,
    )

    assert [item["transcriptome_pipeline_status"] for item in progress_updates] == [
        "running",
        "failed",
    ]
    assert progress_updates[-1]["pipeline_log_path"] == result["summary"]["pipeline_log_path"]
    assert progress_updates[-1]["transcriptome_path_exists"] is False


def test_omics_breeding_analysis_tool_discovers_upload_root_inputs_before_pipeline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "A_1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (fq_dir / "A_2.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    (upload_root / "metabolome_raw_3372.tsv").write_text("compound\tvalue\ntrait_a\t12.5\n", encoding="utf-8")

    captured_payload: dict[str, object] = {}

    class FakeTranscriptomeTool:
        @staticmethod
        def invoke(payload):
            captured_payload.update(payload)
            out_dir = Path(payload["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            deg_path = out_dir / "significant_de_genes.tsv"
            deg_path.write_text(
                "gene_id\tlogFC\tpvalue\tpadj\nGeneA\t1.5\t0.01\t0.03\n",
                encoding="utf-8",
            )
            run_log = out_dir / "run.log"
            run_log.write_text("pipeline completed\n", encoding="utf-8")
            return {
                "status": "completed",
                "significant_de_genes_path": str(deg_path),
                "pipeline_result": {"attempted": True, "returncode": 0},
                "artifacts": [str(deg_path), str(run_log)],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools.breeding_transcriptome_deg",
        FakeTranscriptomeTool(),
    )

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="高产相关",
        question="围绕高产相关给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path="",
        genome_gff_path="",
        annotation_path="",
        sample_map_path="",
        rnaseq_read_paths=[],
        upload_root=str(upload_root),
        uploaded_file_count=6,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert captured_payload["data_dir"] == str(upload_root)
    assert captured_payload["fq_dir"] == "fq"
    assert captured_payload["sample_map"] == "sampleName_clientId.txt"
    assert captured_payload["genome_fa"] == "genome.fa"
    assert captured_payload["genome_gff"] == "genome.gff"
    assert captured_payload["out_dir"] == str(upload_root / "transcriptome_deg")
    assert result["summary"]["transcriptome_pipeline_status"] == "completed"
    assert result["summary"]["transcriptome_path_exists"] is True
    assert result["summary"]["metabolome_path_exists"] is True
    assert result["summary"]["submitted_rnaseq_read_paths"] == []
    assert result["summary"]["normalized_rnaseq_read_paths"]


def test_omics_breeding_analysis_tool_creates_run_log_when_fastq_inputs_incomplete(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "A_1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample1\tclient1\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "metabolome_raw_3372.tsv").write_text("compound\tvalue\ntrait_a\t12.5\n", encoding="utf-8")

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="抗旱相关",
        question="围绕抗旱相关给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path="",
        genome_gff_path="",
        annotation_path="",
        sample_map_path="",
        rnaseq_read_paths=[],
        upload_root=str(upload_root),
        uploaded_file_count=4,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    run_log = upload_root / "transcriptome_deg" / "run.log"
    assert run_log.exists()
    assert "missing genome.gff" in run_log.read_text(encoding="utf-8")
    assert result["summary"]["transcriptome_pipeline_status"] == "not_enough_inputs"
    assert result["summary"]["transcriptome_input_status"] == "fastq_uploaded"
    assert result["summary"]["pipeline_log_path"] == str(run_log)
    assert result["summary"]["data_source"] == "user_provided_path"
    assert result["summary"]["metabolome_path_exists"] is True


def test_omics_breeding_analysis_tool_does_not_fallback_to_smoke_gene_when_current_deg_failed(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    fq_dir = upload_root / "fq"
    fq_dir.mkdir(parents=True)
    (fq_dir / "sample1_R1.fq.gz").write_text("fake fastq\n", encoding="utf-8")
    (upload_root / "sampleName_clientId.txt").write_text("sample\tgroup\nsample1\tFla-LH\n", encoding="utf-8")
    (upload_root / "genome.fa").write_text(">chr1\nACGT\n", encoding="utf-8")
    (upload_root / "genome.gff").write_text("chr1\tsource\tgene\t1\t4\t.\t+\t.\tID=GeneA\n", encoding="utf-8")

    class FakeTranscriptomeTool:
        @staticmethod
        def invoke(payload):
            out_dir = Path(payload["out_dir"])
            out_dir.mkdir(parents=True, exist_ok=True)
            run_log = out_dir / "run.log"
            run_log.write_text("pipeline failed\n", encoding="utf-8")
            return {
                "status": "error",
                "significant_de_genes_path": "",
                "missing_inputs": [],
                "missing_tools": [],
                "pipeline_result": {"attempted": True, "returncode": 1},
                "artifacts": [str(run_log)],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools.breeding_transcriptome_deg",
        FakeTranscriptomeTool(),
    )

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path=str(upload_root / "genome.fa"),
        genome_gff_path=str(upload_root / "genome.gff"),
        annotation_path="",
        sample_map_path=str(upload_root / "sampleName_clientId.txt"),
        rnaseq_read_paths=[str(fq_dir / "sample1_R1.fq.gz")],
        upload_root=str(upload_root),
        uploaded_file_count=4,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["summary"]["candidate_genes"] == []
    assert result["summary"]["candidate_gene_source"] == "none"
    assert result["summary"]["candidate_gene_source_path"] == ""
    assert result["summary"]["candidate_gene_fallback_used"] is False
    assert "Si9g037800" not in result["answer_markdown"]
    assert "[T1]" not in result["answer_markdown"]


def test_omics_breeding_analysis_tool_uses_only_current_run_deg_output_for_candidate_gene(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    upload_root.mkdir(parents=True)
    deg_path = upload_root / "transcriptome_deg" / "significant_de_genes.tsv"
    deg_path.parent.mkdir(parents=True)
    deg_path.write_text(
        "gene_id\tlogFC\tpvalue\tpadj\tannotation\n"
        "GeneA\t1.5\t0.01\t0.03\tannotation A\n",
        encoding="utf-8",
    )
    historical_root = tmp_path / "historical_workspace"
    historical_root.mkdir(parents=True)
    (historical_root / "significant_de_genes.tsv").write_text(
        "gene_id\tlogFC\tpvalue\tpadj\nSi9g037800\t2.0\t0.001\t0.01\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path=str(deg_path),
        metabolome_path="",
        reference_genome_path="",
        genome_gff_path="",
        annotation_path="",
        sample_map_path="",
        rnaseq_read_paths=[],
        upload_root=str(upload_root),
        uploaded_file_count=1,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["summary"]["candidate_genes"] == ["GeneA"]
    assert result["summary"]["candidate_gene_source"] == "current_run_deg"
    assert result["summary"]["candidate_gene_source_path"] == str(deg_path)
    assert result["summary"]["candidate_gene_fallback_used"] is False
    assert "GeneA" in result["answer_markdown"]
    assert "Si9g037800" not in result["answer_markdown"]
    assert "[T1] 转录组 DEG" in result["answer_markdown"]
    assert "基因：GeneA" in result["answer_markdown"]
    assert "基因：Si9g037800" not in result["answer_markdown"]
    assert all("Si9g037800" not in row["text"] for row in result["claim_trace"])
    assert any("GeneA" in row["text"] and "T1" in row["citation_ids"] for row in result["claim_trace"])


def test_omics_breeding_analysis_tool_does_not_read_historical_deg_outside_current_upload_root(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(
        "yuxi.agents.buildin.omics_breeding_analysis.citation_engine.load_chat_model",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("disable llm for unit test")),
    )
    monkeypatch.setattr(
        omics_workflow,
        "search_background_literature",
        lambda **kwargs: {
            "status": "disabled_for_unit_test",
            "backend": "mock",
            "literature_source": "mock",
            "records": [],
            "warnings": [],
        },
    )

    upload_root = tmp_path / "uploaded_case"
    upload_root.mkdir(parents=True)
    historical_root = tmp_path / "historical_workspace"
    historical_root.mkdir(parents=True)
    (historical_root / "significant_de_genes.tsv").write_text(
        "gene_id\tlogFC\tpvalue\tpadj\nSi9g037800\t2.0\t0.001\t0.01\n",
        encoding="utf-8",
    )

    output_dir = tmp_path / "omics_run"
    result = _run_omics_breeding_analysis_impl(
        trait="黄酮相关",
        question="给出一些育种建议",
        transcriptome_result_path="",
        metabolome_path="",
        reference_genome_path="",
        genome_gff_path="",
        annotation_path="",
        sample_map_path="",
        rnaseq_read_paths=[],
        upload_root=str(upload_root),
        uploaded_file_count=0,
        literature_evidence_path="",
        evidence_pack_output_path=str(output_dir / "omics_evidence_pack.json"),
        output_dir=str(output_dir),
        use_llamaindex=False,
    )

    assert result["summary"]["candidate_genes"] == []
    assert result["summary"]["candidate_gene_source"] == "none"
    assert result["summary"]["candidate_gene_fallback_used"] is False
    assert "Si9g037800" not in result["answer_markdown"]
    assert "[T1]" not in result["answer_markdown"]
    assert "[T1] 转录组 DEG" not in result["answer_markdown"]
    assert all("T1" not in row["citation_ids"] for row in result["claim_trace"])
