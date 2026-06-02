# 多组学分析智能体五条学习路线流程文档

## 0. 整体链路

```text
线 1：前端上传文件 → breeding_context → run meta
  ↓
线 2：worker 读取 run meta → 判断 direct tool route → 调用 omics_breeding_analysis_run
  ↓
线 3：omics_breeding_analysis_run 内部触发 FASTQ → DEG
  ↓
线 4：DEG / 代谢组 → Evidence Pack
  ↓
线 5：T1/M1/BG/Guard → citation 报告
```

---

## 1. 线 1：上传文件如何进入后端业务上下文

### 1.1 核心问题

线 1 解决的是：
上传文件路径如何进入 breeding_context / run meta


### 1.2 数据流程位置

```text
浏览器页面
  ↓
Vue 文件上传控件
  ↓
前端上传 API
  ↓
YuXi workspace 保存文件
  ↓
后端返回 server_path
  ↓
前端保存 serverPath
  ↓
buildSubmissionContext()
  ↓
组装 breeding_context / metadata
  ↓
chat_service.py 写入 run meta
  ↓
worker 从 Redis / run meta 恢复上下文
  ↓
omics_breeding_analysis_run 收到上下文
```

### 1.3 此线路的完整链路

```text
BreedingWorkbenchView.vue
  用户上传文件
  保存 item.serverPath
  汇总 uploadedServerPaths
  buildSubmissionContext()
        ↓
breeding_workbench_api.js
  发送 question + trait + breeding_context / metadata
        ↓
chat_service.py
  创建 run
  保存 run meta
        ↓
run_worker.py
  读取任务
  恢复 run meta
  取出 breeding_context
        ↓
omics_analysis.py
  接收 upload_root / rnaseq_read_paths / sample_map_path / metabolome_path
  做路径归一化
  返回 submitted_* / normalized_* / path_exists
```

---

## 2. 线 2：worker 如何强制走育种分析工具

### 2.1 核心问题

线 2 解决的是：
worker 拿到 run meta 后，如何决定这次任务要走育种分析工具


### 2.2 任务路由链路

```text
前端提交 trait/question/breeding_context
  ↓
chat_service.py 创建 run 并保存 meta
  ↓
worker 读取任务
  ↓
worker 判断 source=breeding-workbench
  ↓
worker 识别 preferred_tool=omics_breeding_analysis_run
  ↓
worker 不走普通 Agent 对话
  ↓
直接调用 omics_breeding_analysis_run
```

线 2 的重点不是生信流程本身，而是任务路由机制


### 2.3 完整链路

```text
chat_service.py
  创建 run
  保存 metadata:
    source=breeding-workbench
    preferred_tool=omics_breeding_analysis_run
    breeding_context={...}
        ↓
run_worker.py
  取出任务
  恢复 metadata
  判断：
    source 是否为 breeding-workbench
    preferred_tool 是否为 omics_breeding_analysis_run
    是否 has_breeding_context
        ↓
  如果满足：
    启用 Breeding workbench direct tool route
        ↓
  构造 tool_input
        ↓
  调用 omics_breeding_analysis_run
        ↓
omics_analysis.py
  接收上下文
  进入后续组学分析 workflow
```

---

## 3. 线 3：FASTQ → DEG 固定转录组流程

### 3.1 核心问题

线 3 只回答一个问题：
```text
用户上传的 fq/*.fq.gz 文件，如何通过固定生信流程，变成后续 Evidence Pack 可以读取的 significant_de_genes.tsv？
```

### 3.2 固定生信流程

```text
FASTQ
  ↓
hisat2-build
  ↓
hisat2
  ↓
samtools
  ↓
featureCounts
  ↓
R limma-voom
  ↓
significant_de_genes.tsv
```

### 3.3 学完后应能画出的链路

