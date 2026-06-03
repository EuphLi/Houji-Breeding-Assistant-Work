from __future__ import annotations

import re
from typing import Any

PUBMED_QUERY_LIMIT = 8
PUBMED_MAX_RESULTS = 2
PUBMED_RECORD_LIMIT = 5
QUERY_PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "fallback": 3}
LOW_VALUE_QUERY_PATTERNS = (
    r"\bLSE\d+\b",
    r"\bK\d{4,}\b",
    r"\bko\d{4,}\b",
    r"\bE\d+(?:\.\d+)+\b",
    r"http://",
    r"https://",
    r"www\.",
    r"genome\.jp",
    r"dbget-bin",
    r"\[X\]",
    r"Unnamed protein",
    r"Uncharacterized protein",
)


def build_literature_queries(
    trait: str,
    target_genes: list[str] | None,
    species: str = "Setaria italica",
) -> list[str]:
    queries: list[str] = []
    normalized_trait = str(trait or "").strip()
    normalized_species = str(species or "").strip() or "Setaria italica"
    lowered_trait = normalized_trait.lower()

    if normalized_trait:
        queries.append(f"{normalized_species} {normalized_trait}")

    if "黄酮" in normalized_trait or "flavonoid" in lowered_trait:
        queries.extend(
            [
                f"{normalized_species} flavonoid",
                "foxtail millet flavonoid biosynthesis",
            ]
        )
    elif "抗旱" in normalized_trait or "drought" in lowered_trait:
        queries.extend(
            [
                f"{normalized_species} drought tolerance",
                "foxtail millet abiotic stress",
            ]
        )
    elif "高产" in normalized_trait or "yield" in lowered_trait or "产量" in normalized_trait:
        queries.extend(
            [
                f"{normalized_species} yield",
                "foxtail millet grain yield",
            ]
        )

    for gene_id in target_genes or []:
        gene = str(gene_id or "").strip()
        if gene:
            queries.append(f"{gene} {normalized_species}")

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        if query not in seen:
            seen.add(query)
            deduped.append(query)
    return deduped


