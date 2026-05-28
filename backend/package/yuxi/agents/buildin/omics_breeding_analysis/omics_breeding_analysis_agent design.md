# OmicsBreedingAnalysisAgent 阶段记录

## 当前总体状态

### 已完成的大阶段闭环

- 前端 `breeding-workbench` 页面已经能够正常提交任务。
- 后端已支持 `breeding-workbench` 直达执行链路：
  - `source=breeding-workbench`
  - `preferred_tool=omics_breeding_analysis_run`
  - 直接执行 `omics_breeding_analysis_run.invoke({"input": payload})`
- 页面不再等待 `ChatbotAgent / LLM` 自主选择工具。
- 页面可正常显示：
  - 状态：已完成
  - 工具调用链：多组学育种分析
  - 育种建议 Markdown 正文
  - 下载育种建议 Markdown 按钮
- PubMed 动态背景文献检索已接入。
- LLM 证据整合分析已接入，当前运行结果中可见：
  - `analysis_backend = llm`
- 黄酮、抗旱、高产/抗寒等不同性状的输出已经能明显分化。

### 当前尚未完成的部分

- 真实转录组差异基因结果尚未接入：
  - `transcriptome_path_exists = False`
- 当前代谢组主要来自默认 smoke 数据：
  - `metabolome_path_exists = True`
  - `evidence_level = default_smoke_data`
- 前端文件输入与 worker 容器内真实可读路径尚未完全打通。
- 当前不能声称已经完成真实多组学数据输入闭环。
- 当前不能声称已经基于真实转录组 DEG 确认候选基因。

---

## Phase 1：YuXi 官方 Agent 骨架接入

### 已完成

- 新增 `OmicsBreedingAnalysisAgent`
- 新增 `OmicsBreedingAnalysisContext`
- 将智能体放入 YuXi 自动发现目录：
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/`
- YuXi `agent_manager` 已能自动发现 `OmicsBreedingAnalysisAgent`
- `configurable_items` 已暴露自定义字段：
  - `trait`
  - `question`
  - `transcriptome_result_path`
  - `literature_evidence_path`
  - `metabolome_path`
  - `genome_context_path`
  - `evidence_pack_output_path`
  - `citation_mode`
  - `guard_mode`
- `mcps` 字段继承 `BaseContext` 默认配置：
  - `template_metadata.kind = mcps`
- `graph.py` 已对齐 YuXi 最小官方执行链路：
  - `load_chat_model(context.model)`
  - `system_prompt`
  - `RuntimeConfigMiddleware`
  - `BaseState`
  - `checkpointer`
- 新增 Agent 单元测试，覆盖：
  - Agent 自动发现
  - Context 默认值
  - configurable_items
  - BaseContext MCP 配置继承
  - system prompt 边界
  - RuntimeConfigMiddleware 接入

### 验证结果

- `py_compile` 通过
- `backend/test/unit/agents/test_omics_breeding_analysis_agent.py` 通过
- 与旧 breeding tools / tool_service 联合小测试通过
- `agent_manager` 可发现：
  - `OmicsBreedingAnalysisAgent`
  - `ChatbotAgent`

### 阶段结论

`OmicsBreedingAnalysisAgent` 已进入 YuXi 官方 Agent / Context / Graph / Middleware 基础链路，可以作为后续多组学育种分析智能体的正式落点。

---

## Phase 2：Evidence Pack 证据准备层

### Phase 2 Step 1：Evidence Pack 标准结构

#### 已完成

- 新增：
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/evidence_pack.py`
- 实现 Evidence Pack 构建函数：
  - `infer_task_intent()`
  - `extract_target_genes()`
  - `build_guard_requirements()`
  - `build_omics_evidence_pack()`
  - `write_evidence_pack()`
- Evidence Pack 当前标准结构包括：
  - `schema_version`
  - `task`
  - `targets`
  - `evidence`
  - `guard_requirements`
- 动态规则已初步建立：
  - target gene 从输入证据提取，不写死
  - trait 从用户输入或 Context 来，不写死
  - 是否需要群体验证建议由任务 intent 判断
  - DOI 和 quoted_sentence 来自 literature_records

### Phase 2 Step 2：TSV Evidence Adapter

#### 已完成

