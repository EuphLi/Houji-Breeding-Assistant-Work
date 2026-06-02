from __future__ import annotations

import importlib
import json
from pathlib import Path
from contextlib import asynccontextmanager
import sys
from types import SimpleNamespace
from types import ModuleType

import pytest
from langchain.messages import AIMessageChunk, HumanMessage


def _load_chat_service_module():
    # 旧测试导入方式保留供学习对照：
    # old:
    # from yuxi.services import chat_service as svc
    #
    # 原导入方式的问题：
    # 这个测试只想验证 stream_agent_chat 的 input_context 组装逻辑，
    # 但 chat_service 的顶层导入会连带拉起 buildin agent、数据库和 langfuse 等重依赖，
    # 导致 pytest 在 collection 阶段就因为无关依赖失败。
    #
    # 新导入方式的设计：
    # 先为 chat_service 的少量重依赖放入最小 stub，再导入真实 chat_service 模块。
    # 这样测试仍然覆盖真实的 stream_agent_chat 代码路径，
    # 但不会把本轮无关的 Agent 自动发现、数据库初始化链路一起拉进来。
    def _install_stub(module_name: str, *, attributes: dict[str, object]) -> None:
        if module_name in sys.modules:
            return
        module = ModuleType(module_name)
        for key, value in attributes.items():
            setattr(module, key, value)
        sys.modules[module_name] = module

    class _ImportStubRepository:
        def __init__(self, *args, **kwargs):
            del args, kwargs

    _install_stub(
        "yuxi.agents.backends",
        attributes={"__path__": []},
    )
    _install_stub(
        "yuxi.agents.backends.sandbox",
        attributes={"__path__": []},
    )
    _install_stub(
        "yuxi.agents.backends.sandbox.paths",
        attributes={"sandbox_workspace_agents_prompt_file": lambda _thread_id, _user_id: Path("/tmp/nonexistent-agents-md")},
    )
    _install_stub(
        "yuxi.agents.buildin",
        attributes={
            "agent_manager": SimpleNamespace(get_agent=lambda _agent_id: None),
            "__path__": [
                str(
                    Path(__file__).resolve().parents[3]
                    / "package"
                    / "yuxi"
                    / "agents"
                    / "buildin"
                )
            ],
        },
    )
    _install_stub(
        "yuxi.repositories.agent_config_repository",
        attributes={"AgentConfigRepository": _ImportStubRepository},
    )
    _install_stub(
        "yuxi.repositories.conversation_repository",
        attributes={"ConversationRepository": _ImportStubRepository},
    )
    _install_stub(
        "yuxi.services.langfuse_service",
        attributes={
            "LangfuseRunContext": SimpleNamespace,
            "build_run_context": lambda **kwargs: SimpleNamespace(
                callbacks=[],
                metadata={},
                tags=[],
                trace_id=None,
                seed_kwargs=kwargs,
            ),
            "flush_langfuse": lambda: None,
            "get_trace_info": lambda _run_context: {},
        },
    )
    _install_stub(
        "yuxi.storage.postgres.manager",
        attributes={"pg_manager": SimpleNamespace()},
    )
    _install_stub(
        "yuxi.storage.postgres.models_business",
        attributes={
            "User": type("User", (), {}),
            "MCPServer": type("MCPServer", (), {}),
            "AgentRun": type("AgentRun", (), {}),
        },
    )
    return importlib.import_module("yuxi.services.chat_service")


svc = _load_chat_service_module()