```text
omics_analysis.py
  接收 tool_input:
    upload_root
    rnaseq_read_paths
    sample_map_path
    reference_genome_path
    genome_gff_path
        ↓
  判断是否需要运行转录组 DEG
        ↓
tools.py
  _run_transcriptome_deg_impl
        ↓
  _resolve_transcriptome_pipeline_script
        ↓
  _run_transcriptome_pipeline
        ↓
TRANSCRIPTOME_PIPELINE_RUNNER
  注入 rnaseq_deg 环境 PATH
        ↓
外部生信命令
  hisat2-build
  hisat2
  samtools
  featureCounts
  Rscript limma-voom
        ↓
输出目录
  transcriptome_deg/
    significant_de_genes.tsv
    manifest.json
    run.log
        ↓
omics_analysis.py
  summary:
    transcriptome_path_exists=True
    submitted_rnaseq_read_paths=[...]
    transcriptome_result_path=...
```

---

## 4. 线 4：Evidence Pack 如何读取 DEG 和代谢组

### 4.1 核心问题

线 4 只回答一个问题：

```text
固定转录组流程生成的 significant_de_genes.tsv，
以及用户上传的 metabolome_raw_3372.tsv，
如何被后端读取、筛选、摘要，
并变成 T1 / M1 / BG / Guard 这类可溯源证据？
```

### 4.2 线 4 研究对象

```text
significant_de_genes.tsv
  ↓
读取 DEG 结果
  ↓
筛选 Si9g037800 等候选基因
  ↓
生成 T1 转录组证据

metabolome_raw_3372.tsv
  ↓
读取代谢组表格
  ↓
筛选黄酮/苯丙烷/酚酸等相关代谢物
  ↓
生成 M1 代谢组证据

文献证据 / PubMed 背景
  ↓
生成 BG1/BG2 背景证据

边界规则
  ↓
生成 Guard 证据
```

### 4.3 所属层次与核心作用

线 4 属于：

```text
证据适配层 / 证据包构建层 / 后端业务证据标准化层
```

核心业务作用是：

```text
把各种异构输入文件统一整理成大模型和 citation renderer 能使用的结构化证据。
```

### 4.4 T1 转录组证据流

```text
upload_root/transcriptome_deg/significant_de_genes.tsv
  ↓
evidence_adapters.py 读取 DEG
  ↓
筛选核心候选基因 Si9g037800
  ↓
提取 logFC / padj / annotation
  ↓
生成 EvidenceItem:
    citation_id = T1
    source_type = transcriptome
    metadata = {
      file_path,
      gene_id,
      logFC,
      padj,
      annotation
    }
  ↓
Evidence Pack
```

T1 的业务含义：

```text
当前实验直接组学证据。
```

但是 T1 不能直接证明：

```text
Si9g037800 已完成基因功能验证
Si9g037800 已完成群体验证
Si9g037800 已开发最终 KASP/CAPS 标记
```

这些必须由 Guard 限制。

### 4.5 M1 代谢组证据流

```text
metabolome_raw_3372.tsv
  ↓
evidence_adapters.py 读取代谢组表
  ↓
统计总记录数
  ↓
筛选显著差异代谢物
  ↓
优先挑选黄酮/苯丙烷/酚酸相关代谢物
  ↓
生成摘要，不保留整张 TSV
  ↓
生成 EvidenceItem:
    citation_id = M1
    source_type = metabolome
    metadata = {
      file_path,
      total_records,
      significant_records,
      top_metabolites
    }
  ↓
Evidence Pack
```

M1 的业务含义：

```text
代谢组线索。
```

M1 不能被写成：

```text
已经证明 Si9g037800 调控黄酮
```

正确写法是：

```text
代谢组结果提示黄酮相关代谢分支可能发生扰动，
但不能单独证明 Si9g037800 直接调控黄酮积累。[M1][Guard]
```

### 4.6 BG 背景文献证据流

```text
literature evidence / PubMed result
  ↓
读取 DOI / PMID / title / quoted_sentence
  ↓
过滤 demo / fake / 空结果
  ↓
生成 BG1 / BG2 ...
  ↓
Evidence Pack
```

BG 的业务含义：

```text
背景文献证据。
```

它不能被当成：

