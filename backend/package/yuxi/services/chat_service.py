import asyncio
import json
import traceback
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.types import Command
from yuxi import config as conf
from yuxi.agents.backends.sandbox.paths import sandbox_workspace_agents_prompt_file
from yuxi.agents.buildin import agent_manager
from yuxi.agents.state import AgentStatePayload
from yuxi.plugins.guard import content_guard
from yuxi.repositories.agent_config_repository import AgentConfigRepository
from yuxi.repositories.conversation_repository import ConversationRepository
from yuxi.services.langfuse_service import (
    LangfuseRunContext,
    build_run_context,
    flush_langfuse,
    get_trace_info,
)
from yuxi.storage.postgres.manager import pg_manager
from yuxi.storage.postgres.models_business import User
from yuxi.utils.logging_config import logger
from yuxi.utils.question_utils import (
    normalize_options as _normalize_interrupt_options,
)
from yuxi.utils.question_utils import (
    normalize_questions as _normalize_interrupt_questions,
)

# direct route 的基础配置
WORKSPACE_AGENTS_PROMPT_MAX_BYTES = 64 * 1024
BREEDING_WORKBENCH_SOURCE = "breeding-workbench"
BREEDING_WORKBENCH_DIRECT_TOOL = "omics_breeding_analysis_run"
DEFAULT_BREEDING_DATA_DIR = (
    "/mnt/yuxi-breeding-data/smoke_test_minimal/Si9g037800_smoke_test_minimal"
)


"""
后端服务层 / Chat Run 创建层 / run meta 写入层 / worker 上游
是 YuXi 框架中的聊天服务入口。它负责把前端提交的问题、上下文、metadata 等写入后端运行任务。

它在数据流中的位置：相当于前后端中转站
前端提交请求
  ↓
chat_service.py
  ↓
创建 run / 写入 run meta
  ↓
worker 后续读取任务
如果这里没有把 breeding_context 写入 run meta，那么 worker 后面就拿不到用户上传路径。
"""
# 前端 createAgentRun
#   meta.source = breeding-workbench
#   meta.preferred_tool = omics_breeding_analysis_run
#   meta.trait = 用户性状
#   meta.question = 用户问题
#   meta.breeding_context = 表单上下文
#         ↓
# run_worker.py 调用 stream_agent_chat()
#         ↓
# stream_agent_chat()
#   补齐 meta.query / agent_id / thread_id / user_id
#         ↓
# _is_direct_breeding_workbench_tool_run(meta)
#         ↓ true
# _build_direct_breeding_tool_input()
#         ↓
# omics_breeding_analysis_run.invoke({"input": tool_input})
#         ↓
# _save_direct_breeding_workbench_tool_messages()
#         ↓
# yield finished(frontend_payload, answer_markdown)
#         ↓
# 前端轮询 history
#         ↓
# buildRunSnapshot()
#         ↓
# 页面展示结果

def _load_workspace_agents_prompt(thread_id: str, user_id: str) -> str:
    prompt_file = sandbox_workspace_agents_prompt_file(thread_id, user_id)
    try:
        with prompt_file.open("rb") as buffer:
            content = buffer.read(WORKSPACE_AGENTS_PROMPT_MAX_BYTES + 1)
    except FileNotFoundError:
        return ""
    except IsADirectoryError:
        logger.warning("读取工作区 AGENTS.md 失败: 路径是目录")
        return ""
    except OSError as exc:
        logger.warning(f"读取工作区 AGENTS.md 失败: {exc}")
        return ""

    prompt = content[:WORKSPACE_AGENTS_PROMPT_MAX_BYTES].decode("utf-8", errors="replace").strip()
    if not prompt:
        return ""
    if len(content) > WORKSPACE_AGENTS_PROMPT_MAX_BYTES:
        return f"{prompt}\n\n[AGENTS.md 内容已截断]"
    return prompt


# direct route 的判断函数，判断当前 Run 是否应该走育种工作台直达工具链路
def _is_direct_breeding_workbench_tool_run(meta: dict[str, Any]) -> bool:
    # 只有同时满足：meta.source == "breeding-workbench"
    # meta.preferred_tool == "omics_breeding_analysis_run" 才返回 True。
    # 这里是前后端衔接的关键点
    return (
        str(meta.get("source") or "").strip() == BREEDING_WORKBENCH_SOURCE
        and str(meta.get("preferred_tool") or "").strip() == BREEDING_WORKBENCH_DIRECT_TOOL
    )


# 路径解析函数，负责把前端传来的路径字段转成后端工具可用路径
def _resolve_direct_input_path(
    explicit_path: Any,
    *,
    data_dir: str,
    default_filename: str,
) -> str:
    value = str(explicit_path or "").strip()
    if not value:
        return f"{data_dir}/{default_filename}".strip()
    if "/" in value:
        return value
    return f"{data_dir}/{value}".strip()


def _first_existing_path(candidates: list[str]) -> str:
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if normalized and Path(normalized).is_file():
            return normalized
    return ""


def _resolve_direct_transcriptome_result_path(
    explicit_path: Any,
    *,
    data_dir: str,
) -> str:
    transcriptome_output_dir = f"{data_dir}/transcriptome_deg"
    resolved_explicit_path = _resolve_direct_input_path(
        explicit_path,
        data_dir=data_dir,
        default_filename="transcriptome_deg/significant_de_genes.tsv",
    )
    existing_path = _first_existing_path(
        [
            resolved_explicit_path,
            f"{transcriptome_output_dir}/significant_de_genes.tsv",
            f"{transcriptome_output_dir}/de_pipeline_out/04_de/significant_de_genes.tsv",
        ]
    )
    return existing_path or resolved_explicit_path


