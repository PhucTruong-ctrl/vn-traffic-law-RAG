"""Document upload endpoint (doc 03 §3.28.3, FR-07; VNLRAG-135).

``POST /api/v1/documents`` validates the source PDF, stores it in
``source-pdfs`` (content-addressed per doc 03 §3.12.2), ensures the owning
``legal_documents`` row exists, and enqueues background ingestion. It NEVER
parses, extracts or embeds synchronously (doc 03 §3.13.1: "Không parse PDF
đồng bộ trong request handler") — the handler only stores and enqueues.

Queue integration: the message is published through :func:`_enqueue`, a
monkeypatchable seam over the deferred import ``from app.ingestion.actors
import enqueue_parse`` (VNLRAG-133 provides that package; it may not exist
yet when this module is imported, so the import happens at call time). The
message payload is small — ``job_id`` + ``object_key`` + ``document_id`` —
per the cross-ticket contract; the ``ingestion_runs`` row itself is created
lazily by the parse actor (VNLRAG-133).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import (
    FILE_TOO_LARGE,
    INVALID_CONTENT_TYPE,
    INVALID_DOCUMENT_ID,
    UNSUPPORTED_MEDIA_TYPE,
    error_response,
)
from app.config import get_upload_settings
from app.persistence.models import LegalDocument
from app.persistence.repositories import DocumentRepository
from app.storage import ObjectStoragePort, get_object_storage, object_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["documents"])

#: Content types accepted for a source PDF upload (sanity check: browsers and
#: curl often send ``application/octet-stream`` for ``.pdf`` files, so that
#: variant is allowed; the extension remains the authoritative check).
_ACCEPTED_CONTENT_TYPES = frozenset(
    {"application/pdf", "application/x-pdf", "application/octet-stream"}
)

_SOURCE_SUBPATH = "source"


def _enqueue(job_id: str, object_key_value: str, *, document_id: str | None = None) -> str:
    """Publish the ingestion message (monkeypatch seam for tests).

    Deferred import: :mod:`app.ingestion.actors` is owned by VNLRAG-133 and
    may not exist when this module is imported. Returns the Dramatiq message
    id.
    """
    from app.ingestion.actors import enqueue_parse  # type: ignore[import-not-found]

    return enqueue_parse(job_id, object_key_value, document_id=document_id)


def _new_job_id() -> str:
    """Generate an ingestion job id (doc 03 §3.28.3, e.g. ``job_abc123``)."""
    return f"job_{uuid.uuid4().hex}"


def _ensure_document(
    session: Session, document_id: str, file_hash: str, file_name: str
) -> LegalDocument:
    """Return the ``legal_documents`` row owning ``document_id``.

    The row is created when missing so the parse actor's ``ingestion_runs``
    insert (FK on ``document_id``) cannot fail. Placeholder legal metadata
    (number/title/type) is derived from the upload; the ingestion pipeline
    normalizes the real metadata later. Re-uploads of the same bytes reuse the
    existing row by ``file_hash`` (duplicate check, doc 03 §3.13.7).
    """
    repo = DocumentRepository(session)
    existing = repo.get_document(document_id)
    if existing is not None:
        return existing
    by_hash = session.scalar(select(LegalDocument).where(LegalDocument.file_hash == file_hash))
    if by_hash is not None:
        return by_hash
    document = LegalDocument(
        document_id=document_id,
        document_number=document_id,
        document_title=file_name or document_id,
        document_type="UNKNOWN",
        file_hash=file_hash,
        status="UPLOADED",
    )
    repo.create_document(document)
    return document


@router.post("/documents", status_code=202, response_model=None)
async def upload_document(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    document_id: Annotated[str | None, Form()] = None,
) -> dict[str, str] | JSONResponse:
    """Accept a source PDF, store it, and enqueue background ingestion."""
    settings = get_upload_settings()

    file_name = file.filename or "document.pdf"
    if Path(file_name).suffix.lower() != ".pdf":
        return error_response(
            415,
            UNSUPPORTED_MEDIA_TYPE,
            f"Unsupported file type for {file_name!r}: only PDF documents are accepted.",
        )
    if file.content_type is not None and file.content_type not in _ACCEPTED_CONTENT_TYPES:
        return error_response(
            400,
            INVALID_CONTENT_TYPE,
            f"Unexpected content type {file.content_type!r} for {file_name!r}.",
        )

    data = await file.read()
    max_bytes = settings.max_size_mb * 1024 * 1024
    if len(data) > max_bytes:
        return error_response(
            413,
            FILE_TOO_LARGE,
            f"File {file_name!r} exceeds the {settings.max_size_mb} MB upload limit.",
        )

    file_hash = hashlib.sha256(data).hexdigest()
    job_id = _new_job_id()
    doc_id = document_id or f"documents/{uuid.uuid4().hex}"
    try:
        key = object_key(
            bucket="source-pdfs",
            document_id=doc_id,
            file_name=file_name,
            content_hash=file_hash,
            subpath=_SOURCE_SUBPATH,
        )
    except ValueError as exc:
        return error_response(400, INVALID_DOCUMENT_ID, str(exc))

    row = _ensure_document(db, doc_id, file_hash, file_name)
    if row.document_id != doc_id:
        # Bytes already ingested under another document_id (file_hash dedupe):
        # store under the canonical row so key and document stay consistent.
        key = object_key(
            bucket="source-pdfs",
            document_id=row.document_id,
            file_name=file_name,
            content_hash=file_hash,
            subpath=_SOURCE_SUBPATH,
        )

    storage: ObjectStoragePort = get_object_storage()
    storage.put("source-pdfs", key, data, content_type="application/pdf")
    db.commit()
    _enqueue(job_id, key, document_id=row.document_id)
    logger.info("uploaded job_id=%s object_key=%s", job_id, key)

    return {"ingestion_job_id": job_id, "status": "queued"}
