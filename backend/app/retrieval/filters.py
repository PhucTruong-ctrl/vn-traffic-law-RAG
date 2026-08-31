"""Temporal and vehicle filters for the derived Qdrant provision index."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, time

from qdrant_client import models

from app.ingestion.terminology import canonical_term

from .contracts import RetrievalResult

_ACCEPTED = "ACCEPTED"
_VEHICLE_TYPE_ALIASES = {
    "xe đạp": "BICYCLE",
    "xe máy": "MOTORCYCLE",
    "xe mô tô": "MOTORCYCLE",
    "xe gắn máy": "MOTORCYCLE",
    "ô tô": "CAR",
    "xe ô tô": "CAR",
}


def normalize_vehicle_type(vehicle_type: str) -> str:
    """Map Vietnamese query terms to the enum values stored in Qdrant."""
    normalized = canonical_term(vehicle_type)
    return _VEHICLE_TYPE_ALIASES.get(normalized.casefold(), normalized.upper())

def _at_midnight(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=UTC)


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
        normalized_vehicle_type = normalize_vehicle_type(vehicle_type)
        must.append(
            models.Filter(
                should=[
                    models.FieldCondition(
                        key="vehicle_types",
                        match=models.MatchValue(value=normalized_vehicle_type),
                    ),
                    # Indexing stores [] when no vehicle restriction was given.
                    models.IsEmptyCondition(
                        is_empty=models.PayloadField(key="vehicle_types")
                    ),
                ]
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
        normalized_vehicle_type = normalize_vehicle_type(vehicle_type)
        vehicle_types = payload.get("vehicle_types")
        # [] is the explicit unrestricted value emitted by accepted indexing.
        if vehicle_types == []:
            return True
        if not isinstance(vehicle_types, (list, tuple, set)) or not any(
            isinstance(value, str)
            and normalize_vehicle_type(value) == normalized_vehicle_type
            for value in vehicle_types
        ):
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


def deduplicate_results(
    results: Sequence[RetrievalResult],
    *,
    exact_provision_ids: Collection[str] = (),
) -> list[RetrievalResult]:
    """Deduplicate already-temporally-filtered results by provision ID.

    Temporal filtering belongs to the caller: this operation deliberately has
    no date argument and never changes the validity of a candidate.  The
    lowest rank is retained for each provision, while source and parent
    metadata from duplicates is preserved.  Exact matches are promoted by
    output order only; their rank and score are not fabricated or rewritten.
    """

    best_by_provision: dict[str, RetrievalResult] = {}
    order: dict[str, int] = {}
    source_order: dict[str, list[str]] = {}

    for position, result in enumerate(results):
        provision_id = result.provision_id
        previous = best_by_provision.get(provision_id)
        if previous is None:
            best_by_provision[provision_id] = result
            order[provision_id] = position
            source_order[provision_id] = list(dict.fromkeys(result.retrieval_sources))
            continue

        merged_sources = source_order[provision_id]
        for source in result.retrieval_sources:
            if source not in merged_sources:
                merged_sources.append(source)

        if result.rank < previous.rank:
            chosen = result
            if chosen.parent_context is None:
                chosen = chosen.model_copy(update={"parent_context": previous.parent_context})
            best_by_provision[provision_id] = chosen
        elif previous.parent_context is None and result.parent_context is not None:
            best_by_provision[provision_id] = previous.model_copy(
                update={"parent_context": result.parent_context}
            )

    deduplicated: list[RetrievalResult] = []
    for provision_id, result in sorted(
        best_by_provision.items(),
        key=lambda item: (
            item[0] not in exact_provision_ids,
            item[1].rank,
            order[item[0]],
        ),
    ):
        deduplicated.append(
            result.model_copy(update={"retrieval_sources": source_order[provision_id]})
        )
    return deduplicated


# Short aliases keep call sites readable while the descriptive names remain the API.
payload_is_valid_at = is_payload_temporally_valid
filter_payloads = filter_payloads_temporally

__all__ = [
    "build_temporal_filter",
    "deduplicate_results",
    "filter_payloads",
    "filter_payloads_temporally",
    "is_payload_temporally_valid",
    "normalize_vehicle_type",
    "payload_is_valid_at",
]
