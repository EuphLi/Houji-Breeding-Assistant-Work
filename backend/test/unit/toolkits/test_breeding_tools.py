from __future__ import annotations

"""Unit tests for the flavonoid breeding tools.

这个文件在链路中的作用：
1. 验证 7 个育种 Tool 已注册到 YuXi Tool Registry；
2. 验证 smoke 最小数据场景下，各 Tool 的最小行为合同仍成立；
3. 验证最终建议包含强制字段，并且不会越过当前 demo 边界。

它不是端到端科学验证，也不代表真实群体验证或湿实验验证已经完成。
"""

import json
import subprocess
from pathlib import Path

from yuxi.agents.toolkits import get_all_tool_instances
from yuxi.agents.toolkits.breeding.tools import (
    TARGET_GENE,
    _check_pipeline_dependencies,
    _run_transcriptome_deg_impl,
    _run_transcriptome_pipeline,
    _guard_advice,
    breeding_advice_generate,
    breeding_literature_evidence,
    breeding_metabolome_prepare,
    breeding_reference_prepare,
    breeding_transcriptome_deg,
    breeding_validation_plan,
    smoke_flavonoid_breeding_advice,
)


def _build_smoke_dir(base: Path) -> Path:
    # 这个函数在大多数单元测试开始前被调用。
    # 输入是 pytest 提供的临时目录；输出是一个最小 smoke 数据目录。
    # 它模拟了工作台链路里会被 Tool 读取的关键文件：
    # - 参考信息
    # - DEG 结果
    # - 代谢组 TSV
    # - verified_literature_evidence.tsv
    data_dir = base / "smoke_case"
    (data_dir / "fq").mkdir(parents=True)
    (data_dir / "fq" / "sample1.fq.gz").write_bytes(b"fake-fastq")
    (data_dir / "genome.fa").write_text(">chr1\nATGC\n", encoding="utf-8")
    (data_dir / "genome.gff").write_text(f"chr1\tsrc\tgene\t1\t10\t.\t+\t.\tID={TARGET_GENE}\n", encoding="utf-8")
    (data_dir / "xiaomi_T2T_Annotation.smoke_genes.txt").write_text(
        f"{TARGET_GENE}\tflavonoid candidate\n",
        encoding="utf-8",
    )
    (data_dir / "sampleName_clientId.txt").write_text("sample1\tgroupA\n", encoding="utf-8")
    (data_dir / "run_smoke_de_pipeline.sh").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    (data_dir / "metabolome_raw_3372.tsv").write_text(
        "compound\tannotation\tpathway\nquercetin\tflavonoid\t黄酮\n",
        encoding="utf-8",
    )
    (data_dir / "significant_de_genes.tsv").write_text(
        "gene_id\tlog2FC\tpadj\nSi9g037800\t1.8\t0.001\n",
        encoding="utf-8",
    )
    (data_dir / "verified_literature_evidence.tsv").write_text(
        "\t".join([
            "gene_id",
            "trait",
            "doi",
            "title",
            "quoted_sentence",
            "source",
            "curation_status",
            "evidence_level",
            "note",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.3390/life11060578",
            "Comparative Analysis of Flavonoid Metabolites in Foxtail Millet (Setaria italica) with Different Eating Quality",
            "The yellow pigment mainly includes carotenoids (lutein and zeaxanthin) and flavonoids.",
            "publisher",
            "verified",
            "crop_trait_background",
            "谷子黄酮背景证据，不是 Si9g037800 直接功能验证。",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.1186/s12864-025-11780-x",
            "Targeted metabolomic and transcriptomic analyses provide insights into flavonoid biosynthesis in the grain of Foxtail millet",
            "Foxtail millet (Setaria italica L.), a traditional Chinese crop, is valued for its rich abundance of health-beneficial compounds (e.g., flavonoids).",
            "publisher",
            "accepted",
            "pathway_background",
            "谷子黄酮生物合成背景证据，不是 Si9g037800 直接功能验证。",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.9999/demo-row-should-be-filtered",
            "Demo row should not enter real evidence",
            "This row should never be exposed as a real citation.",
            "publisher",
            "demo",
            "high",
            "演示行，不应进入真实文献证据。",
        ])
        + "\n",
        encoding="utf-8",
    )
    return data_dir


