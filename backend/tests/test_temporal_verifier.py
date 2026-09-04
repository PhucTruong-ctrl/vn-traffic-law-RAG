from datetime import date

from app.query.temporal_verifier import (
    L3_TEMPORAL_INVALID,
    verify_comparison_temporal,
    verify_temporal,
)


def item(provision_id="p", start=date(2020, 1, 1), end=None, status="ACCEPTED"):
    return {
        "provision_id": provision_id,
        "effective_from": start,
        "effective_to": end,
        "review_status": status,
    }


def test_interval_is_inclusive_exclusive_and_accepted_only():
    assert verify_temporal([item(end=date(2024, 1, 1))], query_date=date(2023, 12, 31)).verified
    result = verify_temporal([item(end=date(2024, 1, 1))], query_date=date(2024, 1, 1))
    assert not result.verified and result.reason_code == L3_TEMPORAL_INVALID
    assert not verify_temporal([item(status="PENDING")], query_date=date(2023, 1, 1)).verified


def test_comparison_sides_fail_independently():
    before, after = verify_comparison_temporal(
        [item("before", start=date(2018, 1, 1), end=date(2020, 1, 1))],
        [item("after", start=date(2025, 1, 1))],
        date_from=date(2019, 1, 1),
        date_to=date(2024, 1, 1),
    )
    assert before.verified
    assert not after.verified
