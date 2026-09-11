"""FastAPI routes for the Markdown-backed legal explorer."""

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..ingestion.source import normalize_source_kind
from .corpus import _LOCAL_DIR, chunks, filter_chunks, search_chunks
from .schemas import (
    LegalDocumentSummary,
    LegalProvision,
    LegalSearchResponse,
    LegalSearchResult,
    LegalSource,
)

router = APIRouter(prefix="/api/v1", tags=["legal"])


def _source(md: dict) -> LegalSource:
    source_kind = normalize_source_kind(
        source_file=md.get("source_file"),
        source_kind=md.get("source_kind"),
        source_type=md.get("source_type"),
    )
    return LegalSource(
        source_file=str(md.get("source_file", "unknown")),
        source_url=md.get("source_url") or None,
        pdf_url=md.get("pdf_url") or (md.get("source_url") if source_kind == "pdf" else None),
        source_kind=source_kind,
        source_type=str(md.get("source_type", "markdown")),
        retrieved_at=md.get("retrieved_at") or None,
    )


def _provision(item) -> LegalProvision:
    md = item.metadata
    return LegalProvision(
        chunk_id=str(md.get("chunk_id", "")),
        document_id=str(md.get("document_id", "")),
        document_name=str(md.get("document_name", md.get("document_id", ""))),
        article=md.get("article"),
        clause=md.get("clause"),
        point=md.get("point"),
        text=item.text,
        source=_source(md),
    )


@router.get("/legal-documents", response_model=list[LegalDocumentSummary])
def list_documents() -> list[LegalDocumentSummary]:
    items = chunks()
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(str(item.metadata.get("document_id", "")), []).append(item)
    return [
        LegalDocumentSummary(
            document_id=doc_id,
            document_name=str(rows[0].metadata.get("document_name", doc_id)),
            source=_source(rows[0].metadata),
            provision_count=len(rows),
        )
        for doc_id, rows in sorted(grouped.items())
        if doc_id
    ]


def _markdown_content(document_id: str, rows: list) -> str | None:
    if not rows or _source(rows[0].metadata).source_kind != "markdown":
        return None
    candidate = Path(str(rows[0].metadata.get("source_file", ""))).resolve()
    root = _LOCAL_DIR.resolve()
    if candidate.suffix.casefold() == ".md" and root in candidate.parents and candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return "\n\n".join(row.text for row in rows).strip() or None


@router.get("/legal-documents/{document_id}", response_model=LegalDocumentSummary)
def get_document(document_id: str) -> LegalDocumentSummary:
    items = chunks()
    rows = [item for item in items if str(item.metadata.get("document_id", "")) == document_id]
    if not rows:
        raise HTTPException(status_code=404, detail="legal document not found")
    summary = LegalDocumentSummary(
        document_id=document_id,
        document_name=str(rows[0].metadata.get("document_name", document_id)),
        source=_source(rows[0].metadata),
        provision_count=len(rows),
        content=_markdown_content(document_id, rows),
    )
    return summary


@router.get("/legal-documents/{document_id}/provisions", response_model=list[LegalProvision])
def list_provisions(
    document_id: str,
    article: str | None = None,
    clause: str | None = None,
    point: str | None = None,
) -> list[LegalProvision]:
    rows = filter_chunks(
        chunks(), document_id=document_id, article=article, clause=clause, point=point
    )
    if not rows and not any(d.document_id == document_id for d in list_documents()):
        raise HTTPException(status_code=404, detail="legal document not found")
    return [_provision(item) for item in rows]


@router.get("/legal-search", response_model=LegalSearchResponse)
def legal_search(
    q: str = Query(min_length=1),
    document_id: str | None = None,
    article: str | None = None,
    clause: str | None = None,
    point: str | None = None,
    limit: int = Query(20, ge=1, le=100),
) -> LegalSearchResponse:
    found = search_chunks(
        chunks(), q.strip(), document_id=document_id, article=article, clause=clause, point=point
    )[:limit]
    return LegalSearchResponse(
        query=q.strip(),
        results=[
            LegalSearchResult(**_provision(item).model_dump(), score=score) for item, score in found
        ],
    )


__all__ = ["router"]