def test_all_flavonoid_breeding_tools_registered():
    # 先确认 Tool Registry 里真的能看到这 7 个育种 Tool。
    # 这一步验证的是“Agent 是否有机会调用到它们”，不是验证业务结果内容。
    names = {tool.name for tool in get_all_tool_instances()}

    assert {
        "smoke_flavonoid_breeding_advice",
        "breeding_reference_prepare",
        "breeding_transcriptome_deg",
        "breeding_metabolome_prepare",
        "breeding_literature_evidence",
        "breeding_advice_generate",
        "breeding_validation_plan",
    }.issubset(names)


def test_smoke_tool_missing_data_dir_returns_error(tmp_path: Path):
    # 缺失 data_dir 时，一键 smoke 入口应直接返回统一错误，而不是伪造成功结果。
    result = smoke_flavonoid_breeding_advice.invoke({
        "data_dir": str(tmp_path / "missing"),
        "out_dir": str(tmp_path / "out"),
        "run_transcriptome": False,
    })

    assert result["status"] == "error"
    assert "data_dir does not exist" in result["error"]
    assert result["artifacts"] == []


def test_reference_prepare_finds_target_gene(tmp_path: Path):
    # 参考信息 Tool 只负责从参考文件中确认目标基因痕迹，不做智能分析。
    data_dir = _build_smoke_dir(tmp_path)

    result = breeding_reference_prepare.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "reference_out"),
    })

    assert result["status"] == "completed"
    assert result["gene_found_in_gff"] is True
    assert result["gene_found_in_annotation"] is True


def test_transcriptome_deg_run_pipeline_false_reads_existing_result(tmp_path: Path):
    # 当 run_pipeline=false 时，转录组 Tool 应回收已有 DEG 结果，并检查 Si9g037800 是否出现。
    data_dir = _build_smoke_dir(tmp_path)

    result = breeding_transcriptome_deg.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "transcriptome_out"),
        "run_pipeline": False,
    })

    assert result["status"] == "completed"
    assert result["target_gene_found"] is True
    assert Path(result["significant_de_genes_path"]).exists()