class _FakeConvRepo:
    def __init__(self, _db):
        self.saved_messages: list[dict] = []
        self.bound_agent_configs: list[tuple[str, int]] = []
        self.conversations: dict[str, SimpleNamespace] = {}
        self.tool_calls: list[dict] = []
        self.tool_updates: list[dict] = []

    async def add_message_by_thread_id(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        message_type: str = "text",
        extra_metadata: dict | None = None,
        image_content: str | None = None,
    ):
        self.saved_messages.append(
            {
                "thread_id": thread_id,
                "role": role,
                "content": content,
                "message_type": message_type,
                "extra_metadata": extra_metadata,
                "image_content": image_content,
            }
        )
        return SimpleNamespace(id=1)

    async def get_conversation_by_thread_id(self, thread_id: str):
        return self.conversations.get(thread_id)

    async def create_conversation(self, *, user_id: str, agent_id: str, thread_id: str):
        conversation = SimpleNamespace(
            user_id=user_id,
            agent_id=agent_id,
            thread_id=thread_id,
            extra_metadata={},
        )
        self.conversations[thread_id] = conversation
        return conversation

    async def bind_agent_config(self, thread_id: str, agent_config_id: int):
        conversation = self.conversations.setdefault(
            thread_id,
            SimpleNamespace(user_id="user-1", agent_id="test-agent", thread_id=thread_id, extra_metadata={}),
        )
        conversation.extra_metadata["agent_config_id"] = agent_config_id
        self.bound_agent_configs.append((thread_id, agent_config_id))

    async def add_tool_call(
        self,
        *,
        message_id: int,
        tool_name: str,
        tool_input: dict | None = None,
        status: str = "pending",
        langgraph_tool_call_id: str | None = None,
        **kwargs,
    ):
        del kwargs
        payload = {
            "message_id": message_id,
            "tool_name": tool_name,
            "tool_input": tool_input or {},
            "status": status,
            "langgraph_tool_call_id": langgraph_tool_call_id,
        }
        self.tool_calls.append(payload)
        return SimpleNamespace(id=len(self.tool_calls), **payload)

    async def update_tool_call_output(
        self,
        *,
        langgraph_tool_call_id: str,
        tool_output: str,
        status: str = "success",
        error_message: str | None = None,
    ):
        payload = {
            "langgraph_tool_call_id": langgraph_tool_call_id,
            "tool_output": tool_output,
            "status": status,
            "error_message": error_message,
        }
        self.tool_updates.append(payload)
        return SimpleNamespace(id=1, **payload)


class _FakeSessionContextFactory:
    def __init__(self):
        self.sessions: list[object] = []

    @asynccontextmanager
    async def get_async_session_context(self):
        session = object()
        self.sessions.append(session)
        yield session


async def _capture_stream_input_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    agent_context: dict,
    meta: dict,
) -> dict:
    calls: dict[str, object] = {}

    class FakeAgent:
        async def stream_messages_with_state(self, messages, input_context=None, **kwargs):
            del messages, kwargs
            calls["stream_input_context"] = input_context
            yield "messages", (AIMessageChunk(content="hello"), {"node": "llm"})

        async def get_graph(self):
            class FakeGraph:
                async def aget_state(self, config):
                    del config
                    return SimpleNamespace(values={"messages": [], "files": {}, "artifacts": []})

            return FakeGraph()

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        del db, user, agent_config_id
        return SimpleNamespace(agent_id="test-agent", config_json={"context": agent_context})

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_guard_check(_content):
        return False

    async def fake_guard_check_with_keywords(_content):
        return False

    async def fake_interrupts(agent, langgraph_config, make_chunk, chunk_meta, thread_id):
        del agent, langgraph_config, make_chunk, chunk_meta, thread_id
        if False:
            yield None

    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda agent_id: FakeAgent())
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "ConversationRepository", _FakeConvRepo)
    monkeypatch.setattr(svc, "_ensure_thread_bound_agent_config", fake_noop)
    monkeypatch.setattr(svc, "_load_workspace_agents_prompt", lambda _thread_id, _user_id: "")
    monkeypatch.setattr(svc, "save_messages_from_langgraph_state", fake_noop)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)
    monkeypatch.setattr(svc.content_guard, "check_with_keywords", fake_guard_check_with_keywords)
    monkeypatch.setattr(svc, "check_and_handle_interrupts", fake_interrupts)
    monkeypatch.setattr(
        svc,
        "_build_langfuse_run_context",
        lambda **kwargs: SimpleNamespace(callbacks=[], metadata={}, tags=[], trace_id=None),
    )
    monkeypatch.setattr(svc, "get_trace_info", lambda _run_context: {})
    monkeypatch.setattr(svc, "flush_langfuse", lambda: None)

    async for _chunk in svc.stream_agent_chat(
        query="hello",
        agent_config_id=123,
        thread_id="thread-1",
        meta={"request_id": "req-1", **meta},
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    ):
        pass

    return calls["stream_input_context"]


