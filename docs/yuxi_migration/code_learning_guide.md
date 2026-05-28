# YuXi 育种智能体代码学习指南

## 1. 从哪个文件开始读

建议按下面顺序读：

1. `ARCHITECTURE.md`
2. `backend/package/yuxi/agents/toolkits/registry.py`
3. `backend/package/yuxi/agents/toolkits/breeding/tools.py`
4. `web/src/apis/breeding_workbench_api.js`
5. `web/src/views/BreedingWorkbenchView.vue`
6. `backend/test/unit/toolkits/test_breeding_tools.py`

这样读的原因是：

- 先知道 YuXi 原框架边界。
- 再知道育种 Tool 是怎么挂进 YuXi 的。
- 然后看前端怎样发起 Agent Run、怎样展示结果。
- 最后用测试文件确认“系统承诺输出什么”。

## 2. 后端 Tool 主线

后端主线集中在 `backend/package/yuxi/agents/toolkits/breeding/tools.py`。

可以把它理解成 4 层：

1. 输入合同层
   - 一组 `BaseModel` 输入类。
   - 作用是定义每个 Tool 的参数，也让扩展管理知道这个 Tool 怎么调用。

2. 轻量解析层
   - `_lookup_gene_in_text`
   - `_inspect_metabolome`
   - `_inspect_de_support`
   - `_load_verified_literature_evidence`
   - 作用是从本地文件里提取可直接复述的证据。

3. 业务编排层
   - `_run_reference_prepare_impl`
   - `_run_transcriptome_deg_impl`
   - `_run_metabolome_prepare_impl`
   - `_run_literature_evidence_impl`
   - `_run_breeding_advice_generate_impl`
   - `_run_validation_plan_impl`

4. Tool 暴露层
   - `breeding_reference_prepare`
   - `breeding_transcriptome_deg`
   - `breeding_metabolome_prepare`
   - `breeding_literature_evidence`
   - `breeding_advice_generate`
   - `breeding_validation_plan`
   - `smoke_flavonoid_breeding_advice`

## 3. 前端育种工作台主线

前端主线主要是两个文件：

- `web/src/views/BreedingWorkbenchView.vue`
- `web/src/apis/breeding_workbench_api.js`

职责划分：

- `BreedingWorkbenchView.vue`
  - 负责页面输入、运行状态、合规检查展示、DOI 卡片展示、Markdown 下载。

- `breeding_workbench_api.js`
  - 负责把页面请求转成 YuXi 的 thread + run 调用。
  - 负责轮询 run 状态和历史消息。
  - 负责把后端状态拼成前端可直接消费的 snapshot。

- `web/src/utils/breedingWorkbench.js`
  - 负责默认 smoke 配置、文献解析、合规检查、下载纯函数。

## 4. Agent Run 主线

主线是：

1. 页面调用 `runBreedingWorkbench()`
2. 先 `createThread`
3. 再 `createAgentRun`
4. 前端轮询 `getAgentRun`
5. 前端轮询 `getAgentHistory`
6. 从 history 里取最终 markdown
7. 页面展示工具链、结果、合规项、DOI 卡片
8. 如果缺少强制项，则发起 repair run

这里最关键的理解是：

- `Run` 是异步任务容器。
- `History` 才是最终自然语言结果的真实来源。

## 5. 生信数据怎么进入 Tool

当前 smoke 流程里，数据入口不是上传后端对象存储，而是本地 demo 数据目录。

关键路径：

- `data_dir`
- `genome.fa`
- `genome.gff`
- `xiaomi_T2T_Annotation.smoke_genes.txt`
- `sampleName_clientId.txt`
- `metabolome_raw_3372.tsv`
- `verified_literature_evidence.tsv`
- `run_smoke_de_pipeline.sh`

进入方式：

1. 工作台把默认 smoke 上下文放进 Agent query 和 meta。
2. Agent 调用 `smoke_flavonoid_breeding_advice`。
3. Tool 根据 `data_dir` 去本地目录找文件。
4. 转录组部分按需调用 `run_smoke_de_pipeline.sh`。
5. 其他部分直接从文件中解析目标基因、代谢组关键词、DOI、引用原句。

