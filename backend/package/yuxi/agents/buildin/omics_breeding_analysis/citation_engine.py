from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain.messages import HumanMessage, SystemMessage

from yuxi.agents import load_chat_model

try:
    from llama_index.core import Document, Settings, VectorStoreIndex
    from llama_index.core.query_engine import CitationQueryEngine

    LLAMAINDEX_AVAILABLE = True
except Exception:  # noqa: BLE001
    Document = None
    Settings = None
    VectorStoreIndex = None
    CitationQueryEngine = None
    LLAMAINDEX_AVAILABLE = False


# CitationSource 是中间结构，用来把 Evidence Pack 中的转录组、文献、代谢组、基因组上下文统一成 citation source。
# 不依赖 LlamaIndex，即使环境没装 LlamaIndex，也能测试
@dataclass(frozen=True)
class CitationSource:
    """Citation 输入源。

    这是 Evidence Pack 到 Citation Engine 之间的中间结构。
    它不依赖 LlamaIndex，方便测试和 fallback。
    """

    citation_id: str
    source_type: str
    text: str
    metadata: dict[str, Any]


def _as_str(value: Any) -> str:
    return str(value or "").strip()


def build_citation_sources(evidence_pack: dict[str, Any]) -> list[CitationSource]:
    """将 Evidence Pack 转为 citation source 列表。

    当前支持：
    - transcriptome records -> T1, T2...
    - literature records -> L1, L2...
    - metabolome_context -> M1, M2...
    - genome_context -> G1, G2...

    注意：
    - 这里不生成最终回答；
    - 这里只整理 citation 可用的来源文本；
    - DOI 和 quoted_sentence 必须来自 Evidence Pack。
    """

    evidence = evidence_pack.get("evidence") or {}
    sources: list[CitationSource] = []

    for index, record in enumerate(evidence.get("transcriptome") or [], start=1):
        gene_id = _as_str(record.get("gene_id"))
        if not gene_id:
            continue

        logfc = _as_str(record.get("logfc"))
        pvalue = _as_str(record.get("pvalue"))
        padj = _as_str(record.get("padj"))
        source_file = _as_str(record.get("source_file"))

        stats = []
        if logfc:
            stats.append(f"logFC={logfc}")
        if pvalue:
            stats.append(f"pvalue={pvalue}")
        if padj:
            stats.append(f"padj={padj}")

        stats_text = "，".join(stats) if stats else "未提供统计值"
        text = f"转录组证据显示基因 {gene_id} 出现在差异表达结果中，{stats_text}。"

        sources.append(
            CitationSource(
                citation_id=_as_str(record.get("evidence_id")) or f"T{index}",
                source_type="transcriptome",
                text=text,
                metadata={
                    "gene_id": gene_id,
                    "source_file": source_file,
                    "logfc": logfc,
                    "pvalue": pvalue,
                    "padj": padj,
                },
            )
        )

    for index, record in enumerate(evidence.get("literature") or [], start=1):
        doi = _as_str(record.get("doi"))
        quoted_sentence = _as_str(record.get("quoted_sentence"))
        if not doi or not quoted_sentence:
            continue

        text = f"文献证据 DOI {doi} 的引用原文为：{quoted_sentence}"

        sources.append(
            CitationSource(
                citation_id=_as_str(record.get("evidence_id")) or f"L{index}",
                source_type="literature",
                text=text,
                metadata={
                    "doi": doi,
                    "quoted_sentence": quoted_sentence,
                    "title": _as_str(record.get("title")),
                    "gene_id": _as_str(record.get("gene_id")),
                    "trait": _as_str(record.get("trait")),
                    "relevance_level": _as_str(record.get("relevance_level")),
                    "source_file": _as_str(record.get("source_file")),
                },
            )
        )

    for index, record in enumerate(evidence.get("metabolome_context") or [], start=1):
        summary = _as_str(record.get("preview_text") or record.get("summary") or record.get("text"))
        if not summary:
            continue

        sources.append(
            CitationSource(
                citation_id=_as_str(record.get("evidence_id")) or f"M{index}",
                source_type="metabolome_context",
                text=summary,
                metadata=dict(record),
            )
        )

    for index, record in enumerate(evidence.get("genome_context") or [], start=1):
        summary = _as_str(record.get("summary") or record.get("text"))
        if not summary:
            continue

        sources.append(
            CitationSource(
                citation_id=_as_str(record.get("evidence_id")) or f"G{index}",
                source_type="genome_context",
                text=summary,
                metadata=dict(record),
            )
        )

    for index, record in enumerate(evidence_pack.get("background_literature_records") or [], start=1):
        quoted_sentence = _as_str(record.get("quoted_sentence"))
        title = _as_str(record.get("title"))
        pmid = _as_str(record.get("pmid"))
        doi = _as_str(record.get("doi"))
        if not (title or quoted_sentence or doi or pmid):
            continue

        text = (
            f"PubMed 背景文献 {title or '未命名文献'} "
            f"(PMID {pmid or 'N/A'}; DOI {doi or 'N/A'})"
        )
        if quoted_sentence:
            text += f" 的摘要句为：{quoted_sentence}"

        sources.append(
            CitationSource(
                citation_id=_as_str(record.get("citation_id")) or f"BG{index}",
                source_type="background_literature",
                text=text,
                metadata={
                    "doi": doi,
                    "pmid": pmid,
                    "quoted_sentence": quoted_sentence,
                    "title": title,
                    "url": _as_str(record.get("url")),
                    "source": _as_str(record.get("source")) or "PubMed",
                    "query": _as_str(record.get("query")),
                    "quote_scope": _as_str(record.get("quote_scope")),
                    "relevance_level": _as_str(record.get("relevance_level")) or "background",
                },
            )
        )

    return sources