@pytest.mark.asyncio
async def test_stream_agent_chat_passes_langfuse_callbacks_and_persists_trace_info(monkeypatch: pytest.MonkeyPatch):
    calls: dict[str, object] = {}

    class FakeAgent:
        async def stream_messages(self, messages, input_context=None, **kwargs):
            calls["stream_messages"] = messages
            calls["stream_input_context"] = input_context
            calls["stream_kwargs"] = kwargs
            yield AIMessageChunk(content="hello"), {"node": "llm"}

        async def get_graph(self):
            class FakeGraph:
                async def aget_state(self, config):
                    return SimpleNamespace(values={"messages": [], "files": {}, "artifacts": []})

            return FakeGraph()

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        return SimpleNamespace(agent_id="test-agent", config_json={"context": {"temperature": 0.1}})

    async def fake_save_messages_from_langgraph_state(*, agent_instance, thread_id, conv_repo, config_dict, trace_info):
        calls["saved_state"] = {
            "thread_id": thread_id,
            "config_dict": config_dict,
            "trace_info": trace_info,
        }

    async def fake_guard_check(_content):
        return False

    async def fake_guard_check_with_keywords(_content):
        return False

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
        if False:
            yield None
        return

    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda agent_id: FakeAgent())
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "ConversationRepository", _FakeConvRepo)
    monkeypatch.setattr(svc, "_ensure_thread_bound_agent_config", fake_noop)
    monkeypatch.setattr(svc, "_load_workspace_agents_prompt", lambda _thread_id, _user_id: "")
    monkeypatch.setattr(svc, "save_messages_from_langgraph_state", fake_save_messages_from_langgraph_state)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)
    monkeypatch.setattr(svc.content_guard, "check_with_keywords", fake_guard_check_with_keywords)
    monkeypatch.setattr(svc, "check_and_handle_interrupts", fake_interrupts)
    monkeypatch.setattr(
        svc,
        "_build_langfuse_run_context",
        lambda **kwargs: SimpleNamespace(
            callbacks=["handler-1"],
            metadata={"langfuse_user_id": kwargs["current_user"].id, "langfuse_session_id": kwargs["thread_id"]},
            tags=["yuxi", "chat"],
            trace_id="trace-seeded",
        ),
    )
    monkeypatch.setattr(
        svc,
        "get_trace_info",
        lambda _run_context: {
            "langfuse_trace_id": "trace-runtime",
            "langfuse_session_id": "thread-1",
        },
    )
    monkeypatch.setattr(svc, "flush_langfuse", lambda: calls.setdefault("flushed", True))

    chunks = []
    async for chunk in svc.stream_agent_chat(
        query="hello",
        agent_config_id=123,
        thread_id="thread-1",
        meta={"request_id": "req-1"},
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    ):
        chunks.append(json.loads(chunk.decode("utf-8")))

    assert calls["stream_input_context"] == {"temperature": 0.1, "user_id": "user-1", "thread_id": "thread-1"}
    assert calls["stream_kwargs"] == {
        "callbacks": ["handler-1"],
        "metadata": {"langfuse_user_id": "user-1", "langfuse_session_id": "thread-1"},
        "tags": ["yuxi", "chat"],
    }
    assert calls["saved_state"]["trace_info"] == {
        "langfuse_trace_id": "trace-runtime",
        "langfuse_session_id": "thread-1",
    }
    assert chunks[-1]["status"] == "finished"
    assert calls["flushed"] is True
    assert isinstance(calls["stream_messages"][0], HumanMessage)


