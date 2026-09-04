"""Deterministic L3 verification of temporal citation validity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

L3_TEMPORAL_INVALID = "L3_TEMPORAL_INVALID"
ACCEPTED_REVIEW_STATUS = "ACCEPTED"


@dataclass(frozen=True)
class TemporalVerificationResult:
    """L3 outcome; comparison sides are evaluated independently."""

    verified: bool
    reason_code: str | None = None
    invalid_provision_ids: tuple[str, ...] = ()


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _valid(item: Any, query_date: date) -> bool:
    if _value(item, "review_status") != ACCEPTED_REVIEW_STATUS:
        return False
    start = _value(item, "effective_from")
    end = _value(item, "effective_to")
    return isinstance(start, date) and start <= query_date and (end is None or query_date < end)


def verify_temporal(
    citations: Sequence[Any], *, query_date: date | None
) -> TemporalVerificationResult:
    """Verify every cited provision at ``query_date`` using [from, to)."""
    if query_date is None:
        return TemporalVerificationResult(False, L3_TEMPORAL_INVALID)
    invalid = tuple(
        str(_value(item, "provision_id", "")) for item in citations if not _valid(item, query_date)
    )
    return TemporalVerificationResult(
        not invalid,
        None if not invalid else L3_TEMPORAL_INVALID,
        invalid,
    )


def verify_comparison_temporal(
    before: Sequence[Any],
    after: Sequence[Any],
    *,
    date_from: date | None,
    date_to: date | None,
) -> tuple[TemporalVerificationResult, TemporalVerificationResult]:
    """Validate before and after citation sets independently."""
    return (
        verify_temporal(before, query_date=date_from),
        verify_temporal(after, query_date=date_to),
    )


__all__ = [
    "ACCEPTED_REVIEW_STATUS",
    "L3_TEMPORAL_INVALID",
    "TemporalVerificationResult",
    "verify_comparison_temporal",
    "verify_temporal",
]
