"""Deterministic temporal validity metrics for cited provisions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date
from typing import cast

from .retrieval import MetricReport


def _date(value: object) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def is_temporally_valid(provision: Mapping[str, object], query_date: date) -> bool:
    """Return whether an accepted provision applies at the supplied date."""
    if str(provision.get("review_status", "ACCEPTED")) != "ACCEPTED":
        return False
    start, end = _date(provision.get("effective_from")), _date(provision.get("effective_to"))
    return start is not None and start <= query_date and (end is None or query_date < end)


def temporal_validity_accuracy(
    citations: Sequence[Mapping[str, object]], query_date: date
) -> float | None:
    if not citations:
        return None
    return sum(is_temporally_valid(item, query_date) for item in citations) / len(citations)


def temporal_leakage_rate(
    citations: Sequence[Mapping[str, object]], query_date: date
) -> float | None:
    accuracy = temporal_validity_accuracy(citations, query_date)
    return None if accuracy is None else 1 - accuracy


def _aggregate(values: Mapping[str, float | None], categories: Mapping[str, str]) -> MetricReport:
    eligible = {key: value for key, value in values.items() if value is not None}
    if not eligible:
        return MetricReport.na(
            "no citations eligible for temporal evaluation", per_query=dict(values)
        )
    grouped: dict[str, list[float]] = defaultdict(list)
    for key, value in eligible.items():
        grouped[categories.get(key, "uncategorized")].append(value)
    return MetricReport(
        sum(eligible.values()) / len(eligible),
        len(eligible),
        len(eligible),
        per_query=dict(values),
        by_category={key: sum(v) / len(v) for key, v in grouped.items()},
    )


def evaluate_temporal(
    queries: Mapping[str, Mapping[str, object]] | Sequence[Mapping[str, object]],
) -> dict[str, MetricReport]:
    """Evaluate temporal validity and leakage over query records.

    Each record contains ``query_date`` and ordered mapping citations in
    ``citations`` (or ``results``), with effective interval and review metadata.
    """
    records = list(queries.values()) if isinstance(queries, Mapping) else list(queries)
    values: dict[str, dict[str, float | None]] = {
        "temporal_validity_accuracy": {},
        "temporal_leakage_rate": {},
    }
    categories: dict[str, str] = {}
    for index, record in enumerate(records):
        key = str(record.get("id", index))
        categories[key] = str(record.get("category", "uncategorized"))
        query_date = _date(record.get("query_date"))
        citations = cast(
            Sequence[Mapping[str, object]], record.get("citations", record.get("results", []))
        )
        if query_date is None:
            valid = leakage = None
        else:
            valid = temporal_validity_accuracy(citations, query_date)
            leakage = temporal_leakage_rate(citations, query_date)
        values["temporal_validity_accuracy"][key] = valid
        values["temporal_leakage_rate"][key] = leakage
    return {name: _aggregate(result, categories) for name, result in values.items()}


__all__ = [
    "is_temporally_valid",
    "temporal_validity_accuracy",
    "temporal_leakage_rate",
    "evaluate_temporal",
]
