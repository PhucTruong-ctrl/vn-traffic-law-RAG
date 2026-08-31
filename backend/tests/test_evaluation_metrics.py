from datetime import date
from math import log2

from app.evaluation.metrics.evidence import (
    all_required_evidence_at_10,
    cross_reference_resolution_recall,
    evidence_set_recall,
    multi_hop_evidence_completeness,
)
from app.evaluation.metrics.retrieval import evaluate_retrieval, ndcg_at, recall_at, reciprocal_rank
from app.evaluation.metrics.temporal import temporal_leakage_rate, temporal_validity_accuracy


def test_hand_computed_ranking_metrics_and_duplicate_ids():
    retrieved = ["noise", "p2", "p1", "p2"]
    assert recall_at(retrieved, ["p1", "p2"], 5) == 1
    assert reciprocal_rank(retrieved, ["p1", "p2"]) == 0.5
    ideal = 1 + 1 / log2(3)
    assert round(ndcg_at(retrieved, ["p1", "p2"]) or 0, 6) == round(
        (1 / log2(3) + 1 / log2(4)) / ideal, 6
    )


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
