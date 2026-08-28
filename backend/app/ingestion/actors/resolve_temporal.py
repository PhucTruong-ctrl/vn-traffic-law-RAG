"""Temporal resolution stage (VNLRAG-136)."""
from __future__ import annotations

from typing import Any

import dramatiq
from sqlalchemy import select

from app.config import get_queue_settings
from app.ingestion.temporal_resolver import resolve_temporal
from app.persistence.models import LegalEffectEvent, ProvisionVersion, ReviewItem
from app.persistence.repositories.provisions import ProvisionRepository

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
        rows = list_provisions(session, version.id)
        stored_events = session.scalars(
            select(LegalEffectEvent).where(LegalEffectEvent.document_id == run.document_id)
        ).all()
        stored_inputs = [
            {"event_type": event.event_type, "event_date": event.event_date,
             "affected_provision_versions": event.affected_provision_versions,
             "review_status": event.review_status, "confidence": event.confidence,
             "source_document_id": event.source_document_id, "description": event.description}
            for event in stored_events
        ]
        manifest_events = run.manifest_json.get("effect_events", [])
        event_inputs = [*manifest_events, *stored_inputs]
        manifest = dict(run.manifest_json)
        manifest_provisions = list(manifest.get("provisions", []) or [])
        known_provisions = {
            (str(item.get("provision_id", "")), item.get("version"))
            for item in manifest_provisions
            if isinstance(item, dict)
        }
        for row in rows:
            provision_key = (row.provision_id, row.version)
            if provision_key not in known_provisions:
                manifest_provisions.append(
                    {"provision_id": row.provision_id, "version": row.version}
                )
        manifest["provisions"] = manifest_provisions
        if manifest.get("effective_from") is None and version.effective_from is not None:
            manifest["effective_from"] = version.effective_from
        result = resolve_temporal(manifest, event_inputs)
        provision_repo = ProvisionRepository(session)
        for resolved in result.versions:
            successor = resolved.superseded_by_version
            if successor is None:
                continue
            source_row = next(
                (row for row in rows
                 if row.provision_id == resolved.provision_id
                 and row.version == resolved.version),
                None,
            )
            successor_row = next(
                (row for row in rows
                 if row.provision_id == resolved.provision_id
                 and row.version == successor),
                None,
            )
            if source_row is None or successor_row is None:
                if session.scalar(select(ReviewItem).where(
                    ReviewItem.ingestion_run_id == run.id,
                    ReviewItem.reason_code == "MISSING_SUCCESSOR_CONTENT",
                )) is None:
                    session.add(ReviewItem(
                        ingestion_run_id=run.id, document_id=run.document_id,
                        target_type="provision", target_id=resolved.provision_id,
                        reason_code="MISSING_SUCCESSOR_CONTENT",
                        description="Temporal successor content is not persisted",
                        evidence={"version": successor},
                    ))
                continue
            predecessor = provision_repo.get_registry_entry(
                resolved.provision_id, resolved.version,
            )
            if predecessor is None:
                predecessor = provision_repo.register_version(ProvisionVersion(
                    provision_id=resolved.provision_id, version=resolved.version,
                    document_version_id=source_row.document_version_id,
                ))
            predecessor.superseded_by_version = successor
            successor_entry = provision_repo.get_registry_entry(
                resolved.provision_id, successor,
            )
            if successor_entry is None:
                provision_repo.register_version(ProvisionVersion(
                    provision_id=resolved.provision_id, version=successor,
                    document_version_id=successor_row.document_version_id,
                ))
            else:
                successor_entry.document_version_id = successor_row.document_version_id
        by_id = {(item.provision_id, item.version): item for item in result.versions}
        for row in rows:
            matching_version = by_id.get((row.provision_id, row.version))
            if matching_version:
                row.effective_from = matching_version.effective_from
                row.effective_to = matching_version.effective_to
                row.review_status = matching_version.review_status
            if result.review_required and result.errors:
                existing = session.scalar(
                    select(ReviewItem).where(
                        ReviewItem.ingestion_run_id == run.id,
                        ReviewItem.reason_code == "UNKNOWN_EFFECTIVE_DATE",
                    )
                )
                if existing is None:
                    session.add(ReviewItem(
                        ingestion_run_id=run.id, document_id=run.document_id,
                        target_type="document", target_id=run.document_id,
                        reason_code="UNKNOWN_EFFECTIVE_DATE",
                        description="Temporal resolution requires review",
                        evidence={"errors": list(result.errors)},
                    ))
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
