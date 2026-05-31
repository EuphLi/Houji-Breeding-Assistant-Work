# 固定转录组流程运行环境

本文档只说明 `FASTQ -> significant_de_genes.tsv` 固定转录组流程需要的外部生信环境。不要把这些二进制安装进 `backend/.venv`。

## 依赖

固定流程至少需要：

- `hisat2`
- `samtools`
- `subread`（提供 `featureCounts`）
- `r-base`（提供 `Rscript`）
- `bioconductor-limma`
- `r-optparse`
- `r-data.table`

当前代码默认检查的 R 包是：

- `limma`
- `optparse`
- `data.table`

如果后续固定脚本明确依赖 `edgeR`，再额外安装：

- `bioconductor-edger`

## 推荐安装方式

推荐使用 `micromamba` 或兼容的 conda 环境，不要污染 `backend/.venv`。

示例：

```bash
micromamba install -n rnaseq_deg -c conda-forge -c bioconda \
  hisat2 samtools subread r-base bioconductor-limma r-optparse r-data.table
```

如果脚本确认需要 `edgeR`：

```bash
micromamba install -n rnaseq_deg -c conda-forge -c bioconda bioconductor-edger
```

## Worker 启动方式

保持 API / worker 仍运行在项目自己的 Python 环境里，只把外部生信 CLI 通过 runner 调起：

```bash
MICROMAMBA_BIN="$(command -v micromamba)"
export TRANSCRIPTOME_PIPELINE_RUNNER="$MICROMAMBA_BIN run -n rnaseq_deg"
PYTHONPATH=backend/package:backend backend/.venv/bin/arq server.worker_main.WorkerSettings
```

如果 `command -v micromamba` 返回空值，不要继续用裸 `micromamba`，而应手动写绝对路径，例如：

```bash
export TRANSCRIPTOME_PIPELINE_RUNNER="/home/li/.local/bin/micromamba run -n rnaseq_deg"
```

未设置 `TRANSCRIPTOME_PIPELINE_RUNNER` 时，worker 会直接使用当前 `PATH` 检查和执行 `hisat2` / `samtools` / `featureCounts` / `Rscript`。

## 验证命令

先验证 CLI：

```bash
MICROMAMBA_BIN="$(command -v micromamba)"
echo "$TRANSCRIPTOME_PIPELINE_RUNNER"
$MICROMAMBA_BIN run -n rnaseq_deg hisat2 --version
$MICROMAMBA_BIN run -n rnaseq_deg hisat2-build --version
$MICROMAMBA_BIN run -n rnaseq_deg samtools --version
$MICROMAMBA_BIN run -n rnaseq_deg featureCounts -v
$MICROMAMBA_BIN run -n rnaseq_deg Rscript --version
```

再验证 R 包：

```bash
$MICROMAMBA_BIN run -n rnaseq_deg Rscript -e 'pkgs <- c("limma","optparse","data.table"); for (p in pkgs) cat(p, requireNamespace(p, quietly=TRUE), "\n")'
```

如果固定脚本后续明确要求 `edgeR`，再检查：

```bash
$MICROMAMBA_BIN run -n rnaseq_deg Rscript -e 'cat("edgeR", requireNamespace("edgeR", quietly=TRUE), "\n")'
```

## 故障排查

如果真实页面仍失败，优先看本次 run 的：

- `<upload_root>/transcriptome_deg/run.log`
- `<upload_root>/transcriptome_deg/manifest.json`
- `<upload_root>/transcriptome_deg/transcriptome_manifest.json`

重点字段：

- `transcriptome_pipeline_runner`
- `resolved_pipeline_runner_args`
- `resolved_pipeline_runner_executable`
- `runner_resolution_attempts`
- `runner_executable_not_found`
- `dependency_check_mode`
- `dependency_check_commands`
- `dependency_check_results`
- `missing_tools`
- `missing_r_packages`
- `resolved_pipeline_script_path`
- `final_command`
- `next_step_hint`

当 `missing_tools` 或 `missing_r_packages` 非空时，按 `run.log` 中的提示补齐 `rnaseq_deg` 环境即可。
