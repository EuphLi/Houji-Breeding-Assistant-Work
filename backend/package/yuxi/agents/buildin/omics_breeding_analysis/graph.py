from __future__ import annotations

from langchain.agents import create_agent

from yuxi.agents import BaseAgent, BaseState, load_chat_model

from .context import OmicsBreedingAnalysisContext


# 工具名常量
OMICS_BREEDING_ANALYSIS_TOOL_NAME = "omics_breeding_analysis_run"


OMICS_BREEDING_ANALYSIS_SYSTEM_PROMPT = """你是一个多组学育种分析智能体。

你的任务是基于用户提供的目标性状、问题、多组学证据和已验证文献证据，生成谨慎、可追溯的育种分析结果。

基本边界：
1. 不编造 DOI。
2. 不编造 quoted_sentence。
3. 不声称已完成群体验证。
4. 不声称已完成湿实验。
5. 不声称最终 KASP/CAPS 标记已经开发完成。
6. 不声称最终育种结论已经明确。
7. 目标基因和目标性状必须来自当前用户问题和输入证据，不能写死。
8. 若任务涉及育种建议、标记推荐或候选验证，应给出后续群体层面的验证建议，但不能声称已经完成验证。

工具使用要求：
- 当用户要求进行多组学育种分析、候选基因分析、育种建议、标记候选分析或验证方案时，应优先调用 omics_breeding_analysis_run。
- 该工具会基于 significant_de_genes.tsv 和 verified_literature_evidence.tsv 构建 Evidence Pack，并生成 answer_markdown、citations、literature_cards、claim_trace、guard_result 和 final_result.json。
- 不应调用旧的 smoke_flavonoid_breeding_advice 作为正式多组学育种分析主线。
"""


async def get_tools_from_all_servers():
    """延迟导入 MCP 工具加载函数，避免 toolkits 初始化时出现循环导入。"""

    from yuxi.services.mcp_service import get_tools_from_all_servers as _impl

    return await _impl()


async def _build_middlewares(context: OmicsBreedingAnalysisContext):
    """构建多组学育种分析智能体的最小中间件列表。

    注意：这里使用函数内部 import，避免在 toolkits 初始化过程中形成循环导入。

    当前只接入 YuXi 官方运行链路必需的最小能力：
    - RuntimeConfigMiddleware: 让 context.tools / context.mcps 等运行配置有机会生效。
    - PatchToolCallsMiddleware: 保持工具调用格式兼容。
    - ModelRetryMiddleware: 提供模型调用重试能力。

    暂不接入：
    - SkillsMiddleware
    - SubAgentMiddleware
    - KnowledgeBaseMiddleware
    - TodoListMiddleware
    - SummaryOffloadMiddleware
    """

    from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
    from langchain.agents.middleware import ModelRetryMiddleware
    from yuxi.agents.middlewares import RuntimeConfigMiddleware

    all_mcp_tools = await get_tools_from_all_servers()

    return [
        RuntimeConfigMiddleware(extra_tools=all_mcp_tools),
        PatchToolCallsMiddleware(),
        ModelRetryMiddleware(),
    ]


# 只修改运行时 context，不写数据库，不影响前端保存的 config_json.context。
# 目的只是保证专用 Agent 在运行时默认能看到自己的正式工具。
def _ensure_required_tools(context: OmicsBreedingAnalysisContext) -> OmicsBreedingAnalysisContext:
    """确保多组学育种分析智能体默认可见正式分析 Tool。

    这里修改的是运行期 context，不直接修改数据库中的 AgentConfig。
    目的是避免用户没有在前端手动勾选工具时，专用 Agent 反而看不到自己的核心工具。
    """

    selected_tools = list(getattr(context, "tools", None) or [])

    if OMICS_BREEDING_ANALYSIS_TOOL_NAME not in selected_tools:
        selected_tools.append(OMICS_BREEDING_ANALYSIS_TOOL_NAME)

    setattr(context, "tools", selected_tools)
    return context


def _build_system_prompt(context: OmicsBreedingAnalysisContext) -> str:
    """拼接 Context 中的系统提示词和多组学育种分析边界提示。"""

    base_prompt = str(getattr(context, "system_prompt", "") or "").strip()

    if base_prompt:
        return f"{base_prompt}\n\n{OMICS_BREEDING_ANALYSIS_SYSTEM_PROMPT}"

    return OMICS_BREEDING_ANALYSIS_SYSTEM_PROMPT


class OmicsBreedingAnalysisAgent(BaseAgent):
    name = "多组学育种分析智能体"
    description = "基于固定生信证据、代谢组上下文和已验证文献证据，生成带来源约束的多组学育种分析。"
    context_schema = OmicsBreedingAnalysisContext

    async def get_graph(self, context=None, **kwargs):
        context = context or self.context_schema()
        # 确保后面 RuntimeConfigMiddleware 能根据 context.tools 把 omics_breeding_analysis_run 加入模型可见工具列表
        context = _ensure_required_tools(context)

        graph = create_agent(
            model=load_chat_model(fully_specified_name=context.model),
            system_prompt=_build_system_prompt(context),
            middleware=await _build_middlewares(context),
            state_schema=BaseState,
            checkpointer=await self._get_checkpointer(),
        )

        return graph