def _first_abstract_sentence(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""
    for separator in ["。", ". ", ".\n"]:
        if separator in normalized:
            sentence = normalized.split(separator, 1)[0].strip()
            return f"{sentence}." if separator.startswith(".") and not sentence.endswith(".") else sentence
    return normalized


def _query_plan_entry_sort_key(entry: dict[str, Any], index: int) -> tuple[int, int]:
    priority = str(entry.get("priority") or "").strip().lower()
    return (QUERY_PRIORITY_ORDER.get(priority, 99), index)


def _contains_low_value_query_term(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    return any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in LOW_VALUE_QUERY_PATTERNS)


def _query_plan_needs_cleanup(query_plan: list[dict[str, Any]]) -> bool:
    for entry in query_plan:
        if str(entry.get("priority") or "").strip().lower() != "high":
            continue
        if str(entry.get("query_type") or "").strip() != "species_pfam_pathway":
            continue
        if _contains_low_value_query_term(str(entry.get("query") or "")):
            return True
        for token in entry.get("old_keywords") or []:
            if _contains_low_value_query_term(str(token or "")):
                return True
    return False


def _select_queries_from_plan(query_plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [
        entry
        for _, entry in sorted(
            enumerate(query_plan),
            key=lambda item: _query_plan_entry_sort_key(item[1], item[0]),
        )
        if str(entry.get("query") or "").strip()
    ]
    return ordered[:PUBMED_QUERY_LIMIT]


def _deduplicate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for record in records:
        key = (
            str(record.get("title") or "").strip(),
            str(record.get("doi") or "").strip(),
            str(record.get("pmid") or "").strip(),
            str(record.get("query_id") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)
        if len(deduped) >= PUBMED_RECORD_LIMIT:
            break
    return deduped


def _standardize_background_record(
    item: dict[str, Any],
    *,
    query_entry: dict[str, Any],
    query_text: str,
) -> dict[str, Any]:
    abstract = str(item.get("abstract") or "").strip()
    abstract_sentence = str(item.get("abstract_sentence") or "").strip()
    if not abstract_sentence and abstract:
        abstract_sentence = _first_abstract_sentence(abstract)
    quoted_sentence = str(item.get("quoted_sentence") or "").strip()
    record = {
        "title": str(item.get("title") or "").strip(),
        "abstract": abstract,
        "abstract_sentence": abstract_sentence,
        "source": "PubMed",
        "query_id": str(query_entry.get("query_id") or "").strip(),
        "query_type": str(query_entry.get("query_type") or "").strip(),
        "query_priority": str(query_entry.get("priority") or "").strip(),
        "query": query_text,
        "gene_id": str(query_entry.get("gene_id") or "").strip(),
        "pfam_keyword": str(query_entry.get("pfam_keyword") or "").strip(),
        "evidence_role": "background_literature",
        "relevance_level": "background",
    }
    for field in ("pmid", "doi", "url"):
        value = str(item.get(field) or "").strip()
        if value:
            record[field] = value
    if quoted_sentence:
        record["quoted_sentence"] = quoted_sentence
        if not record.get("abstract_sentence"):
            record["abstract_sentence"] = quoted_sentence
    return record


def search_background_literature(
    *,
    trait: str,
    target_genes: list[str] | None,
    query_plan: list[dict[str, Any]] | None = None,
    species: str = "Setaria italica",
    max_results: int = PUBMED_MAX_RESULTS,
) -> dict[str, Any]:
    normalized_query_plan = list(query_plan or [])
    used_query_plan = bool(normalized_query_plan)
    capped_max_results = min(max(1, int(max_results)), PUBMED_MAX_RESULTS)
    if used_query_plan and _query_plan_needs_cleanup(normalized_query_plan):
        return {
            "status": "query_plan_needs_cleanup",
            "backend": "pubmed_search",
            "literature_source": "query_plan_validation",
            "used_query_plan": True,
            "query_plan_count": len(normalized_query_plan),
            "executed_query_count": 0,
            "query_limit": PUBMED_QUERY_LIMIT,
            "per_query_result_limit": capped_max_results,
            "retained_record_limit": PUBMED_RECORD_LIMIT,
            "queries": [],
            "records": [],
            "warnings": ["literature_query_plan contains low-value ID-like high-priority query terms"],
        }

    if used_query_plan:
        selected_entries = _select_queries_from_plan(normalized_query_plan)
        query_jobs = [
            {
                "query": str(entry.get("query") or "").strip(),
                "entry": entry,
            }
            for entry in selected_entries
        ]
    else:
        selected_entries = []
        query_jobs = [
            {"query": query, "entry": {}}
            for query in build_literature_queries(
                trait=trait,
                target_genes=target_genes,
                species=species,
            )[:PUBMED_QUERY_LIMIT]
        ]

    queries = [job["query"] for job in query_jobs if job["query"]]
    if not queries:
        return {
            "status": "skipped",
            "backend": "none",
            "literature_source": "none",
            "used_query_plan": used_query_plan,
            "query_plan_count": len(normalized_query_plan),
            "executed_query_count": 0,
            "query_limit": PUBMED_QUERY_LIMIT,
            "per_query_result_limit": capped_max_results,
            "retained_record_limit": PUBMED_RECORD_LIMIT,
            "queries": [],
            "records": [],
            "warnings": ["No literature queries were generated."],
        }

    try:
        from yuxi.agents.toolkits.buildin.pubmed import pubmed_search
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "dynamic_search_unavailable",
            "backend": "unavailable",
            "literature_source": "dynamic_search_unavailable",
            "used_query_plan": used_query_plan,
            "query_plan_count": len(normalized_query_plan),
            "executed_query_count": 0,
            "query_limit": PUBMED_QUERY_LIMIT,
            "per_query_result_limit": capped_max_results,
            "retained_record_limit": PUBMED_RECORD_LIMIT,
            "queries": queries,
            "records": [],
            "warnings": [f"PubMed tool unavailable: {type(exc).__name__}: {exc}"],
        }

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    had_failure = False

    executed_query_count = 0
    current_priority = None
    for job in query_jobs:
        query = job["query"]
        query_entry = job["entry"]
        if not query:
            continue
        priority = str(query_entry.get("priority") or "").strip().lower()
        if len(records) >= PUBMED_RECORD_LIMIT and current_priority not in {"high", "medium"} and priority in {"low", "fallback"}:
            break
        current_priority = priority or current_priority
        executed_query_count += 1
        try:
            result = pubmed_search.invoke({"query": query, "max_results": capped_max_results})
        except Exception as exc:  # noqa: BLE001
            had_failure = True
            warnings.append(f"PubMed query failed for '{query}': {type(exc).__name__}: {exc}")
            continue

        warnings.extend(result.get("warnings") or [])
        if result.get("status") == "unavailable":
            had_failure = True

        for item in result.get("records") or []:
            record = _standardize_background_record(item, query_entry=query_entry, query_text=query)
            if record.get("abstract_sentence"):
                record["quote_scope"] = "abstract"
            records.append(record)
            if len(records) >= PUBMED_RECORD_LIMIT:
                break
        if len(records) >= PUBMED_RECORD_LIMIT and priority in {"high", "medium"}:
            continue
        if len(records) >= PUBMED_RECORD_LIMIT:
            break

    deduped = _deduplicate_records(records)

    status = "completed" if deduped else "completed_without_results"
    literature_source = "pubmed_search_with_query_plan" if used_query_plan else "pubmed_search"
    if had_failure and not deduped:
        status = "dynamic_search_unavailable"
        literature_source = "dynamic_search_unavailable"

    return {
        "status": status,
        "backend": "pubmed_search",
        "literature_source": literature_source,
        "used_query_plan": used_query_plan,
        "query_plan_count": len(normalized_query_plan),
        "executed_query_count": executed_query_count,
        "query_limit": PUBMED_QUERY_LIMIT,
        "per_query_result_limit": capped_max_results,
        "retained_record_limit": PUBMED_RECORD_LIMIT,
        "queries": queries,
        "records": deduped,
        "warnings": warnings,
    }