- 新增：
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/evidence_adapters.py`
- 实现从 TSV 文件读取证据：
  - `read_transcriptome_records()`
  - `read_literature_records()`
  - `build_omics_evidence_pack_from_context()`
- 支持从 `significant_de_genes.tsv` 提取动态目标基因
- 支持从 `verified_literature_evidence.tsv` 提取真实 DOI 和 quoted_sentence
- 过滤不适合作为正式证据的文献行：
  - demo
  - fixture
  - pending
  - rejected
  - missing DOI
  - missing quote
- 后续扩展路径诊断字段：
  - `transcriptome_path_exists`
  - `metabolome_path_exists`
  - `literature_path_exists`
  - `evidence_level`
  - `data_source`

### Phase 2 Step 3：旧 Tool 结果桥接层

#### 已完成

- 新增：
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/tool_result_adapters.py`
- 实现旧工具结果到 Evidence Pack 的桥接：
  - `extract_transcriptome_records_from_tool_result()`
  - `extract_literature_records_from_tool_result()`
  - `build_omics_evidence_pack_from_tool_results()`
- 只复用旧工具的证据产物：
  - `significant_de_genes_path`
  - literature `entries`
- 不复用旧 `smoke_flavonoid_breeding_advice` 的最终建议逻辑
- 不使用旧工具中的 `target_gene_found / matches` 作为新任务目标，避免 smoke 硬编码污染

### Phase 2 Step 4：Evidence Pack 落盘 workflow

#### 已完成

- 新增：
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/workflow.py`
- 实现：
  - `summarize_evidence_pack()`
  - `prepare_omics_evidence_pack_from_context()`
  - `prepare_omics_evidence_pack_from_tool_results()`
- 支持生成：
  - `omics_evidence_pack.json`
  - summary
  - warnings
  - artifacts

### 验证结果

- `py_compile` 通过
- Agent / Evidence Adapter / Tool Result Adapter / Workflow 小全量测试通过
- Evidence Pack 相关测试通过

### 阶段结论

项目已具备多组学育种分析的标准证据准备链路：

```text
Context / 旧 Tool 结果
→ Evidence Adapter / Tool Result Adapter
→ Evidence Pack
→ omics_evidence_pack.json
→ summary / artifacts
```

后续 Citation Engine、Guard、前端 payload 都围绕 Evidence Pack 对接。

---

## Phase 3：Dynamic Guard 与 guard_result 落盘

### 已完成

- 新增：
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/output_guard.py`
- 实现：
  - `run_dynamic_output_guard()`
- Guard 不再写死：
  - `Si9g037800`
  - `黄酮`
  - `群体`
- Guard 从 Evidence Pack 的 `guard_requirements` 读取动态要求：
  - `required_gene_ids`
  - `required_trait_terms`
  - `must_include_population_validation`
  - `allowed_dois`
  - `allowed_quoted_sentences`
- 检查范围包括：
  - 是否覆盖目标基因
  - 是否覆盖目标性状
  - 是否在需要时给出群体层面的后续验证建议
  - DOI 是否来自 Evidence Pack
  - quoted_sentence 是否来自 Evidence Pack
  - 是否声称已完成群体验证
  - 是否声称已完成湿实验
  - 是否声称 KASP/CAPS 已开发完成
  - 是否声称最终育种结论已明确
- 扩展 `workflow.py`：
  - `write_json_artifact()`
  - `guard_omics_answer()`
  - `prepare_guarded_omics_answer_from_context()`
- 支持写出：
  - `guard_result.json`
- 支持返回：
  - `answer_markdown`
  - `evidence_pack`
  - `guard_result`
  - `summary`
  - `warnings`
  - `artifacts`

### 验证结果

- `test_omics_output_guard.py` 通过
- `test_omics_guard_workflow.py` 通过
- 当前模块小全量测试通过

### 阶段结论

项目已具备基于 Evidence Pack 的动态输出边界检查能力。当前 Guard 更多作为后端内部保护，不再作为用户侧主要展示卡片。

---

## Phase 4：Citation / 文献卡片 / frontend_payload 结构化输出

### 已完成

- 新增或扩展：
  - `citation_engine.py`
  - `presentation.py`
  - `frontend_payload` 相关结构
- 支持输出：
  - `answer_markdown`
  - `literature_cards`
  - `citations`
  - `claim_trace`
  - `artifact_panel`
  - `frontend_payload.json`
  - `final_result.json`
- 前端可优先消费：
  - `frontend_payload.answer_markdown`
  - `frontend_payload.literature_panel.cards`
  - `frontend_payload.summary`
  - `frontend_payload.artifact_panel`