## 6. 智能体建议怎么生成和展示

生成过程：

1. `breeding_transcriptome_deg` 生成或读取 `significant_de_genes.tsv`
2. `breeding_literature_evidence` 读取 `verified_literature_evidence.tsv`
3. `breeding_advice_generate` 汇总参考基因组、转录组、代谢组、文献证据
4. `_build_advice_markdown` 组织成 Markdown
5. `_guard_advice` 检查是否越界

展示过程：

1. `getAgentHistory` 拿到最终消息
2. `BreedingWorkbenchView.vue` 展示 Markdown
3. `extractLiteratureEvidence()` 解析 DOI 和引用原句
4. `evaluateBreedingCompliance()` 检查必备项
5. 页面展示 DOI 卡片、合规状态、下载按钮

## 7. 老师问代码时的 10 个高频问题与回答

### 1. 这个育种智能体是不是 YuXi 自带的？

不是。YuXi 提供的是智能体框架、Tool 机制和 Agent Run 机制。育种 Tool 是我们基于 YuXi 的 Tool 注册机制封装的业务工具。

### 2. 这些 Tool 是不是开源生信智能体？

不是。它们是项目里的业务 Tool 封装。真正的生信执行只在转录组阶段调用固定脚本和开源软件。

### 3. 转录组分析到底是谁做的？

是 `run_smoke_de_pipeline.sh` 做的。这个脚本是学长给的固定脚本，底层依赖 `hisat2`、`samtools`、`featureCounts`、`Rscript` 等开源生信软件。

### 4. 大模型有没有自己编 DOI？

不能。系统把 DOI 和引用原句限定为从 `verified_literature_evidence.tsv` 读取，后面还有 `_guard_advice` 防止编造。

### 5. 前端为什么要轮询两类接口？

因为 `getAgentRun` 负责看任务状态，`getAgentHistory` 负责拿真实输出内容。只看 Run 不够，只看 History 也不能知道任务是否结束。

### 6. 为什么最终结果从 history 里取？

因为 Agent 的最终回答会落到 thread history 里，这才是后端真实产出的消息记录。前端不能自己拼最终答案。

### 7. `smoke_flavonoid_breeding_advice` 为什么重要？

它是工作台当前最重要的一键入口。工作台要求 Agent 至少调用这个 Tool，后面再由它复用模块化 Tool。

### 8. 现在有没有完成群体验证或湿实验验证？

没有。当前代码只能给出候选线索、群体建议、验证计划和文献背景，不能宣称验证已完成。

### 9. `Si9g037800` 是不是已经被文献直接功能验证？

没有。当前 smoke 数据中的文献证据是背景证据，不是 `Si9g037800` 直接功能验证。

### 10. 现在代码里最该先改哪里？

先改 `BreedingWorkbenchView.vue` 和 `breeding_workbench_api.js` 的结构整理，因为这两处最臃肿，但又不需要改核心业务逻辑。

## 8. 当前仍然臃肿但暂时不建议改的部分

- `backend/package/yuxi/agents/toolkits/registry.py`
  - 这是 YuXi Tool 注册核心，不适合在学习阶段改。

- `backend/package/yuxi/agents/models.py`
  - 这是模型兼容层，会影响全站模型加载。

- `backend/package/yuxi/agents/toolkits/breeding/tools.py`
  - 仍然职责较多，但当前是唯一稳定业务入口，不建议现在做大拆分。

- `web/src/router/index.js`
  - 会影响 `/agent`、`/graph`、`/extensions`、`/model-config` 等全站页面。

- `web/src/layouts/AppLayout.vue`
  - 是全站布局壳，不适合为了瘦身育种工作台去碰。

- `web/src/components/GraphCanvas.vue`
  - 图谱页面当前不在本轮允许修改范围，且风险高。