def test_transcriptome_deg_writes_run_log_when_pipeline_script_missing(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "uploaded_case"
    (data_dir / "fq").mkdir(parents=True)
    (data_dir / "fq" / "sample1.fq.gz").write_bytes(b"fake-fastq")
    (data_dir / "genome.fa").write_text(">chr1\nATGC\n", encoding="utf-8")
    (data_dir / "genome.gff").write_text("chr1\tsrc\tgene\t1\t10\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    (data_dir / "sampleName_clientId.txt").write_text("sample1\tgroupA\n", encoding="utf-8")

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._resolve_transcriptome_pipeline_script",
        lambda _data_dir: (None, None),
    )

    result = _run_transcriptome_deg_impl(
        data_dir=str(data_dir),
        fq_dir="fq",
        sample_map="sampleName_clientId.txt",
        genome_fa="genome.fa",
        genome_gff="genome.gff",
        out_dir=str(data_dir / "transcriptome_deg"),
        threads=4,
        run_pipeline=True,
    )

    run_log = data_dir / "transcriptome_deg" / "run.log"
    assert run_log.exists()
    log_text = run_log.read_text(encoding="utf-8")
    assert "resolved_pipeline_script_path:" in log_text
    assert result["status"] == "error"
    assert result["transcriptome_pipeline_status"] == "failed"
    assert result["pipeline_log_path"] == str(run_log)
    assert result["missing_inputs"] == []


def test_transcriptome_deg_writes_run_log_when_genome_gff_missing(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "uploaded_case"
    (data_dir / "fq").mkdir(parents=True)
    (data_dir / "fq" / "sample1.fq.gz").write_bytes(b"fake-fastq")
    (data_dir / "genome.fa").write_text(">chr1\nATGC\n", encoding="utf-8")
    (data_dir / "sampleName_clientId.txt").write_text("sample1\tgroupA\n", encoding="utf-8")
    script = tmp_path / "run_smoke_de_pipeline.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._resolve_transcriptome_pipeline_script",
        lambda _data_dir: (script, str(script)),
    )

    result = _run_transcriptome_deg_impl(
        data_dir=str(data_dir),
        fq_dir="fq",
        sample_map="sampleName_clientId.txt",
        genome_fa="genome.fa",
        genome_gff="genome.gff",
        out_dir=str(data_dir / "transcriptome_deg"),
        threads=4,
        run_pipeline=True,
    )

    run_log = data_dir / "transcriptome_deg" / "run.log"
    assert run_log.exists()
    assert "genome.gff" in run_log.read_text(encoding="utf-8")
    assert result["status"] == "error"
    assert result["transcriptome_pipeline_status"] == "not_enough_inputs"
    assert any(item.endswith("genome.gff") for item in result["missing_inputs"])


def test_transcriptome_deg_reports_completed_output_in_upload_root(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "uploaded_case"
    (data_dir / "fq").mkdir(parents=True)
    (data_dir / "fq" / "sample1.fq.gz").write_bytes(b"fake-fastq")
    (data_dir / "genome.fa").write_text(">chr1\nATGC\n", encoding="utf-8")
    (data_dir / "genome.gff").write_text("chr1\tsrc\tgene\t1\t10\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    (data_dir / "sampleName_clientId.txt").write_text("sample1\tgroupA\n", encoding="utf-8")
    script = tmp_path / "run_smoke_de_pipeline.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._resolve_transcriptome_pipeline_script",
        lambda _data_dir: (script, str(script)),
    )
    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._check_pipeline_dependencies",
        lambda **kwargs: {
            "runner": "",
            "mode": "current_path",
            "checks": {},
            "r_package_checks": {},
            "missing_tools": [],
            "missing_r_packages": [],
        },
    )

    def fake_pipeline(*args, **kwargs):
        out_dir = args[1]
        deg_dir = out_dir / "de_pipeline_out" / "04_de"
        deg_dir.mkdir(parents=True, exist_ok=True)
        (deg_dir / "significant_de_genes.tsv").write_text(
            "gene_id\tlogFC\tpvalue\tpadj\nGeneA\t1.0\t0.01\t0.02\n",
            encoding="utf-8",
        )
        return {
            "attempted": True,
            "returncode": 0,
            "command": ["bash", str(script)],
            "stdout_tail": "",
            "stderr_tail": "",
            "error": "",
            "resolved_script_path": str(script),
        }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._run_transcriptome_pipeline",
        fake_pipeline,
    )

    result = _run_transcriptome_deg_impl(
        data_dir=str(data_dir),
        fq_dir="fq",
        sample_map="sampleName_clientId.txt",
        genome_fa="genome.fa",
        genome_gff="genome.gff",
        out_dir=str(data_dir / "transcriptome_deg"),
        threads=4,
        run_pipeline=True,
    )

    assert result["status"] == "completed"
    assert result["transcriptome_pipeline_status"] == "completed"
    assert Path(result["significant_de_genes_path"]).exists()
    assert result["significant_de_genes_path"] == str(data_dir / "transcriptome_deg" / "significant_de_genes.tsv")


