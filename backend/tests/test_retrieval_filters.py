from __future__ import annotations

from datetime import date

from qdrant_client import models

from app.retrieval.filters import (
    build_temporal_filter,
    filter_payloads_temporally,
    is_payload_temporally_valid,
)

START = date(2024, 1, 10)
END = date(2024, 2, 10)


def _payload(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "review_status": "ACCEPTED",
        "effective_from": START.isoformat(),
        "effective_to": END.isoformat(),
        "vehicle_types": ["CAR", "MOTORCYCLE"],
    }
    value.update(overrides)
    return value


def test_half_open_interval_boundaries() -> None:
    assert not is_payload_temporally_valid(_payload(), START.replace(day=9))
    assert is_payload_temporally_valid(_payload(), START)
    assert is_payload_temporally_valid(_payload(), date(2024, 2, 9))
    assert not is_payload_temporally_valid(_payload(), END)


def test_open_ended_interval_is_valid_after_start() -> None:
    assert is_payload_temporally_valid(_payload(effective_to=None), date(2030, 1, 1))


def test_review_status_and_vehicle_type_are_enforced() -> None:
    assert not is_payload_temporally_valid(_payload(review_status="PENDING"), START)
    assert is_payload_temporally_valid(_payload(), START, vehicle_type="CAR")
    assert not is_payload_temporally_valid(_payload(), START, vehicle_type="TRUCK")
    assert not is_payload_temporally_valid(_payload(vehicle_types=[]), START, vehicle_type="CAR")


def test_filter_preserves_valid_payloads_and_order() -> None:
    valid = _payload()
    future = _payload(effective_from="2025-01-01")
    assert filter_payloads_temporally([future, valid], START) == [valid]


def test_qdrant_filter_requires_accepted_half_open_interval_and_vehicle() -> None:
    temporal_filter = build_temporal_filter(START, vehicle_type="CAR")

    assert temporal_filter.must is not None
    assert any(
        isinstance(condition, models.FieldCondition)
        and condition.key == "review_status"
        and condition.match == models.MatchValue(value="ACCEPTED")
        for condition in temporal_filter.must
    )
    assert any(
        isinstance(condition, models.FieldCondition)
        and condition.key == "vehicle_types"
        and condition.match == models.MatchValue(value="CAR")
        for condition in temporal_filter.must
    )
    assert any(
        isinstance(condition, models.IsNullCondition)
        for condition in temporal_filter.should
    )
    assert any(
        isinstance(condition, models.FieldCondition)
        and condition.key == "effective_to"
        and condition.range is not None
        and condition.range.gt is not None
        for condition in temporal_filter.should
    )
