

<a href="https://trendshift.io/repositories/24335" target="_blank"><img src="https://trendshift.io/api/badge/repositories/24335" alt="xerrors%2FYuxi | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[[文档]](https://xerrors.github.io/Yuxi)

</div>

![arch](https://xerrors.oss-cn-shanghai.aliyuncs.com/github/gpt-iamge-2-arch.png)


**图由 GPT-Image-2 生成*

## 核心特性

- **智能体开发**：基于 LangGraph，支持子智能体、Skills、MCPs、Tools 与中间件机制
- **知识库（RAG）**：多格式文档解析，支持 Embedding / Rerank 配置及知识库评估
- **知识图谱**：基于 LightRAG 的图谱构建与可视化，支持属性图谱并参与智能体推理
- **平台与工程化**：Vue + FastAPI 架构，支持暗黑模式、Docker 与生产级部署

## 最新动态






<details>
<summary>[2026/04/01] v0.6.0 版本发布</summary>

### 新增

- 重构后端代码 src -> backend/package/yuxi
- 重构文档解析，统一文档解析体验，并新增 Parser 类
- 新增 LITE 模式启动，启动时不加载知识库、知识图谱相关模块，可以使用 make up-lite 快捷启动
- 新增沙盒环境，详见后续文档更新，统一沙盒虚拟路径前缀默认值为 `/home/gem/user-data`
- 新增基于沙盒的文件系统，前端工作台可以查看文件系统，支持预览（文本、图片、PDF、HTML）、下载文件
- 新增 `present_artifacts` 内置工具：Agent 可将 `/home/gem/user-data/outputs/` 下的结果文件显式写入 LangGraph state 的 `artifacts` 字段，前端支持在输入框顶部以默认折叠的堆叠卡片展示本轮交付物文件，并保持可下载、可预览能力
- 新增基于沙盒的知识库只读映射，按“用户可访问知识库 ∩ 当前 Agent 已启用知识库”暴露原始文件与解析后的 Markdown
- 重构附件系统，直接集成在了沙盒文件系统中，附件上传后直接落盘到沙盒挂载目录
- 优化前端流式消息体验：新增通用 `useStreamSmoother` 调度层，统一平滑 Agent runs SSE、普通聊天流与审批恢复流中的 `loading` chunk
- 优化项目文档说明，并添加贡献指南
- 重构前端 Agent 路由结构，体验更加顺畅，切换更加自然（类 chatgpt 体验）
- 新增 API Key 认证功能，支持外部系统通过 API Key 调用系统服务
- 新增 subagents 的支持，支持在 web 中添加 subagents，以及两个内置的子智能体
- 新增内置Skills reporter，并移除内置 Agent reporter，数据库报表将由 Skills 完成
- 新增内置 Skills `deep-reporter`，用于指导生成科研报告、行业调研和其他深度分析类长报告
- 重构内置 Skills/MCP/Subagents 安装/添加/移除机制：内置 skill 支持按需安装、基于 `version + content_hash` 的更新提示与覆盖确认，不再使用服务器级开关切换
- 新增知识库 PDF、图片的预览功能
- 重构后端测试目录结构：按 `unit / integration / e2e` 分层迁移现有测试，拆分全局 `conftest.py`，统一测试入口为 `uv run --group test pytest`，并新增独立测试规范文档 `docs/vibe/testing-guidelines.md`


### 修复

- 修复 Lightrag 知识库修改配置后，模型没有切换的 bug [#580](https://github.com/xerrors/Yuxi/issues/580)
- 修复数据库获取接口未过滤文件字段而导致的数据包过大的情况
- 修复 Thread 未绑定 agent_config_id 导致的历史对话切换后上下文配置错乱的问题


</details>


## 快速开始

克隆代码，并初始化

```
git clone 
cd 

# Linux/macOS
./scripts/init.sh

# Windows PowerShell
.\scripts\init.ps1
```

然后需要使用 docker 启动项目

```
docker compose up --build
```

等待启动完成后，访问 `http://localhost:5173`

