from __future__ import annotations

from yuxi.agents.buildin.omics_breeding_analysis.literature_search import (
    search_background_literature,
)


def test_search_background_literature_prefers_query_plan_and_preserves_priority_order(monkeypatch):
    calls: list[str] = []

    class FakePubMedTool:
        @staticmethod
        def invoke(payload):
            calls.append(payload["query"])
            return {
                "status": "completed",
                "records": [
                    {
                        "title": f"Paper for {payload['query']}",
                        "pmid": f"PMID-{len(calls)}",
                        "abstract": "Background evidence supports this pathway in millet.",
                    }
                ],
                "warnings": [],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.buildin.pubmed.pubmed_search",
        FakePubMedTool(),
    )

    query_plan = [
        {
            "query_id": "PFAM_MED_001",
            "query_type": "species_pfam",
            "priority": "medium",
            "query": 'Setaria italica "Medium domain"',
            "gene_id": "GeneA",
            "pfam_keyword": "Medium domain",
        },
        {
            "query_id": "PFAM_HIGH_001",
            "query_type": "species_pfam_trait",
            "priority": "high",
            "query": 'Setaria italica "High domain" drought',
            "gene_id": "GeneA",
            "pfam_keyword": "High domain",
        },
        {
            "query_id": "PFAM_LOW_001",
            "query_type": "gene_pfam",
            "priority": "low",
            "query": 'GeneA "Low domain"',
            "gene_id": "GeneA",
            "pfam_keyword": "Low domain",
        },
    ]

    result = search_background_literature(
        trait="抗旱",
        target_genes=["GeneA"],
        query_plan=query_plan,
    )

    assert result["status"] == "completed"
    assert result["used_query_plan"] is True
    assert calls[:3] == [
        'Setaria italica "High domain" drought',
        'Setaria italica "Medium domain"',
        'GeneA "Low domain"',
    ]
    assert result["records"][0]["query_id"] == "PFAM_HIGH_001"
    assert result["records"][0]["query_type"] == "species_pfam_trait"
    assert result["records"][0]["query_priority"] == "high"
    assert result["records"][0]["query"] == 'Setaria italica "High domain" drought'
    assert result["records"][0]["evidence_role"] == "background_literature"
    assert result["records"][0]["relevance_level"] == "background"
    assert result["records"][0]["abstract_sentence"] == "Background evidence supports this pathway in millet."
    assert "quoted_sentence" not in result["records"][0]


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
    assert "low-value ID-like" in result["warnings"][0]


def test_search_background_literature_keeps_old_fallback_when_query_plan_is_empty(monkeypatch):
    calls: list[str] = []

    class FakePubMedTool:
        @staticmethod
        def invoke(payload):
            calls.append(payload["query"])
            return {"status": "completed", "records": [], "warnings": []}

    monkeypatch.setattr(
        "yuxi.agents.toolkits.buildin.pubmed.pubmed_search",
        FakePubMedTool(),
    )

    result = search_background_literature(
        trait="高产相关",
        target_genes=["GeneA"],
        query_plan=[],
    )

    assert result["used_query_plan"] is False
    assert result["queries"]
    assert any("yield" in query.lower() for query in calls)


def test_search_background_literature_does_not_fabricate_doi_or_quote(monkeypatch):
    class FakePubMedTool:
        @staticmethod
        def invoke(payload):
            return {
                "status": "completed",
                "records": [
                    {
                        "title": "No DOI paper",
                        "pmid": "99999",
                        "abstract": "",
                    }
                ],
                "warnings": [],
            }

    monkeypatch.setattr(
        "yuxi.agents.toolkits.buildin.pubmed.pubmed_search",
        FakePubMedTool(),
    )

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

