"""IngestionRun state machine + database helpers for the queue actors (VNLRAG-133).

Private support module for ``app.ingestion.actors``: session construction and
the ``ingestion_runs`` state transitions every actor performs.  Stages follow
doc 03 §3.13.2 / §3.4.1:

    QUEUED -> PARSING -> NORMALIZING -> EXTRACTING -> RESOLVING_REFS
    -> RESOLVING_TEMPORAL -> QUALITY_CHECK -> EMBEDDING -> INDEXING
    -> COMPLETED

Terminal states: ``COMPLETED``, ``PENDING_REVIEW`` (a provision routed to
review), ``DROPPED`` (fatal drop), ``STAGED`` (pipeline halted at a staged
actor — the W4 resolvers VNLRAG-31/136) and ``FAILED`` (set by callers /
reconciliation; a ``FAILED`` run is retryable).

Idempotency contract (doc 03 §3.13.3, §3.4.1): an actor only re-runs work for
a stage that is NOT yet recorded on the run.  Each actor sets
``status``/``current_stage`` and performs its work inside ONE transaction
(committed together), so a killed worker rolls back both the work and the
stage marker; on re-run the stage is re-executed exactly once.  ``index`` is
the documented exception: the Qdrant upsert happens AFTER the PostgreSQL
commit (doc 03 §3.4.1) and is idempotent by deterministic point ids.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.structure_extractor import ExtractedLegalProvision
from app.persistence.models import (
    DocumentElement as DocumentElementRow,
)
from app.persistence.models import (
    DocumentVersion,
    IngestionRun,
    LegalProvision,
    ReviewItem,
)
from app.persistence.models import (
    ParsedDocument as ParsedDocumentRow,
)

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_FILE = _BACKEND_DIR.parent / ".env"

#: Ordered pipeline stages (doc 03 §3.13.2).  ``current_stage``/``status`` use
#: these exact values (matching the docs and the existing ``QUEUED`` /
#: ``COMPLETED`` conventions in tests).
STAGE_ORDER: tuple[str, ...] = (
    "PARSING",
    "NORMALIZING",
    "EXTRACTING",
    "RESOLVING_REFS",
    "RESOLVING_TEMPORAL",
    "QUALITY_CHECK",
    "EMBEDDING",
    "INDEXING",
)
STAGE_INDEX: dict[str, int] = {stage: index for index, stage in enumerate(STAGE_ORDER)}

#: Status values used on ``ingestion_runs.status``.
STATUS_QUEUED = "QUEUED"
STATUS_STAGED = "STAGED"
STATUS_PENDING_REVIEW = "PENDING_REVIEW"
STATUS_COMPLETED = "COMPLETED"
STATUS_DROPPED = "DROPPED"
STATUS_FAILED = "FAILED"

#: Terminal states whose actors must never re-run (a ``FAILED`` run is NOT in
#: this set — reconciliation may retry it).
TERMINAL_SKIP_STATUSES = frozenset(
    {STATUS_STAGED, STATUS_PENDING_REVIEW, STATUS_COMPLETED, STATUS_DROPPED}
)

#: Staging message recorded on the run when a staged actor halts the pipeline.
STAGED_RESOLVERS_MESSAGE = (
    "Reference/temporal resolution (VNLRAG-31/136) is staged until W4: the "
    "job halts here in STAGED state and does NOT proceed to quality gates, "
    "embedding or indexing."
)


class JobNotFoundError(LookupError):
    """Raised when an actor cannot find its ``ingestion_runs`` row."""


class JobBootstrapError(RuntimeError):
    """Raised when the parse actor cannot bootstrap a run (no document_id)."""


class JobStateError(RuntimeError):
    """Raised when a job is not in a state the actor can proceed from."""


def _resolve_database_url() -> str:
    """DATABASE_URL environment variable, then the repo-root ``.env`` file.

    Mirrors alembic/env.py and scripts/_connect (doc 07 §7.3.3).
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    if _ENV_FILE.is_file():
        for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return line.partition("=")[2].strip().strip("'\"")
    raise RuntimeError(
        "DATABASE_URL is not set: export the variable or provide a repo-root "
        ".env file (doc 07 §7.3.3)"
    )


def new_session() -> Session:
    """A new session on the configured database (caller commits/closes)."""
    return Session(create_engine(_resolve_database_url()))


def utcnow() -> datetime:
    """Current UTC timestamp for ``completed_at`` / ``reviewed_at`` columns."""
    return datetime.now(UTC)


# --- IngestionRun access -----------------------------------------------------


def load_run(session: Session, job_id: str) -> IngestionRun | None:
    """Fetch the run by its unique ``job_id``, or None."""
    stmt = select(IngestionRun).where(IngestionRun.job_id == job_id)
    return session.scalar(stmt)


