from __future__ import annotations

import pytest

from app.evaluation.metrics.performance import (
    aggregate_numeric,
    aggregate_performance,
    aggregate_token_usage,
    enforce_budget,
)


def test_aggregates_numeric_values_without_treating_missing_as_zero() -> None:
    records = [{"latency_ms": 10}, {"latency_ms": None}, {}, {"latency_ms": 30}]
    assert aggregate_numeric(records, "latency_ms") == {"value": 20.0, "count": 2}


def test_all_missing_values_remain_na() -> None:
    records = [{"latency_ms": None}, {"token_usage": None}, {"estimated_cost": None}]
    assert aggregate_numeric(records, "latency_ms") == {
        "value": None,
        "count": 0,
        "reason": "no eligible values",
    }
    assert aggregate_token_usage(records)["value"] is None


def test_sums_token_counters_and_enforces_cost_and_token_budgets() -> None:
    records = [
        {
            "latency_ms": 12,
            "token_usage": {"input_tokens": 10, "output_tokens": 5},
            "estimated_cost": 0.04,
        },
        {
            "latency_ms": 20,
            "token_usage": {"input_tokens": 4, "output_tokens": 6},
            "estimated_cost": 0.03,
        },
    ]
    report = aggregate_performance(records, budget_usd=0.05, budget_tokens=30)
    assert report["latency_ms"] == {"value": 16.0, "count": 2}
    assert report["token_usage"] == {
        "value": {"input_tokens": 14.0, "output_tokens": 11.0},
        "count": 2,
    }
    assert report["estimated_cost"] == {"value": 0.035, "count": 2}
    assert report["exceeded"] is False
    assert report["status"] == "within_budget"

    exceeded = enforce_budget(records, budget_usd=0.03, budget_tokens=20)
    assert exceeded["exceeded"] is True
    assert exceeded["status"] == "exceeded"


def test_budget_limits_are_validated() -> None:
    with pytest.raises(ValueError, match="budget_usd"):
        enforce_budget([], budget_usd=-1)
    with pytest.raises(ValueError, match="budget_tokens"):
        enforce_budget([], budget_tokens=-1)
