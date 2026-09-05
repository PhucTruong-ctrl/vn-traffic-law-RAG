from datetime import date
from math import log2

from app.evaluation.metrics.evidence import (
    all_required_evidence_at_10,
    cross_reference_resolution_recall,
    evidence_set_recall,
    multi_hop_evidence_completeness,
)
from app.evaluation.metrics.retrieval import evaluate_retrieval, ndcg_at, recall_at, reciprocal_rank
from app.evaluation.metrics.temporal import (
    comparison_separation_accuracy,
    evaluate_temporal,
    temporal_leakage_rate,
    temporal_validity_accuracy,
)


def test_hand_computed_ranking_metrics_and_duplicate_ids():
    retrieved = ["noise", "p2", "p1", "p2"]
    assert recall_at(retrieved, ["p1", "p2"], 5) == 1
    assert reciprocal_rank(retrieved, ["p1", "p2"]) == 0.5
    ideal = 1 + 1 / log2(3)
    assert round(ndcg_at(retrieved, ["p1", "p2"]) or 0, 6) == round(
        (1 / log2(3) + 1 / log2(4)) / ideal, 6
    )


def test_ndcg_preserves_original_rank_positions_when_duplicates_repeat() -> None:
    retrieved = ["noise", "noise", "p1", "p2"]
    ideal = 1 + 1 / log2(3)
    expected = (1 / log2(4) + 1 / log2(5)) / ideal
    assert ndcg_at(retrieved, ["p1", "p2"], 10) == expected


def test_retrieval_reports_na_for_empty_gold_and_category_breakdown():
    report = evaluate_retrieval(
        [
            {"id": "a", "category": "CURRENT", "retrieved": ["p1"], "relevant": ["p1"]},
            {"id": "b", "category": "CURRENT", "retrieved": ["p1"], "relevant": []},
        ]
    )
    assert report["recall@5"].value == 1
    assert report["recall@5"].by_category == {"CURRENT": 1}
    assert report["mrr@10"].per_query["b"] is None


def test_evidence_metrics_and_empty_eligible_population():
    assert evidence_set_recall(["definition", "fine"], ["definition"]) == 0.5
    assert all_required_evidence_at_10(["definition", "fine"], ["definition", "fine"])
    assert cross_reference_resolution_recall(["p2", "p3"], ["p2"]) == 0.5
    assert multi_hop_evidence_completeness(["h1", "h2"], ["h1"]) is False


def test_temporal_half_open_interval_and_leakage():
    citations = [
        {"effective_from": "2024-01-01", "effective_to": "2025-01-01", "review_status": "ACCEPTED"},
        {"effective_from": date(2025, 1, 1), "effective_to": None, "review_status": "ACCEPTED"},
    ]
    assert temporal_validity_accuracy(citations, date(2025, 1, 1)) == 0.5
    assert temporal_leakage_rate(citations, date(2025, 1, 1)) == 0.5
    assert temporal_validity_accuracy([], date.today()) is None


def test_temporal_metadata_without_review_status_is_invalid():
    citations = [{"effective_from": "2024-01-01", "effective_to": None}]
    assert temporal_validity_accuracy(citations, date(2025, 1, 1)) == 0


def _citation(provision_id: str, start: str, end: str | None = None) -> dict[str, object]:
    return {
        "provision_id": provision_id,
        "effective_from": start,
        "effective_to": end,
        "review_status": "ACCEPTED",
    }


def test_current_historical_separation_is_binary_and_category_eligible():
    records = [
        {
            "id": "current-ok",
            "category": "CURRENT",
            "query_date": "2025-01-01",
            "citations": [_citation("new", "2025-01-01")],
        },
        {
            "id": "historical-mixed",
            "category": "HISTORICAL",
            "query_date": "2024-06-01",
            "citations": [
                _citation("old", "2024-01-01", "2025-01-01"),
                _citation("new", "2025-01-01"),
            ],
        },
        {
            "id": "comparison-na",
            "category": "COMPARISON",
            "query_date": "2025-01-01",
            "citations": [],
        },
    ]
    report = evaluate_temporal(records)["current_historical_separation_accuracy"]
    assert report.value == 0.5
    assert report.numerator == 2 and report.denominator == 2
    assert report.per_query == {"current-ok": 1.0, "historical-mixed": 0.0, "comparison-na": None}
    assert report.by_category == {"CURRENT": 1.0, "HISTORICAL": 0.0}


def test_comparison_separation_requires_two_independent_temporal_sides():
    good = {
        "category": "COMPARISON",
        "comparison_dates": ["2024-06-01", "2025-06-01"],
        "comparison_citations": {
            "before": [_citation("old", "2024-01-01", "2025-01-01")],
            "after": [_citation("new", "2025-01-01")],
        },
    }
    mixed = {
        **good,
        "comparison_citations": {
            "before": [_citation("new", "2025-01-01")],
            "after": [_citation("old", "2024-01-01", "2025-01-01")],
        },
    }
    duplicate = {
        **good,
        "comparison_citations": {
            "before": good["comparison_citations"]["before"],
            "after": [_citation("old", "2025-01-01")],
        },
    }
    assert comparison_separation_accuracy(good) == 1.0
    assert comparison_separation_accuracy(mixed) == 0.0
    assert comparison_separation_accuracy(duplicate) == 0.0
    report = evaluate_temporal(
        [{"id": "good", **good}, {"id": "missing", "category": "COMPARISON"}]
    )["comparison_separation_accuracy"]
    assert report.value == 1.0 and report.by_category == {"COMPARISON": 1.0}
    assert report.per_query["missing"] is None


def test_separation_reports_na_without_eligible_population():
    report = evaluate_temporal(
        [{"id": "x", "category": "OUT_OF_SCOPE", "query_date": "2025-01-01", "citations": []}]
    )
    for name in ("current_historical_separation_accuracy", "comparison_separation_accuracy"):
        assert report[name].value is None
        assert report[name].status == "na"
        assert report[name].na_reason == "no citations eligible for temporal evaluation"