# 工具输入构造，是 direct route 的核心 helper。
# 把前端 meta 和 breeding_context 转成 omics_breeding_analysis_run 的输入tool_input
# 文件存在性由后续 evidence_adapters/workflow 判断。
def _build_direct_breeding_tool_input(
    *,
    query: str,
    thread_id: str,
    meta: dict[str, Any],
    agent_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # 从 meta.breeding_context 里拿页面传来的上下文。如果没有，就用默认 smoke 数据目录
    context = meta.get("breeding_context") or {}
    data_dir = str(
        context.get("upload_root") or context.get("data_dir") or DEFAULT_BREEDING_DATA_DIR
    ).strip()
    # 构造输出目录
    output_dir = str(
        context.get("output_dir") or f"/tmp/yuxi_runs/omics_breeding_analysis/{thread_id}"
    ).strip()
    # 构造转录组路径
    transcriptome_result_path = _resolve_direct_transcriptome_result_path(
        context.get("transcriptome_result_path"),
        data_dir=data_dir,
    )
    # 构造代谢组路径
    metabolome_path = _resolve_direct_input_path(
        context.get("metabolome_path") or context.get("metabolome_tsv"),
        data_dir=data_dir,
        default_filename="metabolome_raw_3372.tsv",
    )
    model_name = str(
        context.get("model") or (agent_config or {}).get("model") or ""
    ).strip()
    rnaseq_read_paths = context.get("rnaseq_read_paths") or []
    if isinstance(rnaseq_read_paths, str):
        rnaseq_read_paths = [item.strip() for item in rnaseq_read_paths.split(",") if item.strip()]
    normalized_upload_root = str(context.get("upload_root") or context.get("data_dir") or "").strip()

    # 返回工具输入
    return {
        "trait": str(meta.get("trait") or "").strip(),
        "question": str(meta.get("question") or query).strip(),
        "transcriptome_result_path": transcriptome_result_path,
        "metabolome_path": metabolome_path,
        "reference_genome_path": _resolve_direct_input_path(
            context.get("reference_genome_path") or context.get("reference_genome"),
            data_dir=data_dir,
            default_filename="genome.fa",
        ),
        "genome_gff_path": _resolve_direct_input_path(
            context.get("genome_gff_path") or context.get("genome_gff"),
            data_dir=data_dir,
            default_filename="genome.gff",
        ),
        "annotation_path": _resolve_direct_input_path(
            context.get("annotation_path") or context.get("function_annotation"),
            data_dir=data_dir,
            default_filename="xiaomi_T2T_Annotation.smoke_genes.txt",
        ),
        "sample_map_path": _resolve_direct_input_path(
            context.get("sample_map_path") or context.get("sample_map"),
            data_dir=data_dir,
            default_filename="sampleName_clientId.txt",
        ),
        "rnaseq_read_paths": [
            _resolve_direct_input_path(path, data_dir=data_dir, default_filename="")
            for path in rnaseq_read_paths
            if str(path or "").strip()
        ],
        "upload_root": normalized_upload_root,
        "uploaded_file_count": int(context.get("uploaded_file_count") or 0),
        "literature_evidence_path": _resolve_direct_input_path(
            context.get("literature_evidence_path"),
            data_dir=data_dir,
            default_filename="verified_literature_evidence.tsv",
        ),
        "evidence_pack_output_path": str(
            context.get("evidence_pack_output_path")
            or (
                f"{normalized_upload_root}/omics_evidence_pack.json"
                if normalized_upload_root
                else f"{output_dir}/omics_evidence_pack.json"
            )
        ).strip(),
        "output_dir": output_dir,
        "use_llamaindex": bool(context.get("use_llamaindex", True)),
        "model": model_name,
    }


# 这个函数的本质是：把一次直接执行工具的结果，手动补成 YuXi 前端能识别的标准对话历史。只负责保存结果
# 将 direct route 的工具执行结果写入 YuXi Thread History。没有经过 LangGraph 的标准 tool call 流程，
# 因此这里手动补齐一套前端可识别的消息链：
# 1. user message
# 2. assistant message with tool_calls
# 3. tool_call 数据库记录
# 4. tool role message with frontend_payload
# 5. assistant final message with answer_markdown
# 这样前端 getAgentHistory() 后，仍能解析：
# - 工具调用链 omics_breeding_analysis_run
# - frontend_payload
# - answer_markdown
# - 当前 request_id 对应的结果
async def _save_direct_breeding_workbench_tool_messages(
    *,
    conv_repo: ConversationRepository, # 数据库会话消息仓库，用来写入 thread history 和 tool call 记录
    thread_id: str, # 当前前端创建的对话线程 ID
    query: str, # 前端构造出来的任务说明文本
    request_id: str, # 当前这一次运行的唯一标识，用来防止前端混用旧结果
    tool_input: dict[str, Any], # 传给 omics_breeding_analysis_run 的真实工具入参
    tool_result: dict[str, Any], # omics_breeding_analysis_run 返回的完整结果
) -> None:
    # 保存 user message，把用户问题保存成 thread history 里的 user 消息
    user_content = str(tool_input.get("question") or query)
    await conv_repo.add_message_by_thread_id(
        thread_id=thread_id,
        role="user",
        content=user_content,
        message_type="text",
        extra_metadata={
            "request_id": request_id,
            "source": BREEDING_WORKBENCH_SOURCE,
            "tool_execution_mode": "direct_preferred_tool",
            "raw_message": {"type": "human", "content": user_content},
        },
    )

    # 保存 assistant tool_call message
    tool_call_id = f"direct-{request_id}"
    assistant_message = await conv_repo.add_message_by_thread_id(
        thread_id=thread_id,
        role="assistant",
        content="",
        message_type="text",
        extra_metadata={
            "request_id": request_id,
            "tool_execution_mode": "direct_preferred_tool",
            "tool_calls": [
                {
                    # 就是前端后来能显示：工具调用链：多组学育种分析 的原因之一
                    "name": BREEDING_WORKBENCH_DIRECT_TOOL,
                    "args": tool_input,
                    "id": tool_call_id,
                }
            ],
        },
    )

    # 登记 tool_call 表记录 在数据库中登记
    if assistant_message:
        await conv_repo.add_tool_call(
            message_id=assistant_message.id,
            tool_name=BREEDING_WORKBENCH_DIRECT_TOOL,
            tool_input=tool_input,
            status="pending",
            langgraph_tool_call_id=tool_call_id,
        )

    # 更新 tool_call 输出
    tool_output = json.dumps(tool_result, ensure_ascii=False) # 把工具返回的完整 dict 转成 JSON 字符串，并保留中文不转义
    await conv_repo.update_tool_call_output(
        langgraph_tool_call_id=tool_call_id,
        tool_output=tool_output,
        status="success" if tool_result.get("status") != "error" else "error",
        error_message=tool_result.get("error") or None,
    )
    # 保存 role=tool 的消息，保存的是真正的工具输出消息
    await conv_repo.add_message_by_thread_id(
        thread_id=thread_id,
        role="tool",
        content=tool_output,
        message_type="text",
        extra_metadata={
            "request_id": request_id,
            "tool_name": BREEDING_WORKBENCH_DIRECT_TOOL,
            "tool_call_id": tool_call_id,
            # 前端 extractFrontendPayloadFromHistory() 能从 history 里找到 frontend_payload 的原因
            "frontend_payload": tool_result.get("frontend_payload") or {},
        },
    )

    # 保存 assistant final message 即最终回答
    answer_markdown = str(tool_result.get("answer_markdown") or "").strip()
    if answer_markdown:
        await conv_repo.add_message_by_thread_id(
            thread_id=thread_id,
            role="assistant",
            # 前端 Markdown 正文来自这里
            content=answer_markdown,
            message_type="text",
            extra_metadata={
                "request_id": request_id,
                "tool_execution_mode": "direct_preferred_tool",
                "tool_name": BREEDING_WORKBENCH_DIRECT_TOOL,
                "frontend_payload": tool_result.get("frontend_payload") or {},
            },
        )


async def _save_direct_breeding_workbench_progress_message(
    *,
    thread_id: str,
    run_id: str,
    request_id: str,
    progress_summary: dict[str, Any],
) -> None:
    frontend_payload = {
        "schema_version": "omics_frontend_payload.v1",
        "source": BREEDING_WORKBENCH_SOURCE,
        "run_id": run_id,
        "request_id": request_id,
        "summary": progress_summary,
    }
    async with pg_manager.get_async_session_context() as progress_db:
        progress_repo = ConversationRepository(progress_db)
        await progress_repo.add_message_by_thread_id(
            thread_id=thread_id,
            role="assistant",
            content="",
            message_type="text",
            extra_metadata={
                "request_id": request_id,
                "run_id": run_id,
                "source": BREEDING_WORKBENCH_SOURCE,
                "tool_execution_mode": "direct_preferred_tool",
                "tool_name": BREEDING_WORKBENCH_DIRECT_TOOL,
                "frontend_payload": frontend_payload,
                "progress_snapshot": True,
            },
        )


"""
构造 Agent 运行上下文的函数
两种方式:
1. 通过前端 query 写进去；
2. 在后端把 meta.breeding_context 合并到 input_context。

AgentConfig 表中的 config_json.context
    ↓
_build_agent_input_context()
    ↓
input_context
    ↓
Agent 执行

"""
async def _build_agent_input_context(agent_config: dict, *, thread_id: str, user_id: str) -> dict:
    # 复制 AgentConfig 中的 context    agent_config 来自于 stream_agent_chat()
    input_context = dict(agent_config or {})

    # 如果工作区有 AGENTS.md，就把它追加到 system_prompt
    agents_prompt = await asyncio.to_thread(_load_workspace_agents_prompt, thread_id, user_id)

    if agents_prompt:
        agents_section = f"用户工作区 agents/AGENTS.md 内容：\n{agents_prompt}"
        base_prompt = str(input_context.get("system_prompt") or "").rstrip()
        input_context["system_prompt"] = f"{base_prompt}\n\n{agents_section}" if base_prompt else agents_section

    # 加入 user_id 和 thread_id
    input_context.update({"user_id": user_id, "thread_id": thread_id})
    return input_context


def _build_state_files(attachments: list[dict]) -> dict:
    """将附件列表转换为 StateBackend 格式的 files 字典

    StateBackend 期望的格式:
    {
        "/attachments/file.md": {
            "content": ["line1", "line2", ...],
            "created_at": "...",
            "modified_at": "...",
        }
    }
    """
    files = {}
    for attachment in attachments:
        if attachment.get("status") != "parsed":
            continue

        file_path = attachment.get("file_path")
        markdown = attachment.get("markdown")

        if not file_path or not markdown:
            continue

        now = datetime.now(UTC).isoformat()
        # 将 markdown 内容按行拆分
        content_lines = markdown.split("\n")
        files[file_path] = {
            "content": content_lines,
            "created_at": attachment.get("uploaded_at", now),
            "modified_at": attachment.get("uploaded_at", now),
        }

    return files


async def _get_langgraph_messages(agent_instance, config_dict):
    graph = await agent_instance.get_graph()
    state = await graph.aget_state(config_dict)

    if not state or not state.values:
        logger.warning("No state found in LangGraph")
        return None

    return state.values.get("messages", [])


def _build_langfuse_run_context(
    *,
    current_user,
    thread_id: str,
    agent_id: str,
    request_id: str,
    operation: str,
    agent_config_id: int | None = None,
    message_type: str | None = None,
) -> LangfuseRunContext:
    return build_run_context(
        user_id=str(current_user.id),
        thread_id=thread_id,
        agent_id=agent_id,
        request_id=request_id,
        operation=operation,
        agent_config_id=agent_config_id,
        message_type=message_type,
        username=getattr(current_user, "username", None),
        login_user_id=getattr(current_user, "user_id", None),
        department_id=getattr(current_user, "department_id", None),
    )


def extract_agent_state(values: dict) -> AgentStatePayload:
    """从 LangGraph state 中提取 agent 状态"""
    if not isinstance(values, dict):
        return {"todos": [], "files": {}, "artifacts": []}

    # 直接获取，信任 state 的数据结构
    todos = values.get("todos")
    artifacts = values.get("artifacts")
    result: AgentStatePayload = {
        "todos": list(todos)[:20] if todos else [],
        "files": values.get("files") or {},
        "artifacts": list(artifacts) if artifacts else [],
    }

    return result


def _agent_state_signature(agent_state: AgentStatePayload | dict | None) -> str:
    if not agent_state:
        return ""
    try:
        return json.dumps(agent_state, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(agent_state)


# Agent 流式执行适配器,兼容两种 Agent 实现。
# 第一种 支持 stream_messages_with_state()，返回 messages、values（常用表示LangGraph state，例如 todos、files、artifacts）
# 第二种 只支持 stream_messages()，只返回信息流
# 代码会统一包装成：mode, payload
# 这样 stream_agent_chat() 就不用关心具体 Agent 类型
# _stream_agent_events() 是 chat_service.py 和具体 Agent 实现之间的桥。
async def _stream_agent_events(agent, messages, *, input_context=None, **kwargs):
    if hasattr(agent, "stream_messages_with_state"):
        async for mode, payload in agent.stream_messages_with_state(
            messages,
            input_context=input_context,
            **kwargs,
        ):
            yield mode, payload
        return

    async for msg, metadata in agent.stream_messages(messages, input_context=input_context, **kwargs):
        yield "messages", (msg, metadata)


async def _get_existing_message_ids(conv_repo: ConversationRepository, thread_id: str) -> set[str]:
    existing_messages = await conv_repo.get_messages_by_thread_id(thread_id)
    return {
        msg.extra_metadata["id"]
        for msg in existing_messages
        if msg.extra_metadata and "id" in msg.extra_metadata and isinstance(msg.extra_metadata["id"], str)
    }


"""
保存 assistant 消息，并登记 tool call 的函数
1. assistant 的自然语言内容；
2. assistant 发起的 tool_calls。
如果模型决定调用：smoke_flavonoid_breeding_advice
那么 AIMessage 里可能会出现：
{
  "tool_calls": [
    {
      "name": "smoke_flavonoid_breeding_advice",
      "args": {...},
      "id": "call_xxx"
    }
  ]
}
_save_ai_message() 会把这个 tool call 登记到数据库。
前端之后可以通过 history/tool_calls 展示：Agent 调用了哪个工具、传入参数是什么

但是注意：
_save_ai_message() 只登记“准备调用工具”；
真正工具输出由 _save_tool_message() 更新。
"""
async def _save_ai_message(
    conv_repo: ConversationRepository,
    thread_id: str,
    msg_dict: dict,
    trace_info: dict[str, Any] | None = None,
) -> None:
    content = msg_dict.get("content", "")
    tool_calls_data = msg_dict.get("tool_calls", [])
    extra_metadata = dict(msg_dict)
    if trace_info:
        extra_metadata.update(trace_info)

    ai_msg = await conv_repo.add_message_by_thread_id(
        thread_id=thread_id,
        role="assistant",
        content=content,
        message_type="text",
        extra_metadata=extra_metadata,
    )

    if ai_msg and tool_calls_data:
        for tc in tool_calls_data:
            await conv_repo.add_tool_call(
                message_id=ai_msg.id,
                tool_name=tc.get("name", "unknown"),
                tool_input=tc.get("args", {}),
                status="pending",
                langgraph_tool_call_id=tc.get("id"),
            )


"""
保存工具执行结果的函数
找到之前 pending 的 tool_call，把工具输出写进去，并把状态改成 success。

如果工具：smoke_flavonoid_breeding_advice
返回了：Si9g037800、黄酮、群体、DOI引用原句、验证计划
那么这些内容会作为 tool message 的 content 进入 LangGraph state。
_save_tool_message() 会把它保存为 tool call output。
这样前端就有可能展示：
工具调用、工具结果、真实 tool 输出
"""
async def _save_tool_message(conv_repo: ConversationRepository, msg_dict: dict) -> None:
    tool_call_id = msg_dict.get("tool_call_id")
    content = msg_dict.get("content", "")

    if not tool_call_id:
        return

    if isinstance(content, list):
        tool_output = json.dumps(content) if content else ""
    else:
        tool_output = str(content)

    await conv_repo.update_tool_call_output(
        langgraph_tool_call_id=tool_call_id,
        tool_output=tool_output,
        status="success",
    )


async def save_partial_message(
    conv_repo: ConversationRepository,
    thread_id: str,
    full_msg=None,
    error_message: str | None = None,
    error_type: str = "interrupted",
    trace_info: dict[str, Any] | None = None,
):
    try:
        extra_metadata = {
            "error_type": error_type,
            "is_error": True,
            "error_message": error_message or f"发生错误: {error_type}",
        }
        if full_msg:
            msg_dict = full_msg.model_dump() if hasattr(full_msg, "model_dump") else {}
            content = full_msg.content if hasattr(full_msg, "content") else str(full_msg)
            extra_metadata = msg_dict | extra_metadata
        else:
            content = ""

        if trace_info:
            extra_metadata.update(trace_info)

        return await conv_repo.add_message_by_thread_id(
            thread_id=thread_id,
            role="assistant",
            content=content,
            message_type="text",
            extra_metadata=extra_metadata,
        )

    except Exception as e:
        logger.error(f"Error saving message: {e}")
        logger.error(traceback.format_exc())
        return None


"""
把 LangGraph state 中的消息保存到数据库 history 的函数
前端最终展示依赖：GET /api/chat/thread/{thread_id}/history
前端看不到 LangGraph 内存里的 state，它只能看到数据库中的 history。
此函数就是把：
Agent / LangGraph 内部消息 落地成：Thread History
这也是为什么 stream_agent_chat() 在 yield finished 前要先调用它。
"""
async def save_messages_from_langgraph_state(
    agent_instance,
    thread_id: str,
    conv_repo: ConversationRepository,
    config_dict: dict,
    trace_info: dict[str, Any] | None = None,
) -> None:
    # 从 LangGraph state 取出 messages
    messages = await _get_langgraph_messages(agent_instance, config_dict)
    if messages is None:
        return

    #查数据库里已有消息 id，避免重复保存
    existing_ids = await _get_existing_message_ids(conv_repo, thread_id)

    for msg in messages:
        msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else {}
        msg_type = msg_dict.get("type", "unknown")

        # 跳过 human 消息
        if msg_type == "human" or getattr(msg, "id", None) in existing_ids:
            continue

        # ai 消息交给 _save_ai_message()
        if msg_type == "ai":
            await _save_ai_message(conv_repo, thread_id, msg_dict, trace_info=trace_info)
        # tool 消息交给 _save_tool_message()
        elif msg_type == "tool":
            await _save_tool_message(conv_repo, msg_dict)


def _extract_interrupt_info(state) -> Any | None:
    """从 LangGraph state 中提取中断信息"""
    if hasattr(state, "tasks") and state.tasks:
        for task in state.tasks:
            if hasattr(task, "interrupts") and task.interrupts:
                return task.interrupts[0]

    interrupt_data = state.values.get("__interrupt__")
    if isinstance(interrupt_data, list) and interrupt_data:
        return interrupt_data[0]

    return None


def _coerce_interrupt_payload(info: Any) -> dict:
    """将 LangGraph interrupt 对象转换为 dict 结构。"""
    if isinstance(info, dict):
        return info

    payload = getattr(info, "value", None)
    if isinstance(payload, dict):
        return payload

    questions = getattr(info, "questions", None)
    question = getattr(info, "question", None)
    question_id = getattr(info, "question_id", None)
    options = getattr(info, "options", None)
    multi_select = getattr(info, "multi_select", None)
    allow_other = getattr(info, "allow_other", None)
    operation = getattr(info, "operation", None)
    source = getattr(info, "source", None)
    result: dict[str, Any] = {}
    if isinstance(questions, list):
        result["questions"] = questions
    if isinstance(question, str) and question.strip():
        result["question"] = question
    if isinstance(question_id, str) and question_id.strip():
        result["question_id"] = question_id
    if isinstance(options, list):
        result["options"] = options
    if isinstance(multi_select, bool):
        result["multi_select"] = multi_select
    if isinstance(allow_other, bool):
        result["allow_other"] = allow_other
    if isinstance(operation, str) and operation.strip():
        result["operation"] = operation
    if isinstance(source, str) and source.strip():
        result["source"] = source
    return result


def _build_ask_user_question_payload(info: Any, thread_id: str) -> dict[str, Any]:
    """将 interrupt 信息标准化为 ask_user_question_required 载荷。"""
    payload = _coerce_interrupt_payload(info)

    questions = _normalize_interrupt_questions(payload.get("questions"))
    if not questions:
        legacy_question = str(payload.get("question") or "").strip()
        if legacy_question:
            legacy_item: dict[str, Any] = {
                "question_id": str(payload.get("question_id") or uuid.uuid4()),
                "question": legacy_question,
                "options": _normalize_interrupt_options(payload.get("options")),
                "multi_select": bool(payload.get("multi_select", False)),
                "allow_other": bool(payload.get("allow_other", True)),
            }
            legacy_operation = payload.get("operation")
            if isinstance(legacy_operation, str) and legacy_operation.strip():
                legacy_item["operation"] = legacy_operation.strip()
            questions = [legacy_item]

    if not questions:
        questions = [
            {
                "question_id": str(uuid.uuid4()),
                "question": "请选择一个选项",
                "options": [],
                "multi_select": False,
                "allow_other": True,
            }
        ]

    source = str(payload.get("source") or payload.get("tool_name") or "interrupt")

    return {
        "questions": questions,
        "source": source,
        "thread_id": thread_id,
    }


def _ensure_full_msg(full_msg: AIMessage | None, accumulated_content: list[str]) -> AIMessage | None:
    """如果 full_msg 为空且有累积内容，构建 AIMessage"""
    if not full_msg and accumulated_content:
        return AIMessage(content="".join(accumulated_content))
    return full_msg


def _extract_ai_message(messages: list[Any] | None) -> AIMessage | None:
    """从消息列表中提取最后一条 AIMessage。"""
    if not isinstance(messages, list):
        return None

    for msg in reversed(messages):
        if isinstance(msg, AIMessage):
            return msg

        msg_dict = msg.model_dump() if hasattr(msg, "model_dump") else {}
        if msg_dict.get("type") == "ai":
            content = msg_dict.get("content", "")
            return msg if hasattr(msg, "content") else AIMessage(content=content)

    return None


async def get_agent_config_by_id(db, user: User, agent_config_id: int):
    """按配置 ID 解析 AgentConfig 记录。"""
    department_id = user.department_id

    agent_config_repo = AgentConfigRepository(db)
    config_item = await agent_config_repo.get_by_id(config_id=int(agent_config_id))
    if config_item is None or config_item.department_id != department_id:
        raise ValueError("配置不存在")

    return config_item


async def _resolve_agent_config(db, agent_id: str, user: User, agent_config_id):
    """解析 agent_config，返回 agent_config"""
    department_id = user.department_id

    agent_config_repo = AgentConfigRepository(db)
    config_item = None
    if agent_config_id is not None:
        config_item = await get_agent_config_by_id(db, user, int(agent_config_id))
        if config_item.agent_id != agent_id:
            config_item = None

    if config_item is None:
        config_item = await agent_config_repo.get_or_create_default(
            department_id=department_id, agent_id=agent_id, created_by=str(user.id)
        )

    return (config_item.config_json or {}).get("context", {})


async def check_and_handle_interrupts(
    agent,
    langgraph_config: dict,
    make_chunk,
    meta: dict,
    thread_id: str,
) -> AsyncIterator[bytes]:
    try:
        graph = await agent.get_graph()
        state = await graph.aget_state(langgraph_config)

        if not state or not state.values:
            return

        interrupt_info = _extract_interrupt_info(state)
        if interrupt_info:
            question_payload = _build_ask_user_question_payload(interrupt_info, thread_id)
            meta["interrupt"] = question_payload
            yield make_chunk(status="ask_user_question_required", meta=meta, **question_payload)

    except Exception as e:
        logger.error(f"Error checking interrupts: {e}")
        logger.error(traceback.format_exc())


async def _ensure_thread_bound_agent_config(
    *,
    conv_repo: ConversationRepository,
    agent_config_repo: AgentConfigRepository,
    thread_id: str,
    user_id: str,
    department_id: int,
    agent_id: str,
    agent_config_id: int,
) -> None:
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation:
        conversation = await conv_repo.create_conversation(
            user_id=user_id,
            agent_id=agent_id,
            thread_id=thread_id,
        )

    current_agent_config_id = (conversation.extra_metadata or {}).get("agent_config_id")
    if current_agent_config_id != int(agent_config_id):
        # 检查目标配置是否存在于配置表中
        config_item = await agent_config_repo.get_by_id(int(agent_config_id))
        if config_item is None:
            # 配置已损坏或已移除，切换到默认配置
            logger.warning(
                f"Config {agent_config_id} not found for thread {thread_id}, "
                f"switching to default config for agent {agent_id}"
            )
            default_config = await agent_config_repo.get_or_create_default(
                department_id=department_id,
                agent_id=agent_id,
                created_by=user_id,
            )
            await conv_repo.bind_agent_config(thread_id, default_config.id)
        else:
            await conv_repo.bind_agent_config(thread_id, agent_config_id)


"""
agent_chat() 是 非流式 Agent 执行函数。
它和 stream_agent_chat() 做的事情类似，但区别是：stream_agent_chat()：边执行边 yield chunk
agent_chat()：执行完后一次性 return dict。是理解 Agent 执行逻辑的参考版本，不是当前育种工作台异步 Run 的主入口。
"""
async def agent_chat(
    *,
    query: str,
    agent_config_id: int,
    thread_id: str | None,
    meta: dict,
    image_content: str | None,
    current_user,
    db,
) -> dict:
    """非流式对话，返回完整响应"""
    start_time = asyncio.get_event_loop().time()

    if image_content:
        human_message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
            ]
        )
        message_type = "multimodal_image"
    else:
        human_message = HumanMessage(content=query)
        message_type = "text"

    if conf.enable_content_guard and await content_guard.check(query):
        return {
            "status": "error",
            "error_type": "content_guard_blocked",
            "error_message": "输入内容包含敏感词",
            "request_id": meta.get("request_id"),
        }

    if not current_user.department_id:
        return {
            "status": "error",
            "error_type": "invalid_config",
            "error_message": "当前用户未绑定部门",
            "request_id": meta.get("request_id"),
        }

    user_id = str(current_user.id)
    meta = dict(meta or {})
    if "request_id" not in meta or not meta.get("request_id"):
        logger.warning("请求缺少 request_id，已自动生成一个新的 request_id")
        meta["request_id"] = str(uuid.uuid4())

    ''' 根据 agent_config_id 找配置 '''
    try:
        config_item = await get_agent_config_by_id(db, current_user, agent_config_id)
    except ValueError as e:
        return {
            "status": "error",
            "error_type": "invalid_config",
            "error_message": str(e),
            "request_id": meta.get("request_id"),
        }

    agent_id = config_item.agent_id
    meta.update(
        {
            "query": query,
            "agent_id": agent_id,
            "server_model_name": agent_id,
            "thread_id": thread_id,
            "user_id": current_user.id,
            "has_image": bool(image_content),
        }
    )

    ''' 获取 Agent 实例 '''
    try:
        agent = agent_manager.get_agent(agent_id)
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}, {traceback.format_exc()}")
        return {
            "status": "error",
            "error_type": "agent_error",
            "error_message": f"智能体 {agent_id} 获取失败: {str(e)}",
            "request_id": meta.get("request_id"),
        }

    ''' 构造输入上下文 '''
    messages = [human_message]
    agent_config = (config_item.config_json or {}).get("context", {})

    if not thread_id:
        thread_id = str(uuid.uuid4())
        logger.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

    input_context = await _build_agent_input_context(agent_config, thread_id=thread_id, user_id=user_id)
    langfuse_run = _build_langfuse_run_context(
        current_user=current_user,
        thread_id=thread_id,
        agent_id=agent_id,
        request_id=meta["request_id"],
        operation="agent_chat_sync",
        agent_config_id=agent_config_id,
        message_type=message_type,
    )
    trace_info: dict[str, Any] = {}

    try:
        conv_repo = ConversationRepository(db)
        agent_config_repo = AgentConfigRepository(db)
        await _ensure_thread_bound_agent_config(
            conv_repo=conv_repo,
            agent_config_repo=agent_config_repo,
            thread_id=thread_id,
            user_id=user_id,
            department_id=current_user.department_id,
            agent_id=agent_id,
            agent_config_id=agent_config_id,
        )

        try:
            await conv_repo.add_message_by_thread_id(
                thread_id=thread_id,
                role="user",
                content=query,
                message_type=message_type,
                image_content=image_content,
                extra_metadata={
                    "raw_message": human_message.model_dump(),
                    "request_id": meta.get("request_id"),
                },
            )
        except Exception as e:
            logger.error(f"Error saving user message: {e}")


        ''' 调用Agent '''
        # 非流式调用：
        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}
        invoke_result = await agent.invoke_messages(
            messages,
            input_context=input_context,
            callbacks=langfuse_run.callbacks,
            metadata=langfuse_run.metadata,
            tags=langfuse_run.tags,
        )
        full_msg = _extract_ai_message(invoke_result.get("messages") if isinstance(invoke_result, dict) else None)
        trace_info = get_trace_info(langfuse_run)

        if full_msg is None:
            try:
                graph = await agent.get_graph()
                state = await graph.aget_state(langgraph_config)
                full_msg = _extract_ai_message(getattr(state, "values", {}).get("messages", [])) if state else None
            except Exception:
                full_msg = None

        full_content = full_msg.content if full_msg else ""

        if conf.enable_content_guard and await content_guard.check(full_content):
            await save_partial_message(
                conv_repo,
                thread_id,
                full_msg,
                "content_guard_blocked",
                trace_info=trace_info,
            )
            return {
                "status": "interrupted",
                "message": "检测到敏感内容，已中断输出",
                "request_id": meta.get("request_id"),
                "time_cost": asyncio.get_event_loop().time() - start_time,
            }

        try:
            graph = await agent.get_graph()
            state = await graph.aget_state(langgraph_config)
            agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
        except Exception:
            agent_state = {}

        try:
            await save_messages_from_langgraph_state(
                agent_instance=agent,
                thread_id=thread_id,
                conv_repo=conv_repo,
                config_dict=langgraph_config,
                trace_info=trace_info,
            )
        except Exception as e:
            logger.error(f"Error saving messages from LangGraph state: {e}")
            logger.error(traceback.format_exc())
            return {
                "status": "error",
                "error_type": "save_message_error",
                "error_message": f"消息保存失败: {e}",
                "request_id": meta.get("request_id"),
            }

        return {
            "status": "finished",
            "response": full_content,
            "request_id": meta.get("request_id"),
            "thread_id": thread_id,
            "agent_state": agent_state,
            "time_cost": asyncio.get_event_loop().time() - start_time,
        }

    except Exception as e:
        logger.error(f"Error in agent_chat: {e}, {traceback.format_exc()}")
        return {
            "status": "error",
            "error_type": "unexpected_error",
            "error_message": str(e),
            "request_id": meta.get("request_id"),
        }
    finally:
        flush_langfuse()


