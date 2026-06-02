from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from langchain.messages import HumanMessage, SystemMessage

from yuxi.agents import load_chat_model

"""
citation 生成层 / 证据匹配层 / 逐句溯源逻辑层

拿到 Evidence Pack
  ↓
根据证据生成或校验 citation
  ↓
把回答中的句子和 T1/M1/BG/Guard 绑定
  ↓
生成 citations / claim_trace / sources

在数据流中的位置
Evidence Pack
  ↓
citation_engine.py
  ↓
claim_trace / citations
  ↓
presentation.py / workflow.py
"""

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


def _has_real_background_literature_evidence(record: dict[str, Any]) -> bool:
    quoted_sentence = _as_str(record.get("quoted_sentence"))
    if not quoted_sentence:
        return False
    return any(
        _as_str(record.get(field))
        for field in ("pmid", "doi", "title", "url")
    )


def _format_citation_suffix(citation_ids: list[str]) -> str:
    normalized = [str(item).strip() for item in citation_ids if str(item).strip()]
    if not normalized:
        return ""
    return "".join(f"[{citation_id}]" if index == 0 else f" [{citation_id}]" for index, citation_id in enumerate(normalized))


def _citation_ids_by_type(sources: list["CitationSource"]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for source in sources:
        grouped.setdefault(source.source_type, []).append(source.citation_id)
    return grouped


def build_citation_sources(evidence_pack: dict[str, Any]) -> list[CitationSource]:
    """将 Evidence Pack 转为 citation source 列表。

    当前支持：
    - transcriptome records -> T1, T2...
    - annotation evidence -> A1
    - literature records -> L1, L2...
    - metabolome_context -> M1, M2...
    - genome_context -> G1, G2...

    注意：
    - 这里不生成最终回答；
    - 这里只整理 citation 可用的来源文本；
    - DOI 和 quoted_sentence 必须来自 Evidence Pack。
    """

    evidence = evidence_pack.get("evidence") or {}
    debug_inputs = ((evidence_pack.get("debug") or {}).get("inputs") or {})
    sources: list[CitationSource] = []

    for index, record in enumerate(evidence.get("transcriptome") or [], start=1):
        gene_id = _as_str(record.get("gene_id"))
        if not gene_id:
            continue

        logfc = _as_str(record.get("logfc"))
        pvalue = _as_str(record.get("pvalue"))
        padj = _as_str(record.get("padj"))
        source_file = _as_str(record.get("source_file"))
        annotation = _as_str(record.get("annotation") or record.get("description"))

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
                    "annotation": annotation,
                },
            )
        )

    for index, record in enumerate(evidence.get("annotation") or [], start=1):
        metadata = dict(record.get("metadata") or {})
        candidate_annotations = list(metadata.get("candidate_annotations") or [])
        if not candidate_annotations:
            continue
        gene_ids = metadata.get("annotation_candidate_gene_ids") or [
            item.get("gene_id") for item in candidate_annotations if item.get("gene_id")
        ]
        pathway_summary = metadata.get("pathway_summary") or []
        source_file = _as_str(record.get("source_file") or metadata.get("annotation_file"))
        text_parts = [
            "用户上传功能注释文件按 gene_id 与 DEG 结果关联。",
            f"匹配候选基因数：{int(metadata.get('annotation_gene_match_count') or len(candidate_annotations))}。",
        ]
        if gene_ids:
            text_parts.append(f"匹配基因：{', '.join(str(item) for item in gene_ids[:8])}。")
        if pathway_summary:
            text_parts.append(f"关键通路/功能术语：{', '.join(str(item) for item in pathway_summary[:8])}。")
        sources.append(
            CitationSource(
                citation_id=_as_str(record.get("evidence_id")) or f"A{index}",
                source_type="annotation",
                text="".join(text_parts),
                metadata={
                    **metadata,
                    "source_file": source_file,
                    "annotation_file": source_file,
                    "evidence_role": "功能注释线索，不等同于功能验证",
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
        summary = _as_str(record.get("summary") or record.get("text"))
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

    transcriptome_input_status = _as_str(debug_inputs.get("transcriptome_input_status"))
    rnaseq_read_count = int(debug_inputs.get("rnaseq_read_count") or 0)
    transcriptome_supporting_input_exists = bool(
        debug_inputs.get("transcriptome_supporting_input_exists")
    )
    transcriptome_exists = bool(debug_inputs.get("transcriptome_path_exists")) or bool(
        evidence.get("transcriptome")
    )
    if not transcriptome_exists and (
        transcriptome_input_status == "fastq_uploaded" or transcriptome_supporting_input_exists
    ):
        if rnaseq_read_count > 0:
            text = (
                f"已上传 {rnaseq_read_count} 个 FASTQ 文件及转录组辅助输入，但尚未生成 "
                "significant_de_genes.tsv。"
            )
        else:
            text = "已上传转录组辅助输入，但尚未生成 significant_de_genes.tsv。"
        sources.append(
            CitationSource(
                citation_id="T-input",
                source_type="transcriptome_input",
                text=text,
                metadata={
                    "transcriptome_input_status": transcriptome_input_status,
                    "rnaseq_read_count": rnaseq_read_count,
                },
            )
        )

    for index, record in enumerate(evidence_pack.get("background_literature_records") or [], start=1):
        if not _has_real_background_literature_evidence(record):
            continue
        quoted_sentence = _as_str(record.get("quoted_sentence"))
        title = _as_str(record.get("title"))
        pmid = _as_str(record.get("pmid"))
        doi = _as_str(record.get("doi"))

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

    sources.append(
        CitationSource(
            citation_id="Guard",
            source_type="guard_rule",
            text="不声称已完成湿实验、群体验证或最终 KASP/CAPS 标记开发。",
            metadata={
                "rule": "no_overclaiming",
                "scope": "boundary",
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
                "quote_scope": source.metadata.get("quote_scope", "")
                or ("abstract" if source.source_type == "background_literature" else ""),
                "title": source.metadata.get("title", ""),
                "relevance_level": source.metadata.get("relevance_level", ""),
                "source": source.metadata.get("source", "") or source.source_type,
                "url": source.metadata.get("url", ""),
                "source_file": source.metadata.get("source_file", ""),
            }
        )

    return cards


def _contains_flavonoid_keyword(text: str) -> bool:
    normalized = _as_str(text).lower()
    return any(keyword in normalized for keyword in ["黄酮", "flavonoid", "苯丙烷"])


def _transcriptome_sources(sources: list[CitationSource]) -> list[CitationSource]:
    return [source for source in sources if source.source_type == "transcriptome"]


def _metabolome_sources(sources: list[CitationSource]) -> list[CitationSource]:
    return [source for source in sources if source.source_type == "metabolome_context"]


def _annotation_sources(sources: list[CitationSource]) -> list[CitationSource]:
    return [source for source in sources if source.source_type == "annotation"]


def _background_sources(sources: list[CitationSource]) -> list[CitationSource]:
    return [source for source in sources if source.source_type == "background_literature"]


def _guard_sources(sources: list[CitationSource]) -> list[CitationSource]:
    return [source for source in sources if source.source_type == "guard_rule"]


def _pick_primary_gene(evidence_pack: dict[str, Any], sources: list[CitationSource]) -> str:
    targets = evidence_pack.get("targets") or {}
    target_genes = [str(item).strip() for item in (targets.get("genes") or []) if str(item).strip()]
    if target_genes:
        return target_genes[0]

    transcriptome = _transcriptome_sources(sources)
    if transcriptome:
        return _as_str(transcriptome[0].metadata.get("gene_id"))

    evidence_level = _as_str((((evidence_pack.get("debug") or {}).get("inputs") or {}).get("evidence_level")))
    smoke_primary_gene = _smoke_context_primary_gene(evidence_pack)
    if evidence_level == "default_smoke_data" and smoke_primary_gene:
        return smoke_primary_gene

    return ""


def _parse_preview_table_rows(record: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    preview_rows = record.get("preview_rows") or []
    if not preview_rows:
        preview_text = _as_str(record.get("preview_text"))
        preview_rows = [line for line in preview_text.splitlines() if line.strip()]
    if not preview_rows:
        return [], []

    parsed_rows = [[cell.strip() for cell in row.split("\t")] for row in preview_rows if row.strip()]
    if len(parsed_rows) < 2:
        return [], []
    return parsed_rows[0], parsed_rows[1:]


def _find_column_index(headers: list[str], aliases: tuple[str, ...]) -> int | None:
    normalized_headers = [header.strip().lower() for header in headers]
    for alias in aliases:
        if alias in normalized_headers:
            return normalized_headers.index(alias)
    for index, header in enumerate(normalized_headers):
        if any(alias in header for alias in aliases):
            return index
    return None


def _summarize_metabolome_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": _as_str(record.get("source_file")),
        "total_records": int(record.get("total_record_count") or record.get("row_count") or record.get("preview_row_count") or 0),
        "significant_records": int(record.get("significant_record_count") or 0),
        "top_metabolites": list(record.get("top_metabolites") or []),
        "trait_relevance_note": _as_str(record.get("trait_relevance_note")),
    }


def _summarize_annotation_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": _as_str(record.get("annotation_file") or record.get("source_file")),
        "annotated_transcriptome_path": _as_str(record.get("annotated_transcriptome_path")),
        "match_count": int(record.get("annotation_gene_match_count") or 0),
        "unmatched_count": int(record.get("annotation_unmatched_gene_count") or 0),
        "duplicate_gene_id_count": int(record.get("annotation_duplicate_gene_id_count") or 0),
        "isoform_count": int(record.get("annotation_isoform_count") or 0),
        "candidate_annotations": list(record.get("candidate_annotations") or []),
        "pathway_summary": list(record.get("pathway_summary") or []),
        "pubmed_query_terms": list(record.get("pubmed_query_terms") or []),
    }


def _clean_annotation_display_value(value: Any) -> str:
    text = _as_str(value)
    if not text:
        return ""
    lower = text.lower()
    if lower in {"http:", "https:"}:
        return ""
    if any(token in lower for token in ("dbget-bin", "www_bget", "url 片段")):
        return ""
    if lower.startswith(("http://", "https://", "www.")) or "genome.jp" in lower:
        return ""
    if text in {"[X]", "X", "-", "--", "NA", "N/A", "none", "None"}:
        return ""
    if "unnamed protein" in lower or "uncharacterized protein" in lower:
        return ""
    return text


def _clean_annotation_display_values(value: Any) -> list[str]:
    values: list[str] = []
    for item in re.split(r"\s*\|\s*|\s*;\s*", _as_str(value)):
        cleaned = _clean_annotation_display_value(item)
        if cleaned and cleaned not in values:
            values.append(cleaned)
    return values


def _normalize_annotation_field_values(field_name: str, value: Any) -> list[str]:
    cleaned_values = _clean_annotation_display_values(value)
    if _as_str(field_name).lower() == "ko":
        normalized_values = []
        for item in cleaned_values:
            normalized = re.sub(r"(?i)^ko\s*:\s*", "", item).strip()
            if normalized and normalized not in normalized_values:
                normalized_values.append(normalized)
        return normalized_values
    return cleaned_values


def _first_annotation_field(annotation_fields: dict[str, Any], names: tuple[str, ...]) -> list[str]:
    normalized_names = {name.lower() for name in names}
    for key, value in annotation_fields.items():
        if _as_str(key).lower() in normalized_names:
            values = _normalize_annotation_field_values(key, value)
            if values:
                return values
    return []


def _format_annotation_candidate_detail(candidate: dict[str, Any]) -> str:
    gene_id = _as_str(candidate.get("gene_id")) or "N/A"
    annotation_fields = candidate.get("annotation_fields") or {}
    if not isinstance(annotation_fields, dict):
        annotation_fields = {}

    nr_function_values = (
        _first_annotation_field(annotation_fields, ("NR_annotation", "nr_annotation"))
        or _first_annotation_field(annotation_fields, ("annotation", "description", "function"))
    )
    swissprot_function_values = _first_annotation_field(annotation_fields, ("SwissProt_annotation",))
    function_values = (
        nr_function_values
        or swissprot_function_values
        or _first_annotation_field(annotation_fields, ("TrEMBL_annotation",))
    )
    trembl_function_values = _first_annotation_field(annotation_fields, ("TrEMBL_annotation",))
    ko_values = _first_annotation_field(annotation_fields, ("KO",))
    kegg_name_values = _first_annotation_field(annotation_fields, ("KEGG_gene_name",))
    kegg_pathway_values = _first_annotation_field(
        annotation_fields,
        ("KEGG_Pathway", "KeGG_Pathway"),
    )
    pathway_definition_values = _first_annotation_field(
        annotation_fields,
        ("Pathway_defination", "Pathway_definition"),
    )
    go_values = _first_annotation_field(annotation_fields, ("GO_annotation", "GO_IDs"))
    pfam_values = _first_annotation_field(annotation_fields, ("Pfam_Description", "Pfam"))
    interpro_values = _first_annotation_field(
        annotation_fields,
        ("InterPro_Description", "InterPro"),
    )

    lines = [f"- 候选基因：{gene_id}"]
    if function_values:
        lines.append(f"  功能：{'; '.join(function_values[:3])}")
    if swissprot_function_values and swissprot_function_values != function_values:
        lines.append(f"  SwissProt/同源注释：{'; '.join(swissprot_function_values[:3])}")
    if (
        trembl_function_values
        and trembl_function_values != function_values
        and trembl_function_values != swissprot_function_values
    ):
        lines.append(f"  TrEMBL/同源注释：{'; '.join(trembl_function_values[:3])}")
    if ko_values:
        lines.append(f"  KO：{'; '.join(ko_values[:3])}")
    if kegg_name_values:
        lines.append(f"  KEGG gene：{'; '.join(kegg_name_values[:3])}")
    pathway_values = [*kegg_pathway_values, *pathway_definition_values]
    if pathway_values:
        lines.append(f"  KEGG Pathway：{'; '.join(pathway_values[:4])}")
    if go_values:
        lines.append(f"  GO：{'; '.join(go_values[:4])}")
    if pfam_values:
        lines.append(f"  Pfam：{'; '.join(pfam_values[:4])}")
    if interpro_values:
        lines.append(f"  InterPro：{'; '.join(interpro_values[:4])}")
    if len(lines) == 1:
        lines[0] = f"- {_format_annotation_candidate_summary(candidate)}"
    return "\n".join(lines)


def _annotation_highlight_terms(candidate_annotations: list[dict[str, Any]]) -> list[str]:
    highlight_terms: list[str] = []
    for candidate in candidate_annotations:
        if not isinstance(candidate, dict):
            continue
        annotation_fields = candidate.get("annotation_fields") or {}
        if not isinstance(annotation_fields, dict):
            continue
        for field_name in (
            "KEGG_Pathway",
            "KeGG_Pathway",
            "Pathway_defination",
            "Pathway_definition",
            "GO_annotation",
            "GO_IDs",
            "Pfam_Description",
            "Pfam",
            "InterPro_Description",
            "InterPro",
        ):
            for value in _first_annotation_field(annotation_fields, (field_name,)):
                if value not in highlight_terms:
                    highlight_terms.append(value)
    return highlight_terms[:12]


def _format_annotation_candidate_summary(candidate: dict[str, Any]) -> str:
    gene_id = _as_str(candidate.get("gene_id")) or "N/A"
    functions = [
        _clean_annotation_display_value(item)
        for item in (candidate.get("normalized_function_terms") or [])
        if _clean_annotation_display_value(item)
    ][:4]
    pathways = [
        _clean_annotation_display_value(item)
        for item in (candidate.get("pathway_terms") or [])
        if _clean_annotation_display_value(item)
    ][:4]
    domains = [
        _clean_annotation_display_value(item)
        for item in (candidate.get("domain_terms") or [])
        if _clean_annotation_display_value(item)
    ][:3]
    parts = [gene_id]
    if functions:
        parts.append(f"功能={'; '.join(functions)}")
    if pathways:
        parts.append(f"通路={'; '.join(pathways)}")
    if domains:
        parts.append(f"domain={'; '.join(domains)}")
    if _as_str(candidate.get("trait_relevance_level")):
        parts.append(f"trait_relevance={_as_str(candidate.get('trait_relevance_level'))}")
    return " / ".join(parts)


def _build_source_index_sections(sources: list[CitationSource]) -> list[str]:
    lines = ["## 来源索引", ""]
    has_annotation_source = any(source.source_type == "annotation" for source in sources)

    for source in sources:
        metadata = source.metadata or {}
        if source.source_type == "transcriptome":
            annotation_text = _as_str(metadata.get("annotation") or metadata.get("description"))
            if not annotation_text and has_annotation_source:
                annotation_text = "DEG 文件未提供完整功能注释；用户上传功能注释见 [A1]"
            lines.extend(
                [
                    f"[{source.citation_id}] 转录组 DEG",
                    f"文件：{_as_str(metadata.get('source_file')) or 'significant_de_genes.tsv'}",
                    f"基因：{_as_str(metadata.get('gene_id')) or 'N/A'}",
                    f"logFC={_as_str(metadata.get('logfc')) or 'N/A'}",
                    f"padj={_as_str(metadata.get('padj')) or 'N/A'}",
                    f"注释：{annotation_text or '未提供'}",
                    "证据角色：当前实验直接组学证据",
                    "",
                ]
            )
            continue

        if source.source_type == "metabolome_context":
            metabolome_summary = _summarize_metabolome_record(metadata)
            lines.extend(
                [
                    f"[{source.citation_id}] 代谢组",
                    f"文件：{metabolome_summary['source_file'] or 'metabolome_raw_3372.tsv'}",
                    f"总记录数：{metabolome_summary['total_records']}",
                    f"显著差异代谢物数：{metabolome_summary['significant_records']}",
                    "Top 关键代谢物：",
                ]
            )
            if metabolome_summary["top_metabolites"]:
                for item in metabolome_summary["top_metabolites"]:
                    if isinstance(item, dict):
                        leading_parts = []
                        if _as_str(item.get("compound_id")):
                            leading_parts.append(_as_str(item.get("compound_id")))
                        leading_parts.append(_as_str(item.get("name")) or "未提供名称")
                        lines.append(
                            "- "
                            + " / ".join(
                                leading_parts
                                + [
                                    f"Class={_as_str(item.get('class')) or '未提供'}",
                                    f"Log2FC={_as_str(item.get('log2fc')) or 'N/A'}",
                                    f"FDR={_as_str(item.get('fdr')) or 'N/A'}",
                                    f"Type={_as_str(item.get('type')) or 'unknown'}",
                                ]
                            )
                        )
                    else:
                        lines.append(f"- {_as_str(item)}")
            else:
                lines.append("- 当前仅保留摘要，未展示原始 TSV 明细。")
            if metabolome_summary["trait_relevance_note"]:
                lines.append(metabolome_summary["trait_relevance_note"])
            lines.extend(
                [
                    "证据角色：代谢组线索，用于提示黄酮/苯丙烷相关代谢分支可能变化",
                    "",
                ]
            )
            continue

        if source.source_type == "annotation":
            annotation_summary = _summarize_annotation_record(metadata)
            lines.extend(
                [
                    f"[{source.citation_id}] 基因功能注释证据",
                    f"注释文件：{annotation_summary['source_file'] or '未提供'}",
                    "匹配方式：按 gene_id 与 DEG 结果关联；如 DEG 与注释文件同时提供 transcript_id，则记录辅助匹配。",
                    f"匹配基因数量：{annotation_summary['match_count']}",
                    f"未匹配基因数量：{annotation_summary['unmatched_count']}",
                    f"多 isoform / transcript 记录数：{annotation_summary['isoform_count']}",
                    f"duplicate gene_id 数：{annotation_summary['duplicate_gene_id_count']}",
                    f"annotated DEG artifact：{annotation_summary['annotated_transcriptome_path'] or '未生成'}",
                    "候选基因功能注释摘要：",
                ]
            )
            for candidate in annotation_summary["candidate_annotations"][:8]:
                if isinstance(candidate, dict):
                    lines.append(_format_annotation_candidate_detail(candidate))
            if not annotation_summary["candidate_annotations"]:
                lines.append("- 当前无匹配候选注释摘要。")
            pathway_summary = _annotation_highlight_terms(annotation_summary["candidate_annotations"]) or [
                _clean_annotation_display_value(item)
                for item in annotation_summary["pathway_summary"]
                if _clean_annotation_display_value(item)
            ]
            if pathway_summary:
                lines.append(
                    "关键通路 / GO / domain："
                    + ", ".join(str(item) for item in pathway_summary[:12])
                )
            lines.extend(
                [
                    "证据角色：功能注释线索，不等同于功能验证",
                    "",
                ]
            )
            continue

        if source.source_type in {"literature", "background_literature"}:
            label = "PubMed 背景文献" if source.source_type == "background_literature" else "已验证文献证据"
            lines.extend(
                [
                    f"[{source.citation_id}] {label}",
                    f"DOI：{_as_str(metadata.get('doi')) or 'N/A'}",
                    f"PMID：{_as_str(metadata.get('pmid')) or 'N/A'}",
                    f"标题：{_as_str(metadata.get('title')) or '未提供'}",
                    f"引用原句：{_as_str(metadata.get('quoted_sentence')) or '未提供'}",
                    (
                        "证据角色：背景文献，不是当前候选基因直接证据"
                        if source.source_type == "background_literature"
                        else "证据角色：文献支持线索，需与当前实验结果分开解读"
                    ),
                    "",
                ]
            )
            continue

        if source.source_type == "guard_rule":
            lines.extend(
                [
                    f"[{source.citation_id}] 边界规则",
                    "不声称已完成湿实验、群体验证、最终 KASP/CAPS 标记开发。",
                    "",
                ]
            )

    return lines


def build_canonical_cited_answer(
    *,
    evidence_pack: dict[str, Any],
    sources: list[CitationSource],
) -> str:
    task = evidence_pack.get("task") or {}
    trait = _as_str(task.get("trait")) or "未指定"
    target_gene = _pick_primary_gene(evidence_pack, sources)
    target_gene_label = target_gene or "候选基因"
    transcriptome_citations = [source.citation_id for source in _transcriptome_sources(sources)]
    annotation_citations = [source.citation_id for source in _annotation_sources(sources)]
    metabolome_citations = [source.citation_id for source in _metabolome_sources(sources)]
    background_citations = [source.citation_id for source in _background_sources(sources)]
    guard_citations = [source.citation_id for source in _guard_sources(sources)] or ["Guard"]

    transcriptome_exists = bool(transcriptome_citations)
    metabolome_exists = bool(metabolome_citations)
    background_exists = bool(background_citations)
    flavonoid_trait = _contains_flavonoid_keyword(trait)
    metabolome_phrase = "黄酮/苯丙烷相关代谢线索" if flavonoid_trait else "与当前性状相关的代谢线索"
    metabolome_branch_phrase = "黄酮相关代谢分支" if flavonoid_trait else "相关代谢分支"
    transcriptome_source = _transcriptome_sources(sources)[0] if _transcriptome_sources(sources) else None
    metabolome_source = _metabolome_sources(sources)[0] if _metabolome_sources(sources) else None
    annotation_source = _annotation_sources(sources)[0] if _annotation_sources(sources) else None
    transcriptome_annotation = _as_str(
        transcriptome_source.metadata.get("annotation") if transcriptome_source else ""
    )
    transcriptome_logfc = _as_str(transcriptome_source.metadata.get("logfc") if transcriptome_source else "")
    transcriptome_padj = _as_str(transcriptome_source.metadata.get("padj") if transcriptome_source else "")
    metabolome_summary = _summarize_metabolome_record(metabolome_source.metadata) if metabolome_source else {}
    annotation_summary = (
        _summarize_annotation_record(annotation_source.metadata) if annotation_source else {}
    )
    top_metabolites = list(metabolome_summary.get("top_metabolites") or [])
    top_metabolite_names = [
        _as_str(item.get("name") or item.get("compound_id"))
        for item in top_metabolites
        if isinstance(item, dict) and _as_str(item.get("name") or item.get("compound_id"))
    ]

    transcriptome_sentence = (
        f"- 转录组数据已完成固定流程分析，当前从 DEG 结果中提取到候选基因 {target_gene_label}。{_format_citation_suffix(transcriptome_citations[:1])}"
        if transcriptome_exists
        else f"- 当前未读取到可确认候选基因的 DEG 结果，仍需等待当前 run 的转录组结果再确定候选基因。{_format_citation_suffix(guard_citations[:1])}"
    )
    metabolome_sentence = (
        f"- 代谢组数据已可用，检测到{metabolome_phrase}。"
        f"{_format_citation_suffix(metabolome_citations[:1])}"
        if metabolome_exists
        else f"- 当前未读取到可用代谢组结果，尚不能判断{metabolome_branch_phrase}是否变化。{_format_citation_suffix(guard_citations[:1])}"
    )
    background_sentence = (
        "- PubMed 文献仅作为背景线索，不等同于当前实验直接验证。"
        f"{_format_citation_suffix(background_citations[:2] + guard_citations[:1])}"
        if background_exists
        else f"- 当前未检索到可用 PubMed 背景文献。{_format_citation_suffix(guard_citations[:1])}"
    )
    annotation_sentence = (
        f"- 已从用户上传功能注释文件生成 A1 功能注释证据，匹配 {annotation_summary.get('match_count', 0)} 个 DEG 候选基因；这些注释只能作为候选功能线索。{_format_citation_suffix(annotation_citations[:1] + guard_citations[:1])}"
        if annotation_citations
        else f"- 当前未纳入用户上传功能注释证据，不能编造候选基因的 KEGG/GO/Pfam/InterPro 功能解释。{_format_citation_suffix(guard_citations[:1])}"
    )
    if transcriptome_logfc and transcriptome_padj:
        transcriptome_effect_sentence = (
            f"- {target_gene_label} 在当前比较中的差异表达幅度和统计显著性均达到候选筛选阈值，当前 logFC 与 padj 支持其进入优先验证名单。"
            f"{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1])}"
        )
    else:
        transcriptome_effect_sentence = (
            f"- 当前转录组结果已经支持 {target_gene_label} 进入候选清单，但仍需结合后续验证判断其真实育种价值。"
            f"{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1] if transcriptome_exists else guard_citations[:1])}"
        )
    metabolome_boundary_sentence = (
        f"- 代谢组数据已读取，结果提示 {metabolome_phrase}，但这类线索主要用于限定候选通路方向，不替代基因功能验证。{_format_citation_suffix(metabolome_citations[:1] + guard_citations[:1])}"
        if metabolome_exists
        else f"- 当前没有可用于通路方向判断的代谢组摘要，后续仍建议补充代谢层面的独立验证。{_format_citation_suffix(guard_citations[:1])}"
    )

    body_lines = [
        "# 育种建议报告",
        "",
        "## 当前输入与证据状态",
        f"- 目标性状：{trait}。",
        transcriptome_sentence,
        (
            f"- {target_gene_label} 在当前比较中显著{'下调' if transcriptome_logfc.startswith('-') else '变化'}，提示其可能与目标性状相关，但当前仍属于候选线索。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1])}"
            if transcriptome_exists and transcriptome_logfc
            else f"- 当前转录组证据主要用于锁定候选基因方向，仍需结合后续验证判断其真实育种价值。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1] if transcriptome_exists else guard_citations[:1])}"
        ),
        transcriptome_effect_sentence,
        metabolome_sentence,
        annotation_sentence,
        (
            f"- 代谢组结果提示{metabolome_branch_phrase}可能发生扰动，但不能单独证明 {target_gene_label} 直接调控当前性状积累。{_format_citation_suffix(metabolome_citations[:1] + guard_citations[:1])}"
            if metabolome_exists
            else None
        ),
        metabolome_boundary_sentence,
        background_sentence,
        "",
        "## 候选基因与候选通路",
        (
            f"- {target_gene_label} 是当前 DEG 结果支持的核心候选基因。{_format_citation_suffix(transcriptome_citations[:1])}"
            if transcriptome_exists
            else f"- 当前候选基因仍待真实 DEG 结果确认，现阶段不能把任何基因表述为已被当前 run 的转录组证据支持。{_format_citation_suffix(guard_citations[:1])}"
        ),
        (
            f"- {target_gene_label} 可作为后续 qRT-PCR、群体验证和候选变异筛查的优先对象。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1])}"
            if transcriptome_exists
            else None
        ),
        (
            f"- A1 功能注释显示 {target_gene_label} 存在候选功能/通路线索，可优先结合 DEG 方向和目标性状验证其通路位置；这不是湿实验功能验证。{_format_citation_suffix(transcriptome_citations[:1] + annotation_citations[:1] + guard_citations[:1])}"
            if annotation_citations
            else f"- 当前注释提示 {target_gene_label} 可能与 {transcriptome_annotation} 相关，可据此优先关注其在目标性状通路中的位置。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1])}"
            if transcriptome_annotation
            else f"- 当前功能注释仍需补充，建议结合注释文件或同源基因信息进一步确认 {target_gene_label} 的潜在通路角色。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1] if transcriptome_exists else guard_citations[:1])}"
        ),
        (
            f"- 代谢组结果可用于提示候选通路方向，当前重点关注的代谢物包括 {', '.join(top_metabolite_names[:3]) or '摘要中的代表代谢物'}，但这类线索不能替代基因功能验证。{_format_citation_suffix(metabolome_citations[:1] + guard_citations[:1])}"
            if metabolome_exists
            else f"- 当前缺少代谢组直接支持，尚不能将 {target_gene_label} 与当前性状变化建立直接因果关系。{_format_citation_suffix(guard_citations[:1])}"
        ),
        f"- 当前更合理的策略是先用转录组证据锁定核心候选基因，再用功能注释、代谢组和群体数据逐步缩小通路与变异位点范围。{_format_citation_suffix((transcriptome_citations[:1] + annotation_citations[:1] + metabolome_citations[:1] + guard_citations[:1]) if (transcriptome_exists or metabolome_exists or annotation_citations) else guard_citations[:1])}",
        "",
        "## 育种建议",
        f"- 建议围绕 {target_gene_label if transcriptome_exists else '当前 run 后续确认的核心候选基因'} 及其邻近区域筛查启动子区、外显子区和剪接相关变异，作为候选 SNP/InDel 位点来源。{_format_citation_suffix(transcriptome_citations[:1] or guard_citations[:1])}",
        (
            f"- 建议在黄酮含量分层材料中联合检测 {target_gene_label if transcriptome_exists else '候选基因'} 基因型、表达量和黄酮含量，优先开展群体验证。"
            f"{_format_citation_suffix((transcriptome_citations[:1] + metabolome_citations[:1] + guard_citations[:1]))}"
            if flavonoid_trait
            else f"- 建议在群体中联合检测目标性状表型、{target_gene_label if transcriptome_exists else '候选基因'} 基因型和表达量开展群体验证。{_format_citation_suffix((transcriptome_citations[:1] + guard_citations[:1]))}"
        ),
        f"- 在群体验证显著后，再评估 KASP/CAPS 标记开发，不应在当前阶段称其为最终可用标记。{_format_citation_suffix((transcriptome_citations[:1] + guard_citations[:1]))}",
        f"- 如果后续群体关联结果稳定，可再把候选位点整理为低成本分型列表，用于下一阶段标记筛选准备。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1])}",
        "",
        "## 后续验证建议",
        f"- 使用 qRT-PCR 复验 {target_gene_label if transcriptome_exists else '候选基因'} 的表达趋势。{_format_citation_suffix(transcriptome_citations[:1] or guard_citations[:1])}",
        (
            f"- 在自然群体或分离群体中联合检测黄酮含量、基因型和表达量。{_format_citation_suffix((transcriptome_citations[:1] + metabolome_citations[:1] + guard_citations[:1]))}"
            if flavonoid_trait
            else f"- 在自然群体或分离群体中联合检测目标性状、基因型和表达量。{_format_citation_suffix((transcriptome_citations[:1] + guard_citations[:1]))}"
        ),
        f"- 结合多年多点或不同环境材料评估候选位点稳定性。{_format_citation_suffix(guard_citations[:1])}",
        f"- 必要时在群体验证之后补充酶活、过表达或敲降等湿实验功能验证，以确认 {target_gene_label if transcriptome_exists else '候选基因'} 的实际作用方向。{_format_citation_suffix(transcriptome_citations[:1] + guard_citations[:1])}",
        f"- 当前不应声称已完成湿实验验证、群体验证或最终 KASP/CAPS 标记开发。{_format_citation_suffix(guard_citations[:1])}",
        "",
        "## 边界说明",
        (
            f"- {target_gene_label} 当前仅为基于转录组、功能注释和代谢组线索提出的候选基因，不是已经完成验证的育种结论。{_format_citation_suffix((transcriptome_citations[:1] + annotation_citations[:1] + metabolome_citations[:1] + guard_citations[:1]))}"
            if transcriptome_exists or metabolome_exists or annotation_citations
            else f"- 当前候选基因仍属于待验证线索，不是已经完成验证的育种结论。{_format_citation_suffix(guard_citations[:1])}"
        ),
        (
            f"- PubMed 文献是背景线索，不是当前材料中 {target_gene_label if target_gene else '候选基因'} 功能的直接实验证据。{_format_citation_suffix((background_citations[:2] + guard_citations[:1]))}"
            if background_exists
            else f"- 当前未检索到可用 PubMed 背景文献，因此不能以文献背景替代当前材料中的直接实验证据。{_format_citation_suffix(guard_citations[:1])}"
        ),
        "",
        "---",
        "",
        *_build_source_index_sections(sources),
    ]

    return "\n".join(str(line) for line in body_lines if line is not None).strip()


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
    transcriptome_input_status = _as_str(debug_inputs.get("transcriptome_input_status"))
    transcriptome_supporting_input_exists = bool(
        debug_inputs.get("transcriptome_supporting_input_exists")
    )
    rnaseq_read_count = int(debug_inputs.get("rnaseq_read_count") or 0)
    evidence_level = _as_str(debug_inputs.get("evidence_level"))

    lines = [
        f"- transcriptome_path_exists={transcriptome_exists}",
        f"- metabolome_path_exists={metabolome_exists}",
        f"- evidence_level={evidence_level or 'unknown'}",
    ]

    if not transcriptome_exists:
        lines.append("- 当前未读取到有效的转录组差异基因结果。")
    if transcriptome_supporting_input_exists and not transcriptome_exists:
        if rnaseq_read_count > 0:
            lines.append(
                f"- 已检测到 {rnaseq_read_count} 个 FASTQ 文件，但 significant_de_genes.tsv 尚未生成或当前未被读取。"
            )
        else:
            lines.append("- 已检测到转录组辅助输入，但 significant_de_genes.tsv 尚未生成或当前未被读取。")
    if transcriptome_input_status:
        lines.append(f"- transcriptome_input_status={transcriptome_input_status}")
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


def _format_annotation_context(evidence_pack: dict[str, Any]) -> str:
    records = ((evidence_pack.get("evidence") or {}).get("annotation") or [])
    if not records:
        return "- 未提供可匹配的用户功能注释证据。"
    metadata = (records[0].get("metadata") or {}) if isinstance(records[0], dict) else {}
    lines = [
        f"- annotation_file={_as_str(metadata.get('annotation_file_name') or metadata.get('annotation_file')) or 'N/A'}",
        f"- annotation_gene_match_count={int(metadata.get('annotation_gene_match_count') or 0)}",
        f"- annotation_unmatched_gene_count={int(metadata.get('annotation_unmatched_gene_count') or 0)}",
    ]
    for candidate in list(metadata.get("candidate_annotations") or [])[:6]:
        if isinstance(candidate, dict):
            lines.append(f"- {_format_annotation_candidate_summary(candidate)}")
    pathway_summary = list(metadata.get("pathway_summary") or [])[:12]
    if pathway_summary:
        lines.append("- pathway_summary=" + ", ".join(str(item) for item in pathway_summary))
    return "\n".join(lines)


def _smoke_context_primary_gene(evidence_pack: dict[str, Any]) -> str:
    return _as_str((((evidence_pack.get("debug") or {}).get("smoke_context") or {}).get("primary_gene_id")))


def _is_flavonoid_trait(trait: str) -> bool:
    normalized = _as_str(trait).lower()
    return "黄酮" in normalized or "flavonoid" in normalized


def _build_structured_analysis_sections(
    *,
    evidence_pack: dict[str, Any],
    literature_cards: list[dict[str, Any]],
    sources: list[CitationSource],
) -> str:
    task = evidence_pack.get("task") or {}
    targets = evidence_pack.get("targets") or {}
    evidence = evidence_pack.get("evidence") or {}
    debug_inputs = ((evidence_pack.get("debug") or {}).get("inputs") or {})
    background_records = evidence_pack.get("background_literature_records") or []
    citation_ids = _citation_ids_by_type(sources)
    transcriptome_citations = citation_ids.get("transcriptome") or []
    literature_citations = citation_ids.get("literature") or []
    metabolome_citations = citation_ids.get("metabolome_context") or []
    annotation_citations = citation_ids.get("annotation") or []
    genome_citations = citation_ids.get("genome_context") or []
    background_citations = citation_ids.get("background_literature") or []
    transcriptome_input_citations = citation_ids.get("transcriptome_input") or []

    trait = _as_str(task.get("trait"))
    question = _as_str(task.get("question"))
    target_genes = [str(item).strip() for item in (targets.get("genes") or []) if str(item).strip()]
    smoke_primary_gene = _smoke_context_primary_gene(evidence_pack)
    transcriptome_exists = bool(debug_inputs.get("transcriptome_path_exists")) or bool(target_genes)
    metabolome_exists = bool(debug_inputs.get("metabolome_path_exists"))
    transcriptome_supporting_input_exists = bool(
        debug_inputs.get("transcriptome_supporting_input_exists")
    )
    transcriptome_input_status = _as_str(debug_inputs.get("transcriptome_input_status"))
    rnaseq_read_count = int(debug_inputs.get("rnaseq_read_count") or 0)
    data_source = _as_str(debug_inputs.get("data_source") or debug_inputs.get("evidence_level"))
    evidence_level = _as_str(debug_inputs.get("evidence_level"))
    verified_literature_records = evidence.get("literature") or []
    annotation_records = evidence.get("annotation") or []

    input_lines = [
        "## 当前输入与证据状态",
        f"- 性状：{trait or '未指定'}",
        f"- 用户问题：{question or '未指定'}",
        f"- 数据来源：{data_source or 'unknown'}",
        f"- transcriptome_path_exists={transcriptome_exists}",
        f"- metabolome_path_exists={metabolome_exists}",
        f"- annotation_evidence_count={len(annotation_records)}",
        f"- background_literature_count={len(background_records)}",
    ]

    candidate_lines = ["## 候选基因与当前判断"]
    if transcriptome_exists and target_genes:
        candidate_lines.append(
            f"- 当前已从转录组差异结果中提取候选基因：{', '.join(target_genes)}。"
            f"{_format_citation_suffix(transcriptome_citations[:2])}"
        )
    elif transcriptome_supporting_input_exists:
        if rnaseq_read_count > 0:
            candidate_lines.append(
                f"- 已上传 {rnaseq_read_count} 个 FASTQ 文件，但 significant_de_genes.tsv 尚未生成或当前未被读取；因此暂时不能把任何基因表述为已被 DEG 证据支持。"
                f"{_format_citation_suffix(transcriptome_input_citations[:1])}"
            )
        else:
            candidate_lines.append(
                "- 已上传转录组相关辅助文件，但 significant_de_genes.tsv 尚未生成或当前未被读取；因此暂时不能把任何基因表述为已被 DEG 证据支持。"
                f"{_format_citation_suffix(transcriptome_input_citations[:1])}"
            )
    elif _is_flavonoid_trait(trait) and smoke_primary_gene:
        candidate_lines.append(
            f"- 当前未读取到真实 DEG 结果；{smoke_primary_gene} 仅来自默认 smoke 数据包的局部区域上下文线索，不应表述为已被差异表达证据证明。 [G1]"
        )
    else:
        candidate_lines.append(
            "- 当前未读取到可确认候选基因的真实转录组差异结果，因此本轮建议以代谢组文件存在性和 PubMed 背景线索为主。"
            f"{_format_citation_suffix((metabolome_citations + background_citations + literature_citations)[:3])}"
        )

    if evidence_level == "default_smoke_data":
        candidate_lines.append(
            "- 当前演示使用默认 smoke 数据目录，适合说明分析链路，不等同于用户已上传并跑通完整多组学正式数据。"
            f"{_format_citation_suffix(genome_citations[:1])}"
        )
    elif transcriptome_input_status == "fastq_uploaded":
        candidate_lines.append(
            "- 当前运行已识别到 FASTQ 上传，但还没有可用于候选基因筛选的 DEG 结果文件。"
            f"{_format_citation_suffix(transcriptome_input_citations[:1])}"
        )

    if annotation_records:
        annotation_summary = _summarize_annotation_record(
            (annotation_records[0].get("metadata") or {})
            if isinstance(annotation_records[0], dict)
            else {}
        )
        candidate_lines.append(
            f"- 用户上传功能注释文件已匹配 {annotation_summary['match_count']} 个 DEG 候选基因，可作为候选功能线索，但不能替代 qRT-PCR、群体验证或功能实验。"
            f"{_format_citation_suffix(annotation_citations[:1] + ['Guard'])}"
        )

    literature_lines = ["## 文献依据"]
    if not verified_literature_records:
        literature_lines.append("- 当前输入中未提供可用的已验证文献证据记录，因此本次建议不包含 DOI 引用。")
        if background_records:
            literature_lines.append(
                f"- 当前仅补充 PubMed 背景文献线索，请结合对应 citation id 查看结构化卡片，不应将其视为当前实验的直接验证证据。{_format_citation_suffix(background_citations[:2])}"
            )
    if literature_cards:
        for card in literature_cards[:3]:
            citation_id = _as_str(card.get("citation_id"))
            citation_suffix = _format_citation_suffix([citation_id] if citation_id else [])
            doi = _as_str(card.get("doi"))
            quoted_sentence = _as_str(
                card.get("quoted_sentence") or card.get("abstract_sentence")
            )
            literature_lines.extend(
                [
                    f"### {card.get('citation_id') or '文献'}{citation_suffix}",
                    f"- 已纳入一条结构化文献证据，请在文献卡片中查看 DOI、标题与引用原句。{citation_suffix}",
                ]
            )
    else:
        literature_lines.append("- 当前未检索到可展示的 DOI/PMID 文献依据。")

    advice_lines = ["## 育种建议"]
    if _is_flavonoid_trait(trait):
        if transcriptome_exists and target_genes:
            advice_lines.append(
                f"- 可优先围绕 {target_genes[0]} 及其邻近通路基因，结合黄酮含量分层材料开展候选位点筛选。"
                f"{_format_citation_suffix(transcriptome_citations[:1])}"
            )
        elif evidence_level == "default_smoke_data" and smoke_primary_gene:
            candidate_gene = smoke_primary_gene
            advice_lines.append(
                f"- 在黄酮相关任务下，可将 {candidate_gene} 作为待验证候选基因线索，先在不同群体材料中检查其基因型与黄酮表型分化是否一致。"
                f"{_format_citation_suffix((genome_citations or background_citations)[:1])}"
            )
        advice_lines.append(
            "- 结合代谢组文件中黄酮相关化合物丰度分层结果，优先筛选与黄酮积累方向一致的材料进入后续验证。"
            f"{_format_citation_suffix(metabolome_citations[:1])}"
        )
    else:
        advice_lines.append(
            "- 建议优先围绕当前性状相关的候选基因、代谢表型和背景文献线索制定验证顺序。"
            f"{_format_citation_suffix((transcriptome_citations + metabolome_citations + background_citations)[:3])}"
        )

    validation_lines = [
        "## 后续群体验证建议",
        (
            "- 建议在群体层面结合目标性状表型、候选基因基因型和必要的表达检测开展关联验证，"
            "先做群体验证，再决定是否进入湿实验或标记开发。"
            f"{_format_citation_suffix((transcriptome_citations or genome_citations)[:2])}"
        ),
    ]

    boundary_lines = ["## 边界说明"]
    if not transcriptome_exists:
        boundary_lines.append(
            "- 当前未读取到真实 DEG 文件，因此不能将候选基因表述为已被转录组证据确认。"
            f"{_format_citation_suffix(genome_citations[:1])}"
        )
    if transcriptome_supporting_input_exists and not transcriptome_exists:
        boundary_lines.append(
            "- FASTQ 或相关转录组辅助文件已上传，但本轮输出不等同于已完成 DEG 分析。"
            f"{_format_citation_suffix(transcriptome_input_citations[:1])}"
        )
    boundary_lines.append(
        "- PubMed 文献在本轮中仅作为背景文献线索，不等同于已经直接验证当前候选基因。"
        f"{_format_citation_suffix(background_citations[:2])}"
    )
    if annotation_records:
        boundary_lines.append(
            "- A1 功能注释仅支持候选功能推断，不等同于该基因已被湿实验验证或已证明调控当前材料中的目标性状。"
            f"{_format_citation_suffix(annotation_citations[:1] + ['Guard'])}"
        )
    boundary_lines.append("- 本轮输出仅为前期证据整理，后续仍需群体验证、湿实验验证与 KASP/CAPS 标记开发评估。")

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
            "用户上传功能注释 A1 只能作为候选功能线索，不得表述成湿实验验证、直接因果证明或最终育种结论。",
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
            "用户上传功能注释证据摘要：",
            _format_annotation_context(evidence_pack),
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
            "- 只有在 default smoke 数据演示场景下，且 smoke context primary gene 非空时，才能把它写成待验证上下文线索；同时必须说明它不是已确认的 DEG 证据。",
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

    return "\n".join(
        [
            "# 多组学育种分析结果",
            "",
            (
                "当前未命中可用的在线 LLM 分析，因此以下内容基于现有 Evidence Pack 做规则化汇总。"
                f"{_format_citation_suffix([source.citation_id for source in sources[:3]])}"
            ),
            "",
            _build_structured_analysis_sections(
                evidence_pack=evidence_pack,
                literature_cards=build_literature_cards(build_citation_sources(evidence_pack)),
                sources=sources,
            ),
        ]
    )


# 把回答拆成简单 claim，并记录每条 claim 是否含有 [T1] / [L1] 这类 citation。TODO：后续如果老师要求“逗号级短句”，可以继续改这里
def _strip_markdown_prefix(line: str) -> str:
    normalized = str(line or "").strip()
    normalized = re.sub(r"^[-*+]\s*", "", normalized)
    normalized = re.sub(r"^\d+\.\s*", "", normalized)
    return normalized.strip()


def _split_answer_into_claim_segments(answer_markdown: str) -> list[str]:
    segments: list[str] = []
    in_code_block = False
    inside_source_index = False

    for raw_line in answer_markdown.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue
        if stripped == "## 来源索引":
            inside_source_index = True
            continue
        if inside_source_index:
            continue
        if not stripped or stripped.startswith("#") or stripped == "---":
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            continue
        if re.fullmatch(r"\|?(?:\s*:?-+:?\s*\|)+\s*", stripped):
            continue
        if stripped.endswith("：") or stripped.endswith(":"):
            continue

        segment = _strip_markdown_prefix(stripped)
        if not segment:
            continue
        if segment in {"复制代码", "以下为来源索引"}:
            continue
        if re.fullmatch(r"\[[^\]]+\]", segment):
            continue
        if segment.startswith("[") and ("DOI：" in segment or "PMID：" in segment):
            continue
        segments.append(segment)

    return segments


def _is_meaningful_claim_segment(segment: str) -> bool:
    normalized = str(segment or "").strip()
    if not normalized:
        return False
    if normalized.startswith(("文件：", "DOI：", "PMID：", "引用原句：", "证据角色：")):
        return False
    if normalized.startswith("[") and "] " in normalized:
        return False
    if normalized.startswith("目标性状："):
        return False
    return True


def _extract_citation_ids_from_segment(segment: str, valid_source_ids: list[str]) -> list[str]:
    valid = set(valid_source_ids)
    found: list[str] = []
    for match in re.findall(r"\[([^\[\]]+)\]", segment):
        for token in re.split(r"[\s,]+", match.strip()):
            citation_id = token.strip()
            if citation_id and citation_id in valid and citation_id not in found:
                found.append(citation_id)
    return found


def _build_claim_status(
    citation_ids: list[str],
    source_index: dict[str, CitationSource],
) -> tuple[str, str]:
    if not citation_ids:
        return "needs_citation", "关键结论句缺少 citation id。"

    source_types = {source_index[citation_id].source_type for citation_id in citation_ids if citation_id in source_index}
    if source_types == {"guard_rule"}:
        return "guard", "该句用于声明边界或禁止过度声称。"
    if source_types and source_types.issubset({"background_literature", "literature"}):
        return "background", "该句主要由背景文献支持，不等同于当前实验直接验证。"
    if "guard_rule" in source_types:
        return "supported", "该句同时引用了实验/背景证据与边界规则。"
    return "supported", "该句具有可追溯证据支持。"


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
    source_index = {source.citation_id: source for source in sources}
    raw_segments = _split_answer_into_claim_segments(answer_markdown)

    trace: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments, start=1):
        if not _is_meaningful_claim_segment(segment):
            continue
        cited_ids = _extract_citation_ids_from_segment(segment, source_ids)
        source_status, explanation = _build_claim_status(cited_ids, source_index)
        trace.append(
            {
                "claim_id": f"C{index}",
                "text": segment,
                "citation_ids": cited_ids,
                "source_status": source_status,
                "explanation": explanation,
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
    raw_llm_answer = engine_result["answer_markdown"]
    answer_markdown = build_canonical_cited_answer(
        evidence_pack=evidence_pack,
        sources=sources,
    )

    citations = [
        {
            "citation_id": source.citation_id,
            "source_type": source.source_type,
            "text": source.text,
            "metadata": source.metadata,
        }
        for source in sources
    ]

    literature_cards = build_literature_cards(sources)
    claim_trace = build_claim_trace(
        answer_markdown=answer_markdown,
        sources=sources,
    )

    return {
        "backend": "canonical_renderer",
        "raw_answer_backend": engine_result["backend"],
        "citation_backend": citation_backend,
        "llamaindex_available": LLAMAINDEX_AVAILABLE,
        "answer_markdown": answer_markdown,
        "canonical_answer_markdown": answer_markdown,
        "raw_llm_answer": raw_llm_answer,
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