def test_pipeline_dependency_checks_use_current_path_when_runner_unset(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TRANSCRIPTOME_PIPELINE_RUNNER", raising=False)
    seen_commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        seen_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    diagnostics = _check_pipeline_dependencies(data_dir=tmp_path)

    assert diagnostics["mode"] == "current_path"
    assert diagnostics["runner"] == ""
    assert seen_commands[0] == ["hisat2-build", "--version"]
    assert all(command[0] != "micromamba" for command in seen_commands)


def test_pipeline_dependency_checks_use_configured_runner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPTOME_PIPELINE_RUNNER", "micromamba run -n rnaseq_deg")
    seen_commands: list[list[str]] = []
    monkeypatch.setattr("shutil.which", lambda name: f"/home/test/.local/bin/{name}" if name == "micromamba" else None)

    def fake_run(command, **kwargs):
        assert isinstance(command, list)
        seen_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    diagnostics = _check_pipeline_dependencies(data_dir=tmp_path)

    assert diagnostics["mode"] == "runner"
    assert diagnostics["runner"] == "micromamba run -n rnaseq_deg"
    assert seen_commands[0][:4] == ["/home/test/.local/bin/micromamba", "run", "-n", "rnaseq_deg"]
    assert "Rscript" in seen_commands[-1]
    assert all("||" not in command for command in seen_commands)
    assert diagnostics["checks"]["hisat2"]["command_list"] == [
        "/home/test/.local/bin/micromamba",
        "run",
        "-n",
        "rnaseq_deg",
        "hisat2",
        "--version",
    ]
    assert diagnostics["runner_info"]["resolved_executable"] == "/home/test/.local/bin/micromamba"


def test_pipeline_dependency_checks_accept_absolute_runner_path(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPTOME_PIPELINE_RUNNER", "/tmp/fake-micromamba run -n rnaseq_deg")
    seen_commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        seen_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    diagnostics = _check_pipeline_dependencies(data_dir=tmp_path)

    assert seen_commands[0][:4] == ["/tmp/fake-micromamba", "run", "-n", "rnaseq_deg"]
    assert diagnostics["runner_info"]["resolved_args"][:4] == ["/tmp/fake-micromamba", "run", "-n", "rnaseq_deg"]


def test_pipeline_dependency_checks_capture_runner_executable_not_found(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPTOME_PIPELINE_RUNNER", "micromamba run -n rnaseq_deg")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr("pathlib.Path.exists", lambda self: False)

    diagnostics = _check_pipeline_dependencies(data_dir=tmp_path)

    assert diagnostics["missing_tools"] == ["hisat2-build", "hisat2", "samtools", "featureCounts", "Rscript"]
    assert diagnostics["checks"]["hisat2"]["runner_executable_not_found"] == "micromamba"
    assert "FileNotFoundError" in diagnostics["checks"]["hisat2"]["exception"]
    assert diagnostics["checks"]["hisat2"]["runner_resolution_attempts"]


def test_pipeline_r_package_checks_use_same_runner(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPTOME_PIPELINE_RUNNER", "micromamba run -n rnaseq_deg")
    seen_commands: list[list[str]] = []
    monkeypatch.setattr("shutil.which", lambda name: f"/home/test/.local/bin/{name}" if name == "micromamba" else None)

    def fake_run(command, **kwargs):
        seen_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    diagnostics = _check_pipeline_dependencies(data_dir=tmp_path)

    rscript_commands = [command for command in seen_commands if "Rscript" in command]
    assert rscript_commands
    assert all(
        command[:4] == ["/home/test/.local/bin/micromamba", "run", "-n", "rnaseq_deg"]
        for command in rscript_commands
    )
    assert diagnostics["missing_r_packages"] == []


def test_transcriptome_pipeline_executes_with_runner_prefix(tmp_path: Path, monkeypatch):
    script = tmp_path / "run_smoke_de_pipeline.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    run_log = tmp_path / "run.log"
    monkeypatch.setenv("TRANSCRIPTOME_PIPELINE_RUNNER", "micromamba run -n rnaseq_deg")
    monkeypatch.setattr("shutil.which", lambda name: f"/home/test/.local/bin/{name}" if name == "micromamba" else None)
    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._resolve_transcriptome_pipeline_script",
        lambda _data_dir: (script, str(script)),
    )
    seen_commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        seen_commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="pipeline ok\n", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    result = _run_transcriptome_pipeline(
        tmp_path,
        tmp_path / "transcriptome_deg",
        4,
        run_log,
        fq_dir="fq",
        sample_map="sampleName_clientId.txt",
        genome_fa="genome.fa",
        genome_gff="genome.gff",
    )

    assert result["runner"] == "micromamba run -n rnaseq_deg"
    assert seen_commands[0][:4] == ["/home/test/.local/bin/micromamba", "run", "-n", "rnaseq_deg"]
    assert seen_commands[0][4:] == [
        "bash",
        str(script),
        "--fa",
        "genome.fa",
        "--gff",
        "genome.gff",
        "--fq-dir",
        "fq",
        "--sample-map",
        "sampleName_clientId.txt",
        "--outdir",
        str(tmp_path / "transcriptome_deg" / "de_pipeline_out"),
        "--threads",
        "4",
    ]


def test_transcriptome_deg_reports_missing_runner_dependencies(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "uploaded_case"
    (data_dir / "fq").mkdir(parents=True)
    (data_dir / "fq" / "sample1.fq.gz").write_bytes(b"fake-fastq")
    (data_dir / "genome.fa").write_text(">chr1\nATGC\n", encoding="utf-8")
    (data_dir / "genome.gff").write_text("chr1\tsrc\tgene\t1\t10\t.\t+\t.\tID=GeneA\n", encoding="utf-8")
    (data_dir / "sampleName_clientId.txt").write_text("sample1\tgroupA\n", encoding="utf-8")
    script = tmp_path / "run_smoke_de_pipeline.sh"
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")

    monkeypatch.setenv("TRANSCRIPTOME_PIPELINE_RUNNER", "micromamba run -n rnaseq_deg")
    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._resolve_transcriptome_pipeline_script",
        lambda _data_dir: (script, str(script)),
    )
    monkeypatch.setattr(
        "yuxi.agents.toolkits.breeding.tools._check_pipeline_dependencies",
        lambda **kwargs: {
            "runner": "micromamba run -n rnaseq_deg",
            "mode": "runner",
            "checks": {
                "hisat2": {
                    "tool": "hisat2",
                    "command": ["micromamba", "run", "-n", "rnaseq_deg", "hisat2", "--version"],
                    "command_display": "micromamba run -n rnaseq_deg hisat2 --version",
                    "available": False,
                    "returncode": 1,
                    "stdout_tail": "",
                    "stderr_tail": "missing",
                    "exception": "",
                    "runner_executable_not_found": "",
                }
            },
            "r_package_checks": {},
            "missing_tools": ["hisat2", "samtools"],
            "missing_r_packages": [],
        },
    )

    result = _run_transcriptome_deg_impl(
        data_dir=str(data_dir),
        fq_dir="fq",
        sample_map="sampleName_clientId.txt",
        genome_fa="genome.fa",
        genome_gff="genome.gff",
        out_dir=str(data_dir / "transcriptome_deg"),
        threads=4,
        run_pipeline=True,
    )

    run_log = data_dir / "transcriptome_deg" / "run.log"
    log_text = run_log.read_text(encoding="utf-8")
    assert result["transcriptome_pipeline_status"] == "failed"
    assert result["transcriptome_pipeline_decision_reason"] == "pipeline_dependencies_missing"
    assert result["transcriptome_pipeline_runner"] == "micromamba run -n rnaseq_deg"
    assert "transcriptome_pipeline_runner: micromamba run -n rnaseq_deg" in log_text
    assert "missing_tools: hisat2, samtools" in log_text
    assert "dependency_check_results:" in log_text
    assert "  - tool: hisat2" in log_text
    assert "command: micromamba run -n rnaseq_deg hisat2 --version" in log_text


def test_metabolome_prepare_detects_flavonoid_keywords(tmp_path: Path):
    # 代谢组 Tool 当前只读取 TSV 并识别黄酮相关背景词，不宣称因果验证。
    data_dir = _build_smoke_dir(tmp_path)

    result = breeding_metabolome_prepare.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "metabolome_out"),
    })

    assert result["status"] == "completed"
    assert result["flavonoid_related"] is True
    assert "黄酮" in result["matched_terms"] or "flavonoid" in result["matched_terms"]


