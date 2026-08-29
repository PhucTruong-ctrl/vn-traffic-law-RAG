from datetime import date

from app.ingestion.temporal_resolver import EVENT_TYPES, resolve_temporal


def test_all_event_types_are_supported() -> None:
    assert {
        "EFFECTIVE",
        "AMENDED",
        "PARTIAL_AMENDED",
        "SUPERSEDED",
        "REPEALED",
        "CORRECTED",
        "EXPIRED",
    } == EVENT_TYPES


def test_partial_amendment_creates_half_open_lineage() -> None:
    result = resolve_temporal(
        {"effective_from": "2024-01-01", "review_status": "ACCEPTED"},
        [
            {
                "event_type": "PARTIAL_AMENDED",
                "event_date": "2025-01-01",
                "review_status": "ACCEPTED",
                "affected_provision_versions": [{"provision_id": "p"}],
            }
        ],
    )
    assert [(item.version, item.effective_from, item.effective_to) for item in result.versions] == [
        (1, date(2024, 1, 1), date(2025, 1, 1)),
        (2, date(2025, 1, 1), None),
    ]
    assert result.versions[0].superseded_by_version == 2
    assert result.versions[1].lineage[0]["event_type"] == "PARTIAL_AMENDED"


def test_manifest_provisions_resolve_without_effect_events() -> None:
    result = resolve_temporal(
        {
            "effective_from": "2024-01-01",
            "review_status": "ACCEPTED",
            "provisions": [{"provision_id": "p", "version": 1}],
        }
    )

    assert result.review_required is False
    assert [(item.provision_id, item.version, item.effective_from) for item in result.versions] == [
        ("p", 1, date(2024, 1, 1))
    ]


def test_uncertain_date_routes_review_and_blocks_index() -> None:
    result = resolve_temporal(
        {"effective_from": "UNKNOWN", "review_status": "ACCEPTED"},
        [
            {
                "event_type": "EFFECTIVE",
                "event_date": None,
                "affected_provision_versions": [{"provision_id": "p"}],
            }
        ],
    )
    assert result.review_required
    assert result.errors
    assert all(not item.indexable for item in result.versions)


def test_missing_event_date_requires_review_with_manifest_base_date() -> None:
    result = resolve_temporal(
        {
            "effective_from": "2024-01-01",
            "review_status": "ACCEPTED",
            "provisions": [{"provision_id": "p", "version": 1}],
        },
        [
            {
                "event_type": "AMENDED",
                "event_date": None,
                "review_status": "ACCEPTED",
                "affected_provision_versions": [{"provision_id": "p"}],
            }
        ],
    )

    assert result.review_required is True
    assert result.errors == ("uncertain event date: AMENDED",)
    assert result.versions[0].indexable is False


def test_terminal_event_closes_interval_at_event_date() -> None:
    result = resolve_temporal(
        {"effective_from": "2024-01-01", "review_status": "ACCEPTED"},
        [
            {
                "event_type": "REPEALED",
                "event_date": "2025-06-01",
                "review_status": "ACCEPTED",
                "affected_provision_versions": [{"provision_id": "p"}],
            }
        ],
    )
    assert result.versions[0].effective_to == date(2025, 6, 1)
