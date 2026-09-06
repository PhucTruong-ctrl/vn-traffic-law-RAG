"""Deterministic performance aggregation and budget reporting helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from numbers import Real
from typing import Any

NA_REASON = "no eligible values"


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, Real) and not isinstance(value, bool) else None


def aggregate_numeric(records: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    """Return a mean over present numeric values, preserving NA when absent."""
    values = [
        number
        for number in (_number(record.get(field)) for record in records)
        if number is not None
    ]
    if not values:
        return {"value": None, "count": 0, "reason": NA_REASON}
    return {"value": sum(values) / len(values), "count": len(values)}


def _usage(record: Mapping[str, Any]) -> dict[str, float]:
    value = record.get("token_usage")
    if isinstance(value, Mapping):
        return {
            str(key): number for key, raw in value.items() if (number := _number(raw)) is not None
        }
    total = _number(value)
    return {"total_tokens": total} if total is not None else {}


def aggregate_token_usage(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Sum numeric token counters across records; missing records stay ineligible."""
    totals: dict[str, float] = {}
    count = 0
    for record in records:
        usage = _usage(record)
        if not usage:
            continue
        count += 1
        for key, value in usage.items():
            totals[key] = totals.get(key, 0.0) + value
    if not totals:
        return {"value": None, "count": 0, "reason": NA_REASON}
    return {"value": totals, "count": count}


def enforce_budget(
    records: Sequence[Mapping[str, Any]],
    *,
    budget_usd: float | None = None,
    budget_tokens: float | None = None,
) -> dict[str, Any]:
    """Report deterministic budget usage and whether configured limits are exceeded."""
    if budget_usd is not None and budget_usd < 0:
        raise ValueError("budget_usd must be non-negative")
    if budget_tokens is not None and budget_tokens < 0:
        raise ValueError("budget_tokens must be non-negative")
    cost = aggregate_numeric(records, "estimated_cost")
    usage = aggregate_token_usage(records)
    token_total = None if usage["value"] is None else usage["value"].get("total_tokens")
    exceeded = bool(
        (budget_usd is not None and cost["value"] is not None and cost["value"] > budget_usd)
        or (budget_tokens is not None and token_total is not None and token_total > budget_tokens)
    )
    return {
        "estimated_cost": cost,
        "token_usage": usage,
        "budget_usd": budget_usd,
        "budget_tokens": budget_tokens,
        "exceeded": exceeded,
        "status": "exceeded" if exceeded else "within_budget",
    }


def aggregate_performance(
    records: Sequence[Mapping[str, Any]],
    *,
    budget_usd: float | None = None,
    budget_tokens: float | None = None,
) -> dict[str, Any]:
    """Build a report for latency, tokens, estimated cost, and budget status."""
    return {
        "latency_ms": aggregate_numeric(records, "latency_ms"),
        **enforce_budget(records, budget_usd=budget_usd, budget_tokens=budget_tokens),
    }


__all__ = [
    "aggregate_numeric",
    "aggregate_token_usage",
    "aggregate_performance",
    "enforce_budget",
]
