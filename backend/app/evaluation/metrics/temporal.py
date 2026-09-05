"""Deterministic temporal metrics for validity and context separation."""

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
    if provision.get("review_status") != "ACCEPTED":
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


def _citation_ids(values: object) -> set[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return set()
    return {
        str(item.get("provision_id"))
        if isinstance(item, Mapping) and item.get("provision_id") is not None
        else str(item)
        for item in values
    }


def current_historical_separation_accuracy(record: Mapping[str, object]) -> float | None:
    """Score CURRENT/HISTORICAL citations as one if all are valid at query_date.

    Contract: category, query_date, and non-empty citations (or results).
    Other categories and missing/empty populations are NA.
    """
    if str(record.get("category", "")) not in {"CURRENT", "HISTORICAL"}:
        return None
    query_date = _date(record.get("query_date"))
    citations = cast(
        Sequence[Mapping[str, object]], record.get("citations", record.get("results", []))
    )
    if query_date is None or not citations:
        return None
    return float(all(is_temporally_valid(item, query_date) for item in citations))


def comparison_separation_accuracy(record: Mapping[str, object]) -> float | None:
    """Score independent before/after citation populations for COMPARISON.

    Contract: comparison_dates is a pair of dates and comparison_citations is
    {"before": [...], "after": [...]}. Both sides must be non-empty, valid at
    their own date, and have no citation ID in common. Missing data is NA.
    """
    if str(record.get("category", "")) != "COMPARISON":
        return None
    raw_dates = record.get("comparison_dates")
    if (
        not isinstance(raw_dates, Sequence)
        or isinstance(raw_dates, (str, bytes))
        or len(raw_dates) != 2
    ):
        return None
    dates = (_date(raw_dates[0]), _date(raw_dates[1]))
    sides = record.get("comparison_citations")
    if not isinstance(sides, Mapping) or dates[0] is None or dates[1] is None:
        return None
    before, after = sides.get("before", []), sides.get("after", [])
    if (
        not isinstance(before, Sequence)
        or isinstance(before, (str, bytes))
        or not before
        or not isinstance(after, Sequence)
        or isinstance(after, (str, bytes))
        or not after
    ):
        return None
    if _citation_ids(before) & _citation_ids(after):
        return 0.0
    return float(
        all(is_temporally_valid(item, dates[0]) for item in before)
        and all(is_temporally_valid(item, dates[1]) for item in after)
    )


def evaluate_temporal(
    queries: Mapping[str, Mapping[str, object]] | Sequence[Mapping[str, object]],
) -> dict[str, MetricReport]:
    """Evaluate validity, leakage, and temporal separation over records.

    Records contain category, query_date, and citations/results. COMPARISON
    records additionally contain comparison_dates and comparison_citations.
    """
    records = list(queries.values()) if isinstance(queries, Mapping) else list(queries)
    values: dict[str, dict[str, float | None]] = {
        "temporal_validity_accuracy": {},
        "temporal_leakage_rate": {},
        "current_historical_separation_accuracy": {},
        "comparison_separation_accuracy": {},
    }
    categories: dict[str, str] = {}
    for index, record in enumerate(records):
        key = str(record.get("id", index))
        categories[key] = str(record.get("category", "uncategorized"))
        query_date = _date(record.get("query_date"))
        citations = cast(
            Sequence[Mapping[str, object]], record.get("citations", record.get("results", []))
        )
        valid = leakage = None
        if query_date is not None:
            valid, leakage = (
                temporal_validity_accuracy(citations, query_date),
                temporal_leakage_rate(citations, query_date),
            )
        values["temporal_validity_accuracy"][key] = valid
        values["temporal_leakage_rate"][key] = leakage
        values["current_historical_separation_accuracy"][key] = (
            current_historical_separation_accuracy(record)
        )
        values["comparison_separation_accuracy"][key] = comparison_separation_accuracy(record)
    return {name: _aggregate(result, categories) for name, result in values.items()}


__all__ = [
    "is_temporally_valid",
    "temporal_validity_accuracy",
    "temporal_leakage_rate",
    "current_historical_separation_accuracy",
    "comparison_separation_accuracy",
    "evaluate_temporal",
]