'''
育种工作台进入 YuXi Agent 流式执行层的核心函数。
在异步 Run 链路里，run_worker.py 会调用它：育种工作台通过 /api/chat/runs 创建异步任务后，最终会走到 stream_agent_chat()
本身是 YuXi 的后端函数，所有的育种内容来自前端 query、meta、Agent 工具调用、breeding/tools.py 返回结果
'''
async def stream_agent_chat(
    *,
    query: str,  # 用户问题（前端构建后的育种任务提示词）
    agent_config_id: int,  # 当前使用的 Agent 配置
    thread_id: str | None,  # 当前对话线程
    meta: dict,  # 请求上下文 包含 source / trait / breeding_context / allowed_tools / preferred_tool
    image_content: str | None,  # 图片输入，后续可接入
    current_user,  # 当前用户
    db,  # 数据库会话
) -> AsyncIterator[bytes]:
    start_time = asyncio.get_event_loop().time()

    # 构造 make_chunk()   把执行过程中的状态、消息、错误、最终结果统一包装成 JSON 行。
    # run_worker.py 会不断消费这些 chunk，然后写入 run event
    def make_chunk(content=None, **kwargs):
        return (
            json.dumps(
                {"request_id": meta.get("request_id"), "response": content, **kwargs}, ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        )

    # 把用户输入构造成 HumanMessage
    if image_content:
        human_message = HumanMessage(
            content=[
                {"type": "text", "text": query},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_content}"}},
            ]
        )
        message_type = "multimodal_image"
    else:
        # 如果没有输入图片  纯文本任务
        human_message = HumanMessage(content=query)
        message_type = "text"

    init_msg = {"role": "user", "content": query, "type": "human"}
    if image_content:
        init_msg["message_type"] = "multimodal_image"
        init_msg["image_content"] = image_content
    else:
        init_msg["message_type"] = "text"

    # 先返回一个 init chunk，表示 Agent 已经开始处理这次输入
    yield make_chunk(status="init", meta=meta, msg=init_msg)

    # 输入安全检查和用户配置检查
    if conf.enable_content_guard and await content_guard.check(query):
        yield make_chunk(
            status="error", error_type="content_guard_blocked", error_message="输入内容包含敏感词", meta=meta
        )
        return

    if not current_user.department_id:
        yield make_chunk(status="error", error_type="invalid_config", error_message="当前用户未绑定部门", meta=meta)
        return

    meta = dict(meta or {})
    if "request_id" not in meta or not meta.get("request_id"):
        logger.warning("请求缺少 request_id，已自动生成一个新的 request_id")
        meta["request_id"] = str(uuid.uuid4())

    # 根据 agent_config_id 找 AgentConfig
    # 前端传的是 agent_config_id；后端通过它找到具体 agent_id 和 config_json。
    user_id = str(current_user.id)
    try:
        config_item = await get_agent_config_by_id(db, current_user, agent_config_id)
    except ValueError as e:
        yield make_chunk(status="error", error_type="invalid_config", error_message=str(e), meta=meta)
        return

    agent_id = config_item.agent_id

    # 更新meta上下文，把运行时可信字段补进 meta。
    # 前端传入的 source / trait / breeding_context / allowed_tools / preferred_tool 会继续保留；
    # 后端运行时字段 query / agent_id / thread_id / user_id 会覆盖或补齐。
    meta.update(
        {
            "query": query,
            "agent_id": agent_id,
            "server_model_name": agent_id,
            "thread_id": thread_id,
            "user_id": current_user.id,
            "has_image": bool(image_content),
        }
    )

    # 只要这个判断为真，就进入 direct route，就是当前项目”改成“固定业务入口”的关键
