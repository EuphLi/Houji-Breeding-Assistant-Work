# Phase 7: 黄酮相关育种子智能体 Tool 模块化设计

## 目标

当前继续保留 `smoke_flavonoid_breeding_advice` 作为一键演示入口，同时在后端补齐黄酮相关育种子智能体所需的模块化 Tool 体系，便于后续把性状子智能体和组学 Tool 解耦。

## 当前结构

- 保留总入口 Tool：
  - `smoke_flavonoid_breeding_advice`
- 新增模块化 Tool：
  - `breeding_reference_prepare`
  - `breeding_transcriptome_deg`
  - `breeding_metabolome_prepare`
  - `breeding_literature_evidence`
  - `breeding_advice_generate`
  - `breeding_validation_plan`

## 为什么按性状划分子智能体、按组学划分 Tool

- 子智能体更适合按性状划分，因为育种建议的目标、边界和输出模板首先取决于性状语义。
- Tool 更适合按参考基因组、转录组、代谢组、文献、验证计划拆分，因为这些能力可被多个性状模板复用。
- 这样保留了演示时的一键入口，也为后续把更多性状接入 YuXi 时复用同一条组学工具链留出空间。

## 本轮范围

- 只实现黄酮相关方向。
- 不扩展抗旱、抗病、产量等其他性状。
- 不改前端、不接 artifacts、不改图谱逻辑。

## Tool 角色说明

### `breeding_reference_prepare`

- 校验 `genome.fa`、`genome.gff`、`xiaomi_T2T_Annotation.smoke_genes.txt`
- 检查 `Si9g037800` 是否出现在参考文件中
- 输出 `reference_manifest.json`

### `breeding_transcriptome_deg`

- 校验 `fq/`、`sampleName_clientId.txt`、`genome.fa`、`genome.gff`、`run_smoke_de_pipeline.sh`
- 支持运行流程或直接读取已有 `significant_de_genes.tsv`
- 输出 `transcriptome_manifest.json`
- 缺少 `hisat2-build`、`hisat2`、`samtools`、`featureCounts`、`Rscript` 时返回 `missing_tools`

### `breeding_metabolome_prepare`

- 读取 `metabolome_raw_3372.tsv`
- 检查黄酮相关字段和样本行
- 输出 `metabolome_manifest.json`
- 只作为背景证据，不作为 `Si9g037800` 因果证明

### `breeding_literature_evidence`

- 读取 `verified_literature_evidence.tsv`
- 只接受真实 DOI 和真实引用原文
- 统计 `evidence_level`
- 输出 `literature_manifest.json`
- 若只有背景证据，明确不能作为 `Si9g037800` 直接功能验证

### `breeding_advice_generate`

- 汇总参考基因组、转录组、代谢组、文献结果
- 生成 `breeding_advice.md`
- 生成 `guard_result.json`
- 生成 `run_manifest.json`
- 输出必须包含 `Si9g037800`、`群体`、`黄酮`

### `breeding_validation_plan`

- 生成后续验证计划
- 包含群体构建、基因型检测、黄酮表型测定、关联分析、候选变异确认、KASP/CAPS 后续转化设计
- 明确这些内容是计划，不是已完成结果

## 当前边界

- 当前文献证据仍可能只是背景级，不是 `Si9g037800` 直接功能验证。
- 当前仍未完成群体验证。
- 当前仍未完成湿实验验证。
- 当前仍未完成最终 KASP/CAPS 标记开发。

## 后续复用方向

- 未来如果接入其他性状，可以复用这套“性状子智能体 + 组学 Tool”模板。
- 其他性状只需要替换 trait-specific prompt、目标基因筛选逻辑和相应背景证据，即可沿用参考基因组、转录组、代谢组、文献、验证计划的拆分模式。