# 从 literature source 中提取前端可展示的文献卡片字段，后续可直接用于展示方案的文献证据卡片
def build_literature_cards(sources: list[CitationSource]) -> list[dict[str, Any]]:
    """从 citation sources 中提取前端文献卡片。"""

    cards: list[dict[str, Any]] = []

    for source in sources:
        if source.source_type not in {"literature", "background_literature"}:
            continue

        cards.append(
            {
                "citation_id": source.citation_id,
                "doi": source.metadata.get("doi", ""),
                "pmid": source.metadata.get("pmid", ""),
                "quoted_sentence": source.metadata.get("quoted_sentence", ""),
                "abstract_sentence": source.metadata.get("quoted_sentence", ""),
                "title": source.metadata.get("title", ""),
                "relevance_level": source.metadata.get("relevance_level", ""),
                "source": source.metadata.get("source", "") or source.source_type,
                "url": source.metadata.get("url", ""),
                "source_file": source.metadata.get("source_file", ""),
            }
        )

    return cards


def _trait_guidance(trait: str) -> list[str]:
    normalized = _as_str(trait).lower()
    if "黄酮" in normalized or "flavonoid" in normalized:
        return [
            "围绕黄酮含量、黄酮生物合成通路和关键调控因子组织建议。",
            "强调候选基因筛选、代谢通路定位和群体关联验证。",
        ]
    if "抗旱" in normalized or "drought" in normalized:
        return [
            "围绕抗旱表型、胁迫处理、根系性状和水分利用效率组织建议。",
            "强调 abiotic stress 场景下的候选基因验证和群体验证。",
        ]
    if "高产" in normalized or "yield" in normalized or "产量" in normalized:
        return [
            "围绕穗粒数、粒重、株型和 grain yield 相关表型组织建议。",
            "强调多环境比较、产量构成因子拆解和群体验证。",
        ]
    return ["围绕当前目标性状组织候选基因筛选、背景文献查证和后续验证建议。"]


def _summarize_input_availability(evidence_pack: dict[str, Any]) -> str:
    debug_inputs = ((evidence_pack.get("debug") or {}).get("inputs") or {})
    targets = evidence_pack.get("targets") or {}
    evidence = evidence_pack.get("evidence") or {}
    transcriptome_exists = bool(debug_inputs.get("transcriptome_path_exists")) or bool(
        targets.get("genes") or evidence.get("transcriptome")
    )
    metabolome_exists = bool(debug_inputs.get("metabolome_path_exists")) or bool(
        evidence.get("metabolome_context")
    )
    evidence_level = _as_str(debug_inputs.get("evidence_level"))

    lines = [
        f"- transcriptome_path_exists={transcriptome_exists}",
        f"- metabolome_path_exists={metabolome_exists}",
        f"- evidence_level={evidence_level or 'unknown'}",
    ]

    if not transcriptome_exists:
        lines.append("- 当前未读取到有效的转录组差异基因结果。")
    if not metabolome_exists:
        lines.append("- 当前未读取到有效的代谢组结果文件。")
    if evidence_level == "default_smoke_data":
        lines.append("- 当前读取的是默认 smoke 数据包，不代表用户本轮上传了新组学文件。")

    return "\n".join(lines)