@pytest.mark.asyncio
async def test_stream_agent_chat_maps_breeding_workbench_allowed_tools_to_input_context(
    monkeypatch: pytest.MonkeyPatch,
):
    allowed_tools = [
        "smoke_flavonoid_breeding_advice",
        "breeding_advice_generate",
    ]

    input_context = await _capture_stream_input_context(
        monkeypatch,
        agent_context={"tools": ["ask_user_question", "tavily_search"]},
        meta={
            "source": "breeding-workbench",
            "allowed_tools": allowed_tools,
        },
    )

    assert input_context["tools"] == allowed_tools


@pytest.mark.asyncio
async def test_stream_agent_chat_keeps_agent_tools_for_non_breeding_source(monkeypatch: pytest.MonkeyPatch):
    agent_tools = ["ask_user_question", "tavily_search"]

    input_context = await _capture_stream_input_context(
        monkeypatch,
        agent_context={"tools": agent_tools},
        meta={
            "source": "agent-chat",
            "allowed_tools": [
                "smoke_flavonoid_breeding_advice",
                "breeding_advice_generate",
            ],
        },
    )

    assert input_context["tools"] == agent_tools


@pytest.mark.asyncio
async def test_stream_agent_chat_keeps_agent_tools_when_breeding_allowed_tools_is_empty(
    monkeypatch: pytest.MonkeyPatch,
):
    agent_tools = ["ask_user_question", "tavily_search"]

    input_context = await _capture_stream_input_context(
        monkeypatch,
        agent_context={"tools": agent_tools},
        meta={
            "source": "breeding-workbench",
            "allowed_tools": [],
        },
    )

    assert input_context["tools"] == agent_tools


@pytest.mark.asyncio
async def test_stream_agent_chat_filters_non_string_allowed_tools(monkeypatch: pytest.MonkeyPatch):
    input_context = await _capture_stream_input_context(
        monkeypatch,
        agent_context={"tools": ["ask_user_question"]},
        meta={
            "source": "breeding-workbench",
            "allowed_tools": [
                " smoke_flavonoid_breeding_advice ",
                "",
                None,
                123,
                "breeding_advice_generate",
            ],
        },
    )

    assert input_context["tools"] == [
        "smoke_flavonoid_breeding_advice",
        "breeding_advice_generate",
    ]


@pytest.mark.asyncio
async def test_stream_agent_chat_directly_runs_omics_tool_for_breeding_workbench(
    monkeypatch: pytest.MonkeyPatch,
):
    repo_holder: dict[str, _FakeConvRepo] = {}

    def fake_conv_repo(db):
        repo = _FakeConvRepo(db)
        repo_holder["repo"] = repo
        return repo

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        del db, user, agent_config_id
        return SimpleNamespace(agent_id="test-agent", config_json={"context": {}})

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_guard_check(_content):
        return False

    monkeypatch.setattr(svc, "ConversationRepository", fake_conv_repo)
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "_ensure_thread_bound_agent_config", fake_noop)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)
    fake_tool_module = ModuleType("yuxi.agents.toolkits.breeding.omics_analysis")
    fake_tool_module.omics_breeding_analysis_run = SimpleNamespace(
        invoke=lambda payload: {
            "status": "completed",
            "backend": "rule_fallback",
            "answer_markdown": "# 多组学育种分析结果\n\n分析流程已完成。",
            "frontend_payload": {
                "schema_version": "omics_frontend_payload.v1",
                "answer_markdown": "# 多组学育种分析结果\n\n分析流程已完成。",
                "summary": {"analysis_backend": "rule_fallback"},
            },
            "warnings": [],
        }
    )
    monkeypatch.setitem(sys.modules, "yuxi.agents.toolkits.breeding.omics_analysis", fake_tool_module)

    chunks = []
    async for chunk in svc.stream_agent_chat(
        query="给出一些育种建议",
        agent_config_id=123,
        thread_id="thread-1",
        meta={
            "request_id": "req-1",
            "source": "breeding-workbench",
            "trait": "黄酮相关",
            "question": "给出一些育种建议",
            "preferred_tool": "omics_breeding_analysis_run",
            "breeding_context": {"data_dir": "/tmp/demo"},
        },
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    ):
        chunks.append(json.loads(chunk.decode("utf-8").strip()))

    repo = repo_holder["repo"]
    assert chunks[-1]["status"] == "finished"
    assert chunks[-1]["tool_name"] == "omics_breeding_analysis_run"
    assert chunks[-1]["frontend_payload"]["schema_version"] == "omics_frontend_payload.v1"
    assert chunks[-1]["result"]["backend"] in {"llm", "rule_fallback"}
    assert repo.tool_calls[0]["tool_name"] == "omics_breeding_analysis_run"
    assert [item["role"] for item in repo.saved_messages] == ["user", "assistant", "tool", "assistant"]


