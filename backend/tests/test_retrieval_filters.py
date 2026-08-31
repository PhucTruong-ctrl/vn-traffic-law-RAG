from __future__ import annotations

from datetime import date

from qdrant_client import models

from app.retrieval.contracts import RetrievalResult
from app.retrieval.filters import (
    build_temporal_filter,
    deduplicate_results,
    filter_payloads_temporally,
    is_payload_temporally_valid,
    normalize_vehicle_type,
)


def _result(
    provision_id: str,
    *,
    rank: int,
    sources: list[str],
    parent_context: str | None = None,
    fused_score: float | None = 0.5,
) -> RetrievalResult:
    return RetrievalResult(
        rank=rank,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc-1",
        document_version_id="doc-version-1",
        text="Nội dung",
        source_text="Nguồn",
        parent_context=parent_context,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause=None,
        point=None,
        effective_from=START,
        effective_to=None,
        page_number=1,
        retrieval_sources=sources,
        fused_score=fused_score,
        added_by=None,
        source_id=None,
        depth=0,
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


def test_vehicle_terms_normalize_and_unrestricted_payloads_are_kept() -> None:
    assert normalize_vehicle_type("xe máy") == "MOTORCYCLE"
    assert normalize_vehicle_type(" ô tô ") == "CAR"
    assert normalize_vehicle_type("xe đạp") == "BICYCLE"
    assert is_payload_temporally_valid(_payload(vehicle_types=[]), START, vehicle_type="xe máy")
    assert is_payload_temporally_valid(
        _payload(vehicle_types=["MOTORCYCLE"]), START, vehicle_type="xe máy"
    )
    assert not is_payload_temporally_valid(
        _payload(vehicle_types=["CAR"]), START, vehicle_type="xe máy"
    )


def test_vehicle_filter_matches_raw_vietnamese_and_excludes_other_vehicle() -> None:
    assert is_payload_temporally_valid(
        _payload(vehicle_types=["xe máy"]), START, vehicle_type="MOTORCYCLE"
    )
    assert not is_payload_temporally_valid(
        _payload(vehicle_types=["ô tô"]), START, vehicle_type="xe máy"
    )
    assert is_payload_temporally_valid(
        _payload(vehicle_types=["ô tô"]), START, vehicle_type="CAR"
    )
    assert not is_payload_temporally_valid(
        _payload(vehicle_types=["xe máy"]), START, vehicle_type="ô tô"
    )

def test_filter_preserves_valid_payloads_and_order() -> None:
    valid = _payload()
    future = _payload(effective_from="2025-01-01")
    assert filter_payloads_temporally([future, valid], START) == [valid]


def test_qdrant_filter_requires_accepted_half_open_interval_and_vehicle() -> None:
    temporal_filter = build_temporal_filter(START, vehicle_type="xe máy")

    assert temporal_filter.must is not None
    assert any(
        isinstance(condition, models.FieldCondition)
        and condition.key == "review_status"
        and condition.match == models.MatchValue(value="ACCEPTED")
        for condition in temporal_filter.must
    )
    vehicle_filter = next(
        condition
        for condition in temporal_filter.must
        if isinstance(condition, models.Filter)
    )
    assert vehicle_filter.should is not None
    assert any(
        isinstance(condition, models.FieldCondition)
        and condition.key == "vehicle_types"
        and condition.match == models.MatchValue(value="MOTORCYCLE")
        for condition in vehicle_filter.should
    )
    assert any(
        isinstance(condition, models.FieldCondition)
        and condition.key == "vehicle_types"
        and condition.match == models.MatchValue(value="xe máy")
        for condition in vehicle_filter.should
    )
    assert any(
        isinstance(condition, models.IsEmptyCondition)
        and condition.is_empty == models.PayloadField(key="vehicle_types")
        for condition in vehicle_filter.should
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


def test_deduplicate_keeps_lowest_rank_and_merges_sources_and_parent() -> None:
    duplicate_late = _result("p1", rank=4, sources=["dense"])
    duplicate_best = _result("p1", rank=2, sources=["sparse", "dense"], parent_context="Điều 7")

    [result] = deduplicate_results([duplicate_late, duplicate_best])

    assert result.rank == 2
    assert result.retrieval_sources == ["dense", "sparse"]
    assert result.parent_context == "Điều 7"


def test_deduplicate_preserves_stable_order_for_equal_ranks() -> None:
    results = [
        _result("first", rank=1, sources=["dense"]),
        _result("second", rank=1, sources=["sparse"]),
        _result("first", rank=1, sources=["exact"]),
    ]

    deduplicated = deduplicate_results(results)

    assert [result.provision_id for result in deduplicated] == ["first", "second"]
    assert deduplicated[0].retrieval_sources == ["dense", "exact"]


def test_deduplicate_promotes_exact_ids_without_rewriting_rank_or_score() -> None:
    results = [
        _result("semantic", rank=1, sources=["dense"], fused_score=0.9),
        _result("exact", rank=5, sources=["exact"], fused_score=None),
    ]

    deduplicated = deduplicate_results(results, exact_provision_ids={"exact"})

    assert [result.provision_id for result in deduplicated] == ["exact", "semantic"]
    assert deduplicated[0].rank == 5
    assert deduplicated[0].fused_score is None


def test_deduplicate_uses_parent_metadata_from_any_duplicate() -> None:
    results = [
        _result("p1", rank=1, sources=["dense"], parent_context=None),
        _result("p1", rank=3, sources=["parent"], parent_context="Khoản 2"),
    ]

    [result] = deduplicate_results(results)

    assert result.rank == 1
    assert result.parent_context == "Khoản 2"