- 早期曾展示：
  - Guard 校验面板
  - 文献 DOI 与引用原文卡片
  - Claim Trace
  - 产物清单
- 后续根据用户侧展示要求，隐藏了大部分内部卡片，只保留：
  - 正文
  - 工具调用链
  - 下载按钮
  - 运行诊断折叠区

### 阶段结论

项目从纯 Markdown 输出升级为：

```text
Markdown 正文
+ frontend_payload 结构化结果
+ 可下载产物
+ 可选内部诊断
```

---

## Phase 5：正式 Tool `omics_breeding_analysis_run` 接入

### 已完成

- 新增：
  - `backend/package/yuxi/agents/toolkits/breeding/omics_analysis.py`
- 在：
  - `backend/package/yuxi/agents/toolkits/breeding/__init__.py`
  中导出：
  - `omics_breeding_analysis_run`
- 明确 `omics_breeding_analysis_run` 是新主线工具
- 旧 `smoke_flavonoid_breeding_advice` 保留为兼容 / smoke 工具
- 工具输入采用 LangChain StructuredTool 形式
- 正确直接调用方式：

```python
omics_breeding_analysis_run.invoke({"input": payload})
```

- 错误调用方式：

```python
omics_breeding_analysis_run.invoke({"trait": "黄酮相关"})
```

会触发：

```text
input Field required
```

- 工具返回：
  - `status`
  - `answer_markdown`
  - `summary`
  - `guard_result`
  - `citations`
  - `literature_cards`
  - `frontend_payload`
  - artifacts

### 验证结果

- 工具可直接 invoke
- 返回 `status=completed`
- PubMed 背景记录可进入 `literature_cards`
- 工具测试已覆盖正确 invoke 和错误 invoke 场景

### 阶段结论

`omics_breeding_analysis_run` 已成为育种工作台正式主工具。

---

## Phase 6：PubMed 动态背景文献检索

### 已完成

- 新增或重构：
  - `backend/package/yuxi/agents/toolkits/buildin/pubmed.py`
  - `backend/package/yuxi/agents/buildin/omics_breeding_analysis/literature_search.py`
- 文献路线从“必须依赖 `verified_literature_evidence.tsv`”调整为：
  - 已验证文献 TSV 可选
  - PubMed 动态背景检索可用
  - 没有 TSV 不阻断主流程
- `pubmed.py` 从依赖 `xmltodict` 改为标准库：
  - `urllib.request`
  - `xml.etree.ElementTree`
- PubMed 请求设置：
  - timeout
  - 最大 query 数
  - 每个 query 最大结果数
- 文献记录包括：
  - `title`
  - `doi`
  - `pmid`
  - `abstract`
  - `url`
  - `source=PubMed`
  - `quoted_sentence`
- `quoted_sentence` 只允许从 abstract 首句或原始字段截取
- 不允许 LLM 编造 quoted_sentence
- `literature_search.py` 支持 trait 动态 query：
  - 黄酮 → `flavonoid`
  - 抗旱 → `drought tolerance / abiotic stress`
  - 高产 → `yield / grain yield`
  - 其他 trait → 使用原始 trait 构造 query

### 验证结果

- worker 中 PubMed DNS / HTTP 可访问
- `Setaria italica flavonoid` 可返回真实 PubMed 结果
- 工具运行可产生背景文献记录
- 不同 trait 可得到不同 PubMed query 和不同背景文献数量

### 阶段结论

项目已具备无本地文献 TSV 时自动进行 PubMed 背景文献检索的能力。当前 PubMed 结果只能称为背景线索，不能当作候选基因直接实验证据。

---

## Phase 7：前端 breeding-workbench 展示链路改造

### 已完成

- 修改：
  - `web/src/views/BreedingWorkbenchView.vue`
  - `web/src/apis/breeding_workbench_api.js`
  - `web/src/utils/breedingWorkbench.js`
- 前端主链路：
  - 创建 Thread
  - 创建 Agent Run
  - 轮询 Run 状态
  - 读取 history
  - 解析 tool call / tool output / frontend_payload
  - 页面展示 Markdown 与工具调用链
- 支持：
  - `frontendPayload`
  - `visibleToolChain`
  - `displayStatus`
  - `request_id` 绑定
  - 提交前清理旧结果
- 停用文本推断工具链，避免出现伪工具：
  - `smoke_test_minimal`
  - `omics_evidence_pack`
  - `Smoke 黄酮育种建议`