def _format_pubmed_background_records(evidence_pack: dict[str, Any]) -> str:
    records = evidence_pack.get("background_literature_records") or []
    if not records:
        return "- 未检索到 PubMed 背景文献线索。"

    lines = []
    for index, record in enumerate(records[:5], start=1):
        parts = [
            f"{index}. title={_as_str(record.get('title')) or 'N/A'}",
            f"pmid={_as_str(record.get('pmid')) or 'N/A'}",
            f"doi={_as_str(record.get('doi')) or 'N/A'}",
            f"query={_as_str(record.get('query')) or 'N/A'}",
        ]
        quoted = _as_str(record.get("quoted_sentence"))
        if quoted:
            parts.append(f"abstract_sentence={quoted}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _format_citation_sources(sources: list[CitationSource], source_type: str) -> str:
    filtered = [source for source in sources if source.source_type == source_type]
    if not filtered:
        return "- 无"
    return "\n".join(f"- [{source.citation_id}] {source.text}" for source in filtered[:6])


def _smoke_context_primary_gene(evidence_pack: dict[str, Any]) -> str:
    return _as_str((((evidence_pack.get("debug") or {}).get("smoke_context") or {}).get("primary_gene_id")))


def _is_flavonoid_trait(trait: str) -> bool:
    normalized = _as_str(trait).lower()
    return "黄酮" in normalized or "flavonoid" in normalized


def _build_structured_analysis_sections(
    *,
    evidence_pack: dict[str, Any],
    literature_cards: list[dict[str, Any]],
) -> str:
    task = evidence_pack.get("task") or {}
    targets = evidence_pack.get("targets") or {}
    debug_inputs = ((evidence_pack.get("debug") or {}).get("inputs") or {})
    background_records = evidence_pack.get("background_literature_records") or []

    trait = _as_str(task.get("trait"))
    question = _as_str(task.get("question"))
    target_genes = [str(item).strip() for item in (targets.get("genes") or []) if str(item).strip()]
    smoke_primary_gene = _smoke_context_primary_gene(evidence_pack)
    transcriptome_exists = bool(debug_inputs.get("transcriptome_path_exists")) or bool(target_genes)
    metabolome_exists = bool(debug_inputs.get("metabolome_path_exists"))
    data_source = _as_str(debug_inputs.get("data_source") or debug_inputs.get("evidence_level"))
    evidence_level = _as_str(debug_inputs.get("evidence_level"))

    input_lines = [
        "## 当前输入与证据状态",
        f"- 性状：{trait or '未指定'}",
        f"- 用户问题：{question or '未指定'}",
        f"- 数据来源：{data_source or 'unknown'}",
        f"- transcriptome_path_exists={transcriptome_exists}",
        f"- metabolome_path_exists={metabolome_exists}",
        f"- background_literature_count={len(background_records)}",
    ]

    candidate_lines = ["## 候选基因与当前判断"]
    if transcriptome_exists and target_genes:
        candidate_lines.append(
            f"- 当前已从转录组差异结果中提取候选基因：{', '.join(target_genes)}。"
        )
    elif _is_flavonoid_trait(trait) and smoke_primary_gene:
        candidate_lines.append(
            f"- 当前未读取到真实 DEG 结果；{smoke_primary_gene} 仅来自默认 smoke 数据包的局部区域上下文线索，不应表述为已被差异表达证据证明。 [G1]"
        )
    else:
        candidate_lines.append(
            "- 当前未读取到可确认候选基因的真实转录组差异结果，因此本轮建议以代谢组文件存在性和 PubMed 背景线索为主。"
        )

    if evidence_level == "default_smoke_data":
        candidate_lines.append(
            "- 当前演示使用默认 smoke 数据目录，适合说明分析链路，不等同于用户已上传并跑通完整多组学正式数据。"
        )

    literature_lines = ["## 文献依据"]
    if literature_cards:
        for card in literature_cards[:3]:
            identifier = _as_str(card.get("doi")) or _as_str(card.get("pmid")) or "未检索到可用文献标识"
            identifier_label = "DOI" if _as_str(card.get("doi")) else ("PMID" if _as_str(card.get("pmid")) else "标识")
            quote = _as_str(card.get("quoted_sentence") or card.get("abstract_sentence"))
            literature_lines.extend(
                [
                    f"### {card.get('citation_id') or '文献'}",
                    f"- title: {_as_str(card.get('title')) or 'N/A'}",
                    f"- {identifier_label}: {identifier}",
                    f"- source: {_as_str(card.get('source')) or 'N/A'}",
                    f"- 引用原文: {quote or '未检索到可展示摘要句'}",
                ]
            )
    else:
        literature_lines.append("- 当前未检索到可展示的 DOI/PMID 文献依据。")

    advice_lines = ["## 育种建议"]
    if _is_flavonoid_trait(trait):
        if transcriptome_exists and target_genes:
            advice_lines.append(
                f"- 可优先围绕 {target_genes[0]} 及其邻近通路基因，结合黄酮含量分层材料开展候选位点筛选。"
            )
        elif smoke_primary_gene:
            advice_lines.append(
                f"- 在黄酮相关演示场景下，可将 {smoke_primary_gene} 作为待验证候选基因线索，先在不同群体材料中检查其基因型与黄酮表型分化是否一致。"
            )
        advice_lines.append(
            "- 结合代谢组文件中黄酮相关化合物丰度分层结果，优先筛选与黄酮积累方向一致的材料进入后续验证。"
        )
    else:
        advice_lines.append("- 建议优先围绕当前性状相关的候选基因、代谢表型和背景文献线索制定验证顺序。")

    validation_lines = [
        "## 后续群体验证建议",
        "- 建议在群体层面结合目标性状表型、候选基因基因型和必要的表达检测开展关联验证，先做群体验证，再决定是否进入湿实验或标记开发。",
    ]

    boundary_lines = ["## 边界说明"]
    if not transcriptome_exists:
        boundary_lines.append("- 当前未读取到真实 DEG 文件，因此不能宣称已完成候选基因的转录组证据确认。")
    boundary_lines.append("- PubMed 文献在本轮中仅作为背景文献线索，不等同于已经直接验证当前候选基因。")
    boundary_lines.append("- 本轮输出不代表已完成群体验证、湿实验验证或最终 KASP/CAPS 标记开发。")

    return "\n".join(
        [
            *input_lines,
            "",
            *candidate_lines,
            "",
            *literature_lines,
            "",
            *advice_lines,
            "",
            *validation_lines,
            "",
            *boundary_lines,
        ]
    )


def build_breeding_analysis_prompt(
    *,
    evidence_pack: dict[str, Any],
    question: str,
    sources: list[CitationSource],
) -> dict[str, str]:
    task = evidence_pack.get("task") or {}
    targets = evidence_pack.get("targets") or {}
    trait = _as_str(task.get("trait"))
    target_genes = targets.get("genes") or []
    smoke_primary_gene = _smoke_context_primary_gene(evidence_pack)
    flavonoid_trait = _is_flavonoid_trait(trait)

    system_prompt = "\n".join(
        [
            "你是 YuXi 育种工作台中的多组学育种分析助手。",
            "你必须只基于提供的证据摘要、已验证文献证据和 PubMed 背景文献线索生成 answer_markdown。",
            "不要编造 DOI。",
            "不要编造 quoted_sentence。",
            "不要声称已完成群体验证、湿实验验证或最终 KASP/CAPS 标记开发。",
            "如果没有真实组学输入文件，必须明确说明当前未读取到有效组学结果。",
            "PubMed 记录只能作为背景文献线索，不得表述成已完成的直接实验证据。",
            "正文可以引用 PMID/DOI 作为背景文献标识，但不得编造未提供的编号或原句。",
            "必须提出后续群体验证建议。",
            "如果 trait 为黄酮相关且转录组候选基因为空，但 smoke context primary gene 存在，只能把该基因写成演示上下文线索，不能写成已由 DEG 证据确认。",
        ]
    )

    user_prompt = "\n".join(
        [
            f"目标性状 trait: {trait or '未指定'}",
            f"用户问题 question: {_as_str(question) or _as_str(task.get('question')) or '未指定'}",
            f"候选基因列表: {', '.join(target_genes) if target_genes else '当前为空'}",
            "输入可用性：",
            _summarize_input_availability(evidence_pack),
            "转录组证据摘要：",
            _format_citation_sources(sources, "transcriptome"),
            "代谢组证据摘要：",
            _format_citation_sources(sources, "metabolome_context"),
            "已验证文献证据摘要：",
            _format_citation_sources(sources, "literature"),
            "PubMed 背景文献线索：",
            _format_pubmed_background_records(evidence_pack),
            f"smoke context primary gene: {smoke_primary_gene or 'N/A'}",
            "针对当前性状的建议偏向：",
            *[f"- {item}" for item in _trait_guidance(trait)],
            "输出要求：",
            "- 使用 Markdown 输出，至少包含：当前输入与证据状态、候选基因/候选方向、文献依据、育种建议、后续验证建议、边界说明。",
            "- 如果未读取到有效转录组结果，要明确说明无法确认候选基因，只能给出后续分析和验证建议。",
            "- 如果 trait 是黄酮相关且 smoke context primary gene 为 Si9g037800，请明确写出 Si9g037800，但同时说明它只是 smoke 数据上下文线索，不是已确认 DEG 证据。",
            "- 如果 PubMed 有背景文献，请说明检索到的条数以及这些记录更像背景线索而非直接实验证据。",
            "- 文献依据部分必须引用真实 DOI 或 PMID、title，以及来自 literature_cards 的 quoted_sentence 或 abstract sentence。",
            "- 不要输出内部推理过程。",
        ]
    )

    return {"system_prompt": system_prompt, "user_prompt": user_prompt}


def generate_llm_breeding_analysis(
    *,
    evidence_pack: dict[str, Any],
    question: str,
    sources: list[CitationSource],
    model_name: str,
    fallback_enabled: bool = True,
) -> dict[str, Any]:
    prompt = build_breeding_analysis_prompt(
        evidence_pack=evidence_pack,
        question=question,
        sources=sources,
    )

    try:
        if not _as_str(model_name):
            raise ValueError("No model configured for omics breeding analysis.")

        model = load_chat_model(fully_specified_name=model_name)
        response = model.invoke(
            [
                SystemMessage(content=prompt["system_prompt"]),
                HumanMessage(content=prompt["user_prompt"]),
            ]
        )
        answer_markdown = response.content if hasattr(response, "content") else str(response)
        answer_markdown = _as_str(answer_markdown)
        if not answer_markdown:
            raise ValueError("LLM returned empty analysis markdown.")
        return {
            "backend": "llm",
            "answer_markdown": answer_markdown,
            "warnings": [],
            "prompt": prompt,
        }
    except Exception as exc:  # noqa: BLE001
        if not fallback_enabled:
            raise

        return {
            "backend": "rule_fallback",
            "answer_markdown": build_mock_cited_answer(
                evidence_pack=evidence_pack,
                sources=sources,
            ),
            "warnings": [f"LLM analysis fallback: {type(exc).__name__}: {exc}"],
            "prompt": prompt,
        }


# fallback，不冒充真实 LlamaIndex。它只负责在本地未安装 LlamaIndex 或暂时不想调用 LLM 时，生成一个可测试、有 citation 标识的回答
def build_mock_cited_answer(
    *,
    evidence_pack: dict[str, Any],
    sources: list[CitationSource],
) -> str:
    """构建 deterministic fallback 回答。

    这个 fallback 不冒充 LlamaIndex，也不冒充真实 LLM。
    它只用于：
    - 本地未安装 LlamaIndex 时的可测试输出；
    - 后续前端展示结构联调；
    - Guard 前置验证。
    """

    del sources
    return "\n".join(
        [
            "# 多组学育种分析结果",
            "",
            "当前未命中可用的在线 LLM 分析，因此以下内容基于现有 Evidence Pack 做规则化汇总。",
            "",
            _build_structured_analysis_sections(
                evidence_pack=evidence_pack,
                literature_cards=build_literature_cards(build_citation_sources(evidence_pack)),
            ),
        ]
    )


# 把回答拆成简单 claim，并记录每条 claim 是否含有 [T1] / [L1] 这类 citation。TODO：后续如果老师要求“逗号级短句”，可以继续改这里
def build_claim_trace(
    *,
    answer_markdown: str,
    sources: list[CitationSource],
) -> list[dict[str, Any]]:
    """构建简化 claim_trace。

    第一版按句号和换行做粗粒度拆分。
    后续如果老师要求短句级，可在这里扩展为逗号级拆分。
    """

    source_ids = [source.citation_id for source in sources]
    raw_segments = []

    for line in answer_markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        raw_segments.extend([part.strip() for part in line.split("。") if part.strip()])

    trace: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments, start=1):
        cited_ids = [source_id for source_id in source_ids if f"[{source_id}]" in segment]
        trace.append(
            {
                "claim_id": f"C{index}",
                "text": segment,
                "citation_ids": cited_ids,
                "source_status": "supported" if cited_ids else "uncited",
            }
        )

    return trace

