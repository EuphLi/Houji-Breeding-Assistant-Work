from __future__ import annotations

from typing import Any

PUBMED_QUERY_LIMIT = 3
PUBMED_MAX_RESULTS = 3


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


def search_background_literature(
    *,
    trait: str,
    target_genes: list[str] | None,
    species: str = "Setaria italica",
    max_results: int = PUBMED_MAX_RESULTS,
) -> dict[str, Any]:
    queries = build_literature_queries(
        trait=trait,
        target_genes=target_genes,
        species=species,
    )[:PUBMED_QUERY_LIMIT]
    capped_max_results = min(max(1, int(max_results)), PUBMED_MAX_RESULTS)
    if not queries:
        return {
            "status": "skipped",
            "backend": "none",
            "literature_source": "none",
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
            "queries": queries,
            "records": [],
            "warnings": [f"PubMed tool unavailable: {type(exc).__name__}: {exc}"],
        }

    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    had_failure = False

    for query in queries:
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
            abstract = str(item.get("abstract") or "").strip()
            quoted_sentence = _first_abstract_sentence(abstract) if abstract else ""
            record = {
                "query": query,
                "title": str(item.get("title") or "").strip(),
                "doi": str(item.get("doi") or "").strip(),
                "pmid": str(item.get("pmid") or "").strip(),
                "abstract": abstract,
                "url": str(item.get("url") or "").strip(),
                "source": "PubMed",
                "quote_scope": "abstract" if quoted_sentence else "",
                "quoted_sentence": quoted_sentence,
            }
            records.append(record)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for record in records:
        key = (record["title"], record["doi"], record["pmid"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(record)

    status = "completed" if deduped else "completed_without_results"
    literature_source = "pubmed_search"
    if had_failure and not deduped:
        status = "dynamic_search_unavailable"
        literature_source = "dynamic_search_unavailable"

    return {
        "status": status,
        "backend": "pubmed_search",
        "literature_source": literature_source,
        "queries": queries,
        "records": deduped,
        "warnings": warnings,
    }