- 用户侧隐藏：
  - 合规检查卡片
  - 文献 DOI 与引用原文独立卡片
  - Claim Trace
  - 产物清单
- 保留：
  - 正文
  - 工具调用链
  - 下载育种建议 Markdown
  - 运行诊断折叠区

### 验证结果

- `npm run build` 通过
- 页面可显示：
  - 状态：已完成
  - 工具调用链：`omics_breeding_analysis_run / 多组学育种分析`
  - 正文输出
  - 下载按钮

### 阶段结论

前端已从旧 smoke / repair / 硬编码展示，转为消费后端结构化 `frontend_payload` 和真实工具调用链。

---

## Phase 8：breeding-workbench 直达执行链路

### 已完成

- 修改：
  - `backend/package/yuxi/services/chat_service.py`
  - `backend/package/yuxi/services/run_worker.py`
  - `web/src/apis/breeding_workbench_api.js`
- 当 run meta 满足：
  - `source=breeding-workbench`
  - `preferred_tool=omics_breeding_analysis_run`
- 后端不再等待 ChatbotAgent / LLM 自主选择工具
- 而是直接执行：

```python
omics_breeding_analysis_run.invoke({"input": payload})
```

- 写回消息链：
  - user message
  - assistant tool_call
  - tool output
  - assistant final markdown
- 仍复用 YuXi 现有：
  - Agent Run
  - worker
  - history
  - 前端轮询
  - frontend_payload 解析

### 验证结果

- 日志可见：
  - `source=breeding-workbench`
  - `preferred_tool=omics_breeding_analysis_run`
  - `Breeding workbench direct tool route enabled`
  - `Added tool call omics_breeding_analysis_run`
- 页面不再卡在等待模型选择工具
- 页面可完成展示

### 阶段结论

育种工作台已从不稳定的 LLM 自主选工具，改为固定业务入口直达正式育种分析工具。

---

## Phase 9：LLM 证据整合分析接入

### 已完成

- 修改：
  - `workflow.py`
  - `citation_engine.py`
  - `literature_search.py`
  - `omics_analysis.py`
  - `chat_service.py`
- 工具内部新增 LLM 证据整合路径：
  - Evidence Pack
  - 代谢组上下文
  - PubMed 背景文献
  - trait / question
  - 边界约束
  一起进入 LLM prompt
- `summary.analysis_backend` 标记：
  - `llm`
  - `rule_fallback`
- 正常情况下使用 LLM 生成正式 `answer_markdown`
- LLM 失败时才回退规则模板
- 不同性状输出开始明显分化：
  - 黄酮相关 → 黄酮代谢、黄酮生物合成、代谢组筛选、群体验证
  - 抗旱相关 → 干旱胁迫、根系、水分利用效率、ABA/MAPK、抗旱表型
  - 高产 / 抗寒 → 产量、抗寒、背景文献与代谢组线索
- LLM prompt 约束：
  - 不编造 DOI
  - 不编造 quoted_sentence
  - 不声称已完成群体验证
  - 不声称已完成湿实验
  - 不声称最终 KASP/CAPS 已开发完成
  - 没有真实组学输入时必须说明证据限制

### 当前验证结果

- 最新运行结果可见：
  - `status=completed`
  - `analysis_backend=llm`
  - `transcriptome_path_exists=False`
  - `metabolome_path_exists=True`
  - `evidence_level=default_smoke_data`
  - `background_literature_count` 有值
  - `literature_card_count` 有值
- 页面可显示黄酮、抗旱等差异化结果
- 日志中未见新的：
  - `Traceback`
  - `ValidationError`
  - `exception`
  - `error`

### 阶段结论

当前已经完成：

```text
固定业务入口
→ 正式工具直达执行
→ PubMed 背景文献
→ LLM 证据整合
→ 前端展示
```

这是当前可演示的大阶段闭环。

---

## Phase 10：真实数据路径闭环，尚未完成

### 当前状态

- 前端页面能展示：
  - `genome.fa`
  - `genome.gff`
  - `fq/*.fq.gz`
  - `sampleName_clientId.txt`
  - `metabolome_raw_3372.tsv`
- 但当前这些字段大概率仍是：
  - 默认文件名
  - 占位符
  - smoke 数据路径
- 最新结果显示：
  - `transcriptome_path_exists=False`
  - `metabolome_path_exists=True`
  - `evidence_level=default_smoke_data`
  - `trait=None`
  - `question=None`
  - `data_source=None`
