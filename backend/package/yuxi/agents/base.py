from __future__ import annotations

import os
from abc import abstractmethod
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver, aiosqlite
from langgraph.graph.state import CompiledStateGraph

from yuxi import config as sys_config
from yuxi.agents.context import BaseContext
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils import logger

"""
YuXi Agent 的基础执行协议层：它规定一个 Agent 如何拿到 LangGraph、如何流式执行、如何非流式执行、如何保存/恢复 LangGraph 状态

base.py 在当前育种工作台链路中的位置
前端 BreedingWorkbench
↓
POST /api/chat/runs
↓
agent_run_service.py 创建 AgentRun
↓
run_worker.py: process_agent_run()
↓
chat_service.py: stream_agent_chat()
↓
chat_service.py: _stream_agent_events()
↓
base.py: BaseAgent.stream_messages_with_state()
↓
base.py: BaseAgent.get_graph()
↓
具体 Agent 子类的 get_graph()
↓
LangGraph 执行
↓
模型 + 工具
↓
保存 assistant/tool 消息到 history

所以 base.py 这一层解决的是：
stream_agent_chat() 拿到 Agent 实例后，如何真正进入 LangGraph 执行。
它是后续所有这些功能进入 Agent 执行链路的基础。
"""
class BaseAgent:
    """
    定义一个基础 Agent 供 各类 graph 继承 即所有Agent的基础协议
    """

    name = "base_agent"
    description = "base_agent"
    capabilities: list[str] = []  # 智能体能力列表，如 ["file_upload", "web_search"] 等
    # chat_service.py 传进来的 input_context，会在 BaseAgent 这一层转成 Agent 运行时 context。
    # 这就是 chat_service.py 和 Agent 图执行之间的桥
    context_schema: type[BaseContext] = BaseContext  # 智能体上下文 schema

    # 初始化 graph、checkpointer 和工作目录
    # 具体工具、模型、middleware 的绑定，发生在子类 get_graph() 中，而不是 BaseAgent.__init__()
    def __init__(self, **kwargs):
        # 先不构图，后续 get_graph() 再构建
        self.graph = None  # will be covered by get_graph
        # LangGraph 状态保存器暂时为空
        self.checkpointer = None
        # sqlite 异步连接暂时为空
        self._async_conn = None
        # 为当前 Agent 准备独立工作目录
        self.workdir = Path(sys_config.save_dir) / "agents" / self.module_name
        self.workdir.mkdir(parents=True, exist_ok=True)

    # module_name 和 id 用于识别当前 Agent
    @property
    def module_name(self) -> str:
        """Get the module name of the agent class."""
        return self.__class__.__module__.split(".")[-2]

    @property
    def id(self) -> str:
        """Get the agent's class name."""
        return self.__class__.__name__

    # 给前端/管理页面看的 Agent 信息
    async def get_info(self, include_configurable_items: bool = True):
        # metadata 固定在代码中，由各 Agent 的类属性提供
        metadata = self.load_metadata()
        configurable_items = {}
        if include_configurable_items:
            configurable_items = self.context_schema.get_configurable_items()

        # Merge metadata with class attributes, metadata takes precedence
        return {
            "id": self.id,
            "name": getattr(self, "name", "Unknown"),
            "description": getattr(self, "description", "Unknown"),
            "metadata": metadata,
            "configurable_items": configurable_items,
            "capabilities": getattr(self, "capabilities", []),  # 智能体能力列表
        }

    async def get_config(self):
        return self.context_schema()

    async def stream_values(self, messages: list[str], input_context=None, **kwargs):
        context = self.context_schema()
        context.update_from_dict(input_context or {})
        graph = await self.get_graph(context=context)
        for event in graph.astream({"messages": messages}, stream_mode="values", context=context):
            yield event["messages"]

    # 只流式返回消息，不返回 state
    # 和 stream_messages_with_state() 的区别是不返回 state values
    async def stream_messages(self, messages: list[str], input_context=None, **kwargs):
        context = self.context_schema()
        context.update_from_dict(input_context or {})
        graph = await self.get_graph(context=context)
        logger.debug(f"stream_messages: {context=}")

        # 构建配置：LangGraph 会自动从 checkpointer 恢复 state
        input_config = {
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},
            "recursion_limit": 300,
        }

        # langfuse metadata and callbacks integration
        if callbacks := kwargs.get("callbacks"):
            input_config["callbacks"] = list(callbacks)
        if metadata := kwargs.get("metadata"):
            input_config["metadata"] = dict(metadata)
        if tags := kwargs.get("tags"):
            input_config["tags"] = list(tags)

        async for msg, metadata in graph.astream(
            {"messages": messages},
            stream_mode="messages",
            context=context,
            config=input_config,
        ):
            yield msg, metadata

    # ***当前最重要的执行入口
    # 三个输入对应到 chat_service.py
    async def stream_messages_with_state(self, messages: list[str], input_context=None, **kwargs):
        # 构造 context，把 chat_service.py 准备好的 input_context 灌入 Agent 的上下文对象
        context = self.context_schema()
        context.update_from_dict(input_context or {})

        # 获取 graph（来自于get_graph子类实现）
        graph = await self.get_graph(context=context)
        logger.debug(f"stream_messages_with_state: {context=}")

        # 构造 LangGraph config
        input_config = {
            # 同一个 thread_id 可以恢复同一条对话状态，不同用户/线程之间隔离
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},
            # 限制 LangGraph 最大递归循环步数
            "recursion_limit": 300,
        }

        # 传入 callbacks / metadata / tags   主要用于 Langfuse 或追踪系统
        # TODO：后续要判断：meta.allowed_tools 是否会进入 metadata？metadata 是否会被 Agent / middleware 使用？
        if callbacks := kwargs.get("callbacks"):
            input_config["callbacks"] = list(callbacks)
        if metadata := kwargs.get("metadata"):
            input_config["metadata"] = dict(metadata)
        if tags := kwargs.get("tags"):
            input_config["tags"] = list(tags)

        # 调用 graph.astream()，是实际执行 LangGraph 的地方
        async for mode, payload in graph.astream(
            # 告诉LangGraph  输入、流式模式、Agent运行上下文、配置信息
            {"messages": messages},
            stream_mode=["messages", "values"],  # messages：模型输出、工具调用消息等  values：LangGraph state 值，例如 todos、files、artifacts
            context=context,
            config=input_config,
        ):
            yield mode, payload

    # 非流式执行入口 对应的是非流式调用：
    # chat_service.py: agent_chat() ——》agent.invoke_messages()
    async def invoke_messages(self, messages: list[str], input_context=None, **kwargs):
        context = self.context_schema()
        context.update_from_dict(input_context or {})
        graph = await self.get_graph(context=context)
        logger.debug(f"invoke_messages: {context}")

        # 构建配置
        input_config = {
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},
            "recursion_limit": 100,
        }

        # langfuse metadata and callbacks integration
        if callbacks := kwargs.get("callbacks"):
            input_config["callbacks"] = list(callbacks)
        if metadata := kwargs.get("metadata"):
            input_config["metadata"] = dict(metadata)
        if tags := kwargs.get("tags"):
            input_config["tags"] = list(tags)

        msg = await graph.ainvoke(
            {"messages": messages},
            context=context,
            config=input_config,
        )
        return msg

    async def check_checkpointer(self):
        app = await self.get_graph()
        if not hasattr(app, "checkpointer") or app.checkpointer is None:
            return False
        return True

    # 从 LangGraph state 里读历史
    async def get_history(self, user_id, thread_id) -> list[dict]:
        """获取历史消息"""
        try:
            app = await self.get_graph()

            # 从 LangGraph checkpointer 中读取 state messages
            if not await self.check_checkpointer():
                return []

            config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
            state = await app.aget_state(config)

            result = []
            if state:
                messages = state.values.get("messages", [])
                for msg in messages:
                    if hasattr(msg, "model_dump"):
                        msg_dict = msg.model_dump()  # 转换成字典
                    else:
                        msg_dict = dict(msg) if hasattr(msg, "__dict__") else {"content": str(msg)}
                    result.append(msg_dict)

            return result

        except Exception as e:
            logger.error(f"获取智能体 {self.name} 历史消息出错: {e}")
            return []

    def reload_graph(self):
        """重置 graph 缓存，强制下次调用 get_graph 时重新构建"""
        self.graph = None
        logger.info(f"{self.name} graph 缓存已清空，将在下次调用时重新构建")


    # 最关键的抽象点
    # 说明：BaseAgent 不知道具体图怎么构建。具体 Agent 子类必须实现 get_graph()。
    # BaseAgent 只是规定：子类必须给一个已经编译好的 CompiledStateGraph
    @abstractmethod
    async def get_graph(self, **kwargs) -> CompiledStateGraph:
        """
        获取并编译对话图实例。
        必须确保在编译时设置 checkpointer，否则将无法获取历史记录。
        例如: graph = workflow.compile(checkpointer=sqlite_checkpointer)
        """
        pass

    # LangGraph 状态保存器
    # 优先级：
    # 1. 如果 self.checkpointer 已存在，直接复用；
    # 2. 如果 LANGGRAPH_CHECKPOINTER_BACKEND=postgres，尝试用 Postgres；
    # 3. 否则用 sqlite；
    # 4. sqlite 失败则退回内存。
    async def _get_checkpointer(self):
        if self.checkpointer is not None:
            return self.checkpointer

        checkpointer = None
        backend = os.getenv("LANGGRAPH_CHECKPOINTER_BACKEND", "sqlite").strip().lower()

        if backend == "postgres":
            checkpointer = await self._create_postgres_checkpointer()

        if checkpointer is None:
            try:
                checkpointer = AsyncSqliteSaver(await self.get_async_conn())
            except Exception as e:
                logger.error(f"构建 sqlite checkpointer 失败: {e}, 尝试使用内存存储")
                checkpointer = InMemorySaver()

        self.checkpointer = checkpointer
        return self.checkpointer

    async def _create_postgres_checkpointer(self):
        postgres_url = os.getenv("POSTGRES_URL")
        if not postgres_url:
            logger.warning("POSTGRES_URL 未配置，无法启用 postgres checkpointer，回退 sqlite")
            return None

        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver  # type: ignore
        except Exception as e:
            logger.warning(f"langgraph postgres checkpointer 不可用，回退 sqlite: {e}")
            return None

        try:
            saver = AsyncPostgresSaver(pg_manager.langgraph_pool)

            logger.info(f"{self.name} 使用 postgres checkpointer")
            return saver
        except Exception as e:
            logger.warning(f"初始化 postgres checkpointer 失败，回退 sqlite: {e}")
            return None

    # 创建 sqlite 异步连接，给 AsyncSqliteSaver 使用。
    async def get_async_conn(self) -> aiosqlite.Connection:
        """获取异步数据库连接"""
        if self._async_conn is not None:
            return self._async_conn

        conn = await aiosqlite.connect(os.path.join(self.workdir, "aio_history.db"))
        # Patch: langgraph's AsyncSqliteSaver expects is_alive() method which aiosqlite may not have
        if not hasattr(conn, "is_alive"):
            conn.is_alive = lambda: True
        self._async_conn = conn
        return self._async_conn

    # 返回 sqlite checkpointer。
    async def get_aio_memory(self) -> AsyncSqliteSaver:
        """获取异步存储实例"""
        return AsyncSqliteSaver(await self.get_async_conn())

    # 读取 Agent 类上的 metadata。主要用于 get_info()
    def load_metadata(self) -> dict:
        """Load metadata from agent class attribute."""
        metadata = getattr(self, "metadata", {})
        if isinstance(metadata, dict):
            return metadata
        logger.warning(f"Agent {self.module_name} metadata is not a dict, fallback to empty metadata")
        return {}
