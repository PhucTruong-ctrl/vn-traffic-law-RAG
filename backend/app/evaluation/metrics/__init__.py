"""Deterministic evaluation metrics."""

from .evidence import (
    all_required_evidence_at_10,
    cross_reference_resolution_recall,
    evaluate_evidence,
    evidence_set_recall,
    multi_hop_evidence_completeness,
)
from .retrieval import MetricReport, evaluate_retrieval, mrr_at_10, ndcg_at_10, recall_at
from .temporal import (
    comparison_separation_accuracy,
    current_historical_separation_accuracy,
    evaluate_temporal,
    is_temporally_valid,
    temporal_leakage_rate,
    temporal_validity_accuracy,
)

__all__ = [
    "MetricReport",
    "recall_at",
    "mrr_at_10",
    "ndcg_at_10",
    "evaluate_retrieval",
    "evidence_set_recall",
    "all_required_evidence_at_10",
    "cross_reference_resolution_recall",
    "multi_hop_evidence_completeness",
    "evaluate_evidence",
    "is_temporally_valid",
    "temporal_validity_accuracy",
    "temporal_leakage_rate",
    "current_historical_separation_accuracy",
    "comparison_separation_accuracy",
    "evaluate_temporal",
]
