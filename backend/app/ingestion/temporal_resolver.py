"""Resolve legal-effect events into half-open provision intervals (VNLRAG-136)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping

EVENT_TYPES = frozenset({"EFFECTIVE", "AMENDED", "PARTIAL_AMENDED", "SUPERSEDED", "REPEALED", "CORRECTED", "EXPIRED"})
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
    """Resolve a manifest and amendment events without guessing uncertain dates.

    ``affected_provision_versions`` entries identify stable ``provision_id`` and
    optionally a source version. Every amendment creates the next version;
    partial amendments retain lineage in the new version's event metadata.
    """
    errors: list[str] = []
    parsed: list[EffectEvent] = []
    for raw in events or []:
        event = raw if isinstance(raw, EffectEvent) else EffectEvent(
            event_type=str(raw.get("event_type", "")),
            event_date=_date(raw.get("event_date") or raw.get("effective_from")),
            affected_provision_versions=tuple(raw.get("affected_provision_versions") or ()),
            confidence=raw.get("confidence"), review_status=str(raw.get("review_status", "PENDING")),
            source_document_id=raw.get("source_document_id"), description=raw.get("description"),
        )
        if event.event_type not in EVENT_TYPES:
            errors.append(f"unsupported event type: {event.event_type}")
        if event.event_date is None:
            errors.append(f"uncertain date for {event.event_type}")
        parsed.append(event)
    base = _date(manifest.get("effective_from"))
    if base is None:
        errors.append("uncertain effective_from")
    default_status = review_status or str(manifest.get("review_status", "PENDING"))
    review = bool(errors) or any(e.review_status != "ACCEPTED" for e in parsed)
    grouped: dict[str, list[tuple[date, EffectEvent, dict[str, Any]]]] = {}
    for event in sorted(parsed, key=lambda e: e.event_date or date.max):
        if event.event_date is None:
            continue
        for affected in event.affected_provision_versions:
            pid = str(affected.get("provision_id", ""))
            if pid:
                grouped.setdefault(pid, []).append((event.event_date, event, affected))
    if not grouped:
        for item in manifest.get("provisions", []) or []:
            pid = str(item.get("provision_id", ""))
            if pid: grouped.setdefault(pid, [])
    result: list[ResolvedVersion] = []
    for pid, changes in grouped.items():
        version = 1
        start = base
        lineage: list[dict[str, Any]] = []
        for when, event, affected in changes:
            if event.event_type in {"AMENDED", "PARTIAL_AMENDED", "CORRECTED"}:
                result.append(ResolvedVersion(pid, version, start, when, version + 1, "PENDING" if review else default_status, not review and default_status == "ACCEPTED", tuple(lineage)))
                version += 1; start = when; lineage.append({"event_type": event.event_type, **affected})
            elif event.event_type in TERMINAL_EVENTS:
                result.append(ResolvedVersion(pid, version, start, when, None, "PENDING" if review else default_status, not review and default_status == "ACCEPTED", tuple(lineage)))
                start = None
        if start is not None:
            result.append(ResolvedVersion(pid, version, start, None, None, "PENDING" if review else default_status, not review and default_status == "ACCEPTED", tuple(lineage)))
    return ResolutionResult(tuple(result), tuple(parsed), review, tuple(errors))

__all__ = ["EVENT_TYPES", "EffectEvent", "ResolvedVersion", "ResolutionResult", "resolve_temporal"]