```text
当前实验直接验证
当前基因直接功能证明
当前材料中完成过群体验证
```

如果没有文献，正确输出是：

```text
当前未检索到可用 PubMed 背景文献。[Guard]
```

不能无中生有：

```text
[BG1]
[BG2]
```

### 4.7 Guard 证据流

```text
固定边界规则
  ↓
output_guard.py / workflow.py 添加
  ↓
Evidence Pack
  ↓
正文句尾 [Guard]
  ↓
来源索引 [Guard] 边界规则详情
```

Guard 的业务含义：

```text
声明哪些事情不能被当前证据支持。
```

---

## 5. 线 5：溯源与输出展示

### 5.1 核心问题

线 5 只回答一个问题：

```text
T1 / M1 / BG / Guard 这些证据，
如何变成最终报告中的句尾 citation、
文末来源索引、
文献卡片、
逐句追溯表、
前端展示区域？
```

### 5.2 线 5 研究对象

```text
Evidence Pack
  ↓
citation_engine.py
  ↓
presentation.py
  ↓
output_guard.py
  ↓
workflow.py 汇总结果
  ↓
omics_analysis.py 返回 tool result
  ↓
BreedingWorkbenchView.vue 展示
```

### 5.3 主报告生成流

```text
Evidence Pack
  ↓
workflow.py
  ↓
raw_llm_answer 生成或读取
  ↓
citation_engine.py 生成证据引用关系
  ↓
presentation.py 生成 canonical answer_markdown
  ↓
output_guard.py 检查边界
  ↓
最终 answer_markdown 返回前端
```

正确原则：

```text
raw_llm_answer 不是正式主报告；
正式主报告必须是带 citation 的 canonical renderer 输出。
```

### 5.4 来源索引生成流

```text
Evidence Pack:
  T1 / M1 / BG1 / Guard
  ↓
presentation.py
  ↓
来源索引 Markdown / citations metadata
  ↓
前端展示
```

正确展示：

```text
正文句尾只放 [T1][M1][BG1][Guard]
文末来源索引展示 DOI、PMID、引用原句、文件路径、统计量等详情
```

### 5.5 claim_trace 生成流

```text
每个回答句子 / claim
  ↓
citation_engine.py
  ↓
绑定 sources
  ↓
生成 claim_trace row:
    claim
    source_status
    explanation
    sources
  ↓
前端逐句追溯表展示
```

claim_trace 的业务价值：

```text
老师可以检查每句话到底依据 T1、M1、BG 还是 Guard。
```

### 5.6 文献卡片生成流

```text
BG literature evidence
  ↓
metadata:
    DOI
    PMID
    title
    quoted_sentence
  ↓
literature_cards
  ↓
前端文献证据卡片
```

正确边界：

```text
文献卡片只能展示真实 DOI / PMID / 引用原句；
没有文献时不展示假 BG 卡片。
```

### 5.7 Guard 展示流

```text
output_guard.py / guard evidence
  ↓
guard_result
  ↓
presentation.py 来源索引 [Guard]
  ↓
正文中必要句子挂 [Guard]
  ↓
前端展示 Guard 边界说明
```

Guard 的作用不是“装饰”，而是明确告诉用户：

```text
哪些结论当前证据不能支持。
```

### 5.8 学完后应能画出的链路

```text
Evidence Pack
  T1:
    gene_id=Si9g037800
    logFC=-6.23
    padj=0.0031
    annotation=...
  M1:
    total_records=N
    top_metabolites=[...]
  BG:
    doi / pmid / quoted_sentence
  Guard:
    boundary rules
        ↓
citation_engine.py
  citations
  claim_trace
        ↓
presentation.py
  answer_markdown
  来源索引
  literature_cards
        ↓
output_guard.py
  guard_result
        ↓
workflow.py
  result:
    answer_markdown
    citations
    claim_trace
    literature_cards
    guard_result
    summary
        ↓
omics_analysis.py
  tool result
        ↓
BreedingWorkbenchView.vue
  主报告
  来源索引
  文献卡片
  逐句追溯
  调试字段
```