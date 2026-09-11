"""Pure deterministic metrics for saved RAG evaluation predictions."""

from __future__ import annotations

import math
from collections.abc import Iterable

from .schemas import (
    CaseResult,
    Coordinate,
    EvaluationSummary,
    ExpectedCase,
    LatencySummary,
    Prediction,
)


def normalize_coordinate(
    value: Coordinate | dict[str, object],
) -> tuple[str, str | None, str | None, str | None]:
    """Normalize whitespace and case while preserving absent coordinate levels."""
    coordinate = value if isinstance(value, Coordinate) else Coordinate.model_validate(value)

    def clean(item: str | None) -> str | None:
        return " ".join(item.split()).casefold() if item is not None and item.strip() else None

    return (
        clean(coordinate.document) or "",
        clean(coordinate.article),
        clean(coordinate.clause),
        clean(coordinate.point),
    )


def _accuracy(expected: list[Coordinate], actual: list[Coordinate], level: int) -> float | None:
    if not expected:
        return None
    wanted = {normalize_coordinate(item) for item in expected}
    found = {normalize_coordinate(item) for item in actual}
    numerator = sum(
        1
        for item in wanted
        if item[level] is not None
        and any(candidate[: level + 1] == item[: level + 1] for candidate in found)
    )
    denominator = sum(1 for item in wanted if item[level] is not None)
    return numerator / denominator if denominator else None


def score_case(case: ExpectedCase, prediction: Prediction) -> CaseResult:
    expected = case.expected_coordinates
    retrieved = prediction.retrieved_coordinates
    citation_validity = (
        None if not prediction.citations else all(item.valid for item in prediction.citations)
    )
    retrieval_hit = (
        None
        if not case.retrieval_required or not expected
        else bool(
            set(map(normalize_coordinate, expected)) & set(map(normalize_coordinate, retrieved))
        )
    )
    return CaseResult(
        case_id=case.case_id,
        retrieval_hit_at_k=retrieval_hit,
        document_accuracy=_accuracy(expected, retrieved, 0),
        article_accuracy=_accuracy(expected, retrieved, 1),
        clause_accuracy=_accuracy(expected, retrieved, 2),
        point_accuracy=_accuracy(expected, retrieved, 3),
        citation_validity=citation_validity,
        answer_correctness_manual=prediction.manual_answer_correctness,
        abstention_accuracy=prediction.abstained == case.abstention_expected,
        latency_ms=prediction.latency_ms,
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * percentile
    lower, upper = math.floor(index), math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _rate(values: Iterable[bool | None]) -> float | None:
    usable = [float(value) for value in values if value is not None]
    return _mean(usable)


def aggregate_metrics(
    cases: list[ExpectedCase], predictions: list[Prediction]
) -> EvaluationSummary:
    by_id = {item.case_id: item for item in predictions}
    results = [score_case(case, by_id[case.case_id]) for case in cases]
    latencies = [item.latency_ms for item in results]
    return EvaluationSummary(
        case_count=len(results),
        case_results=results,
        retrieval_hit_at_k=_rate(item.retrieval_hit_at_k for item in results),
        document_accuracy=_mean(
            [item.document_accuracy for item in results if item.document_accuracy is not None]
        ),
        article_accuracy=_mean(
            [item.article_accuracy for item in results if item.article_accuracy is not None]
        ),
        clause_accuracy=_mean(
            [item.clause_accuracy for item in results if item.clause_accuracy is not None]
        ),
        point_accuracy=_mean(
            [item.point_accuracy for item in results if item.point_accuracy is not None]
        ),
        citation_validity=_rate(item.citation_validity for item in results),
        answer_correctness_manual=_rate(item.answer_correctness_manual for item in results),
        abstention_accuracy=_rate(item.abstention_accuracy for item in results),
        latency=LatencySummary(
            count=len(latencies),
            mean_ms=_mean(latencies),
            p50_ms=_percentile(latencies, 0.5),
            p95_ms=_percentile(latencies, 0.95),
        ),
    )


__all__ = ["aggregate_metrics", "normalize_coordinate", "score_case"]
