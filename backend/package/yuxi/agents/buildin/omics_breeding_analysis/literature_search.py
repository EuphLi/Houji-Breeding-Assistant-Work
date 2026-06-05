from __future__ import annotations

import re
from typing import Any

PUBMED_QUERY_LIMIT = 9
PUBMED_MAX_RESULTS = 2
PUBMED_RECORD_LIMIT = 5
PUBMED_DESIRED_RECORD_COUNT = 5
QUERY_PRIORITY_BUDGETS = {
    "high": 4,
    "medium": 2,
    "low": 1,
    "fallback": 2,
}
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
    ordered_entries = [
        entry
        for _, entry in sorted(
            enumerate(query_plan),
            key=lambda item: _query_plan_entry_sort_key(item[1], item[0]),
        )
        if str(entry.get("query") or "").strip()
    ]
    selected: list[dict[str, Any]] = []
    for priority in ("high", "medium", "low", "fallback"):
        priority_entries = [
            entry
            for entry in ordered_entries
            if str(entry.get("priority") or "").strip().lower() == priority
        ]
        selected.extend(priority_entries[: QUERY_PRIORITY_BUDGETS[priority]])
    return selected[:PUBMED_QUERY_LIMIT]


def _build_priority_counts_from_plan(query_plan: list[dict[str, Any]]) -> dict[str, int]:
    counts = {priority: 0 for priority in QUERY_PRIORITY_ORDER}
    for entry in query_plan:
        priority = str(entry.get("priority") or "").strip().lower()
        if priority in counts:
            counts[priority] += 1
    return counts


def _normalize_title_for_dedup(title: str) -> str:
    normalized = re.sub(r"\s+", " ", str(title or "").strip().lower())
    return normalized.strip(" \t\r\n.,;:!?\"'()[]{}")


def _build_record_dedup_key(record: dict[str, Any]) -> tuple[str, str]:
    pmid = str(record.get("pmid") or "").strip()
    if pmid:
        return ("pmid", pmid)
    doi = str(record.get("doi") or "").strip().lower()
    if doi:
        return ("doi", doi)
    return ("title", _normalize_title_for_dedup(str(record.get("title") or "")))