def test_literature_evidence_reads_real_doi_and_quote(tmp_path: Path):
    # DOI 和引用原句必须来自真实 TSV 证据，而不是由大模型编造。
    data_dir = _build_smoke_dir(tmp_path)

    result = breeding_literature_evidence.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "literature_out"),
    })

    assert result["status"] == "completed"
    assert len(result["entries"]) == 2
    assert result["entries"][0]["doi"] == "10.3390/life11060578"
    assert "flavonoids" in result["entries"][0]["quoted_sentence"]
    assert {entry["evidence_level"] for entry in result["entries"]} == {"background"}


def test_literature_evidence_filters_pending_rejected_and_demo_rows(tmp_path: Path):
    # 只有 verified / curated / accepted 能进入真实 DOI 与引用原句通道。
    data_dir = _build_smoke_dir(tmp_path)
    (data_dir / "verified_literature_evidence.tsv").write_text(
        "\t".join([
            "gene_id",
            "trait",
            "doi",
            "title",
            "quoted_sentence",
            "source",
            "curation_status",
            "evidence_level",
            "note",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.1000/verified-one",
            "Verified row",
            "Verified sentence.",
            "publisher",
            "verified",
            "high",
            "保留",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.1000/pending-one",
            "Pending row",
            "Pending sentence.",
            "publisher",
            "pending",
            "high",
            "过滤",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.1000/rejected-one",
            "Rejected row",
            "Rejected sentence.",
            "publisher",
            "rejected",
            "medium",
            "过滤",
        ])
        + "\n"
        + "\t".join([
            TARGET_GENE,
            "黄酮相关",
            "10.1000/demo-one",
            "Demo row",
            "Demo sentence.",
            "publisher",
            "demo",
            "background",
            "过滤",
        ])
        + "\n",
        encoding="utf-8",
    )

    result = breeding_literature_evidence.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "literature_filter_out"),
    })

    assert result["status"] == "completed"
    assert [entry["doi"] for entry in result["entries"]] == ["10.1000/verified-one"]


