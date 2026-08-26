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
from app.persistence.repositories.review_items import ReviewItemRepository

from ._state import (
    JobNotFoundError,
    STATUS_PENDING_REVIEW,
    finish_terminal,
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
    """Resolve manifest-provided references without fabricating persistence rows."""
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "RESOLVING_REFS"):
            return
        manifest = dict(run.manifest_json or {})
        text = manifest.get("reference_text")
        provisions = manifest.get("provisions")
        known_documents = manifest.get("known_documents", {})
        malformed = not isinstance(known_documents, Mapping)
        if malformed:
            known_documents = {}
        if not isinstance(text, str) or not isinstance(provisions, list) or malformed:
            manifest["reference_resolution"] = {
                "status": "PENDING_REVIEW",
                "reason": "MISSING_REFERENCE_INPUT",
            }
            manifest.setdefault("review_items", []).append(
                {
                "target_id": run.document_id,
                "reason_code": "MISSING_REFERENCE_INPUT",
            })
        else:
            refs = resolve_references(text, run.document_id, provisions)
            docs = extract_document_relations(text, run.document_id, known_documents)
            manifest["reference_resolution"] = {
                "provision_references": [r.__dict__ for r in refs],
                "document_relations": [r.__dict__ for r in docs],
            }
            manifest["review_items"] = [
                review_item_for(r, document_id=run.document_id, ingestion_run_id=job_id)
                for r in refs if r.resolution_status != "RESOLVED"
            ]
        review_rows = manifest.get("review_items", [])
        for item in review_rows:
            ReviewItemRepository(session).create(
                run.id, run.document_id, item.get("target_type", "REFERENCE_RESOLUTION"),
                item["target_id"], item["reason_code"], item.get("description"),
                item.get("evidence"),
            )
        run.manifest_json = manifest
        if review_rows:
            finish_terminal(run, STATUS_PENDING_REVIEW, stage="RESOLVING_REFS")
            session.commit()
            return
        run.manifest_json = manifest
        set_stage(run, "RESOLVING_REFS")
        session.commit()
    finally:
        session.close()
    from .resolve_temporal import resolve_temporal_actor
    resolve_temporal_actor.send(job_id)


__all__ = ["resolve_refs_actor"]

