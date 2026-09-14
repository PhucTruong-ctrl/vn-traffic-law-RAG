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
    coordinate = value if isinstance(value, Coordinate) else Coordinate.model_validate(value)
    document_value = coordinate.document_id or coordinate.document
    if not document_value:
        raise ValueError("coordinate is missing canonical document identity")

    def clean(item: str | None, *, numeric: bool = False) -> str | None:
        if item is None or not item.strip():
            return None
        normalized = " ".join(item.split()).casefold()
        if numeric:
            for prefix in ("điều ", "dieu ", "khoản ", "khoan "):
                normalized = normalized.removeprefix(prefix)
            normalized = normalized.removesuffix(".")
            if normalized.isdigit():
                normalized = str(int(normalized))
        return normalized or None

    document = clean(document_value)
    if document is None:
        raise ValueError("coordinate is missing canonical document identity")
    return (
        document,
        clean(coordinate.article, numeric=True),
        clean(coordinate.clause, numeric=True),
        clean(coordinate.point),
    )


def canonical_coordinate_string(value: Coordinate | dict[str, object]) -> str:
    document, article, clause, point = normalize_coordinate(value)
    return "__".join(
        [document]
        + [
            f"{prefix}{part}"
            for prefix, part in (("dieu-", article), ("khoan-", clause), ("diem-", point))
            if part is not None
        ]
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


def recall_at_k(expected: list[Coordinate], actual: list[Coordinate], k: int) -> float | None:
    """Return exact stable-coordinate recall for the first ``k`` retrieved items."""
    if k < 1:
        raise ValueError("k must be positive")
    if not expected:
        return None
    wanted = {normalize_coordinate(item) for item in expected}
    found = {normalize_coordinate(item) for item in actual[:k]}
    return sum(item in found for item in wanted) / len(wanted)


def coordinate_accuracy(
    expected: list[Coordinate], actual: list[Coordinate], level: int
) -> float | None:
    """Return hierarchical accuracy at document/article/clause/point level."""
    return _accuracy(expected, actual, level)


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


__all__ = [
    "aggregate_metrics",
    "canonical_coordinate_string",
    "coordinate_accuracy",
    "normalize_coordinate",
    "recall_at_k",
    "score_case",
]