def test_advice_generate_uses_placeholder_when_verified_literature_missing(tmp_path: Path):
    # 没有 verified_literature_evidence.tsv 时，只能回退为占位符，不能编造 DOI 或引用原文。
    data_dir = _build_smoke_dir(tmp_path)
    (data_dir / "verified_literature_evidence.tsv").unlink()

    result = breeding_advice_generate.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "advice_placeholder_out"),
    })

    advice = result["advice_markdown"]
    assert "真实 DOI：待文献检索补充" in advice
    assert "引用原文：待文献检索补充" in advice
    assert "10.3390/life11060578" not in advice


def test_advice_generate_contains_required_terms_and_real_evidence(tmp_path: Path):
    # 建议生成 Tool 需要把已打捞到的信息整合成最终建议，同时保留 DOI、引用原文和边界说明。
    data_dir = _build_smoke_dir(tmp_path)

    result = breeding_advice_generate.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "advice_out"),
    })

    advice = result["advice_markdown"]
    assert result["status"] in {"completed", "completed_with_warnings"}
    assert TARGET_GENE in advice
    assert "群体" in advice
    assert "黄酮" in advice
    assert "10.3390/life11060578" in advice
    assert "引用原文" in advice
    assert "不是 Si9g037800 直接功能验证" in advice
    assert result["guard_result"]["passed"] is True


def test_validation_plan_contains_population_trait_and_markers(tmp_path: Path):
    # 验证计划 Tool 只能输出“后续怎么做”，不能写成“已经做完”。
    result = breeding_validation_plan.invoke({
        "out_dir": str(tmp_path / "validation_out"),
    })

    plan = result["validation_plan"]
    assert result["status"] == "completed"
    assert "群体" in plan
    assert "黄酮" in plan
    assert "SNP/InDel/KASP/CAPS" in plan
    assert "不是已完成的群体验证" in plan