# 育种工作台直达工具分支：
# 当前 /breeding-workbench 不再等待 ChatbotAgent/LLM 自主选择工具。
# 只要 meta.source=breeding-workbench 且 preferred_tool=omics_breeding_analysis_run，
# 就直接构造 omics_breeding_analysis_run 的 input 并执行工具。
# 执行完成后手动写入 user / assistant(tool_call) / tool / assistant(final) 消息，
# 使前端仍能通过 thread history 解析 toolChain、frontend_payload 和 answer_markdown。
    if _is_direct_breeding_workbench_tool_run(meta):
        # direct route 内部第一步：绑定会话配置  保证当前 thread 和 agent_config 绑定关系正确
        conv_repo = ConversationRepository(db)
        agent_config_repo = AgentConfigRepository(db)
        await _ensure_thread_bound_agent_config(
            conv_repo=conv_repo,
            agent_config_repo=agent_config_repo,
            thread_id=thread_id,
            user_id=user_id,
            department_id=current_user.department_id,
            agent_id=agent_id,
            agent_config_id=agent_config_id,
        )

        # direct route 内部第二步：构造工具入参  是前端 meta 到后端工具 input 的转换点
        tool_input = _build_direct_breeding_tool_input(
            query=query,
            thread_id=thread_id,
            meta=meta,
            agent_config=(config_item.config_json or {}).get("context", {}),
        )
        # 第三步：先 yield loading，告诉 run_worker / 前端：任务已经进入 direct tool 执行阶段。
        yield make_chunk(
            status="loading",
            response="育种工作台正在直接执行 omics_breeding_analysis_run。",
            meta=meta,
            tool_name=BREEDING_WORKBENCH_DIRECT_TOOL,
        )

        try:
            # 第四步：真正执行工具
            from yuxi.agents.toolkits.breeding import omics_analysis as omics_analysis_module

            progress_runner = getattr(omics_analysis_module, "_run_omics_breeding_analysis_impl", None)
            if callable(progress_runner):
                loop = asyncio.get_running_loop()
                progress_futures = []

                def report_progress(progress_summary: dict[str, Any]) -> None:
                    future = asyncio.run_coroutine_threadsafe(
                        _save_direct_breeding_workbench_progress_message(
                            thread_id=thread_id,
                            run_id=str(meta.get("run_id") or ""),
                            request_id=meta["request_id"],
                            progress_summary=progress_summary,
                        ),
                        loop,
                    )
                    progress_futures.append(future)

                tool_result = await asyncio.to_thread(
                    progress_runner,
                    **tool_input,
                    progress_callback=report_progress,
                )
                for progress_future in progress_futures:
                    try:
                        await asyncio.wrap_future(progress_future)
                    except Exception as progress_error:  # noqa: BLE001
                        logger.warning(f"Error saving direct breeding progress snapshot: {progress_error}")
            else:
                tool_result = await asyncio.to_thread(
                    omics_analysis_module.omics_breeding_analysis_run.invoke,
                    {"input": tool_input},
                )
            # 第五步：保存消息到 history
            await _save_direct_breeding_workbench_tool_messages(
                conv_repo=conv_repo,
                thread_id=thread_id,
                query=query,
                request_id=meta["request_id"],
                tool_input=tool_input,
                tool_result=tool_result,
            )
        # 工具执行抛异常
        except Exception as e:
            logger.error(f"Error running direct breeding tool: {e}")
            logger.error(traceback.format_exc())
            yield make_chunk(
                status="error",
                error_type="direct_tool_error",
                error_message=str(e),
                meta=meta,
            )
            return

        if str(tool_result.get("status") or "").strip().lower() == "error":
            yield make_chunk(
                status="error",
                error_type="direct_tool_error",
                error_message=str(tool_result.get("error") or "direct tool execution failed"),
                meta=meta,
                tool_name=BREEDING_WORKBENCH_DIRECT_TOOL,
                result=tool_result,
            )
            return

        # direct route 成功返回
        yield make_chunk(
            status="finished",
            response=str(tool_result.get("answer_markdown") or ""),
            meta=meta,
            thread_id=thread_id,
            tool_name=BREEDING_WORKBENCH_DIRECT_TOOL,
            frontend_payload=tool_result.get("frontend_payload") or {},
            result=tool_result,
            agent_state={},
            time_cost=asyncio.get_event_loop().time() - start_time,
        )
        return

    # 获取 Agent 实例，这里才真正进入 YuXi 的 Agent 系统，拿到 Agent 对象
    try:
        agent = agent_manager.get_agent(agent_id)
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}, {traceback.format_exc()}")
        yield make_chunk(
            status="error",
            error_type="agent_error",
            error_message=f"智能体 {agent_id} 获取失败: {str(e)}",
            meta=meta,
        )
        return

    # 构造 input_context（传给 Agent 的运行上下文）
    messages = [human_message]
    agent_config = (config_item.config_json or {}).get("context", {})

    if not thread_id:
        thread_id = str(uuid.uuid4())
        logger.warning(f"No thread_id provided, generated new thread_id: {thread_id}")

    # [breeding-workbench allowed_tools runtime constraint] 原逻辑保留供学习对照：
    # 原逻辑只从 AgentConfig.config_json.context 构造 input_context。
    # old:
    # input_context = await _build_agent_input_context(agent_config, thread_id=thread_id, user_id=user_id)
    #
    # 原逻辑的问题：
    # breeding-workbench 的 allowed_tools 虽然已在 meta 中传到 stream_agent_chat，
    # 但 RuntimeConfigMiddleware 读取的是 context.tools，不读取 meta.allowed_tools，
    # 所以原逻辑无法形成工具硬约束。
    input_context = await _build_agent_input_context(agent_config, thread_id=thread_id, user_id=user_id)

    # 只在 breeding-workbench 来源启用该覆盖，避免普通聊天的工具配置被前端 meta 影响。
    source = meta.get("source")
    allowed_tools = meta.get("allowed_tools") or []
    # allowed_tools 是请求侧输入，只有非空字符串列表才可进入 BaseContext.tools。
    # 这里写入运行态 input_context，而不是写回 agent_config/config_json，避免污染持久化 Agent 配置。
    if source == "breeding-workbench" and isinstance(allowed_tools, list) and allowed_tools:
        normalized_allowed_tools = [
            item.strip() for item in allowed_tools if isinstance(item, str) and item.strip()
        ]
        if normalized_allowed_tools:
            # 这一步只控制模型可见工具白名单，不代表 Agent 一定会执行其中某个工具。
            input_context["tools"] = normalized_allowed_tools
            logger.info(
                f"Breeding workbench tool constraint applied: thread_id={thread_id} "
                f"request_id={meta['request_id']} tools={normalized_allowed_tools}"
            )

    langfuse_run = _build_langfuse_run_context(
        current_user=current_user,
        thread_id=thread_id,
        agent_id=agent_id,
        request_id=meta["request_id"],
        operation="agent_chat_stream",
        agent_config_id=agent_config_id,
        message_type=message_type,
    )
    full_msg = None
    accumulated_content: list[str] = []
    trace_info: dict[str, Any] = {}
    last_agent_state_signature = ""

    try:
        conv_repo = ConversationRepository(db)
        agent_config_repo = AgentConfigRepository(db)
        await _ensure_thread_bound_agent_config(
            conv_repo=conv_repo,
            agent_config_repo=agent_config_repo,
            thread_id=thread_id,
            user_id=user_id,
            department_id=current_user.department_id,
            agent_id=agent_id,
            agent_config_id=agent_config_id,
        )

        try:
            await conv_repo.add_message_by_thread_id(
                thread_id=thread_id,
                role="user",
                content=query,
                message_type=message_type,
                image_content=image_content,
                extra_metadata={
                    "raw_message": human_message.model_dump(),
                    "request_id": meta.get("request_id"),
                },
            )
        except Exception as e:
            logger.error(f"Error saving user message: {e}")

        # 先构建 langgraph_config
        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}

        # LangGraph 会自动从 checkpointer 恢复 state（包括 uploads）
        # 无需手动加载或传递

        # 流式调用Agent  这是 stream_agent_chat() 的核心
        # 从此开始，Agent/LangGraph 会 调用模型、产生 assistant 消息、触发 tool call、执行工具、产生 tool 消息、更新 state
        full_msg = None
        accumulated_content = []
        async for mode, payload in _stream_agent_events(
            agent,
            messages,
            input_context=input_context,
            callbacks=langfuse_run.callbacks,
            metadata=langfuse_run.metadata,
            tags=langfuse_run.tags,
        ):
            if mode == "values":
                agent_state = extract_agent_state(payload if isinstance(payload, dict) else {})
                signature = _agent_state_signature(agent_state)
                if signature and signature != last_agent_state_signature:
                    last_agent_state_signature = signature
                    yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)
                continue

            msg, metadata = payload
            if isinstance(msg, AIMessageChunk):
                accumulated_content.append(msg.content)
                trace_info = get_trace_info(langfuse_run)

                content_for_check = "".join(accumulated_content[-10:])
                if conf.enable_content_guard and await content_guard.check_with_keywords(content_for_check):
                    full_msg = AIMessage(content="".join(accumulated_content))
                    await save_partial_message(
                        conv_repo,
                        thread_id,
                        full_msg,
                        "content_guard_blocked",
                        trace_info=trace_info,
                    )
                    meta["time_cost"] = asyncio.get_event_loop().time() - start_time
                    yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
                    return

                yield make_chunk(content=msg.content, msg=msg.model_dump(), metadata=metadata, status="loading")
            else:
                msg_dict = msg.model_dump()
                trace_info = get_trace_info(langfuse_run)
                yield make_chunk(msg=msg_dict, metadata=metadata, status="loading")

        full_msg = _ensure_full_msg(full_msg, accumulated_content)
        trace_info = get_trace_info(langfuse_run)

        if conf.enable_content_guard and hasattr(full_msg, "content") and await content_guard.check(full_msg.content):
            await save_partial_message(
                conv_repo,
                thread_id,
                full_msg,
                "content_guard_blocked",
                trace_info=trace_info,
            )
            meta["time_cost"] = asyncio.get_event_loop().time() - start_time
            yield make_chunk(status="interrupted", message="检测到敏感内容，已中断输出", meta=meta)
            return

        async for chunk in check_and_handle_interrupts(agent, langgraph_config, make_chunk, meta, thread_id):
            yield chunk

        meta["time_cost"] = asyncio.get_event_loop().time() - start_time
        try:
            graph = await agent.get_graph()
            state = await graph.aget_state(langgraph_config)
            agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
        except Exception:
            agent_state = {}

        final_signature = _agent_state_signature(agent_state)
        if final_signature and final_signature != last_agent_state_signature:
            last_agent_state_signature = final_signature
            yield make_chunk(status="agent_state", agent_state=agent_state, meta=meta)

        # 先保存消息到 history 数据库，再返回 finished 通知前端，避免前端查询时数据未落库
        try:  # 保存消息到history  从 LangGraph state 里取消息，然后保存 assistant 消息和 tool 消息
            await save_messages_from_langgraph_state(
                agent_instance=agent,
                thread_id=thread_id,
                conv_repo=conv_repo,
                config_dict=langgraph_config,
                trace_info=trace_info,
            )
        except Exception as e:
            logger.error(f"Error saving messages from LangGraph state: {e}")
            logger.error(traceback.format_exc())
            yield make_chunk(status="warning", message=f"消息保存失败: {e}", meta=meta)

        yield make_chunk(status="finished", meta=meta)

    except (asyncio.CancelledError, ConnectionError) as e:
        logger.warning(f"Client disconnected, cancelling stream: {e}")

        async def save_cleanup():
            nonlocal full_msg
            full_msg = _ensure_full_msg(full_msg, accumulated_content)

            async with pg_manager.get_async_session_context() as new_db:
                new_conv_repo = ConversationRepository(new_db)
                await save_partial_message(
                    new_conv_repo,
                    thread_id,
                    full_msg=full_msg,
                    error_message="对话已中断" if not full_msg else None,
                    error_type="interrupted",
                    trace_info=trace_info,
                )

        cleanup_task = asyncio.create_task(save_cleanup())
        try:
            await asyncio.shield(cleanup_task)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(f"Error during cleanup save: {exc}")

        yield make_chunk(status="interrupted", message="对话已中断", meta=meta)

    except Exception as e:
        logger.error(f"Error streaming messages: {e}, {traceback.format_exc()}")

        error_msg = f"Error streaming messages: {e}"
        error_type = "unexpected_error"

        full_msg = _ensure_full_msg(full_msg, accumulated_content)

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo,
                thread_id,
                full_msg=full_msg,
                error_message=error_msg,
                error_type=error_type,
                trace_info=trace_info,
            )

        yield make_chunk(status="error", error_type=error_type, error_message=error_msg, meta=meta)
    finally:
        flush_langfuse()


