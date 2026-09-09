"""Application-owned contracts for retrieval candidates."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class RetrievalResult(BaseModel):
    """One accepted legal provision returned by a retrieval channel."""

    model_config = ConfigDict(extra="forbid", strict=True)

    rank: int = Field(ge=1)
    provision_id: str
    provision_version: int
    document_id: str | None
    document_version_id: str
    text: str
    source_text: str
    parent_context: str | None
    document_number: str
    document_type: str
    article: str | None
    clause: str | None
    point: str | None
    effective_from: date
    effective_to: date | None
    # Retrieval channels query the accepted-only index and authoritative temporal store.
    review_status: str = "ACCEPTED"
    page_number: int = Field(ge=1)
    bbox: dict[str, float] | None = None
    retrieval_sources: list[str]
    fused_score: float | None
    added_by: str | None
    source_id: str | None
    source_url: str | None = None
    snapshot_at: str | None = None
    content_hash: str | None = None
    depth: int = Field(ge=0)


class CandidateSet(BaseModel):
    """Candidates produced for one query and, optionally, one legal date."""

    model_config = ConfigDict(extra="forbid", strict=True)

    query: str
    results: list[RetrievalResult]
    applied_date: date | None


def _as_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"invalid {field}: {value!r}") from exc
    raise ValueError(f"invalid {field}: {value!r}")


def result_from_payload(
    payload: Mapping[str, object], *, rank: int, score: float | None, source: str
) -> RetrievalResult:
    """Translate an indexed payload without coupling contracts to Qdrant.

    Retrieval serving is ACCEPTED-only.  Missing fields are deliberately left
    to Pydantic validation rather than filled with citation-inaccurate values.
    """

    if payload.get("review_status") != "ACCEPTED":
        raise ValueError("retrieval payload must have review_status='ACCEPTED'")
    values = {
        "rank": rank,
        "provision_id": payload.get("provision_id"),
        "provision_version": payload.get("provision_version"),
        "document_id": payload.get("document_id"),
        "document_version_id": payload.get("document_version_id"),
        "text": payload.get("text"),
        "source_text": payload.get("source_text"),
        "parent_context": payload.get("parent_context"),
        "document_number": payload.get("document_number"),
        "document_type": payload.get("document_type"),
        "article": payload.get("article"),
        "clause": payload.get("clause"),
        "point": payload.get("point"),
        "effective_from": _as_date(payload.get("effective_from"), "effective_from"),
        "effective_to": _as_date(payload.get("effective_to"), "effective_to"),
        "page_number": payload.get("page_number"),
        "bbox": payload.get("bbox"),
        "retrieval_sources": [source],
        "fused_score": score,
        "added_by": payload.get("added_by"),
        "source_id": payload.get("source_id"),
        "source_url": payload.get("source_url"),
        "snapshot_at": payload.get("snapshot_at"),
        "content_hash": payload.get("content_hash"),
        "depth": payload.get("depth", 0),
        "review_status": "ACCEPTED",
    }
    return RetrievalResult.model_validate(values)


__all__ = ["CandidateSet", "RetrievalResult", "result_from_payload"]
