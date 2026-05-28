# Phase 2 Smoke Flavonoid Breeding Tool

This document describes the first local YuXi implementation of the smoke-test
breeding paradigm. It is a minimal Tool, not a full migration of the old
`breeding-ai-agent` Gradio prototype.

## 1. Tool Name

`smoke_flavonoid_breeding_advice`

Registration path:

- `backend/package/yuxi/agents/toolkits/breeding/tools.py`
- imported by `backend/package/yuxi/agents/toolkits/__init__.py`

The Tool uses YuXi's existing `@tool` registration wrapper from
`backend/package/yuxi/agents/toolkits/registry.py`.

## 2. Input Parameters

- `data_dir`
  - Default: `/mnt/yuxi-breeding-data/smoke_test_minimal`
  - Smoke test data directory.
- `trait`
  - Default: `黄酮相关`
  - Trait focus for the advice.
- `out_dir`
  - Default: `/mnt/yuxi-breeding-data/yuxi_runs/smoke_flavonoid_breeding_advice`
  - Output directory for logs, advice, guard result, and manifest.
- `run_transcriptome`
  - Default: `true`
  - If true, calls `run_smoke_de_pipeline.sh`.
  - If false, reuses an existing `significant_de_genes.tsv` if present.

## 3. Output Fields

The Tool returns a dictionary with:

- `status`
  - `completed`, `completed_with_warnings`, `failed_guard`, or `error`.
- `advice_markdown`
  - Markdown breeding advice.
- `significant_de_genes_path`
  - Path to `significant_de_genes.tsv`, when available.
- `metabolome_path`
  - Path to `metabolome_raw_3372.tsv`.
- `guard_result`
  - Lightweight boundary and required-term checks.
- `artifacts`
  - File paths for downstream display or download.

## 4. Data Directory Requirements

The expected `data_dir` contains:

- `genome.fa`
- `genome.gff`
- `xiaomi_T2T_Annotation.smoke_genes.txt`
- `fq/*.fq.gz`
- `sampleName_clientId.txt`
- `metabolome_raw_3372.tsv`
- `USAGE_run_smoke_de_pipeline.md`
- `run_smoke_de_pipeline.sh`

The Tool currently requires `run_smoke_de_pipeline.sh`, but only reads
`USAGE_run_smoke_de_pipeline.md` as project documentation. Missing required
inputs return a structured `error` result with `missing_inputs`.

If the tarball is extracted as one nested payload directory, for example
`/mnt/yuxi-breeding-data/smoke_test_minimal/Si9g037800_smoke_test_minimal/*`,
the Tool auto-resolves that single child directory.

## 5. Running

Inside YuXi, select or call the Tool with defaults if the smoke data is mounted
at:

`/mnt/yuxi-breeding-data/smoke_test_minimal`

For direct backend testing, call the LangChain tool object with `invoke`:

```python
from yuxi.agents.toolkits.breeding.tools import smoke_flavonoid_breeding_advice

result = smoke_flavonoid_breeding_advice.invoke({
    "data_dir": "/mnt/yuxi-breeding-data/smoke_test_minimal",
    "trait": "黄酮相关",
    "out_dir": "/mnt/yuxi-breeding-data/yuxi_runs/smoke_flavonoid_breeding_advice",
    "run_transcriptome": True,
})
```

When `run_transcriptome=true`, the Tool runs:

```bash
bash run_smoke_de_pipeline.sh \
  --fa genome.fa \
  --gff genome.gff \
  --fq-dir fq \
  --sample-map sampleName_clientId.txt \
  --outdir <out_dir>/de_pipeline_out \
  --threads 8
```

with `cwd=data_dir`. stdout/stderr are written to `run.log`.

## 6. Artifacts

The Tool writes or returns:

- `significant_de_genes.tsv`
- `breeding_advice.md`
- `guard_result.json`
- `run_manifest.json`
- `run.log`

The current first version returns these paths in the `artifacts` field. A later
YuXi integration step should copy final files under
`/home/gem/user-data/outputs/` and call YuXi's built-in `present_artifacts`
Tool so the frontend artifact cards can display them automatically.

## 7. Guard Boundaries

The lightweight guard checks:

- advice contains `Si9g037800`
- advice contains `群体`
- advice contains `黄酮`
- advice includes the required missing-literature placeholders when no real
  literature evidence is available:
  - `真实 DOI：待文献检索补充`
  - `引用原文：待文献检索补充`
- no unsupported DOI pattern appears
- no completed population-validation claim appears
- no completed wet-lab-validation claim appears
- no production-grade wording is used for smoke-test results

The Tool does not fabricate DOI or quoted literature sentences.

## 8. Current Limits

- This is one coarse-grained Tool, not a SubAgent or Skill.
- Literature retrieval is not implemented. DOI and quoted sentence evidence are
  explicitly marked as pending.
- `metabolome_raw_3372.tsv` is only inspected for headers and sampled rows; it
  is treated as flavonoid background evidence only.
- `Si9g037800` support is determined from `significant_de_genes.tsv` by direct
  textual/table lookup. If absent, the advice says so.
- The Tool does not claim population validation, wet-lab validation, or
  production-grade conclusions.
- The Tool does not migrate the old Gradio UI or old fixed Omics Bundle logic.

## 9. Future SubAgent / Skill Plan

After the MVP works locally:

1. Split `smoke_flavonoid_breeding_advice` into:
   - `reference_genome_input`
   - `run_transcriptome_de`
   - `load_metabolome`
   - `literature_evidence_search`
   - `breeding_advice_writer`
   - `evidence_guard_check`
   - `package_breeding_artifacts`
2. Add a `smoke-flavonoid-breeding` Skill to enforce advice style and evidence
   boundaries.
3. Add optional SubAgents:
   - transcriptome DE agent
   - metabolome evidence agent
   - literature evidence agent
   - evidence guard agent
4. Add `present_artifacts` integration for files under YuXi sandbox outputs.