async def stream_agent_resume(
    *,
    agent_id: str,
    thread_id: str,
    resume_input: Any,
    meta: dict,
    config: dict,
    current_user,
    db,
) -> AsyncIterator[bytes]:
    start_time = asyncio.get_event_loop().time()

    def make_resume_chunk(content=None, **kwargs):
        return (
            json.dumps(
                {"request_id": meta.get("request_id"), "response": content, **kwargs}, ensure_ascii=False
            ).encode("utf-8")
            + b"\n"
        )

    try:
        agent = agent_manager.get_agent(agent_id)
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}, {traceback.format_exc()}")
        yield (
            f'{{"request_id": "{meta.get("request_id")}", "message": '
            f'"Error getting agent {agent_id}: {e}", "status": "error"}}\n'
        )
        return

    init_msg = {"type": "system", "content": f"Resume with input: {resume_input}"}
    yield make_resume_chunk(status="init", meta=meta, msg=init_msg)

    resume_command = Command(resume=resume_input)

    user_id = str(current_user.id)
    agent_config_id = (config or {}).get("agent_config_id")
    try:
        agent_config = await _resolve_agent_config(db, agent_id, current_user, agent_config_id)
    except ValueError as e:
        yield make_resume_chunk(status="error", error_type="invalid_config", error_message=str(e), meta=meta)
        return

    context = agent.context_schema()
    context.update(await _build_agent_input_context(agent_config or {}, thread_id=thread_id, user_id=user_id))
    graph = await agent.get_graph(context=context)
    langfuse_run = _build_langfuse_run_context(
        current_user=current_user,
        thread_id=thread_id,
        agent_id=agent_id,
        request_id=meta.get("request_id") or str(uuid.uuid4()),
        operation="agent_chat_resume",
        agent_config_id=agent_config_id,
        message_type="resume",
    )
    trace_info: dict[str, Any] = {}
    last_agent_state_signature = ""

    stream_source = graph.astream(
        resume_command,
        context=context,
        config={
            "configurable": {"thread_id": thread_id, "user_id": user_id},
            "callbacks": langfuse_run.callbacks,
            "metadata": langfuse_run.metadata,
            "tags": langfuse_run.tags,
        },
        stream_mode=["messages", "values"],
    )

    try:
        async for mode, payload in stream_source:
            if mode == "values":
                agent_state = extract_agent_state(payload if isinstance(payload, dict) else {})
                signature = _agent_state_signature(agent_state)
                if signature and signature != last_agent_state_signature:
                    last_agent_state_signature = signature
                    yield make_resume_chunk(status="agent_state", agent_state=agent_state, meta=meta)
                continue

            msg, metadata = payload
            trace_info = get_trace_info(langfuse_run)
            msg_dict = msg.model_dump()
            if "id" not in msg_dict:
                msg_dict["id"] = str(uuid.uuid4())

            yield make_resume_chunk(
                content=getattr(msg, "content", ""), msg=msg_dict, metadata=metadata, status="loading"
            )

        langgraph_config = {"configurable": {"thread_id": thread_id, "user_id": str(current_user.id)}}
        async for chunk in check_and_handle_interrupts(agent, langgraph_config, make_resume_chunk, meta, thread_id):
            yield chunk

        meta["time_cost"] = asyncio.get_event_loop().time() - start_time

        try:
            state = await graph.aget_state(langgraph_config)
            agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}
        except Exception:
            agent_state = {}

        final_signature = _agent_state_signature(agent_state)
        if final_signature and final_signature != last_agent_state_signature:
            yield make_resume_chunk(status="agent_state", agent_state=agent_state, meta=meta)

        # 先存储数据库，再返回 finished，避免前端查询时数据未落库
        conv_repo = ConversationRepository(db)
        try:
            await save_messages_from_langgraph_state(
                agent_instance=agent,
                thread_id=thread_id,
                conv_repo=conv_repo,
                config_dict=langgraph_config,
                trace_info=trace_info,
            )
        except Exception as e:
            logger.error(f"Error saving messages from LangGraph state: {e}")
            logger.error(traceback.format_exc())
            yield make_resume_chunk(status="warning", message=f"消息保存失败: {e}", meta=meta)

        yield make_resume_chunk(status="finished", meta=meta)

    except (asyncio.CancelledError, ConnectionError) as e:
        logger.warning(f"Client disconnected during resume: {e}")

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo,
                thread_id,
                error_message="对话恢复已中断",
                error_type="resume_interrupted",
                trace_info=trace_info,
            )

        yield make_resume_chunk(status="interrupted", message="对话恢复已中断", meta=meta)

    except Exception as e:
        logger.error(f"Error during resume: {e}, {traceback.format_exc()}")

        async with pg_manager.get_async_session_context() as new_db:
            new_conv_repo = ConversationRepository(new_db)
            await save_partial_message(
                new_conv_repo,
                thread_id,
                error_message=f"Error during resume: {e}",
                error_type="resume_error",
                trace_info=trace_info,
            )

        yield make_resume_chunk(message=f"Error during resume: {e}", status="error")
    finally:
        flush_langfuse()


async def get_agent_state_view(
    *,
    thread_id: str,
    current_user_id: str,
    db,
) -> dict:
    conv_repo = ConversationRepository(db)
    conversation = await conv_repo.get_conversation_by_thread_id(thread_id)
    if not conversation or conversation.user_id != str(current_user_id) or conversation.status == "deleted":
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="对话线程不存在")

    agent = agent_manager.get_agent(conversation.agent_id)
    graph = await agent.get_graph()
    langgraph_config = {"configurable": {"user_id": str(current_user_id), "thread_id": thread_id}}
    state = await graph.aget_state(langgraph_config)
    agent_state = extract_agent_state(getattr(state, "values", {})) if state else {}

    return {"agent_state": agent_state}
