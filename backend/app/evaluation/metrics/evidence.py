"""Deterministic evidence coverage metrics."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from .retrieval import MetricReport


def _as_set(values: Iterable[object]) -> set[str]:
    return {getattr(value, "value", str(value)) for value in values}


def evidence_set_recall(required: Iterable[object], covered: Iterable[object]) -> float | None:
    required_set, covered_set = _as_set(required), _as_set(covered)
    if not required_set:
        return None
    return len(required_set & covered_set) / len(required_set)


def all_required_evidence_at_10(required: Iterable[object], retrieved_evidence: Sequence[object]) -> bool | None:
    required_set = _as_set(required)
    if not required_set:
        return None
    covered = _as_set(retrieved_evidence[:10])
    return required_set <= covered


def cross_reference_resolution_recall(expected_targets: Iterable[str], resolved_targets: Iterable[str]) -> float | None:
    expected = set(expected_targets)
    if not expected:
        return None
    return len(expected & set(resolved_targets)) / len(expected)


def multi_hop_evidence_completeness(required_hops: Iterable[object], collected_hops: Iterable[object]) -> bool | None:
    required = _as_set(required_hops)
    if not required:
        return None
    return required <= _as_set(collected_hops)


def _report(name: str, values: Mapping[str, float | None], categories: Mapping[str, str]) -> MetricReport:
    eligible = {key: value for key, value in values.items() if value is not None}
    if not eligible:
        return MetricReport.na("no eligible queries", per_query=dict(values))
    grouped: dict[str, list[float]] = defaultdict(list)
    for key, value in eligible.items():
        grouped[categories.get(key, "uncategorized")].append(value)
    return MetricReport(
        sum(eligible.values()) / len(eligible), len(eligible), len(eligible),
        per_query=dict(values), by_category={key: sum(v) / len(v) for key, v in grouped.items()},
    )


def evaluate_evidence(
    queries: Mapping[str, Mapping[str, object]] | Sequence[Mapping[str, object]],
) -> dict[str, MetricReport]:
    """Evaluate evidence metrics over records with explicit evidence sets.

    ``required_evidence`` is the gold set. Records may provide ``covered_evidence``,
    ``retrieved_evidence`` (ordered), ``expected_relation_targets`` and
    ``resolved_relation_targets``, plus ``required_hops``/``collected_hops``.
    """
    records = list(queries.values()) if isinstance(queries, Mapping) else list(queries)
    names = ("evidence_set_recall", "all_required_evidence@10", "cross_reference_resolution_recall", "multi_hop_evidence_completeness")
    values = {name: {} for name in names}
    categories: dict[str, str] = {}
    for index, record in enumerate(records):
        key = str(record.get("id", index))
        required = record.get("required_evidence", [])  # type: ignore[assignment]
        categories[key] = str(record.get("category", "uncategorized"))
        covered = record.get("covered_evidence", record.get("retrieved_evidence", []))
        values["evidence_set_recall"][key] = evidence_set_recall(required, covered)  # type: ignore[arg-type]
        values["all_required_evidence@10"][key] = float(all_required_evidence_at_10(required, record.get("retrieved_evidence", [])[:10])) if all_required_evidence_at_10(required, record.get("retrieved_evidence", [])[:10]) is not None else None  # type: ignore[index,arg-type]
        expected_targets = record.get("expected_relation_targets", [])
        values["cross_reference_resolution_recall"][key] = cross_reference_resolution_recall(expected_targets, record.get("resolved_relation_targets", []))  # type: ignore[arg-type]
        values["multi_hop_evidence_completeness"][key] = float(multi_hop_evidence_completeness(record.get("required_hops", required), record.get("collected_hops", covered))) if multi_hop_evidence_completeness(record.get("required_hops", required), record.get("collected_hops", covered)) is not None else None  # type: ignore[arg-type]
    return {name: _report(name, result, categories) for name, result in values.items()}


__all__ = ["evidence_set_recall", "all_required_evidence_at_10", "cross_reference_resolution_recall", "multi_hop_evidence_completeness", "evaluate_evidence"]
