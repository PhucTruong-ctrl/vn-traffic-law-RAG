"""Bounded, failure-aware workflow repair routing."""

from __future__ import annotations

from typing import Any

MAX_REPAIR_ATTEMPTS = 3
ABSTAIN = "abstain"


def repair_reason(state: dict[str, Any]) -> str | None:
    result = state.get("verification_result") or {}
    return result.get("reason_code") if isinstance(result, dict) else None


def repair_route(state: dict[str, Any], *, max_attempts: int = MAX_REPAIR_ATTEMPTS) -> str:
    """Choose one bounded repair action, or terminal abstention.

    L1 regenerates the structured answer; L2 rebuilds context/retrieval; L3
    retries temporal resolution. L4-L6 unsupported claims use regeneration.
    Unknown failures are terminal rather than looping indefinitely.
    """
    if state.get("repair_attempts", 0) >= max_attempts:
        return ABSTAIN
    reason = repair_reason(state)
    if reason == "L1_SCHEMA_INVALID" or reason == "L1_SUMMARY_UNSUPPORTED":
        return "regenerate"
    if reason in {"L2_INVALID_CITATION", "L2_UNKNOWN_PROVISION"}:
        return "targeted_retrieval"
    if reason in {"L3_TEMPORAL_INVALID", "L3_TEMPORAL_RETRY"}:
        return "temporal_retry"
    if reason and any(reason.startswith(prefix) for prefix in ("L4_", "L5_", "L6_")):
        return "regenerate"
    return ABSTAIN


def next_attempt(state: dict[str, Any]) -> dict[str, int]:
    """Return the shared monotonic repair counter update."""
    return {"repair_attempts": state.get("repair_attempts", 0) + 1}


__all__ = ["ABSTAIN", "MAX_REPAIR_ATTEMPTS", "next_attempt", "repair_reason", "repair_route"]