- 说明：
  - 转录组 DEG 结果 `significant_de_genes.tsv` 尚未真正接入
  - 代谢组主要来自默认 smoke 数据
  - 结构化 summary 中 trait/question/data_source 回填仍需修复
  - 不能声称已完成真实多组学数据输入闭环

### 下一阶段目标

Phase 10 应只聚焦：

```text
前端文件输入
→ 后端 direct route payload
→ worker 可读路径
→ evidence_adapters path_exists
→ summary / answer_markdown 正确反映真实数据来源
```

### 阶段结论

Phase 10 尚未完成。当前版本可以用于演示智能体工作台执行闭环，但不能用于宣称用户上传数据完整处理闭环。

---

# 学习路线规划

## 学习阶段 A：前端入口与 Run 创建

### 目标

搞清楚页面按钮如何触发 YuXi Agent Run。

### 重点文件

- `web/src/views/BreedingWorkbenchView.vue`
- `web/src/apis/breeding_workbench_api.js`
- `web/src/utils/breedingWorkbench.js`

### 重点理解

- `handleSubmit()`
- `runBreedingWorkbench()`
- `threadApi.createThread()`
- `agentApi.createAgentRun()`
- run 轮询
- history 读取
- `buildRunSnapshot()`
- `syncResultFromPayload()`

### 学习成果

能画出：

```text
点击按钮
→ 创建 thread
→ 创建 run
→ 轮询 run
→ 读取 history
→ 解析 frontend_payload
→ 渲染结果
```

---

## 学习阶段 B：YuXi 异步执行链路

### 目标

搞清楚后端如何处理 `/api/chat/runs`。

### 重点文件

- `backend/server/routers/chat_router.py`
- `backend/package/yuxi/services/agent_run_service.py`
- `backend/package/yuxi/services/run_worker.py`
- `backend/package/yuxi/services/chat_service.py`

### 重点理解

- `create_agent_run_view()`
- `enqueue_job("process_agent_run")`
- `process_agent_run()`
- `stream_agent_chat()`
- `meta.source`
- `meta.preferred_tool`
- breeding-workbench direct route

### 学习成果

能解释为什么当前工作台不再依赖 LLM 自己调用工具。

---

## 学习阶段 C：正式工具入口

### 目标

理解 `omics_breeding_analysis_run` 是如何被注册、调用、返回结果的。

### 重点文件

- `backend/package/yuxi/agents/toolkits/breeding/__init__.py`
- `backend/package/yuxi/agents/toolkits/breeding/omics_analysis.py`
- `backend/package/yuxi/agents/toolkits/registry.py`

### 重点理解

- `@tool`
- StructuredTool
- input schema
- `invoke({"input": payload})`
- 工具返回 dict

### 学习成果

能解释为什么：

```python
omics_breeding_analysis_run.invoke({"input": payload})
```

是正确的，而：

```python
omics_breeding_analysis_run.invoke({"trait": "黄酮相关"})
```

会失败。

---

## 学习阶段 D：多组学业务 workflow

### 目标

理解业务结果如何生成。

### 重点文件

- `backend/package/yuxi/agents/buildin/omics_breeding_analysis/workflow.py`
- `backend/package/yuxi/agents/buildin/omics_breeding_analysis/evidence_pack.py`
- `backend/package/yuxi/agents/buildin/omics_breeding_analysis/evidence_adapters.py`
- `backend/package/yuxi/agents/buildin/omics_breeding_analysis/literature_search.py`
- `backend/package/yuxi/agents/buildin/omics_breeding_analysis/citation_engine.py`
- `backend/package/yuxi/agents/buildin/omics_breeding_analysis/output_guard.py`

### 重点理解

- 读取证据
- 构建 Evidence Pack
- PubMed 检索
- 构造 LLM prompt
- 生成 answer_markdown
- Guard 检查
- 写 final_result.json

### 学习成果

能解释为什么当前：

```text
transcriptome_path_exists=False
```

但页面仍能生成建议。

---

## 学习阶段 E：测试保护线

### 目标

理解当前哪些测试在保护关键链路。

### 重点文件

- `backend/test/unit/toolkits/test_omics_analysis_tool.py`
- `backend/test/unit/services/test_chat_service_langfuse_stream.py`
- `backend/test/unit/services/test_run_worker.py`
- `backend/test/unit/agents/test_omics_workflow.py`
- `backend/test/unit/agents/test_omics_citation_engine.py`
- `backend/test/unit/agents/test_omics_frontend_payload_workflow.py`