@pytest.mark.asyncio
async def test_stream_agent_chat_persists_progress_snapshots_before_final_result(
    monkeypatch: pytest.MonkeyPatch,
):
    repo_holder: dict[str, _FakeConvRepo] = {}
    progress_sessions = _FakeSessionContextFactory()

    def fake_conv_repo(db):
        repo = _FakeConvRepo(db)
        repo_holder.setdefault(str(id(db)), repo)
        return repo

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        del db, user, agent_config_id
        return SimpleNamespace(agent_id="test-agent", config_json={"context": {}})

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_guard_check(_content):
        return False

    monkeypatch.setattr(svc, "ConversationRepository", fake_conv_repo)
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "_ensure_thread_bound_agent_config", fake_noop)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)
    monkeypatch.setattr(svc, "pg_manager", progress_sessions)

    fake_tool_module = ModuleType("yuxi.agents.toolkits.breeding.omics_analysis")

    def fake_runner(**kwargs):
        progress_callback = kwargs["progress_callback"]
        progress_callback(
            {
                "transcriptome_pipeline_status": "running",
                "transcriptome_path_exists": False,
                "pipeline_log_path": "/tmp/run.log",
            }
        )
        progress_callback(
            {
                "transcriptome_pipeline_status": "completed",
                "transcriptome_path_exists": True,
                "transcriptome_result_path": "/tmp/significant_de_genes.tsv",
                "pipeline_log_path": "/tmp/run.log",
            }
        )
        return {
            "status": "completed",
            "backend": "rule_fallback",
            "answer_markdown": "# 多组学育种分析结果\n\n分析流程已完成。",
            "frontend_payload": {
                "schema_version": "omics_frontend_payload.v1",
                "answer_markdown": "# 多组学育种分析结果\n\n分析流程已完成。",
                "summary": {"analysis_backend": "rule_fallback"},
            },
            "warnings": [],
        }

    fake_tool_module._run_omics_breeding_analysis_impl = fake_runner
    fake_tool_module.omics_breeding_analysis_run = SimpleNamespace(
        invoke=lambda payload: (_ for _ in ()).throw(AssertionError(f"unexpected fallback invoke: {payload}"))
    )
    monkeypatch.setitem(sys.modules, "yuxi.agents.toolkits.breeding.omics_analysis", fake_tool_module)

    chunks = []
    async for chunk in svc.stream_agent_chat(
        query="给出一些育种建议",
        agent_config_id=123,
        thread_id="thread-1",
        meta={
            "run_id": "run-1",
            "request_id": "req-1",
            "source": "breeding-workbench",
            "trait": "黄酮相关",
            "question": "给出一些育种建议",
            "preferred_tool": "omics_breeding_analysis_run",
            "breeding_context": {"data_dir": "/tmp/demo"},
        },
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    ):
        chunks.append(json.loads(chunk.decode("utf-8").strip()))

    direct_repo = next(repo for key, repo in repo_holder.items() if repo.tool_calls)
    progress_repos = [repo for repo in repo_holder.values() if repo is not direct_repo]
    assert chunks[-1]["status"] == "finished"
    assert len(progress_sessions.sessions) == 2
    assert len(progress_repos) == 2
    assert [repo.saved_messages[0]["extra_metadata"]["frontend_payload"]["summary"]["transcriptome_pipeline_status"] for repo in progress_repos] == [
        "running",
        "completed",
    ]
    assert all(repo.saved_messages[0]["extra_metadata"]["run_id"] == "run-1" for repo in progress_repos)
    assert all(repo.saved_messages[0]["extra_metadata"]["progress_snapshot"] is True for repo in progress_repos)


