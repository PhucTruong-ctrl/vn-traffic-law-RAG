"""Deterministic ranking metrics for retrieval evaluation."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import log2
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class MetricReport:
    value: float | None
    numerator: int | float | None = None
    denominator: int | float | None = None
    status: str = "computed"
    na_reason: str | None = None
    per_query: dict[str, float | None] = field(default_factory=dict)
    by_category: dict[str, float | None] = field(default_factory=dict)

    @classmethod
    def na(cls, reason: str, *, per_query: dict[str, float | None] | None = None) -> "MetricReport":
        return cls(None, status="na", na_reason=reason, per_query=per_query or {})


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def recall_at(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float | None:
    gold = set(relevant)
    if not gold:
        return None
    return len(set(retrieved[:k]) & gold) / len(gold)


def reciprocal_rank(retrieved: Sequence[str], relevant: Iterable[str], k: int = 10) -> float | None:
    gold = set(relevant)
    if not gold:
        return None
    for rank, value in enumerate(retrieved[:k], 1):
        if value in gold:
            return 1 / rank
    return 0.0


def ndcg_at(retrieved: Sequence[str], relevant: Iterable[str], k: int = 10) -> float | None:
    gold = set(relevant)
    if not gold:
        return None
    actual = sum(
        1 / log2(rank + 1)
        for rank, value in enumerate(_unique(retrieved)[:k], 1)
        if value in gold
    )
    ideal = sum(1 / log2(rank + 1) for rank in range(1, min(k, len(gold)) + 1))
    return actual / ideal if ideal else None


def _aggregate(name: str, values: Mapping[str, float | None], categories: Mapping[str, str] | None = None) -> MetricReport:
    usable = {key: value for key, value in values.items() if value is not None}
    if not usable:
        return MetricReport.na("no eligible queries", per_query=dict(values))
    by_category: dict[str, float | None] = {}
    if categories:
        grouped: dict[str, list[float]] = {}
        for key, value in usable.items():
            grouped.setdefault(categories.get(key, "uncategorized"), []).append(value)
        by_category = {key: sum(items) / len(items) for key, items in grouped.items()}
    return MetricReport(sum(usable.values()) / len(usable), len(usable), len(usable), per_query=dict(values), by_category=by_category)


def evaluate_retrieval(
    queries: Mapping[str, Mapping[str, object]] | Sequence[Mapping[str, object]],
) -> dict[str, MetricReport]:
    """Evaluate ranking metrics over query records.

    Records use ``retrieved`` and ``relevant`` (or ``expected_provision_ids``),
    with optional ``id`` and ``category`` fields.
    """
    records = list(queries.values()) if isinstance(queries, Mapping) else list(queries)
    values: dict[str, dict[str, float | None]] = {name: {} for name in ("recall@5", "recall@10", "recall@20", "mrr@10", "ndcg@10")}
    categories: dict[str, str] = {}
    for index, record in enumerate(records):
        key = str(record.get("id", index))
        retrieved = [str(value) for value in record.get("retrieved", record.get("results", []))]  # type: ignore[arg-type]
        relevant = record.get("relevant", record.get("expected_provision_ids", []))
        relevant_ids = [str(value) for value in relevant]  # type: ignore[union-attr]
        categories[key] = str(record.get("category", "uncategorized"))
        values["recall@5"][key] = recall_at(retrieved, relevant_ids, 5)
        values["recall@10"][key] = recall_at(retrieved, relevant_ids, 10)
        values["recall@20"][key] = recall_at(retrieved, relevant_ids, 20)
        values["mrr@10"][key] = reciprocal_rank(retrieved, relevant_ids)
        values["ndcg@10"][key] = ndcg_at(retrieved, relevant_ids)
    return {name: _aggregate(name, result, categories) for name, result in values.items()}


# Explicit aliases make the public contract convenient for callers and tests.
recall_at_k = recall_at
mrr_at_10 = reciprocal_rank
ndcg_at_10 = ndcg_at

__all__ = ["MetricReport", "recall_at", "recall_at_k", "reciprocal_rank", "mrr_at_10", "ndcg_at", "ndcg_at_10", "evaluate_retrieval"]
