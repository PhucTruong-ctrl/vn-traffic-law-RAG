"""Resolve explicit legal references and hand off to temporal resolution."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import dramatiq

from app.config import get_queue_settings
from app.ingestion.reference_resolver import (
    extract_document_relations,
    resolve_references,
    review_item_for,
)
from app.persistence.models import DocumentRelation, ProvisionReference
from app.persistence.repositories.relations import RelationRepository
from app.persistence.repositories.review_items import ReviewItemRepository

from ._state import (
    STATUS_PENDING_REVIEW,
    JobNotFoundError,
    finish_terminal,
    latest_document_version,
    list_provisions,
    load_run,
    new_session,
    set_stage,
    stage_done,
)

_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "resolve_refs",
    "time_limit": get_queue_settings().actor_timeouts_seconds["resolve_refs"],
    "max_retries": get_queue_settings().max_retries,
}


@dramatiq.actor(**_ACTOR_OPTIONS)
def resolve_refs_actor(job_id: str) -> None:
    session = new_session()
    review_rows: list[dict[str, Any]] = []
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "RESOLVING_REFS"):
            return
        version = latest_document_version(session, run.document_id)
        manifest = dict(run.manifest_json or {})
        text = manifest.get("reference_text", "")
        rows = list_provisions(session, version.id) if version else []
        refs = resolve_references(
            text, run.document_id, rows,
            source_version=version.version if version else None,
        )
        known = manifest.get("known_documents", {})
        docs = extract_document_relations(
            text, run.document_id,
            known if isinstance(known, Mapping) else {},
        )
        repo = RelationRepository(session)
        source = next(
            (p for p in rows if p.provision_id == manifest.get("source_provision_id")),
            None,
        )
        for candidate in refs:
            target = next((p for p in rows if str(p.id) == candidate.target_provision_id), None)
            if source is None or candidate.resolution_status != "RESOLVED" or target is None:
                review_rows.append(review_item_for(
                    candidate, document_id=run.document_id, ingestion_run_id=job_id,
                ))
                continue
            repo.upsert_provision_reference(ProvisionReference(
                source_legal_provision_id=source.id,
                target_legal_provision_id=target.id,
                source_provision_id=source.provision_id,
                source_provision_version_id=str(source.version),
                target_provision_id=target.provision_id,
                target_provision_version_id=str(target.version),
                relation_type=candidate.relation_type,
                confidence=candidate.confidence,
                extraction_method=candidate.extraction_method,
                source_text=candidate.source_text,
                resolution_status="RESOLVED",
                review_status="PENDING",
            ))
        for candidate in docs:
            if candidate.target_document_id is None:
                review_rows.append({
                    "target_type": "DOCUMENT_RELATION",
                    "target_id": run.document_id,
                    "reason_code": "TARGET_NOT_FOUND",
                    "description": candidate.source_note,
                })
            else:
                repo.upsert_document_relation(DocumentRelation(
                    source_document_id=candidate.source_document_id,
                    target_document_id=candidate.target_document_id,
                    relation_type=candidate.relation_type,
                    source_note=candidate.source_note,
                    source="extracted",
                    resolution_status="RESOLVED",
                    review_status="PENDING",
                ))
        for item in review_rows:
            ReviewItemRepository(session).create(
                run.id, run.document_id,
                item.get("target_type", "REFERENCE_RESOLUTION"),
                item["target_id"], item["reason_code"],
                item.get("description"), item.get("evidence"),
            )
        run.manifest_json = {**manifest, "review_items": review_rows}
        if review_rows:
            finish_terminal(run, STATUS_PENDING_REVIEW, stage="RESOLVING_REFS")
        else:
            set_stage(run, "RESOLVING_REFS")
        session.commit()
    finally:
        session.close()
    if not review_rows:
        from .resolve_temporal import resolve_temporal_actor
        resolve_temporal_actor.send(job_id)


__all__ = ["resolve_refs_actor"]