def bootstrap_run(
    session: Session,
    *,
    job_id: str,
    document_id: str | None,
    object_key: str,
) -> IngestionRun:
    """Create the ``ingestion_runs`` row for a job (status ``QUEUED``).

    The queue message carries only small fields (job_id + object_key +
    document_id), so the run is bootstrapped here with the object key recorded
    in ``manifest_json`` (recoverable on resume) and the real manifest merged
    later by the upload/API flow.  ``file_hash`` is computed by the parse
    actor from the PDF bytes; it starts as a placeholder (NOT NULL column).
    """
    if not document_id:
        raise JobBootstrapError(
            "cannot bootstrap ingestion_runs without a document_id; the parse "
            "message must carry document_id when no run row exists yet"
        )
    run = IngestionRun(
        job_id=job_id,
        document_id=document_id,
        manifest_json={"source_object_key": object_key},
        file_hash="",
        status=STATUS_QUEUED,
        current_stage=STATUS_QUEUED,
    )
    session.add(run)
    session.flush()
    return run


def stage_done(run: IngestionRun, stage: str) -> bool:
    """True when the stage is already recorded as passed on the run.

    A terminal run (COMPLETED / PENDING_REVIEW / DROPPED / STAGED) never
    re-runs.  A non-terminal run re-executes ``stage`` unless its
    ``current_stage`` is strictly AFTER ``stage`` in :data:`STAGE_ORDER` —
    so an in-progress stage (killed worker, failed Qdrant upsert) is re-run
    exactly once per attempt.
    """
    if run.status in TERMINAL_SKIP_STATUSES:
        return True
    if run.current_stage is None:
        return False
    current_index = STAGE_INDEX.get(run.current_stage)
    if current_index is None:
        return False
    return current_index > STAGE_INDEX[stage]


def set_stage(run: IngestionRun, stage: str) -> None:
    """Mark the stage as the run's current state (status + current_stage)."""
    if stage not in STAGE_INDEX:
        raise ValueError(f"unknown stage {stage!r}; expected one of {STAGE_ORDER}")
    run.status = stage
    run.current_stage = stage
    run.error = None


def finish_terminal(
    run: IngestionRun,
    status: str,
    *,
    stage: str | None = None,
    error: dict[str, Any] | None = None,
) -> None:
    """Move the run to a terminal state (current_stage stays at the last stage)."""
    run.status = status
    if stage is not None:
        run.current_stage = stage
    run.error = error
    if status == STATUS_COMPLETED and run.completed_at is None:
        run.completed_at = utcnow()


# --- ParsedDocument (IR) persistence -----------------------------------------


def persist_parsed_document(
    session: Session, ir: ParsedDocument, *, run: IngestionRun
) -> ParsedDocumentRow:
    """Persist the canonical IR (parsed_documents + document_elements rows).

    One row per IR element; the row ``id`` (generated UUID) is not referenced
    by the IR, so a re-run of the parse actor after a kill inserts nothing —
    the actor only reaches this point inside the PARSING transaction.
    """
    parsed_row = ParsedDocumentRow(
        document_id=ir.document_id,
        parser=ir.parser,
        parser_version=ir.parser_version,
        ir_schema_version=ir.ir_schema_version,
        source_object_key=ir.source_object_key,
        parse_status="SUCCESS",
        quality_report=ir.quality_report,
        started_at=ir.parse_started_at,
        completed_at=ir.parse_completed_at,
    )
    session.add(parsed_row)
    session.flush()
    for page in ir.pages:
        for element in page.elements:
            session.add(
                DocumentElementRow(
                    parsed_document_id=parsed_row.id,
                    element_id=element.element_id,
                    element_type=element.element_type,
                    text=element.text,
                    page_number=element.page_number,
                    bbox=element.bbox.model_dump() if element.bbox is not None else None,
                    reading_order=element.reading_order,
                    parent_element_id=element.parent_element_id,
                    table_html=element.table_html,
                    source_parser=element.source_parser,
                    parser_version=element.parser_version,
                    parser_confidence=element.parser_confidence,
                    raw_reference=element.raw_reference,
                )
            )
    session.flush()
    return parsed_row


def load_parsed_document(
    session: Session, document_id: str
) -> tuple[ParsedDocumentRow | None, list[DocumentElementRow]]:
    """Latest parsed_documents row of a document plus its elements, or
    ``(None, [])`` when the document has never been parsed."""
    row = session.scalar(
        select(ParsedDocumentRow)
        .where(ParsedDocumentRow.document_id == document_id)
        .order_by(ParsedDocumentRow.started_at.desc(), ParsedDocumentRow.id.desc())
        .limit(1)
    )
    if row is None:
        return None, []
    elements = list(
        session.scalars(
            select(DocumentElementRow)
            .where(DocumentElementRow.parsed_document_id == row.id)
            .order_by(
                DocumentElementRow.page_number.asc(),
                DocumentElementRow.reading_order.asc(),
            )
        )
    )
    return row, elements