def test_smoke_flavonoid_breeding_advice_old_entrypoint_still_works(tmp_path: Path):
    # 一键 smoke 入口仍然要能复用模块化 Tool，并产出受 guard 约束的最终建议。
    data_dir = _build_smoke_dir(tmp_path)

    result = smoke_flavonoid_breeding_advice.invoke({
        "data_dir": str(data_dir),
        "out_dir": str(tmp_path / "smoke_out"),
        "run_transcriptome": False,
    })

    advice = result["advice_markdown"]
    assert result["status"] in {"completed", "completed_with_warnings"}
    assert TARGET_GENE in advice
    assert "群体" in advice
    assert "黄酮" in advice
    assert "10.3390/life11060578" in advice
    assert result["guard_result"]["passed"] is True
    guard_path = Path(tmp_path / "smoke_out" / "guard_result.json")
    assert json.loads(guard_path.read_text(encoding="utf-8"))["passed"] is True


def test_smoke_advice_guard_required_terms_pass():
    # guard 至少要检查目标基因、群体、黄酮和文献占位字段是否存在。
    advice = "\n".join([
        f"核心基因：{TARGET_GENE}",
        "建议扩大群体并检测黄酮含量。",
        "真实 DOI：待文献检索补充",
        "引用原文：待文献检索补充",
    ])

    result = _guard_advice(advice)

    assert result["passed"] is True
    assert result["checks"]["contains_target_gene"] is True
    assert result["checks"]["contains_population"] is True
    assert result["checks"]["contains_flavonoid"] is True


def test_smoke_advice_guard_rejects_missing_required_terms():
    # 如果最终输出缺少强制字段，guard 应明确拒绝。
    result = _guard_advice("候选建议：后续验证。")

    assert result["passed"] is False
    assert any(TARGET_GENE in err for err in result["errors"])
    assert any("群体" in err for err in result["errors"])
    assert any("黄酮" in err for err in result["errors"])


def test_smoke_guard_does_not_fabricate_doi_placeholder():
    # 当 advice 只展示“待文献检索补充”占位符时，guard 不应把它误判成伪造 DOI。
    advice = "\n".join([
        f"{TARGET_GENE} 可作为黄酮相关候选线索。",
        "后续需要在群体中验证。",
        "真实 DOI：待文献检索补充",
        "引用原文：待文献检索补充",
    ])

    result = _guard_advice(advice)

    assert result["passed"] is True
    assert result["unsupported_dois"] == []
    assert result["checks"]["has_literature_placeholder"] is True


def test_smoke_guard_allows_explicit_smoke_boundary():
    # 显式写出 smoke 边界时，guard 应允许这种“非生产级”表述存在。
    advice = "\n".join([
        f"{TARGET_GENE} 是黄酮相关候选线索。",
        "后续需要在群体中验证。",
        "本结果来自 smoke 测试流程，不是生产级全基因组结论。",
        "真实 DOI：待文献检索补充",
        "引用原文：待文献检索补充",
    ])

    result = _guard_advice(advice)

    assert result["passed"] is True
    assert result["checks"]["claims_production_grade"] is False


def test_smoke_guard_rejects_boundary_overclaims():
    # 如果输出声称群体验证或湿实验已经完成，guard 必须拦截。
    advice = "\n".join([
        f"{TARGET_GENE} 是黄酮相关候选基因。",
        "已完成群体验证，已完成湿实验验证。",
        "真实 DOI：待文献检索补充",
        "引用原文：待文献检索补充",
    ])

    result = _guard_advice(advice)

    assert result["passed"] is False
    assert result["checks"]["claims_population_validation_completed"] is True
    assert result["checks"]["claims_wet_lab_completed"] is True


def test_smoke_guard_rejects_marker_completion_and_final_conclusion_overclaims():
    # KASP/CAPS 和“最终育种结论”在本轮都只能作为后续计划，不能写成已完成。
    advice = "\n".join([
        f"{TARGET_GENE} 是黄酮相关候选基因。",
        "后续需要在群体中验证。",
        "最终育种结论已经明确，KASP 标记已开发完成。",
        "真实 DOI：待文献检索补充",
        "引用原文：待文献检索补充",
    ])

    result = _guard_advice(advice)

    assert result["passed"] is False
    assert result["checks"]["claims_marker_development_completed"] is True
    assert result["checks"]["claims_final_breeding_conclusion"] is True
