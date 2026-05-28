import json

import pytest

from yuxi.agents.buildin import agent_manager
from yuxi.agents.buildin.omics_breeding_analysis import (
    OmicsBreedingAnalysisAgent,
    OmicsBreedingAnalysisContext,
)

from yuxi.agents.middlewares import RuntimeConfigMiddleware
from yuxi.agents.buildin.omics_breeding_analysis.context import OmicsBreedingAnalysisContext
from yuxi.agents.buildin.omics_breeding_analysis import graph as graph_module
from yuxi.agents.buildin.omics_breeding_analysis.graph import _build_system_prompt

from yuxi.agents.buildin.omics_breeding_analysis.evidence_pack import (
    build_omics_evidence_pack,
    write_evidence_pack,
)

from yuxi.agents.buildin.omics_breeding_analysis.graph import (
    OMICS_BREEDING_ANALYSIS_TOOL_NAME,
    _build_system_prompt,
    _ensure_required_tools,
    OmicsBreedingAnalysisAgent,
)

# OmicsBreedingAnalysisContext 可以正常实例化；
# trait 和 question 可以由外部动态传入；
# citation_mode 默认是 sentence；
# guard_mode 默认是 strict。
# citation_mode 和 guard_mode 是运行配置，不是运行结果。
def test_omics_breeding_analysis_context_defaults():
    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
    )

    assert context.trait == "黄酮相关"
    assert context.question == "给出一些育种建议"
    assert context.citation_mode == "sentence"
    assert context.guard_mode == "strict"

# 测试 OmicsBreedingAnalysisAgent 已经进入 YuXi 官方 Agent 自动发现链路。
# 注释表示 pytest 用异步事件循环运行这个测试。
@pytest.mark.asyncio
async def test_omics_breeding_analysis_agent_is_auto_discovered():
    agents = await agent_manager.get_agents_info(include_configurable_items=True)
    agent_ids = {item.get("id") for item in agents}

    assert "OmicsBreedingAnalysisAgent" in agent_ids


# 验证 OmicsBreedingAnalysisContext 中定义的字段，是否能通过 BaseContext.get_configurable_items() 暴露出去。
# 对应 YuXi 官方链路：
# context_schema
# → get_configurable_items()
# → agent_manager.get_agents_info()
# → 前端 Agent 配置侧边栏
@pytest.mark.asyncio
async def test_omics_breeding_analysis_configurable_items():
    agents = await agent_manager.get_agents_info(include_configurable_items=True)

    target = None
    for item in agents:
        if item.get("id") == "OmicsBreedingAnalysisAgent":
            target = item
            break

    assert target is not None

    configurable_items = target.get("configurable_items") or {}

    assert "trait" in configurable_items
    assert "question" in configurable_items
    assert "transcriptome_result_path" in configurable_items
    assert "literature_evidence_path" in configurable_items
    assert "metabolome_path" in configurable_items
    assert "genome_context_path" in configurable_items
    assert "evidence_pack_output_path" in configurable_items
    assert "citation_mode" in configurable_items
    assert "guard_mode" in configurable_items

    # 验证前段显示字段元数据
    # YuXi 前端配置项不是手写 Vue 表单，而是由 Context 的 metadata 自动生成
    # 即此测试等于锁定： 后端 Context → 前端配置描述
    assert configurable_items["trait"]["name"] == "目标性状"
    assert configurable_items["question"]["name"] == "用户问题"
    assert configurable_items["citation_mode"]["options"] == ["sentence", "short_clause"]
    assert configurable_items["guard_mode"]["options"] == ["normal", "strict"]


# 这个测试的意义是：
# 防止以后再次在子 Context 中覆盖 mcps，破坏 YuXi 前端 MCP 选择控件。
# 因为 template_metadata.kind = mcps 是前端识别“这个字段应该渲染为 MCP 服务器选择器”的关键。
@pytest.mark.asyncio
async def test_omics_breeding_analysis_inherits_base_context_mcps_config():
    agents = await agent_manager.get_agents_info(include_configurable_items=True)

    target = None
    for item in agents:
        if item.get("id") == "OmicsBreedingAnalysisAgent":
            target = item
            break

    assert target is not None

    mcps = (target.get("configurable_items") or {}).get("mcps")

    assert mcps is not None
    assert mcps["name"] == "MCP服务器"
    assert mcps["template_metadata"] == {"kind": "mcps"}

# 确认 system_prompt 中包含多组学育种分析边界
def test_omics_breeding_analysis_system_prompt_contains_boundaries():
    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
    )

    prompt = _build_system_prompt(context)

    assert "多组学育种分析智能体" in prompt
    assert "不编造 DOI" in prompt
    assert "不编造 quoted_sentence" in prompt
    assert "不声称已完成群体验证" in prompt
    assert "目标基因和目标性状必须来自当前用户问题和输入证据" in prompt


# 测试确认 _build_middlewares() 至少包含 RuntimeConfigMiddleware
# 测试时不要真的去查 MCP server
# 而是临时替换 get_tools_from_all_servers()
# 让它返回 []
# 然后只检查 middleware 列表里有没有 RuntimeConfigMiddleware
@pytest.mark.asyncio
async def test_omics_breeding_analysis_middlewares_include_runtime_config(monkeypatch):
    async def fake_get_tools_from_all_servers():
        return []

    monkeypatch.setattr(
        graph_module,
        "get_tools_from_all_servers",
        fake_get_tools_from_all_servers,
    )

    context = OmicsBreedingAnalysisContext(
        trait="黄酮相关",
        question="给出一些育种建议",
    )

    middlewares = await graph_module._build_middlewares(context)

    assert any(isinstance(item, RuntimeConfigMiddleware) for item in middlewares)



