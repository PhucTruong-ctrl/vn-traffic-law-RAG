"""Provider-independent RAG evaluation models and metrics."""

from .metrics import aggregate_metrics, normalize_coordinate, score_case
from .schemas import (
    CaseResult,
    CitationPrediction,
    Coordinate,
    EvaluationSummary,
    ExpectedCase,
    LatencySummary,
    Prediction,
)

__all__ = [
    "CaseResult",
    "CitationPrediction",
    "Coordinate",
    "EvaluationSummary",
    "ExpectedCase",
    "LatencySummary",
    "Prediction",
    "aggregate_metrics",
    "normalize_coordinate",
    "score_case",
]