def _split_answer_into_claim_segments(answer_markdown: str) -> list[str]:
    """将回答拆成 claim 片段，并尽量保留紧跟在句号后的 citation 标记。

    支持常见形式：
    - GeneA 是候选基因。[T1]
    - GeneA 是候选基因。[T1, L1]
    - GeneA 是候选基因[T1]。
    """

    segments: list[str] = []

    for line in answer_markdown.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = [part.strip() for part in line.split("。") if part.strip()]

        for part in parts:
            # 如果当前 part 只是 citation 标记，例如 [T1] 或 [T1, L1]，
            # 则把它合并到上一条 claim 上。
            if (
                segments
                and part.startswith("[")
                and part.endswith("]")
                and len(part) <= 80
            ):
                segments[-1] = f"{segments[-1]} {part}"
            else:
                segments.append(part)

    return segments

# 修改 build_claim_trace() 的拆句逻辑：
# 修改前：GeneA 是候选基因。[T1]
# 被拆成：["GeneA 是候选基因", "[T1]"]
#
# 修改后会合并成：["GeneA 是候选基因 [T1]"]
# 于是：f"[T1]" in segment 就能识别成功。
def build_claim_trace(
    *,
    answer_markdown: str,
    sources: list[CitationSource],
) -> list[dict[str, Any]]:
    """构建简化 claim_trace。

    第一版按句号和换行做粗粒度拆分。
    如果 citation 标记紧跟在句号后，例如“GeneA 是候选基因。[T1]”，
    会把 [T1] 归并到前一句 claim。
    """

    source_ids = [source.citation_id for source in sources]
    raw_segments = _split_answer_into_claim_segments(answer_markdown)

    trace: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments, start=1):
        cited_ids = [source_id for source_id in source_ids if f"[{source_id}]" in segment]
        trace.append(
            {
                "claim_id": f"C{index}",
                "text": segment,
                "citation_ids": cited_ids,
                "source_status": "supported" if cited_ids else "uncited",
            }
        )

    return trace