# 构造一个黄酮任务进行测试
def test_build_omics_evidence_pack_uses_dynamic_trait_and_genes():
    pack = build_omics_evidence_pack(
        trait="黄酮相关",
        question="请给出一些育种建议",
        transcriptome_records=[
            {
                "evidence_id": "T1",
                "gene_id": "Si9g037800",
                "source_file": "significant_de_genes.tsv",
            }
        ],
        literature_records=[
            {
                "evidence_id": "L1",
                "doi": "10.1234/example",
                "quoted_sentence": "Example verified sentence.",
                "relevance_level": "background",
            }
        ],
    )

    assert pack["task"]["trait"] == "黄酮相关"
    assert pack["task"]["intent"] == "breeding_advice"
    assert pack["targets"]["genes"] == ["Si9g037800"]
    assert pack["targets"]["trait_terms"] == ["黄酮相关"]

    guard = pack["guard_requirements"]
    assert guard["required_gene_ids"] == ["Si9g037800"]
    assert guard["required_trait_terms"] == ["黄酮相关"]
    assert guard["must_include_population_validation"] is True
    assert guard["allowed_dois"] == ["10.1234/example"]
    assert guard["allowed_quoted_sentences"] == ["Example verified sentence."]


# 非黄酮测试任务
def test_build_omics_evidence_pack_does_not_hardcode_smoke_terms():
    pack = build_omics_evidence_pack(
        trait="抗旱",
        question="根据数据给出候选验证方案",
        transcriptome_records=[
            {
                "evidence_id": "T1",
                "gene_id": "GeneA",
            }
        ],
        literature_records=[],
    )

    assert pack["task"]["trait"] == "抗旱"
    assert pack["targets"]["genes"] == ["GeneA"]
    assert pack["guard_requirements"]["required_gene_ids"] == ["GeneA"]
    assert pack["guard_requirements"]["required_trait_terms"] == ["抗旱"]

    serialized = json.dumps(pack, ensure_ascii=False)
    assert "Si9g037800" not in serialized
    assert "黄酮" not in serialized


# 测试验证写文件功能
def test_write_omics_evidence_pack(tmp_path):
    pack = build_omics_evidence_pack(
        trait="产量",
        question="给出一般分析",
        transcriptome_records=[],
        literature_records=[],
    )

    output_path = write_evidence_pack(pack, tmp_path / "omics_evidence_pack.json")

    assert output_path.exists()
    loaded = json.loads(output_path.read_text(encoding="utf-8"))
    assert loaded["schema_version"] == "omics_evidence_pack.v1"
    assert loaded["task"]["trait"] == "产量"


# 测试确认：即使 context.tools 初始为空，专用 Agent 运行前也会自动加入：omics_breeding_analysis_run
def test_omics_breeding_analysis_agent_ensures_required_tool():
    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
    )
    context.tools = []

    updated = _ensure_required_tools(context)

    assert OMICS_BREEDING_ANALYSIS_TOOL_NAME in updated.tools


# 测试确认：系统提示词明确告诉模型优先使用新工具，并避免把旧 smoke 工具当正式主线。
def test_omics_breeding_analysis_system_prompt_mentions_formal_tool():
    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
    )

    prompt = _build_system_prompt(context)

    assert OMICS_BREEDING_ANALYSIS_TOOL_NAME in prompt
    assert "smoke_flavonoid_breeding_advice" in prompt
    assert "不应调用旧的 smoke_flavonoid_breeding_advice" in prompt

# 通过 monkeypatch 把这些重依赖替换掉：
# _build_middlewares
# create_agent
# load_chat_model
# _get_checkpointer
#
# 然后只检查一件核心事情：
# agent.get_graph(context)
# ↓
# _ensure_required_tools(context)
# ↓
# context.tools 包含 omics_breeding_analysis_run
#
# 这能防止后续改 graph.py 时误删：
# context = _ensure_required_tools(context)
@pytest.mark.asyncio
async def test_omics_breeding_analysis_get_graph_injects_required_tool(monkeypatch):
    captured = {}

    async def fake_build_middlewares(context):
        captured["tools"] = list(getattr(context, "tools", []) or [])
        return []

    def fake_create_agent(**kwargs):
        captured["create_agent_kwargs"] = kwargs
        return {"mock_graph": True}

    def fake_load_chat_model(*args, **kwargs):
        captured["model_args"] = args
        captured["model_kwargs"] = kwargs
        return "mock-model"

    async def fake_get_checkpointer(self):
        return "mock-checkpointer"

    monkeypatch.setattr(graph_module, "_build_middlewares", fake_build_middlewares)
    monkeypatch.setattr(graph_module, "create_agent", fake_create_agent)
    monkeypatch.setattr(graph_module, "load_chat_model", fake_load_chat_model)
    monkeypatch.setattr(
        OmicsBreedingAnalysisAgent,
        "_get_checkpointer",
        fake_get_checkpointer,
    )

    context = OmicsBreedingAnalysisContext(
        trait="抗旱",
        question="根据数据给出候选验证方案",
    )
    context.tools = []

    agent = OmicsBreedingAnalysisAgent()
    graph = await agent.get_graph(context=context)

    assert graph == {"mock_graph": True}
    assert OMICS_BREEDING_ANALYSIS_TOOL_NAME in captured["tools"]
    assert captured["create_agent_kwargs"]["model"] == "mock-model"
    assert captured["create_agent_kwargs"]["checkpointer"] == "mock-checkpointer"