### 重点理解

- 工具直接调用测试
- direct route 测试
- PubMed mock 测试
- 前端 payload 测试
- 测试污染与 `sys.modules` mock 问题

### 学习成果

后续修改 Phase 10 时，知道应该跑哪些最小测试。

---

# 第一阶段学习指导：前端入口与 Run 创建

## 第 1 步：定位按钮入口

打开：

```text
web/src/views/BreedingWorkbenchView.vue
```

搜索：

```text
handleSubmit
```

重点看：

- 点击按钮后是否进入 `handleSubmit()`
- `handleSubmit()` 是否会清空旧结果
- 是否设置 `running`
- 是否调用 `runBreedingWorkbench()`

需要回答：

- trait 从哪个输入框来？
- question 从哪个 textarea 来？
- context 里包含哪些字段？
- 每次点击前有没有清空旧 result？
- payload 返回后通过哪个函数同步到 result？

---

## 第 2 步：看前端 API 适配层

打开：

```text
web/src/apis/breeding_workbench_api.js
```

搜索：

```text
runBreedingWorkbench
```

重点看参数：

- `agentId`
- `agentConfigId`
- `trait`
- `question`
- `context`
- `threadId`
- `meta`
- `onProgress`
- `onSoftTimeout`

需要回答：

- createThread 在哪里调用？
- createAgentRun 在哪里调用？
- meta 里传了哪些 breeding-workbench 信息？
- allowed_tools / preferred_tool 是在哪里设置的？
- request_id 是在哪里生成和使用的？

---

## 第 3 步：看 snapshot 如何解析结果

继续在：

```text
web/src/apis/breeding_workbench_api.js
```

搜索：

```text
buildRunSnapshot
extractFrontendPayloadFromHistory
```

重点理解：

- history message
- tool output
- frontend_payload
- answer_markdown
- visibleToolChain
- run_status

需要回答：

- 前端如何从 history 中找到 frontend_payload？
- 如果有 frontend_payload，markdown 优先取哪里？
- 如果没有 frontend_payload，前端会 fallback 到哪里？
- visibleToolChain 为什么只显示 `omics_breeding_analysis_run`？
- request_id 如何避免新旧结果混用？

---

## 第 4 步：回到 Vue 看页面渲染

打开：

```text
web/src/views/BreedingWorkbenchView.vue
```

搜索：

```text
result.markdown
visibleToolChain
displayStatus
downloadMarkdown
运行诊断信息
```

需要对应页面理解：

- 状态：已完成
- 工具调用链：多组学育种分析
- 正文 Markdown
- 下载育种建议 Markdown
- 运行诊断信息

需要回答：

- 页面“已完成”来自哪个 computed？
- 工具 chip 的中文名在哪里映射？
- 正文 Markdown 是哪个字段？
- 下载按钮下载的是哪个字段？
- 运行诊断信息显示了哪些字段？

---

## 第 5 步：用 grep 辅助学习

执行：

```bash
cd ~/projects/Houji-Breeding-Assistant

grep -R "handleSubmit\|runBreedingWorkbench\|buildRunSnapshot\|extractFrontendPayloadFromHistory\|syncResultFromPayload\|visibleToolChain\|displayStatus" -n \
  web/src/views/BreedingWorkbenchView.vue \
  web/src/apis/breeding_workbench_api.js
```

按 grep 输出顺序阅读，不要整文件从头到尾读。

---

## 第 6 步：整理一张链路图

建议在笔记里写：

```text
BreedingWorkbenchView.vue
  handleSubmit()
    ↓
breeding_workbench_api.js
  runBreedingWorkbench()
    ↓
threadApi.createThread()
    ↓
agentApi.createAgentRun(meta: source=breeding-workbench, preferred_tool=omics_breeding_analysis_run)
    ↓
poll run status + history
    ↓
buildRunSnapshot()
    ↓
extract frontend_payload / answer_markdown / tool calls
    ↓
BreedingWorkbenchView.vue
  syncResultFromPayload()
    ↓
页面展示：状态、工具链、Markdown、下载按钮
```

---

## 第一阶段验收问题

学完后应能回答：

- 为什么页面现在显示“多组学育种分析”，而不是旧 smoke 工具？
- 为什么之前会出现旧结果混用？
- 现在 request_id 是如何避免旧结果混用的？
- 为什么前端本身不做育种分析？
- 为什么页面能在后端完成后自动显示 Markdown？