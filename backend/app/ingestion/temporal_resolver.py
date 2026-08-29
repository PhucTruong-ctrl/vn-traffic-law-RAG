"""Resolve legal-effect events into half-open provision intervals (VNLRAG-136)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

EVENT_TYPES = frozenset(
    {
        "EFFECTIVE",
        "AMENDED",
        "PARTIAL_AMENDED",
        "SUPERSEDED",
        "REPEALED",
        "CORRECTED",
        "EXPIRED",
    }
)
TERMINAL_EVENTS = frozenset({"SUPERSEDED", "REPEALED", "EXPIRED"})


@dataclass(frozen=True)
class EffectEvent:
    event_type: str
    event_date: date | None
    affected_provision_versions: tuple[dict[str, Any], ...] = ()
    confidence: float | None = None
    review_status: str = "PENDING"
    source_document_id: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ResolvedVersion:
    provision_id: str
    version: int
    effective_from: date | None
    effective_to: date | None
    superseded_by_version: int | None = None
    review_status: str = "PENDING"
    indexable: bool = False
    lineage: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ResolutionResult:
    versions: tuple[ResolvedVersion, ...]
    events: tuple[EffectEvent, ...]
    review_required: bool = False
    errors: tuple[str, ...] = ()


def _date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def resolve_temporal(
    manifest: Mapping[str, Any],
    events: list[Mapping[str, Any] | EffectEvent] | None = None,
    *,
    review_status: str | None = None,
) -> ResolutionResult:
    """Resolve intervals without guessing uncertain dates."""
    errors: list[str] = []
    parsed: list[EffectEvent] = []
    for raw in events or []:
        event = (
            raw
            if isinstance(raw, EffectEvent)
            else EffectEvent(
                event_type=str(raw.get("event_type", "")),
                event_date=_date(raw.get("event_date") or raw.get("effective_from")),
                affected_provision_versions=tuple(raw.get("affected_provision_versions") or ()),
                confidence=raw.get("confidence"),
                review_status=str(raw.get("review_status", "PENDING")),
                source_document_id=raw.get("source_document_id"),
                description=raw.get("description"),
            )
        )
        if event.event_type not in EVENT_TYPES:
            errors.append(f"unsupported event type: {event.event_type}")
        parsed.append(event)
    base = _date(manifest.get("effective_from"))
    if base is None:
        base = next(
            (event.event_date for event in parsed if event.event_type == "EFFECTIVE"),
            None,
        )
    if base is None:
        errors.append("uncertain effective_from")
    default_status = review_status or str(manifest.get("review_status", "PENDING"))
    grouped: dict[str, list[tuple[date, EffectEvent, dict[str, Any]]]] = {}
    for event in sorted(
        (item for item in parsed if item.event_type != "EFFECTIVE"),
        key=lambda item: item.event_date or date.max,
    ):
        if event.event_date is None:
            errors.append(f"uncertain event date: {event.event_type}")
            continue
        for affected in event.affected_provision_versions:
            pid = str(affected.get("provision_id", ""))
            if pid:
                grouped.setdefault(pid, []).append((event.event_date, event, affected))
    for item in manifest.get("provisions", []) or []:
        pid = str(item.get("provision_id", ""))
        if pid:
            grouped.setdefault(pid, [])
    review = bool(errors) or any(event.review_status != "ACCEPTED" for event in parsed)
    result: list[ResolvedVersion] = []
    for pid, changes in grouped.items():
        version = 1
        start = base
        lineage: list[dict[str, Any]] = []
        terminal = False
        for when, event, affected in changes:
            status = "PENDING" if review else default_status
            indexable = not review and default_status == "ACCEPTED"
            if terminal or start is None:
                errors.append(f"event after terminal for {pid}")
                review = True
                continue
            if when <= start:
                errors.append(f"non-chronological event for {pid}")
                review = True
                continue
            if event.event_type in {"AMENDED", "PARTIAL_AMENDED", "CORRECTED"}:
                result.append(
                    ResolvedVersion(
                        pid,
                        version,
                        start,
                        when,
                        version + 1,
                        status,
                        indexable,
                        tuple(lineage),
                    )
                )
                version += 1
                start = when
                lineage.append({"event_type": event.event_type, **affected})
            elif event.event_type in TERMINAL_EVENTS:
                result.append(
                    ResolvedVersion(
                        pid,
                        version,
                        start,
                        when,
                        None,
                        "PENDING" if review else default_status,
                        not review and default_status == "ACCEPTED",
                        tuple(lineage),
                    )
                )
                terminal = True
                start = None
        if start is not None:
            result.append(
                ResolvedVersion(
                    pid,
                    version,
                    start,
                    None,
                    None,
                    "PENDING" if review else default_status,
                    not review and default_status == "ACCEPTED",
                    tuple(lineage),
                )
            )
    review = bool(errors) or any(event.review_status != "ACCEPTED" for event in parsed)
    if review:
        result = [
            ResolvedVersion(
                item.provision_id,
                item.version,
                item.effective_from,
                item.effective_to,
                item.superseded_by_version,
                "PENDING",
                False,
                item.lineage,
            )
            for item in result
        ]
    return ResolutionResult(tuple(result), tuple(parsed), review, tuple(errors))


__all__ = ["EVENT_TYPES", "EffectEvent", "ResolvedVersion", "ResolutionResult", "resolve_temporal"]
