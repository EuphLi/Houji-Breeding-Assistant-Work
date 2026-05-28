"""Agent run service (run creation, polling stream, cancel)."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from yuxi.agents.buildin import agent_manager
from yuxi.repositories.agent_config_repository import AgentConfigRepository
from yuxi.repositories.agent_run_repository import TERMINAL_RUN_STATUSES, AgentRunRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.run_queue_service import (
    get_arq_pool,
    get_last_run_stream_seq,
    list_run_stream_events,
    normalize_after_seq,
    publish_cancel_signal,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.utils.datetime_utils import utc_now_naive
from yuxi.utils.logging_config import logger
"""
# /api/chat/runs 只负责创建异步任务并入队，不在这个函数里真正执行大模型或工具
# 也就是说：
# chat_router.py
#     只是路由入口
# agent_run_service.py
#     只是创建 run + 入队
# 真正执行 Agent / Tool 的地方
#     是 process_agent_run 对应的 worker
"""

SSE_HEARTBEAT_SECONDS = int(os.getenv("RUN_SSE_HEARTBEAT_SECONDS", "15"))
SSE_MAX_CONNECTION_MINUTES = int(os.getenv("RUN_SSE_MAX_CONNECTION_MINUTES", "30"))
SSE_POLL_INTERVAL_SECONDS = float(os.getenv("RUN_SSE_POLL_INTERVAL_SECONDS", "1.0"))


# 返回给前端信息，前端拿到 run_id 后继续轮询
def _build_run_response(run) -> dict:
    return {
        "run_id": run.id,
        "thread_id": run.thread_id,
        "status": run.status,
        "request_id": run.request_id,
        "stream_url": f"/api/chat/runs/{run.id}/events?after_seq=0",
    }


def _format_sse(data: dict, event: str | None = None) -> str:
    lines = []
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    lines.append("")
    return "\n".join(lines) + "\n"


"""
创建异步 Run
"""
async def create_agent_run_view(
    *,
    query: str,
    agent_config_id: int,
    thread_id: str,
    meta: dict,
    image_content: str | None,
    current_user_id: str,
    db: AsyncSession,
) -> dict:
    if not query:  # 检查 query 是否为空
        raise HTTPException(status_code=422, detail="query 不能为空")

    if not thread_id:  # 判空
        raise HTTPException(status_code=422, detail="thread_id 不能为空")

    # 根据 agent_config_id 找 AgentConfig
    config_repo = AgentConfigRepository(db)
    config_item = await config_repo.get_by_id(config_id=int(agent_config_id))
    if config_item is None:
        raise HTTPException(status_code=404, detail="配置不存在")

    # 从 config 中拿到 agent_id
    agent_id = config_item.agent_id
    if not agent_manager.get_agent(agent_id):  # 检查 agent 是否存在
        raise HTTPException(status_code=404, detail=f"智能体 {agent_id} 不存在")

    # 检查 thread 是否属于当前用户
    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation or conversation.user_id != str(current_user_id) or conversation.status == "deleted":
        raise HTTPException(status_code=404, detail="对话线程不存在")
    if (conversation.extra_metadata or {}).get("agent_config_id") != int(agent_config_id):
        conversation = await conv_repo.bind_agent_config(thread_id, agent_config_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="对话线程不存在")

    # 创建 request_id
    request_id = str((meta or {}).get("request_id") or uuid.uuid4())
    config = {
        "thread_id": thread_id,
        "agent_config_id": int(agent_config_id),
    }
    run_repo = AgentRunRepository(db)
    existing = await run_repo.get_run_by_request_id(request_id)
    if existing and existing.user_id == str(current_user_id):
        return _build_run_response(existing)
    if existing and existing.user_id != str(current_user_id):
        raise HTTPException(status_code=409, detail="request_id 冲突")

    # 创建 run_id
    run_id = str(uuid.uuid4())

    # 创建 input_payload
    # [breeding-workbench meta propagation] 原逻辑保留供学习对照：
    # 原逻辑只保存 query/config 等通用字段，worker 侧无法恢复前端传入的
    # allowed_tools / preferred_tool / breeding_context / source / trait。
    # old:
    # input_payload = {
    #     "query": query,
    #     "config": config or {},
    #     "image_content": image_content,
    #     "agent_id": agent_id,
    #     "thread_id": thread_id,
    #     "user_id": str(current_user_id),
    #     "request_id": request_id,
    #     "created_at": utc_now_naive().isoformat(),
    # }
    # 新逻辑：把完整 meta 一起写入 run.input_payload，供异步 worker 恢复育种工作台结构化上下文。
    # 这一步只解决 meta 传递保真，不代表 allowed_tools 已在执行层成为硬约束。
    input_payload = {
        "query": query,
        "config": config or {},
        "meta": meta or {},
        "image_content": image_content,
        "agent_id": agent_id,
        "thread_id": thread_id,
        "user_id": str(current_user_id),
        "request_id": request_id,
        "created_at": utc_now_naive().isoformat(),
    }
    try:  # 写入 AgentRun
        run = await run_repo.create_run(
            run_id=run_id,
            thread_id=thread_id,
            agent_id=agent_id,
            user_id=str(current_user_id),
            request_id=request_id,
            input_payload=input_payload,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        existing = await run_repo.get_run_by_request_id(request_id)
        if existing and existing.user_id == str(current_user_id):
            return _build_run_response(existing)
        raise HTTPException(status_code=409, detail="request_id 冲突")

    logger.info(
        "Created agent run: "
        f"run_id={run.id} thread_id={thread_id} agent_id={agent_id} "
        f"agent_config_id={agent_config_id} source={(meta or {}).get('source') or ''} "
        f"preferred_tool={(meta or {}).get('preferred_tool') or ''} "
        f"allowed_tools={(meta or {}).get('allowed_tools') or []}"
    )

    # 入队 process_agent_run
    queue = await get_arq_pool()
    # /api/chat/runs 只负责创建异步任务并入队，不在这个函数里真正执行大模型或工具
    # 也就是说：
    # chat_router.py
    #     只是路由入口
    # agent_run_service.py
    #     只是创建 run + 入队
    # 真正执行 Agent / Tool 的地方
    #     是 process_agent_run 对应的 worker
    await queue.enqueue_job("process_agent_run", run.id, _job_id=f"run:{run.id}")
    logger.info(f"Enqueued agent run job: queue=arq job_id=run:{run.id} run_id={run.id} thread_id={thread_id}")

    return _build_run_response(run)


# 负责查状态
async def get_agent_run_view(*, run_id: str, current_user_id: str, db: AsyncSession) -> dict:
    repo = AgentRunRepository(db)
    run = await repo.get_run_for_user(run_id, str(current_user_id))
    if not run:
        raise HTTPException(status_code=404, detail="运行任务不存在")
    return {"run": run.to_dict()}


# 负责请求取消
async def cancel_agent_run_view(*, run_id: str, current_user_id: str, db: AsyncSession) -> dict:
    repo = AgentRunRepository(db)
    run = await repo.get_run_for_user(run_id, str(current_user_id))
    if not run:
        raise HTTPException(status_code=404, detail="运行任务不存在")

    run = await repo.request_cancel(run_id)
    await publish_cancel_signal(run_id)
    return {"run": run.to_dict() if run else None}


# TODO：实现 SSE 的实时进度展示，未来需优化实现
async def stream_agent_run_events(
    *,
    run_id: str,
    after_seq: str | int,
    current_user_id: str,
) -> AsyncIterator[str]:
    started_at = utc_now_naive()
    last_heartbeat_ts = started_at

    last_seq = normalize_after_seq(after_seq)

    try:
        while True:
            try:
                async with pg_manager.get_async_session_context() as db:
                    repo = AgentRunRepository(db)
                    run = await repo.get_run_for_user(run_id, str(current_user_id))
                    if not run:
                        yield _format_sse({"run_id": run_id, "message": "运行任务不存在"}, event="error")
                        yield _format_sse({"run_id": run_id, "last_seq": last_seq}, event="close")
                        return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning(f"Run SSE DB error for run {run_id}: {e}")
                yield _format_sse(
                    {
                        "run_id": run_id,
                        "message": "运行事件流暂时不可用，请重连",
                        "reason": "db_error",
                    },
                    event="error",
                )
                yield _format_sse({"run_id": run_id, "last_seq": last_seq}, event="close")
                return

            try:
                events = await list_run_stream_events(run_id, after_seq=last_seq, limit=200)
            except Exception as e:
                logger.warning(f"Run SSE redis error for run {run_id}: {e}")
                yield _format_sse(
                    {
                        "run_id": run_id,
                        "message": "运行事件流暂时不可用，请重连",
                        "reason": "redis_error",
                    },
                    event="error",
                )
                yield _format_sse({"run_id": run_id, "last_seq": last_seq}, event="close")
                return

            for event in events:
                seq = str(event.get("seq") or "0-0")
                last_seq = seq

                yield _format_sse(
                    {
                        "run_id": run_id,
                        "seq": seq,
                        "event_type": event.get("event_type") or "message",
                        "payload": event.get("payload") or {},
                        "ts": event.get("ts"),
                    },
                    event=event.get("event_type") or "message",
                )

            if run.status in TERMINAL_RUN_STATUSES and not events:
                terminal_seq = last_seq
                if terminal_seq in {"", "0", "0-0"}:
                    terminal_seq = await get_last_run_stream_seq(run_id)

                yield _format_sse(
                    {"run_id": run_id, "status": run.status, "last_seq": terminal_seq},
                    event="close",
                )
                return

            now = utc_now_naive()
            elapsed_seconds = (now - started_at).total_seconds()
            heartbeat_elapsed = (now - last_heartbeat_ts).total_seconds()
            if heartbeat_elapsed >= SSE_HEARTBEAT_SECONDS:
                yield _format_sse({"run_id": run_id, "last_seq": last_seq}, event="heartbeat")
                last_heartbeat_ts = now

            if elapsed_seconds >= SSE_MAX_CONNECTION_MINUTES * 60:
                yield _format_sse({"run_id": run_id, "last_seq": last_seq}, event="close")
                return

            await asyncio.sleep(SSE_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        return


async def get_active_run_by_thread(*, thread_id: str, current_user_id: str, db: AsyncSession) -> dict:
    from sqlalchemy import select
    from yuxi.storage.postgres.models_business import AgentRun

    result = await db.execute(
        select(AgentRun)
        .where(
            AgentRun.thread_id == thread_id,
            AgentRun.user_id == str(current_user_id),
            AgentRun.status.notin_(list(TERMINAL_RUN_STATUSES)),
        )
        .order_by(AgentRun.created_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    return {"run": run.to_dict() if run else None}
