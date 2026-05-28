"""Define the configurable parameters for the agent."""

import uuid
from dataclasses import MISSING, dataclass, field, fields
from typing import Annotated, get_args, get_origin

from yuxi import config as sys_config

"""
前端 BreedingWorkbench
↓
POST /api/chat/runs
↓
agent_run_service.py 创建 AgentRun
↓
run_worker.py 恢复 query/config/meta
↓
chat_service.py: stream_agent_chat()
↓
取 AgentConfig.config_json.context
↓
_build_agent_input_context()
↓
BaseAgent.stream_messages_with_state()
↓
BaseContext.update_from_dict(input_context)
↓
ChatbotAgent.get_graph(context)
↓
RuntimeConfigMiddleware 根据 context.tools 过滤工具
↓
模型执行并调用工具

BaseContext 是：AgentConfig 配置和Agent / LangGraph 执行之间的中间配置对象。RuntimeConfigMiddleware 实际读取的 context.tools 就定义在这里
它决定：用哪个模型、系统提示词是什么、启用哪些工具、启用哪些知识库、启用哪些 MCP server、启用哪些 skills、启用哪些 subagents
"""


@dataclass(kw_only=True)
class BaseContext:
    """
    定义一个基础 Context 供 各类 graph 继承

    配置优先级:
    1. 运行时配置(RunnableConfig)：最高优先级，直接从函数参数传入
    2. 类默认配置：最低优先级，类中定义的默认值
    """

    def update(self, data: dict):
        """更新配置字段"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    # 标识当前对话线程  同一个 thread_id 可以恢复同一轮对话的 LangGraph state。
    # 一次育种任务对应一个 thread。前端后续通过 thread_id 读取 history。
    thread_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={"name": "线程ID", "configurable": False, "description": "用来唯一标识一个对话线程"},
    )

    # 标识当前用户   和 thread_id 一起用于：状态隔离、历史恢复、用户权限边界
    user_id: str = field(
        default_factory=lambda: str(uuid.uuid4()),
        metadata={"name": "用户ID", "configurable": False, "description": "用来唯一标识一个用户"},
    )

    # 定义 Agent 的系统角色和行为边界。TODO：当前前端的育种约束主要还在 query 中，后面可以尝试在 system_prompt 进行更稳定的系统级约束
    system_prompt: Annotated[str, {"__template_metadata__": {"kind": "prompt"}}] = field(
        default="You are a helpful assistant.",
        metadata={"name": "系统提示词", "description": "用来描述智能体的角色和行为"},
    )

    # 指定当前 Agent 用哪个大模型。大模型不是在 tools.py 里调用的；是在 ChatbotAgent.get_graph() 中被加载并交给 create_agent
    # 模型链路：
    # AgentConfig.config_json.context.model
    # ↓
    # BaseContext.model
    # ↓
    # load_chat_model(context.model)
    # ↓
    # create_agent(model=...)
    model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default=sys_config.default_model,
        metadata={
            "name": "智能体模型",
            "options": [],
            "description": "智能体的驱动模型，建议选择 Agent 能力较强的模型，不建议使用小参数模型。",
        },
    )

    # 当前 Agent 配置中启用哪些工具。默认值是ask_user_question、tavily_search
    # 业务链路是：
    # AgentConfig.config_json.context.tools
    # ↓
    # BaseContext.tools
    # ↓
    # RuntimeConfigMiddleware.get_tools_from_context()
    # ↓
    # 选出工具对象
    # ↓
    # 覆盖模型可见工具列表
    # 当前 YuXi 原生的工具启用机制看的是 context.tools。如果 breeding tools 不在 context.tools 中，RuntimeConfigMiddleware 就不会把它们作为启用工具保留下来
    tools: Annotated[list[str], {"__template_metadata__": {"kind": "tools"}}] = field(
        default_factory=lambda: ["ask_user_question", "tavily_search"],
        metadata={
            "name": "工具",
            "description": "内置的工具。",
        },
    )

    # 当前 Agent 启用哪些知识库。
    knowledges: Annotated[list[str], {"__template_metadata__": {"kind": "knowledges"}}] = field(
        default_factory=list,
        metadata={
            "name": "知识库",
            "description": "知识库列表，可以在左侧知识库页面中创建知识库。",
            "type": "list",  # Explicitly mark as list type for frontend if needed
        },
    )

    # 当前 Agent 启用哪些 MCP server。
    # MCP 链路是：
    # context.mcps
    # ↓
    # RuntimeConfigMiddleware
    # ↓
    # get_enabled_mcp_tools()
    # ↓
    # MCP tools
    # ↓
    # 模型可见工具
    mcps: Annotated[list[str], {"__template_metadata__": {"kind": "mcps"}}] = field(
        default_factory=list,
        metadata={
            "name": "MCP服务器",
            "options": [],
            "description": (
                "MCP服务器列表，建议使用支持 SSE 的 MCP 服务器，"
                "如果需要使用 uvx 或 npx 运行的服务器，也请在项目外部启动 MCP 服务器，并在项目中配置 MCP 服务器。"
            ),
        },
    )

    # 启用哪些 Skills。对应 SkillsMiddleware()
    skills: Annotated[list[str], {"__template_metadata__": {"kind": "skills"}}] = field(
        default_factory=list,
        metadata={
            "name": "Skills",
            "options": [],
            "description": "可选技能列表（由超级管理员维护）。运行时仅挂载并只读暴露选中的 "
            "skills。技能依赖的工具和 MCP 服务器也会被自动挂载。",
            "type": "list",
        },
    )

    # 指定 SubAgent 使用的默认模型。TODO：后续可以把单个组学分析或者文献、建议等做成子智能体
    subagents_model: Annotated[str, {"__template_metadata__": {"kind": "llm"}}] = field(
        default=sys_config.default_model,
        metadata={
            "name": "子智能体的默认模型",
            "description": "为所有子智能体设置默认模型，可在各子智能体配置中单独覆盖。",
        },
    )

    # 启用哪些子智能体
    subagents: Annotated[list[str], {"__template_metadata__": {"kind": "subagents"}}] = field(
        default_factory=list,
        metadata={
            "name": "子智能体",
            "options": [],
            "description": "可选子智能体列表。为空表示不启用任何 SubAgent。但依然会启用一个 general-purpose 的子智能体",
            "type": "list",
        },
    )

    # 控制 SummaryOffloadMiddleware 什么时候触发摘要压缩。
    summary_threshold: int = field(
        default=100,
        metadata={
            "name": "上下文摘要触发阈值 (KB)",
            "description": "当上下文大小超过该值时，启用摘要功能以优化上下文使用。单位为 KB，默认值为 100KB。",
            "type": "number",
        },
    )

    # 把 BaseContext 中可配置字段转换成前端配置页面可展示的配置项。说明了 tools 是一个可配置字段。
    # 用户/管理员理论上可以通过 Agent 配置页面选择工具，最后保存到：AgentConfig.config_json.context.tools
    # 然后执行时进入：BaseContext.tools
    @classmethod
    def get_configurable_items(cls):
        """实现一个可配置的参数列表，在 UI 上配置时使用"""
        configurable_items = {}
        for f in fields(cls):
            if f.init and not f.metadata.get("hide", False):
                if f.metadata.get("configurable", True):
                    # 处理类型信息
                    field_type = f.type
                    type_name = cls._get_type_name(field_type)

                    # 提取 Annotated 的元数据
                    template_metadata = cls._extract_template_metadata(field_type)

                    options = f.metadata.get("options", [])
                    if callable(options):
                        options = options()

                    configurable_items[f.name] = {
                        "type": f.metadata.get("type", type_name),
                        "name": f.metadata.get("name", f.name),
                        "options": options,
                        "default": f.default
                        if f.default is not MISSING
                        else f.default_factory()
                        if f.default_factory is not MISSING
                        else None,
                        "description": f.metadata.get("description", ""),
                        "template_metadata": template_metadata,  # Annotated 的额外元数据
                    }

        return configurable_items

    # 这两个函数主要服务 UI 配置生成
    # 前端可以根据 kind=tools 渲染工具选择组件；根据 kind=llm 渲染模型选择组件；根据 kind=prompt 渲染提示词编辑组件。
    # 主要服务 UI 配置生成，从字段类型中提取类型名称。
    @classmethod
    def _get_type_name(cls, field_type) -> str:
        """获取类型名称，处理 Annotated 类型"""
        # 检查是否是 Annotated 类型
        if get_origin(field_type) is not None:
            # 处理泛型类型如 list[str], Annotated[str, {...}]
            origin = get_origin(field_type)
            if hasattr(origin, "__name__"):
                if origin.__name__ == "Annotated":
                    # Annotated 类型，获取真实类型
                    args = get_args(field_type)
                    if args:
                        return cls._get_type_name(args[0])  # 递归处理真实类型
                return origin.__name__
            else:
                return str(origin)
        elif hasattr(field_type, "__name__"):
            return field_type.__name__
        else:
            return str(field_type)

    # 主要服务 UI 配置生成，从 Annotated 类型中提取 __template_metadata__。
    @classmethod
    def _extract_template_metadata(cls, field_type) -> dict:
        """从 Annotated 类型中提取模板元数据"""
        if get_origin(field_type) is not None:
            origin = get_origin(field_type)
            if hasattr(origin, "__name__") and origin.__name__ == "Annotated":
                args = get_args(field_type)
                if len(args) > 1:
                    # 查找包含 __template_metadata__ 的字典
                    for metadata in args[1:]:
                        if isinstance(metadata, dict) and "__template_metadata__" in metadata:
                            return metadata["__template_metadata__"]
        return {}

    # 把字典中的字段更新到 BaseContext 对象上。实现 AgentConfig.config_json.context 进入 BaseContext
    def update_from_dict(self, data: dict):
        """从字典更新配置字段"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
