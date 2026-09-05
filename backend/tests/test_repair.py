"""Behavioral tests for bounded workflow repair routing."""

from __future__ import annotations

from app.workflow.repair import ABSTAIN, MAX_REPAIR_ATTEMPTS, next_attempt, repair_route


def test_repair_route_selects_actions_for_reason_levels() -> None:
    cases = {
        "L1_SCHEMA_INVALID": "regenerate",
        "L1_SUMMARY_UNSUPPORTED": "regenerate",
        "L2_INVALID_CITATION": "targeted_retrieval",
        "L2_UNKNOWN_PROVISION": "targeted_retrieval",
        "L3_TEMPORAL_INVALID": "temporal_retry",
        "L3_TEMPORAL_RETRY": "temporal_retry",
        "L4_UNSUPPORTED_CLAIM": "regenerate",
        "L5_UNSUPPORTED_CLAIM": "regenerate",
        "L6_UNSUPPORTED_CLAIM": "regenerate",
    }
    for reason, expected in cases.items():
        assert repair_route({"verification_result": {"reason_code": reason}}) == expected


def test_repair_route_abstains_for_unknown_or_missing_reason() -> None:
    assert repair_route({}) == ABSTAIN
    assert repair_route({"verification_result": {"reason_code": "OTHER"}}) == ABSTAIN


def test_next_attempt_is_monotonic_from_missing_and_existing_counter() -> None:
    assert next_attempt({}) == {"repair_attempts": 1}
    state = {"repair_attempts": 2}
    assert next_attempt(state) == {"repair_attempts": 3}
    assert state == {"repair_attempts": 2}


def test_repair_route_terminally_abstains_at_max_attempts() -> None:
    state = {
        "repair_attempts": MAX_REPAIR_ATTEMPTS,
        "verification_result": {"reason_code": "L1_SCHEMA_INVALID"},
    }
    assert repair_route(state) == ABSTAIN
    assert repair_route({**state, "repair_attempts": MAX_REPAIR_ATTEMPTS + 1}) == ABSTAIN
