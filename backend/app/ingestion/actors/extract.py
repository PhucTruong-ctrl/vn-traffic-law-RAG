"""Extract actor — EXTRACTING stage (VNLRAG-133).

Runs the Legal Structure Extractor (structure_extractor +
structure_state_parser, doc 03 §3.8) on the persisted canonical IR, enriches
retrieval text (VNLRAG-132) and persists the projected ``LegalProvision`` rows
plus their provenance records (VNLRAG-29/39 conventions via
``projection.project_provisions`` / ``project_provenance``).

The document version row is created here when the upload flow has not created
one yet (version 1, PENDING review); the upload API may pre-create it with the
full manifest — the actor reuses whatever exists.

Idempotency: extraction and the stage marker commit in ONE transaction, and a
document version that already has provision rows is treated as extracted —
a killed worker or a duplicate message never duplicates provisions.
"""

from __future__ import annotations

import hashlib
from typing import Any

import dramatiq

from app.config import get_queue_settings
from app.ingestion.context_enricher import enrich_provision
from app.ingestion.projection import project_provenance, project_provisions, validate_provisions
from app.ingestion.structure_extractor import extract_legal_provisions
from app.persistence.models import DocumentVersion, ProvisionProvenance

from ._state import (
    JobNotFoundError,
    JobStateError,
    latest_document_version,
    list_provisions,
    load_parsed_document,
    load_run,
    new_session,
    rebuild_ir,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "extract",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["extract"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


def _ensure_document_version(
    session, run, *, ir
) -> DocumentVersion:
    """Reuse the latest document version or create version 1 (PENDING)."""
    version = latest_document_version(session, run.document_id)
    if version is not None:
        return version
    fallback_hash = hashlib.sha256(ir.model_dump_json().encode("utf-8")).hexdigest()
    version = DocumentVersion(
        document_id=run.document_id,
        version=1,
        manifest_json=dict(run.manifest_json or {}),
        content_hash=run.file_hash or fallback_hash,
        review_status="PENDING",
    )
    session.add(version)
    session.flush()
    return version


@dramatiq.actor(**_ACTOR_OPTIONS)
def extract_actor(job_id: str) -> None:
    """Extract legal provisions + provenance from the parsed IR (EXTRACTING)."""
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "EXTRACTING"):
            return

        parsed_row, elements = load_parsed_document(session, run.document_id)
        if parsed_row is None:
            raise JobStateError(
                f"no parsed document persisted for run {job_id!r}; parse must run first"
            )
        ir = rebuild_ir(parsed_row, elements)
        version = _ensure_document_version(session, run, ir=ir)

        if list_provisions(session, version.id):
            # Already extracted (resume path) — never duplicate provision rows.
            set_stage(run, "EXTRACTING")
            session.commit()
            return

        extracted = extract_legal_provisions(
            ir, document_version_id=str(version.id)
        )
        extracted = [enrich_provision(provision) for provision in extracted]
        rows = project_provisions(extracted, document_version_id=version.id)
        errors = validate_provisions(rows)
        if errors:
            raise JobStateError("extracted provisions failed validation: " + "; ".join(errors))

        for item, row in zip(extracted, rows, strict=True):
            session.add(row)
            session.flush()
            for record in project_provenance(
                item,
                provision_version_row_id=row.id,
                source_document_version_id=version.id,
            ):
                session.add(
                    ProvisionProvenance(
                        provision_version_row_id=record.provision_version_row_id,
                        source_document_version_id=record.source_document_version_id,
                        source_element_id=record.source_element_id,
                        page_number=record.page_number,
                        bbox=record.bbox,
                        role=record.role,
                    )
                )
        set_stage(run, "EXTRACTING")
        session.commit()
    finally:
        session.close()

    from .resolve_refs import resolve_refs_actor

    resolve_refs_actor.send(job_id)


__all__ = ["extract_actor"]