# 是真实 LlamaIndex 接入口，但当前不会在测试中强制调用。这样做可以避免本地环境没装 LlamaIndex 或没有模型配置时测试失败
def query_with_llamaindex(
    *,
    evidence_pack: dict[str, Any],
    question: str,
    sources: list[CitationSource],
) -> dict[str, Any]:
    """使用 LlamaIndex CitationQueryEngine 生成回答。

    当前只在 LlamaIndex 可用时运行。
    如果环境未安装 LlamaIndex，调用方应使用 fallback。
    """

    if not LLAMAINDEX_AVAILABLE:
        raise RuntimeError("LlamaIndex is not available in current environment.")

    documents = [
        Document(
            text=source.text,
            metadata={
                "citation_id": source.citation_id,
                "source_type": source.source_type,
                **source.metadata,
            },
        )
        for source in sources
    ]

    if not documents:
        raise RuntimeError("No citation documents were generated for LlamaIndex.")

    if _as_str(question):
        query_text = question
    else:
        task = evidence_pack.get("task") or {}
        query_text = _as_str(task.get("question")) or _as_str(task.get("trait")) or "请总结证据并给出育种建议"

    # 当前优先使用全局默认 Settings；如果部署环境已配置 LlamaIndex LLM/embedding，即可直接接通。
    # 若环境缺默认模型或 embedding，调用方会回退到现有 LLM/rule_fallback 主线。
    index = VectorStoreIndex.from_documents(documents)
    query_engine = CitationQueryEngine.from_args(index, similarity_top_k=min(6, len(documents)))
    response = query_engine.query(query_text)

    answer_markdown = str(response)

    return {
        "citation_backend": "llamaindex_citation_query_engine",
        "llamaindex_available": True,
        "answer_markdown": answer_markdown,
        "raw_response": answer_markdown,
        "source_nodes": [
            {
                "score": getattr(node, "score", None),
                "text": _as_str(getattr(getattr(node, "node", None), "text", "")),
                "metadata": dict(getattr(getattr(node, "node", None), "metadata", {}) or {}),
            }
            for node in getattr(response, "source_nodes", []) or []
        ],
    }