def _deduplicate_records(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    deduped: list[dict[str, Any]] = []
    seen_keys: dict[tuple[str, str], dict[str, Any]] = {}
    duplicate_hit_count = 0
    for record in records:
        key = _build_record_dedup_key(record)
        if key[0] == "title" and not key[1]:
            continue
        existing = seen_keys.get(key)
        if existing is not None:
            duplicate_hit_count += 1
            matched_queries = existing.setdefault("matched_queries", [])
            matched_query = {
                "query_id": str(record.get("query_id") or "").strip(),
                "query_type": str(record.get("query_type") or "").strip(),
                "query_priority": str(record.get("query_priority") or "").strip(),
                "query": str(record.get("query") or "").strip(),
            }
            if matched_query["query"] and matched_query not in matched_queries:
                matched_queries.append(matched_query)
            continue
        record["matched_queries"] = []
        seen_keys[key] = record
        deduped.append(record)
        if len(deduped) >= PUBMED_RECORD_LIMIT:
            break
    return deduped, duplicate_hit_count


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
    priority_plan_counts = (
        _build_priority_counts_from_plan(normalized_query_plan)
        if used_query_plan
        else {priority: 0 for priority in QUERY_PRIORITY_ORDER}
    )
    if used_query_plan and _query_plan_needs_cleanup(normalized_query_plan):
        return {
            "status": "query_plan_needs_cleanup",
            "backend": "pubmed_search",
            "literature_source": "query_plan_validation",
            "used_query_plan": True,
            "query_plan_count": len(normalized_query_plan),
            "executed_query_count": 0,
            "unexecuted_query_count": len(normalized_query_plan),
            "query_limit": PUBMED_QUERY_LIMIT,
            "desired_record_count": PUBMED_DESIRED_RECORD_COUNT,
            "per_query_result_limit": capped_max_results,
            "retained_record_limit": PUBMED_RECORD_LIMIT,
            "priority_budgets": dict(QUERY_PRIORITY_BUDGETS),
            "priority_execution_counts": {priority: 0 for priority in QUERY_PRIORITY_ORDER},
            "priority_plan_counts": priority_plan_counts,
            "executed_query_details": [],
            "skipped_query_count": len(normalized_query_plan),
            "fallback_executed": False,
            "stop_reason": "query_plan_needs_cleanup",
            "warning_count": 1,
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
            "unexecuted_query_count": len(normalized_query_plan),
            "query_limit": PUBMED_QUERY_LIMIT,
            "desired_record_count": PUBMED_DESIRED_RECORD_COUNT,
            "per_query_result_limit": capped_max_results,
            "retained_record_limit": PUBMED_RECORD_LIMIT,
            "priority_budgets": dict(QUERY_PRIORITY_BUDGETS),
            "priority_execution_counts": {priority: 0 for priority in QUERY_PRIORITY_ORDER},
            "priority_plan_counts": priority_plan_counts,
            "executed_query_details": [],
            "skipped_query_count": len(normalized_query_plan),
            "fallback_executed": False,
            "stop_reason": "no_queries",
            "warning_count": 1,
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
            "unexecuted_query_count": len(normalized_query_plan),
            "query_limit": PUBMED_QUERY_LIMIT,
            "desired_record_count": PUBMED_DESIRED_RECORD_COUNT,
            "per_query_result_limit": capped_max_results,
            "retained_record_limit": PUBMED_RECORD_LIMIT,
            "priority_budgets": dict(QUERY_PRIORITY_BUDGETS),
            "priority_execution_counts": {priority: 0 for priority in QUERY_PRIORITY_ORDER},
            "priority_plan_counts": priority_plan_counts,
            "executed_query_details": [],
            "skipped_query_count": len(normalized_query_plan) if used_query_plan else len(queries),
            "fallback_executed": False,
            "stop_reason": "pubmed_unavailable",
            "warning_count": 1,
            "queries": queries,
            "records": [],
            "warnings": [f"PubMed tool unavailable: {type(exc).__name__}: {exc}"],
        }

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    executed_query_details: list[dict[str, Any]] = []
    executed_query_count = 0
    priority_execution_counts = {priority: 0 for priority in QUERY_PRIORITY_ORDER}
    fallback_executed = False
    stop_reason = "all_queries_exhausted"
    terminated_by_rate_limit = False
    terminated_by_unavailable = False

    if used_query_plan:
        query_jobs_by_priority = {
            priority: [
                job
                for job in query_jobs
                if str((job.get("entry") or {}).get("priority") or "").strip().lower() == priority
            ]
            for priority in ("high", "medium", "low", "fallback")
        }
    else:
        query_jobs_by_priority = {"fallback": query_jobs}

    for priority in ("high", "medium", "low", "fallback"):
        jobs = query_jobs_by_priority.get(priority) or []
        if priority == "fallback" and jobs:
            fallback_executed = True
        for job in jobs:
            query = job["query"]
            query_entry = job["entry"]
            if not query:
                continue
            executed_query_count += 1
            if priority in priority_execution_counts:
                priority_execution_counts[priority] += 1
            try:
                result = pubmed_search.invoke({"query": query, "max_results": capped_max_results})
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"PubMed query failed for '{query}': {type(exc).__name__}: {exc}")
                executed_query_details.append(
                    {
                        "query_id": str(query_entry.get("query_id") or "").strip(),
                        "query_type": str(query_entry.get("query_type") or "").strip(),
                        "priority": priority or "fallback",
                        "query": query,
                        "status": "error",
                        "raw_result_count": 0,
                        "retained_new_record_count": 0,
                    }
                )
                continue

            result_status = str(result.get("status") or "").strip().lower()
            result_warnings = result.get("warnings") or []
            warnings.extend(result_warnings)
            raw_items = result.get("records") or []
            raw_result_count = len(raw_items)
            before_dedup_count = len(_deduplicate_records(records)[0])
            query_status = "completed"
            if result_status == "rate_limited":
                query_status = "rate_limited"
                terminated_by_rate_limit = True
            elif result_status == "unavailable":
                query_status = "error"
                terminated_by_unavailable = True
            elif raw_result_count == 0:
                query_status = "empty"

            if query_status == "completed":
                for item in raw_items:
                    record = _standardize_background_record(
                        item,
                        query_entry=query_entry,
                        query_text=query,
                    )
                    if record.get("abstract_sentence"):
                        record["quote_scope"] = "abstract"
                    records.append(record)

            deduped_snapshot, _ = _deduplicate_records(records)
            retained_new_record_count = max(0, len(deduped_snapshot) - before_dedup_count)
            executed_query_details.append(
                {
                    "query_id": str(query_entry.get("query_id") or "").strip(),
                    "query_type": str(query_entry.get("query_type") or "").strip(),
                    "priority": priority or "fallback",
                    "query": query,
                    "status": query_status,
                    "raw_result_count": raw_result_count,
                    "retained_new_record_count": retained_new_record_count,
                }
            )
            if len(deduped_snapshot) >= PUBMED_DESIRED_RECORD_COUNT:
                stop_reason = "desired_record_count_reached"
                break
            if terminated_by_rate_limit:
                stop_reason = "rate_limited"
                break
            if terminated_by_unavailable:
                stop_reason = "pubmed_unavailable"
                break
        if stop_reason in {"desired_record_count_reached", "rate_limited", "pubmed_unavailable"}:
            break

    deduped, duplicate_hit_count = _deduplicate_records(records)
    query_statuses = [str(item.get("status") or "").strip() for item in executed_query_details]
    all_queries_failed = bool(query_statuses) and all(status == "error" for status in query_statuses)
    query_plan_count = len(normalized_query_plan)
    unexecuted_query_count = max(
        (query_plan_count if used_query_plan else len(queries)) - executed_query_count,
        0,
    )
    skipped_query_count = unexecuted_query_count
    if stop_reason not in {
        "desired_record_count_reached",
        "rate_limited",
        "pubmed_unavailable",
        "query_plan_needs_cleanup",
        "no_queries",
    }:
        if used_query_plan and unexecuted_query_count > 0:
            stop_reason = "priority_budgets_exhausted"
        else:
            stop_reason = "all_queries_exhausted"

    status = "completed" if deduped else "completed_without_results"
    literature_source = "pubmed_search_with_query_plan" if used_query_plan else "pubmed_search"
    if stop_reason == "pubmed_unavailable" and not deduped:
        status = "dynamic_search_unavailable"
        literature_source = "dynamic_search_unavailable"
    elif all_queries_failed and not deduped:
        status = "dynamic_search_unavailable"
        literature_source = "dynamic_search_unavailable"
        stop_reason = "pubmed_unavailable"
    elif stop_reason == "rate_limited" and not deduped:
        status = "completed_without_results"

    warning_count = len(warnings)
    if duplicate_hit_count:
        warning_count += 1
        warnings.append(f"Deduplicated {duplicate_hit_count} duplicate PubMed record hits across queries.")

    return {
        "status": status,
        "backend": "pubmed_search",
        "literature_source": literature_source,
        "used_query_plan": used_query_plan,
        "query_plan_count": query_plan_count,
        "executed_query_count": executed_query_count,
        "unexecuted_query_count": unexecuted_query_count,
        "query_limit": PUBMED_QUERY_LIMIT,
        "desired_record_count": PUBMED_DESIRED_RECORD_COUNT,
        "per_query_result_limit": capped_max_results,
        "retained_record_limit": PUBMED_RECORD_LIMIT,
        "priority_budgets": dict(QUERY_PRIORITY_BUDGETS),
        "priority_execution_counts": priority_execution_counts,
        "priority_plan_counts": priority_plan_counts,
        "executed_query_details": executed_query_details,
        "skipped_query_count": skipped_query_count,
        "fallback_executed": fallback_executed,
        "stop_reason": stop_reason,
        "warning_count": warning_count,
        "queries": [detail["query"] for detail in executed_query_details],
        "records": deduped,
        "warnings": warnings,
    }