def test_buildin_package_remains_discoverable_after_chat_service_stub():
    import importlib.util

    spec = importlib.util.find_spec(
        "yuxi.agents.buildin.omics_breeding_analysis.literature_search"
    )

    assert spec is not None
    assert spec.loader is not None


@pytest.mark.asyncio
async def test_stream_agent_chat_emits_realtime_agent_state_from_values(monkeypatch: pytest.MonkeyPatch):
    class FakeGraph:
        async def aget_state(self, _config):
            return SimpleNamespace(values={"todos": [{"content": "done", "status": "completed"}]})

    class FakeAgent:
        async def stream_messages_with_state(self, messages, input_context=None, **kwargs):
            yield "values", {"messages": [], "todos": [{"content": "step 1", "status": "pending"}]}
            yield "values", {"messages": [], "todos": [{"content": "step 1", "status": "in_progress"}]}
            yield "values", {"messages": [], "todos": [{"content": "step 1", "status": "in_progress"}]}
            yield "messages", (AIMessageChunk(content="hello"), {"node": "llm"})

        async def stream_messages(self, messages, input_context=None, **kwargs):
            raise AssertionError("stream_messages fallback should not be used")

        async def get_graph(self):
            return FakeGraph()

    async def fake_get_agent_config_by_id(db, user, agent_config_id):
        return SimpleNamespace(agent_id="test-agent", config_json={"context": {}})

    async def fake_save_messages_from_langgraph_state(*, agent_instance, thread_id, conv_repo, config_dict, trace_info):
        return None

    async def fake_guard_check(_content):
        return False

    async def fake_guard_check_with_keywords(_content):
        return False

    async def fake_noop(*args, **kwargs):
        del args, kwargs
        return None

    async def fake_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
        if False:
            yield None
        return

    monkeypatch.setattr(svc.agent_manager, "get_agent", lambda agent_id: FakeAgent())
    monkeypatch.setattr(svc, "get_agent_config_by_id", fake_get_agent_config_by_id)
    monkeypatch.setattr(svc, "ConversationRepository", _FakeConvRepo)
    monkeypatch.setattr(svc, "_ensure_thread_bound_agent_config", fake_noop)
    monkeypatch.setattr(svc, "_load_workspace_agents_prompt", lambda _thread_id, _user_id: "")
    monkeypatch.setattr(svc, "save_messages_from_langgraph_state", fake_save_messages_from_langgraph_state)
    monkeypatch.setattr(svc.content_guard, "check", fake_guard_check)
    monkeypatch.setattr(svc.content_guard, "check_with_keywords", fake_guard_check_with_keywords)
    monkeypatch.setattr(svc, "check_and_handle_interrupts", fake_interrupts)
    monkeypatch.setattr(
        svc,
        "_build_langfuse_run_context",
        lambda **kwargs: SimpleNamespace(callbacks=[], metadata={}, tags=[], trace_id=None),
    )
    monkeypatch.setattr(svc, "get_trace_info", lambda _run_context: {})
    monkeypatch.setattr(svc, "flush_langfuse", lambda: None)

    chunks = []
    async for chunk in svc.stream_agent_chat(
        query="hello",
        agent_config_id=123,
        thread_id="thread-1",
        meta={"request_id": "req-1"},
        image_content=None,
        current_user=SimpleNamespace(id="user-1", department_id="dept-1"),
        db=object(),
    ):
        chunks.append(json.loads(chunk.decode("utf-8")))

    agent_state_chunks = [chunk for chunk in chunks if chunk.get("status") == "agent_state"]
    assert len(agent_state_chunks) == 3
    assert agent_state_chunks[0]["agent_state"]["todos"][0]["status"] == "pending"
    assert agent_state_chunks[1]["agent_state"]["todos"][0]["status"] == "in_progress"
    assert agent_state_chunks[2]["agent_state"]["todos"][0]["status"] == "completed"