# 统一入口，返回正好对应后续前端方案需要的结构
def build_citation_result(
    *,
    evidence_pack: dict[str, Any],
    question: str,
    use_llamaindex: bool = False,
    model_name: str = "",
) -> dict[str, Any]:
    """生成 Citation 结果。

    第一版策略：
    - 默认使用 deterministic fallback，便于本地测试；
    - 当 use_llamaindex=True 且 LlamaIndex 可用时，走 CitationQueryEngine；
    - 无论使用哪个 backend，都返回统一结构。
    """

    sources = build_citation_sources(evidence_pack)

    citation_backend = "llamaindex_disabled"
    disabled_reason = ""
    source_nodes: list[dict[str, Any]] = []
    if use_llamaindex and LLAMAINDEX_AVAILABLE:
        try:
            llamaindex_result = query_with_llamaindex(
                evidence_pack=evidence_pack,
                question=question,
                sources=sources,
            )
            citation_backend = llamaindex_result["citation_backend"]
            source_nodes = llamaindex_result.get("source_nodes") or []
        except Exception as exc:  # noqa: BLE001
            citation_backend = "llamaindex_runtime_fallback"
            disabled_reason = f"{type(exc).__name__}: {exc}"
    elif use_llamaindex and not LLAMAINDEX_AVAILABLE:
        citation_backend = "llamaindex_missing_fallback"
        disabled_reason = "missing_dependency"

    engine_result = generate_llm_breeding_analysis(
        evidence_pack=evidence_pack,
        question=question,
        sources=sources,
        model_name=model_name,
        fallback_enabled=True,
    )
    backend = engine_result["backend"]
    answer_markdown = engine_result["answer_markdown"]

    citations = [
        {
            "citation_id": source.citation_id,
            "source_type": source.source_type,
            "text": source.text,
            "metadata": source.metadata,
        }
        for source in sources
    ]

    claim_trace = build_claim_trace(
        answer_markdown=answer_markdown,
        sources=sources,
    )
    literature_cards = build_literature_cards(sources)
    answer_markdown = "\n\n".join(
        [
            answer_markdown.strip(),
            _build_structured_analysis_sections(
                evidence_pack=evidence_pack,
                literature_cards=literature_cards,
            ),
        ]
    ).strip()
    claim_trace = build_claim_trace(
        answer_markdown=answer_markdown,
        sources=sources,
    )

    return {
        "backend": backend,
        "citation_backend": citation_backend,
        "llamaindex_available": LLAMAINDEX_AVAILABLE,
        "answer_markdown": answer_markdown,
        "citations": citations,
        "literature_cards": literature_cards,
        "claim_trace": claim_trace,
        "source_nodes": source_nodes,
        "disabled_reason": disabled_reason,
        "warnings": [
            *(engine_result.get("warnings") or []),
            *([f"Citation backend fallback: {disabled_reason}"] if disabled_reason else []),
        ],
        "analysis_prompt": engine_result.get("prompt") or {},
    }
