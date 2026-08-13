"""Normalize actor — NORMALIZING stage (VNLRAG-133).

Loads the persisted canonical IR, extracts document metadata and runs the
metadata normalizer (VNLRAG-27 rules: unicode NFC, whitespace collapse,
canonical issuer, no-guess dates).  The normalized values are applied to the
existing ``legal_documents`` row (the upload API owns document creation; the
parse actor's bootstrap FK already guarantees the row exists) and the
normalizer's review flags are recorded on the run's ``manifest_json`` so the
quality gate and corpus QA can see them.

Idempotency: the stage marker is committed in the same transaction as the
metadata writes; a run that already passed NORMALIZING is skipped.
"""

from __future__ import annotations

from typing import Any

import dramatiq

from app.config import get_queue_settings
from app.ingestion.metadata_extractor import extract_document_metadata
from app.ingestion.metadata_normalizer import normalize_metadata
from app.persistence.repositories.documents import DocumentRepository

from ._state import (
    JobNotFoundError,
    JobStateError,
    load_parsed_document,
    load_run,
    new_session,
    rebuild_ir,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "normalize",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["normalize"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


@dramatiq.actor(**_ACTOR_OPTIONS)
def normalize_actor(job_id: str) -> None:
    """Normalize the parsed document's metadata (NORMALIZING)."""
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "NORMALIZING"):
            return

        parsed_row, elements = load_parsed_document(session, run.document_id)
        if parsed_row is None:
            raise JobStateError(
                f"no parsed document persisted for run {job_id!r}; parse must run first"
            )
        ir = rebuild_ir(parsed_row, elements)
        result = normalize_metadata(
            extract_document_metadata(ir), dict(run.manifest_json or {})
        )
        normalized = result.metadata

        document = DocumentRepository(session).get_document(run.document_id)
        if document is not None:
            # Only fill fields the authoritative manifest/API flow left empty;
            # never overwrite values the upload already validated.
            if not document.document_title and normalized.document_title:
                document.document_title = normalized.document_title
            if not document.issuer and normalized.issuer:
                document.issuer = normalized.issuer
            if not document.issued_date and normalized.issued_date:
                document.issued_date = normalized.issued_date

        manifest = dict(run.manifest_json or {})
        manifest["normalize_flags"] = result.needs_review
        run.manifest_json = manifest
        set_stage(run, "NORMALIZING")
        session.commit()
    finally:
        session.close()

    from .extract import extract_actor

    extract_actor.send(job_id)


__all__ = ["normalize_actor"]
