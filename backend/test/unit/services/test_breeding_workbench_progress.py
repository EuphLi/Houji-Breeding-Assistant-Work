from __future__ import annotations

import importlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest


def _load_chat_service_module():
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

    _install_stub("yuxi.agents.backends", attributes={"__path__": []})
    _install_stub("yuxi.agents.backends.sandbox", attributes={"__path__": []})
    _install_stub(
        "yuxi.agents.backends.sandbox.paths",
        attributes={"sandbox_workspace_agents_prompt_file": lambda _thread_id, _user_id: Path("/tmp/nonexistent")},
    )
    _install_stub(
        "yuxi.agents.buildin",
        attributes={
            "agent_manager": SimpleNamespace(get_agent=lambda _agent_id: None),
            "__path__": [str(Path(__file__).resolve().parents[3] / "package" / "yuxi" / "agents" / "buildin")],
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
    _install_stub("yuxi.storage.postgres.manager", attributes={"pg_manager": SimpleNamespace()})
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
    created: list["_FakeConvRepo"] = []

    def __init__(self, _db):
        self.saved_messages: list[dict] = []
        _FakeConvRepo.created.append(self)

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


class _FakePgManager:
    def __init__(self):
        self.session_opened = 0
        self.session_closed = 0

    @asynccontextmanager
    async def get_async_session_context(self):
        self.session_opened += 1
        try:
            yield object()
        finally:
            self.session_closed += 1


@pytest.mark.asyncio
async def test_save_direct_breeding_workbench_progress_message_persists_with_run_context(monkeypatch):
    _FakeConvRepo.created.clear()
    fake_pg = _FakePgManager()
    monkeypatch.setattr(svc, "ConversationRepository", _FakeConvRepo)
    monkeypatch.setattr(svc, "pg_manager", fake_pg)

    await svc._save_direct_breeding_workbench_progress_message(
        thread_id="thread-1",
        run_id="run-1",
        request_id="req-1",
        progress_summary={
            "transcriptome_pipeline_status": "completed",
            "transcriptome_path_exists": True,
            "transcriptome_result_path": "/tmp/significant_de_genes.tsv",
            "pipeline_log_path": "/tmp/run.log",
        },
    )

    assert fake_pg.session_opened == 1
    assert fake_pg.session_closed == 1
    assert len(_FakeConvRepo.created) == 1
    saved = _FakeConvRepo.created[0].saved_messages[0]
    assert saved["thread_id"] == "thread-1"
    assert saved["extra_metadata"]["request_id"] == "req-1"
    assert saved["extra_metadata"]["run_id"] == "run-1"
    assert saved["extra_metadata"]["source"] == "breeding-workbench"
    assert saved["extra_metadata"]["progress_snapshot"] is True
    payload = saved["extra_metadata"]["frontend_payload"]
    assert payload["run_id"] == "run-1"
    assert payload["request_id"] == "req-1"
    assert payload["summary"]["transcriptome_pipeline_status"] == "completed"
