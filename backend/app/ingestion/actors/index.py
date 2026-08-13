"""Index actor — INDEXING stage (VNLRAG-133).

Upserts the job's ACCEPTED provisions into Qdrant via
``retrieval.indexing.index_provision_units`` — the same machinery
``index_accepted_provisions`` (VNLRAG-44) uses, scoped to THIS job's document
(the global/corpus variant is used by reconciliation, not per-job ingestion).
Only ``review_status == 'ACCEPTED'`` rows with an ``effective_from`` are
selected (the DB check constraint already guarantees ACCEPTED rows carry an
interval; the defensive guard mirrors ``index_accepted_provisions``), so
PENDING / NEEDS_REVIEW / DROPPED / REJECTED provisions NEVER enter the index
(doc 00 §8.6, FR-09).

Idempotency (doc 03 §3.4.1): the Qdrant upsert happens AFTER the PostgreSQL
commit and uses deterministic point ids (the row UUID), so a re-run — resume
after a killed worker, a duplicate message or a reconcile-triggered re-run —
REPLACES the same points instead of duplicating them.  On a Qdrant failure
the job stays at INDEXING and the retry/reconcile re-runs the upsert.

Test seams (monkeypatched by unit/integration tests): ``_get_qdrant_client``,
``_get_embedder``, ``_get_sparse_encoder``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

import dramatiq
from qdrant_client import QdrantClient

from app.config import get_embedding_settings, get_queue_settings
from app.retrieval.embedding import EmbeddingProvider, get_embedding_provider
from app.retrieval.indexing import (
    ACCEPTED_REVIEW_STATUS,
    index_provision_units,
    point_id_for,
    provision_row_to_unit,
)
from app.retrieval.qdrant_store import ensure_qdrant_collection
from app.retrieval.sparse import BM25SparseEncoder, SparseEncoder

from ._state import (
    STATUS_COMPLETED,
    JobNotFoundError,
    JobStateError,
    finish_terminal,
    latest_document_version,
    list_provisions,
    load_run,
    new_session,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "index",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["index"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _get_qdrant_client() -> QdrantClient:
    """The provision collection client (idempotent ensure; test seam)."""
    return ensure_qdrant_collection()


def _get_embedder() -> EmbeddingProvider | None:
    """Configured dense embedding provider (test seam)."""
    return get_embedding_provider(get_embedding_settings())


def _get_sparse_encoder() -> SparseEncoder:
    """Configured BM25 sparse encoder (local, deterministic; test seam)."""
    return cast(SparseEncoder, BM25SparseEncoder())


def _accepted_rows(session, document_id: str) -> tuple[list[Any], Any | None]:
    """ACCEPTED provision rows of the job's latest document version.

    Returns ``(rows, version)``; rows carry an ``effective_from`` (defensive
    guard mirroring ``index_accepted_provisions``).
    """
    version = latest_document_version(session, document_id)
    if version is None:
        return [], version
    rows = [
        row
        for row in list_provisions(session, version.id)
        if row.review_status == ACCEPTED_REVIEW_STATUS and row.effective_from is not None
    ]
    return rows, version


@dramatiq.actor(**_ACTOR_OPTIONS)
def index_actor(job_id: str) -> None:
    """Index the job's ACCEPTED provisions into Qdrant (INDEXING)."""
    session = new_session()
    units: list[Any] = []
    point_ids: dict[str, str] = {}
    unit_payloads: dict[str, dict[str, Any]] = {}
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "INDEXING"):
            return
        accepted, version = _accepted_rows(session, run.document_id)
        if version is None:
            raise JobStateError(
                f"no document version for run {job_id!r}; extract must run first"
            )
        # Build every upsert input while the rows are still bound to the
        # session (commit expires them; detached rows cannot be read).
        for row in accepted:
            unit = provision_row_to_unit(row)
            units.append(unit)
            point_ids[unit.unit_id] = point_id_for(row.id)
            unit_payloads[unit.unit_id] = {
                "review_status": ACCEPTED_REVIEW_STATUS,
                "effective_from": _iso(row.effective_from),
                "effective_to": _iso(row.effective_to),
                "chapter": row.chapter,
                "section": row.section,
                "article": row.article,
                "clause": row.clause,
                "point": row.point,
                "heading": row.heading,
                "content_hash": row.content_hash,
            }
        set_stage(run, "INDEXING")
        session.commit()  # PG commit BEFORE the Qdrant upsert (doc 03 §3.4.1)
    finally:
        session.close()

    if units:
        result = index_provision_units(
            _get_qdrant_client(),
            units,
            point_ids=point_ids,
            embedder=_get_embedder(),
            sparse_encoder=_get_sparse_encoder(),
            unit_payloads=unit_payloads,
        )
        if result.errors:
            # Job stays at INDEXING; the retry (or reconcile) re-runs the
            # idempotent upsert — PG data is never rolled back (doc 03 §3.4.1).
            raise RuntimeError(f"indexing failed for run {job_id!r}: {result.errors}")

    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None or stage_done(run, "INDEXING"):
            return  # already completed by a duplicate delivery
        finish_terminal(run, STATUS_COMPLETED, stage="INDEXING")
        session.commit()
    finally:
        session.close()


__all__ = ["index_actor"]
