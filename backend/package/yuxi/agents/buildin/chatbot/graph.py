from deepagents.middleware.filesystem import FilesystemMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.subagents import SubAgentMiddleware
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware, TodoListMiddleware

from yuxi.agents import BaseAgent, BaseState, load_chat_model
from yuxi.services.mcp_service import get_tools_from_all_servers
from yuxi.services.subagent_service import get_subagents_from_names

from .prompt import TODO_MID_PROMPT, build_prompt_with_context

"""
ChatbotAgent.get_graph() 的作用是：
为 BaseAgent 提供一个已经组装好的 LangGraph Agent

run_worker.py: process_agent_run()
↓
chat_service.py: stream_agent_chat()
↓
_stream_agent_events()
↓
BaseAgent.stream_messages_with_state()
↓
ChatbotAgent.get_graph()
↓
create_agent(...)
↓
LangGraph Agent 执行

ChatbotAgent.get_graph() 是 YuXi 通用聊天 Agent 的图构造入口。它继承 BaseAgent，并在 get_graph() 中通过 create_agent() 组装模型、系统提示词、middleware、state_schema 和 checkpointer。
模型由 context.model 通过 load_chat_model() 加载，系统提示词由 build_prompt_with_context(context) 构造，状态保存器由 BaseAgent._get_checkpointer() 提供。
当前 get_graph() 没有直接传 tools=[...]，也没有直接调用 Tool Registry，因此工具能力大概率通过 RuntimeConfigMiddleware、KnowledgeBaseMiddleware、
SkillsMiddleware、MCP tools 或 SubAgentMiddleware 注入。对育种工作台而言，当前 meta.allowed_tools 已经传到 worker/chat_service，
但尚未看到它进入 ChatbotAgent.get_graph() 或 RuntimeConfigMiddleware，所以下一步应重点学习 RuntimeConfigMiddleware，确认工具列表如何从配置进入模型，以及 allowed_tools 应该在哪里实现过滤。
"""


# FIXME：当前 get_graph 没有直接传 tools=[...]；工具可能由 RuntimeConfigMiddleware 根据 context 配置动态注入。后续 allowed_tools 硬约束应重点追这里。
async def _build_middlewares(context):
    """构建中间件列表"""
    # 延迟导入重依赖，避免 worker 在自动发现 ChatbotAgent 时提前拉起知识库/文件系统后端。
    from yuxi.agents.backends.composite import create_agent_composite_backend
    from yuxi.agents.middlewares.attachment_middleware import save_attachments_to_fs
    from yuxi.agents.middlewares.runtime_config_middleware import RuntimeConfigMiddleware
    from yuxi.agents.middlewares.knowledge_base_middleware import KnowledgeBaseMiddleware
    from yuxi.agents.middlewares.skills_middleware import SkillsMiddleware
    from yuxi.agents.middlewares.summary_middleware import SummaryOffloadMiddleware

    # 从所有 MCP server 获取外部工具。
    # TODO：后续要控制育种工具，不能只看 MCP，还要看 RuntimeConfigMiddleware 如何合并本地工具、MCP 工具、配置工具。
    all_mcp_tools = await get_tools_from_all_servers()  # 因为异步加载，无法放在 RuntimeConfigMiddleware 的 __init__ 中

    # summary middleware
    # 主 Agent 上下文优化：90k tokens 触发压缩（128k context window 的 70%）
    summary_middleware = SummaryOffloadMiddleware(
        model=load_chat_model(fully_specified_name=context.model),
        trigger=("tokens", getattr(context, "summary_threshold", 100) * 1024),
        trim_tokens_to_summarize=4000,
        summary_offload_threshold=500,
        max_retention_ratio=0.5,
    )

    # 构建 SubAgentMiddleware，给主 Agent 增加子智能体能力
    subagents = await get_subagents_from_names(context.subagents)
    subagents_middleware = SubAgentMiddleware(
        default_model=load_chat_model(fully_specified_name=context.subagents_model),  # 根据 context.subagents 加载子智能体
        subagents=subagents,
        general_purpose_agent=True,
        default_middleware=[
            FilesystemMiddleware(backend=create_agent_composite_backend),  # 文件系统后端
            PatchToolCallsMiddleware(),
            summary_middleware,
        ],
    )
    # all middlewares
    middlewares = [
        FilesystemMiddleware(backend=create_agent_composite_backend),  # 文件系统后端，给 Agent 提供文件系统能力。
        save_attachments_to_fs,  # 附件注入提示词。把用户上传的附件保存到文件系统，并注入提示词或上下文。
        KnowledgeBaseMiddleware(),  # 知识库工具。给 Agent 增加知识库工具或知识库检索能力。
        RuntimeConfigMiddleware(extra_tools=all_mcp_tools),  # 运行时配置应用（模型/工具/MCP/提示词）
        SkillsMiddleware(),  # Skills 中间件（提示词注入、依赖展开、动态激活）
        subagents_middleware,
        summary_middleware,
        TodoListMiddleware(system_prompt=TODO_MID_PROMPT),  # 待办事项中间件。给 Agent 增加待办事项管理能力。
        PatchToolCallsMiddleware(),  # 修补工具调用格式或兼容性问题。
        ModelRetryMiddleware(),  # 模型重试中间件
    ]

    return middlewares


class ChatbotAgent(BaseAgent):
    name = "禾穗·育种大模型"
    description = "基础的对话机器人，可以回答问题，可在配置中启用需要的工具。"
    capabilities = ["file_upload", "files"]  # 支持文件上传功能
    metadata = {
        "examples": [
            "如何利用分子标记辅助选择实现谷子育种中高产与抗逆的同时改良？",
            "如何精确定位与谷子抗病性、抗虫性相关的QTL？",
            "如何利用全基因组关联分析识别与抗旱性相关的主要基因及其效应？",
            "谷子品种在高温胁迫下的适应性差异，如何通过基因编辑技术提高谷子耐热性？",
            "在谷子的栽培适应性研究中，如何通过转录组学解析不同栽培环境对谷子生长的影响？"
        ]
    }
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, context=None, **kwargs):

        # 如果 BaseAgent.stream_messages_with_state() 已经传入 context，就使用传入的 context。
        # 如果没有，就创建默认 context。这个 context 后面决定：模型用哪个、system prompt 是什么、启用哪些工具和子智能体、摘要阈值
        context = context or self.context_schema()  # 获取上下文配置

        # 使用 create_agent 创建智能体
        graph = create_agent(
            # 模型加载入口，根据 context.model 加载大模型。把模型对象交给 create_agent，真正模型调用发生在 create_agent 生成的 Agent graph 执行过程中
            model=load_chat_model(fully_specified_name=context.model),
            # 系统提示词构造入口（与用户提示词来自前端buildBreedingWorkbenchQuery()，作为 HumanMessage 输入 进行区分）
            system_prompt=build_prompt_with_context(context),
            # 工具和功能扩展入口，通过 middleware 注入
            middleware=await _build_middlewares(context),
            # 表示 LangGraph 的状态结构使用 YuXi 的 BaseState
            state_schema=BaseState,
            # 表示 graph 会带状态保存器。
            # 作用：让 LangGraph 能根据 thread_id / user_id 保存和恢复 state。它对应 BaseAgent 里 _get_checkpointer() 的逻辑
            checkpointer=await self._get_checkpointer(),
        )

        return graph


def main():
    pass


if __name__ == "__main__":
    main()
    # asyncio.run(main())
