"""Temporal and vehicle filters for the derived Qdrant provision index."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, time, timezone

from qdrant_client import models

_ACCEPTED = "ACCEPTED"


def _at_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def build_temporal_filter(
    query_date: date, *, vehicle_type: str | None = None
) -> models.Filter:
    """Build Qdrant's accepted, half-open validity filter for ``query_date``.

    Date payloads are indexed as Qdrant datetimes.  ``effective_to`` is kept
    open-ended by the explicit null branch rather than using a sentinel date.
    """
    must: list[models.Condition] = [
        models.FieldCondition(key="review_status", match=models.MatchValue(value=_ACCEPTED)),
        models.FieldCondition(
            key="effective_from",
            range=models.DatetimeRange(lte=_at_midnight(query_date)),
        ),
    ]
    if vehicle_type is not None:
        must.append(
            models.FieldCondition(
                key="vehicle_types", match=models.MatchValue(value=vehicle_type)
            )
        )

    return models.Filter(
        must=must,
        should=[
            models.IsNullCondition(is_null=models.PayloadField(key="effective_to")),
            models.FieldCondition(
                key="effective_to",
                range=models.DatetimeRange(gt=_at_midnight(query_date)),
            ),
        ],
    )


def _payload_date(payload: Mapping[str, object], key: str) -> date | None:
    value = payload.get(key)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def is_payload_temporally_valid(
    payload: Mapping[str, object], query_date: date, *, vehicle_type: str | None = None
) -> bool:
    """Return whether a payload satisfies the authoritative serving predicate."""
    if payload.get("review_status") != _ACCEPTED:
        return False
    effective_from = _payload_date(payload, "effective_from")
    if effective_from is None or effective_from > query_date:
        return False
    effective_to = _payload_date(payload, "effective_to")
    if payload.get("effective_to") is not None and effective_to is None:
        return False
    if effective_to is not None and query_date >= effective_to:
        return False
    if vehicle_type is not None:
        vehicle_types = payload.get("vehicle_types")
        if not isinstance(vehicle_types, (list, tuple, set)) or vehicle_type not in vehicle_types:
            return False
    return True


def filter_payloads_temporally(
    payloads: Iterable[Mapping[str, object]],
    query_date: date,
    *,
    vehicle_type: str | None = None,
) -> list[Mapping[str, object]]:
    """Keep payloads valid at ``query_date`` without mutating their mappings."""
    return [
        payload
        for payload in payloads
        if is_payload_temporally_valid(payload, query_date, vehicle_type=vehicle_type)
    ]


# Short aliases keep call sites readable while the descriptive names remain the API.
payload_is_valid_at = is_payload_temporally_valid
filter_payloads = filter_payloads_temporally

__all__ = [
    "build_temporal_filter",
    "filter_payloads",
    "filter_payloads_temporally",
    "is_payload_temporally_valid",
    "payload_is_valid_at",
]
