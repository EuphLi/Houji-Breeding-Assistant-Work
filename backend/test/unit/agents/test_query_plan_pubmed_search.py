from __future__ import annotations

from collections.abc import Callable

from yuxi.agents.buildin.omics_breeding_analysis.literature_search import (
    search_background_literature,
)


def _make_query_plan() -> list[dict[str, str]]:
    return [
        {
            "query_id": "HIGH_001",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'Setaria italica "High domain 1" yield',
            "gene_id": "GeneA",
            "pfam_keyword": "High domain 1",
        },
        {
            "query_id": "HIGH_002",
            "query_type": "species_pfam_pathway",
            "priority": "high",
            "query": 'Setaria italica "High domain 2" "Flavonoid biosynthesis"',
            "gene_id": "GeneA",
            "pfam_keyword": "High domain 2",
        },
        {
            "query_id": "HIGH_003",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'foxtail millet "High domain 3" yield',
            "gene_id": "GeneA",
            "pfam_keyword": "High domain 3",
        },
        {
            "query_id": "HIGH_004",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'foxtail millet "High domain 4" grain yield',
            "gene_id": "GeneA",
            "pfam_keyword": "High domain 4",
        },
        {
            "query_id": "HIGH_005",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'Setaria italica "High domain 5" seed weight',
            "gene_id": "GeneA",
            "pfam_keyword": "High domain 5",
        },
        {
            "query_id": "MED_001",
            "query_type": "species_pfam",
            "priority": "medium",
            "query": 'Setaria italica "Medium domain 1"',
            "gene_id": "GeneA",
            "pfam_keyword": "Medium domain 1",
        },
        {
            "query_id": "MED_002",
            "query_type": "pfam_trait",
            "priority": "medium",
            "query": '"Medium domain 2" yield',
            "gene_id": "GeneA",
            "pfam_keyword": "Medium domain 2",
        },
        {
            "query_id": "LOW_001",
            "query_type": "gene_pfam",
            "priority": "low",
            "query": 'GeneA "Low domain"',
            "gene_id": "GeneA",
            "pfam_keyword": "Low domain",
        },
        {
            "query_id": "FB_001",
            "query_type": "species_trait",
            "priority": "fallback",
            "query": "Setaria italica yield",
            "gene_id": "GeneA",
        },
        {
            "query_id": "FB_002",
            "query_type": "trait_only",
            "priority": "fallback",
            "query": "yield",
            "gene_id": "GeneA",
        },
    ]


def _make_large_query_plan() -> list[dict[str, str]]:
    return _make_query_plan() + [
        {
            "query_id": f"EXTRA_{index:03d}",
            "query_type": "species_trait",
            "priority": "fallback",
            "query": f"yield extra {index}",
            "gene_id": "GeneA",
        }
        for index in range(1, 8)
    ]


def _make_budget_sized_query_plan() -> list[dict[str, str]]:
    return [entry for entry in _make_query_plan() if entry["query_id"] != "HIGH_005"]


def _install_fake_pubmed(
    monkeypatch,
    behavior: Callable[[str], dict[str, object]],
    calls: list[str],
) -> None:
    class FakePubMedTool:
        @staticmethod
        def invoke(payload):
            calls.append(payload["query"])
            return behavior(payload["query"])

    monkeypatch.setattr(
        "yuxi.agents.toolkits.buildin.pubmed.pubmed_search",
        FakePubMedTool(),
    )


