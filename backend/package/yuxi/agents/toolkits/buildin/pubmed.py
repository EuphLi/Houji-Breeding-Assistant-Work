from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from yuxi.agents.toolkits.registry import tool
from yuxi.utils import logger

PUBMED_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_REQUEST_TIMEOUT_SECONDS = 10
PUBMED_USER_AGENT = "YuXi-PubMed-Tool/1.0"


def _make_pubmed_url(pmid: str) -> str:
    return f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": PUBMED_USER_AGENT})
    with urllib.request.urlopen(request, timeout=PUBMED_REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8", errors="replace")


def _build_eutils_url(endpoint: str, params: dict[str, Any]) -> str:
    query = urllib.parse.urlencode(
        {key: value for key, value in params.items() if value not in (None, "")}
    )
    return f"{PUBMED_EUTILS_BASE}/{endpoint}?{query}"


def _search_pmids(query: str, max_results: int) -> list[str]:
    url = _build_eutils_url(
        "esearch.fcgi",
        {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results,
            "sort": "relevance",
        },
    )
    payload = json.loads(_http_get(url))
    id_list = ((payload.get("esearchresult") or {}).get("idlist") or [])
    return [_safe_text(item) for item in id_list if _safe_text(item)]


def _extract_abstract(article: ET.Element) -> str:
    parts: list[str] = []
    for node in article.findall(".//Abstract/AbstractText"):
        text = _normalize_whitespace("".join(node.itertext()))
        if not text:
            continue
        label = _safe_text(node.attrib.get("Label"))
        parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts).strip()


def _extract_title(article: ET.Element) -> str:
    title = "".join(article.findtext(".//Article/ArticleTitle", default=""))
    if not title:
        title_node = article.find(".//Article/ArticleTitle")
        if title_node is not None:
            title = "".join(title_node.itertext())
    return _normalize_whitespace(title)


def _extract_doi(article: ET.Element) -> str:
    for node in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        if _safe_text(node.attrib.get("IdType")).lower() == "doi":
            doi = _normalize_whitespace("".join(node.itertext()))
            if doi:
                return doi

    for node in article.findall(".//Article/ELocationID"):
        if _safe_text(node.attrib.get("EIdType")).lower() == "doi":
            doi = _normalize_whitespace("".join(node.itertext()))
            if doi:
                return doi

    return ""


def _parse_pubmed_articles(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    records: list[dict[str, str]] = []

    for article in root.findall(".//PubmedArticle"):
        pmid = _safe_text(article.findtext(".//MedlineCitation/PMID", default=""))
        title = _extract_title(article)
        abstract = _extract_abstract(article)
        doi = _extract_doi(article)

        records.append(
            {
                "title": title,
                "doi": doi,
                "pmid": pmid,
                "abstract": abstract,
                "url": _make_pubmed_url(pmid),
                "source": "PubMed",
            }
        )

    return records


def _fetch_pubmed_records(pmids: list[str]) -> list[dict[str, str]]:
    if not pmids:
        return []

    url = _build_eutils_url(
        "efetch.fcgi",
        {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
        },
    )
    return _parse_pubmed_articles(_http_get(url))


@tool(category="buildin", tags=["搜索"], display_name="PubMed 搜索")
def pubmed_search(query: str, max_results: int = 3) -> dict[str, Any]:
    """PubMed 文献检索工具：返回真实 PubMed 题目、PMID、DOI、摘要和链接。"""

    normalized_query = _safe_text(query)
    capped_results = min(max(1, int(max_results)), 3)
    output: dict[str, Any] = {
        "query": normalized_query,
        "max_results": capped_results,
        "status": "completed",
        "records": [],
        "results": [],
        "warnings": [],
    }

    if not normalized_query:
        output["status"] = "skipped"
        output["warnings"] = ["PubMed search skipped because query is empty."]
        return output

    try:
        pmids = _search_pmids(normalized_query, capped_results)
        records = _fetch_pubmed_records(pmids)[:capped_results]
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"[PubMed_Search] query={normalized_query!r} failed: {type(exc).__name__}: {exc}")
        output["status"] = "unavailable"
        output["warnings"] = [f"PubMed search failed: {type(exc).__name__}: {exc}"]
        return output

    output["records"] = records
    output["results"] = [
        {
            "title": record["title"],
            "content": record["abstract"],
            "url": record["url"],
            "score": float(1.0 / (index + 1)),
            "pmid": record["pmid"],
            "doi": record["doi"],
        }
        for index, record in enumerate(records)
    ]
    return output