def rebuild_ir(row: ParsedDocumentRow, elements: list[DocumentElementRow]) -> ParsedDocument:
    """Reconstruct the canonical IR from persisted rows (normalize/extract).

    Every IR field is persisted (document_ir v2 stores all element fields,
    including the normalized bbox and ``raw_reference``), so the IR is fully
    recoverable without the original parser output artifact.
    """
    pages: dict[int, list[DocumentElement]] = {}
    for element in elements:
        bbox = BoundingBox(**element.bbox) if element.bbox is not None else None
        pages.setdefault(element.page_number, []).append(
            DocumentElement(
                element_id=element.element_id,
                element_type=element.element_type,
                text=element.text,
                page_number=element.page_number,
                bbox=bbox,
                reading_order=element.reading_order,
                parent_element_id=element.parent_element_id,
                table_html=element.table_html,
                source_parser=element.source_parser,
                parser_version=element.parser_version,
                parser_confidence=element.parser_confidence,
                raw_reference=element.raw_reference or {},
            )
        )
    return ParsedDocument(
        parsed_document_id=str(row.id),
        document_id=row.document_id,
        parser=row.parser,
        parser_version=row.parser_version,
        ir_schema_version=row.ir_schema_version,
        source_object_key=row.source_object_key,
        pages=[
            ParsedPage(
                page_number=number,
                width=None,
                height=None,
                # Page text is not a column: reconstruct it deterministically
                # from the element texts (Group A's ``text_extraction_rate``
                # reads ``page.text``, doc 03 §3.7.2 / Suite A metric 1).
                text="\n".join(item.text for item in items if item.text.strip()) or None,
                elements=items,
            )
            for number, items in sorted(pages.items())
        ],
        parse_started_at=row.started_at or utcnow(),
        parse_completed_at=row.completed_at or utcnow(),
        quality_report=row.quality_report or {},
    )


# --- Document / provision queries --------------------------------------------


def latest_document_version(session: Session, document_id: str) -> DocumentVersion | None:
    """Highest version row of a document, or None."""
    return session.scalar(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version.desc())
        .limit(1)
    )


def list_provisions(session: Session, document_version_id: UUID) -> list[LegalProvision]:
    """All provision rows of one document version (stable order)."""
    stmt = (
        select(LegalProvision)
        .where(LegalProvision.document_version_id == document_version_id)
        .order_by(LegalProvision.provision_id, LegalProvision.version)
    )
    return list(session.scalars(stmt))


def list_review_items(session: Session, ingestion_run_id: UUID) -> list[ReviewItem]:
    """Review items created for one ingestion run."""
    stmt = select(ReviewItem).where(ReviewItem.ingestion_run_id == ingestion_run_id)
    return list(session.scalars(stmt))


def provision_row_to_extracted(row: LegalProvision) -> ExtractedLegalProvision:
    """Rebuild an extractor record from a persisted provision row.

    The transient extractor fields (``point_label``, ``short_point``,
    ``needs_review``, ``ambiguity``) are not persisted; they are re-derived
    where routing needs them (``short_point`` follows the indexer's rule:
    a POINT of <= 3 whitespace tokens, doc 03 §3.8.5).
    """
    return ExtractedLegalProvision(
        provision_id=row.provision_id,
        document_version_id=str(row.document_version_id),
        chapter=row.chapter,
        section=row.section,
        article=row.article,
        clause=row.clause,
        point=row.point,
        heading=row.heading,
        source_text=row.source_text,
        retrieval_text=row.retrieval_text,
        parent_context=row.parent_context,
        effective_from=row.effective_from.isoformat() if row.effective_from else None,
        effective_to=row.effective_to.isoformat() if row.effective_to else None,
        status=row.status,
        page_number=row.page_number,
        bbox=row.bbox,
        source_element_ids=list(row.source_element_ids),
        content_hash=row.content_hash,
        version=row.version,
        review_status=row.review_status,
        node_kind=row.node_kind,
        short_point=row.node_kind == "POINT" and len(row.source_text.split()) <= 3,
    )


__all__ = [
    "JobBootstrapError",
    "JobNotFoundError",
    "JobStateError",
    "STAGE_INDEX",
    "STAGE_ORDER",
    "STAGED_RESOLVERS_MESSAGE",
    "STATUS_COMPLETED",
    "STATUS_DROPPED",
    "STATUS_FAILED",
    "STATUS_PENDING_REVIEW",
    "STATUS_QUEUED",
    "STATUS_STAGED",
    "TERMINAL_SKIP_STATUSES",
    "bootstrap_run",
    "finish_terminal",
    "latest_document_version",
    "list_provisions",
    "list_review_items",
    "load_parsed_document",
    "load_run",
    "new_session",
    "persist_parsed_document",
    "provision_row_to_extracted",
    "rebuild_ir",
    "set_stage",
    "stage_done",
    "utcnow",
]