def test_search_background_literature_preserves_priority_order_and_query_plan_order(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        return {
            "status": "completed",
            "records": [
                {
                    "title": f"Paper for {query}",
                    "pmid": f"PMID-{len(calls) + 1}",
                    "abstract": "Background evidence supports this pathway in millet.",
                }
            ],
            "warnings": [],
        }

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert result["status"] == "completed"
    assert result["used_query_plan"] is True
    assert result["priority_budgets"] == {
        "high": 4,
        "medium": 2,
        "low": 1,
        "fallback": 2,
    }
    assert result["priority_execution_counts"] == {
        "high": 4,
        "medium": 1,
        "low": 0,
        "fallback": 0,
    }
    assert calls == [
        'Setaria italica "High domain 1" yield',
        'Setaria italica "High domain 2" "Flavonoid biosynthesis"',
        'foxtail millet "High domain 3" yield',
        'foxtail millet "High domain 4" grain yield',
        'Setaria italica "Medium domain 1"',
    ]
    assert [item["query_id"] for item in result["executed_query_details"][:4]] == [
        "HIGH_001",
        "HIGH_002",
        "HIGH_003",
        "HIGH_004",
    ]
    assert result["records"][0]["query_id"] == "HIGH_001"
    assert result["records"][0]["query_type"] == "species_pfam_trait"
    assert result["records"][0]["query_priority"] == "high"
    assert result["records"][0]["query"] == 'Setaria italica "High domain 1" yield'
    assert result["records"][0]["evidence_role"] == "background_literature"
    assert result["records"][0]["relevance_level"] == "background"
    assert result["records"][0]["abstract_sentence"] == "Background evidence supports this pathway in millet."
    assert "quoted_sentence" not in result["records"][0]


def test_search_background_literature_continues_to_medium_when_high_is_empty(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        if "Medium domain 1" in query:
            return {
                "status": "completed",
                "records": [{"title": "Medium hit", "pmid": "PMID-medium-1"}],
                "warnings": [],
            }
        return {"status": "completed", "records": [], "warnings": []}

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert result["status"] == "completed"
    assert calls[:5] == [
        'Setaria italica "High domain 1" yield',
        'Setaria italica "High domain 2" "Flavonoid biosynthesis"',
        'foxtail millet "High domain 3" yield',
        'foxtail millet "High domain 4" grain yield',
        'Setaria italica "Medium domain 1"',
    ]
    assert result["executed_query_details"][4]["priority"] == "medium"
    assert result["executed_query_details"][4]["status"] == "completed"
    assert result["records"][0]["query_id"] == "MED_001"


def test_search_background_literature_continues_to_fallback_when_high_and_medium_are_empty(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        if query == "Setaria italica yield":
            return {
                "status": "completed",
                "records": [{"title": "Fallback hit", "pmid": "PMID-fallback-1"}],
                "warnings": [],
            }
        return {"status": "completed", "records": [], "warnings": []}

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert result["fallback_executed"] is True
    assert result["executed_query_details"][-2]["priority"] == "fallback"
    assert result["executed_query_details"][-2]["query"] == "Setaria italica yield"
    assert result["executed_query_details"][-2]["status"] == "completed"
    assert result["records"][0]["query_id"] == "FB_001"


def test_search_background_literature_reserves_budget_for_fallback(monkeypatch):
    calls: list[str] = []

    _install_fake_pubmed(
        monkeypatch,
        lambda query: {"status": "completed", "records": [], "warnings": []},
        calls,
    )

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_large_query_plan(),
    )

    assert "Setaria italica yield" in calls
    assert "yield" in calls
    assert 'Setaria italica "High domain 5" seed weight' not in calls
    assert result["executed_query_count"] == 9
    assert result["unexecuted_query_count"] == 8
    assert result["skipped_query_count"] == 8
    assert result["query_limit"] == 9
    assert result["stop_reason"] == "priority_budgets_exhausted"
    assert result["priority_plan_counts"] == {
        "high": 5,
        "medium": 2,
        "low": 1,
        "fallback": 9,
    }
    assert result["priority_execution_counts"] == {
        "high": 4,
        "medium": 2,
        "low": 1,
        "fallback": 2,
    }


def test_search_background_literature_stops_after_desired_record_count(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        return {
            "status": "completed",
            "records": [{"title": f"Paper for {query}", "pmid": f"PMID-{len(calls) + 1}"}],
            "warnings": [],
        }

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert result["stop_reason"] == "desired_record_count_reached"
    assert result["executed_query_count"] == 5
    assert result["unexecuted_query_count"] == 5
    assert all(item["priority"] != "low" for item in result["executed_query_details"])
    assert all(item["priority"] != "fallback" for item in result["executed_query_details"])


def test_search_background_literature_records_executed_query_details(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        if "High domain 1" in query:
            return {
                "status": "completed",
                "records": [{"title": "One hit", "pmid": "PMID-1"}],
                "warnings": [],
            }
        if "High domain 2" in query:
            return {"status": "completed", "records": [], "warnings": []}
        if "High domain 3" in query:
            return {"status": "rate_limited", "records": [], "warnings": ["429"]}
        return {"status": "completed", "records": [], "warnings": []}

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert result["stop_reason"] == "rate_limited"
    assert result["priority_execution_counts"] == {
        "high": 3,
        "medium": 0,
        "low": 0,
        "fallback": 0,
    }
    assert result["executed_query_details"][:3] == [
        {
            "query_id": "HIGH_001",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'Setaria italica "High domain 1" yield',
            "status": "completed",
            "raw_result_count": 1,
            "retained_new_record_count": 1,
        },
        {
            "query_id": "HIGH_002",
            "query_type": "species_pfam_pathway",
            "priority": "high",
            "query": 'Setaria italica "High domain 2" "Flavonoid biosynthesis"',
            "status": "empty",
            "raw_result_count": 0,
            "retained_new_record_count": 0,
        },
        {
            "query_id": "HIGH_003",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'foxtail millet "High domain 3" yield',
            "status": "rate_limited",
            "raw_result_count": 0,
            "retained_new_record_count": 0,
        },
    ]


def test_search_background_literature_deduplicates_by_pmid_then_doi_then_normalized_title(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        if "High domain 1" in query:
            return {
                "status": "completed",
                "records": [{"title": "Same PMID", "pmid": "12345", "doi": "10.1/a"}],
                "warnings": [],
            }
        if "High domain 2" in query:
            return {
                "status": "completed",
                "records": [{"title": "Different title", "pmid": "12345", "doi": "10.1/b"}],
                "warnings": [],
            }
        if "High domain 3" in query:
            return {
                "status": "completed",
                "records": [{"title": "Same DOI", "doi": "10.2/c"}],
                "warnings": [],
            }
        if "High domain 4" in query:
            return {
                "status": "completed",
                "records": [{"title": "Another title", "doi": "10.2/c"}],
                "warnings": [],
            }
        if "Medium domain 1" in query:
            return {
                "status": "completed",
                "records": [{"title": "  Title With   Spaces.  "}],
                "warnings": [],
            }
        if "Medium domain 2" in query:
            return {
                "status": "completed",
                "records": [{"title": "title with spaces"}],
                "warnings": [],
            }
        return {"status": "completed", "records": [], "warnings": []}

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert len(result["records"]) == 3
    assert result["records"][0]["pmid"] == "12345"
    assert result["records"][0]["query_id"] == "HIGH_001"
    assert result["records"][0]["matched_queries"] == [
        {
            "query_id": "HIGH_002",
            "query_type": "species_pfam_pathway",
            "query_priority": "high",
            "query": 'Setaria italica "High domain 2" "Flavonoid biosynthesis"',
        }
    ]
    assert result["records"][1]["doi"] == "10.2/c"
    assert result["records"][1]["query_id"] == "HIGH_003"
    assert result["records"][2]["title"] == "Title With   Spaces."
    assert result["records"][2]["query_id"] == "MED_001"


def test_search_background_literature_returns_cleanup_status_for_dirty_high_pathway_query(monkeypatch):
    called = {"count": 0}

    class FakePubMedTool:
        @staticmethod
        def invoke(payload):
            called["count"] += 1
            return {"status": "completed", "records": [], "warnings": []}

    monkeypatch.setattr(
        "yuxi.agents.toolkits.buildin.pubmed.pubmed_search",
        FakePubMedTool(),
    )

    result = search_background_literature(
        trait="黄酮相关",
        target_genes=["Si9g037800"],
        query_plan=[
            {
                "query_id": "PFAM_HIGH_001",
                "query_type": "species_pfam_pathway",
                "priority": "high",
                "query": 'Setaria italica "Chalcone-flavanone isomerase" "ko00941"',
                "old_keywords": ["Setaria italica", "ko00941"],
            }
        ],
    )

    assert result["status"] == "query_plan_needs_cleanup"
    assert result["records"] == []
    assert called["count"] == 0
    assert result["stop_reason"] == "query_plan_needs_cleanup"
    assert "low-value ID-like" in result["warnings"][0]


def test_search_background_literature_keeps_old_fallback_when_query_plan_is_empty(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        if query == "Setaria italica yield":
            return {
                "status": "completed",
                "records": [{"title": "Trait fallback paper", "pmid": "PMID-legacy"}],
                "warnings": [],
            }
        return {"status": "completed", "records": [], "warnings": []}

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=[],
    )

    assert result["used_query_plan"] is False
    assert result["fallback_executed"] is True
    assert result["stop_reason"] == "all_queries_exhausted"
    assert any("yield" in query.lower() for query in calls)
    assert result["records"][0]["pmid"] == "PMID-legacy"


def test_search_background_literature_reports_all_queries_exhausted_when_every_query_runs(monkeypatch):
    calls: list[str] = []

    _install_fake_pubmed(
        monkeypatch,
        lambda query: {"status": "completed", "records": [], "warnings": []},
        calls,
    )

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_budget_sized_query_plan(),
    )

    assert result["query_plan_count"] == 9
    assert result["executed_query_count"] == 9
    assert result["unexecuted_query_count"] == 0
    assert result["skipped_query_count"] == 0
    assert result["stop_reason"] == "all_queries_exhausted"


def test_search_background_literature_does_not_fabricate_doi_or_quote(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        return {
            "status": "completed",
            "records": [{"title": "No DOI paper", "pmid": "99999", "abstract": ""}],
            "warnings": [],
        }

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="抗旱",
        target_genes=["GeneA"],
        query_plan=[
            {
                "query_id": "PFAM_HIGH_001",
                "query_type": "species_pfam_trait",
                "priority": "high",
                "query": 'Setaria italica "Stress domain" drought',
            }
        ],
    )

    assert result["status"] == "completed"
    assert "doi" not in result["records"][0]
    assert "quoted_sentence" not in result["records"][0]


def test_search_background_literature_does_not_emit_bg_records_for_errors_or_rate_limits(monkeypatch):
    calls: list[str] = []

    def behavior(query: str) -> dict[str, object]:
        if "High domain 1" in query:
            raise RuntimeError("boom")
        if "High domain 2" in query:
            return {"status": "rate_limited", "records": [], "warnings": ["429"]}
        return {"status": "completed", "records": [], "warnings": []}

    _install_fake_pubmed(monkeypatch, behavior, calls)

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=_make_query_plan(),
    )

    assert result["records"] == []
    assert result["status"] == "completed_without_results"
    assert result["executed_query_details"][0]["status"] == "error"
    assert result["executed_query_details"][1]["status"] == "rate_limited"
