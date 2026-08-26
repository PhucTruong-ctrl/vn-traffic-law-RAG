"""Temporal resolution stage (VNLRAG-136)."""
from __future__ import annotations

from typing import Any

import dramatiq
from sqlalchemy import select

from app.config import get_queue_settings
from app.ingestion.temporal_resolver import resolve_temporal
from app.persistence.models import LegalEffectEvent
from ._state import (
    STATUS_PENDING_REVIEW,
    JobNotFoundError,
    latest_document_version,
    list_provisions,
    load_run,
    new_session,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "resolve_temporal",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["resolve_temporal"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}

@dramatiq.actor(**_ACTOR_OPTIONS)
def resolve_temporal_actor(job_id: str) -> None:
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "RESOLVING_TEMPORAL"):
            return
        version = latest_document_version(session, run.document_id)
        if version is None:
            raise ValueError(f"no document version for run {job_id!r}")
        stored_events = session.scalars(
            select(LegalEffectEvent).where(LegalEffectEvent.document_id == run.document_id)
        ).all()
        manifest_events = run.manifest_json.get("effect_events", [])
        event_inputs = [*manifest_events, *stored_events]
        result = resolve_temporal(run.manifest_json, event_inputs)
        by_id = {(item.provision_id, item.version): item for item in result.versions}
        for row in rows:
            resolved = by_id.get((row.provision_id, row.version))
            if resolved:
                row.effective_from = resolved.effective_from
                row.effective_to = resolved.effective_to
                row.review_status = resolved.review_status
        if result.review_required:
            run.status = STATUS_PENDING_REVIEW
            run.error = {"code": "TEMPORAL_REVIEW", "errors": list(result.errors)}
        else:
            set_stage(run, "RESOLVING_TEMPORAL")
        session.commit()
    finally:
        session.close()
    if not result.review_required:
        from .quality_gate import quality_gate_actor
        quality_gate_actor.send(job_id)

__all__ = ["resolve_temporal_actor"]
