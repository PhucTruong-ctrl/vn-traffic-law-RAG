"""Independent legal-provision search API (FR-21)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_embedding_settings
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.retrieval.dense import DenseRetriever
from app.retrieval.embedding import get_embedding_provider
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.qdrant_store import _default_client
from app.retrieval.sparse import BM25SparseEncoder
from app.retrieval.sparse_retriever import SparseRetriever

router = APIRouter(prefix="/api/v1", tags=["search"])


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(min_length=1)
    effective_date: date | None = None
    document_type: str | None = None
    vehicle_type: str | None = None
    top_k: int = Field(default=10, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    page_size: int | None = Field(default=None, ge=1, le=100)
    mode: Literal["hybrid", "dense", "sparse"] = "hybrid"


def _serialize(result: RetrievalResult) -> dict[str, Any]:
    interval = {
        "from": result.effective_from.isoformat(),
        "to": result.effective_to.isoformat() if result.effective_to else None,
    }
    return {
        "rank": result.rank,
        "provision_id": result.provision_id,
        "provision_version": result.provision_version,
        "document_id": result.document_id,
        "document_version_id": result.document_version_id,
        "document_number": result.document_number,
        "article": result.article,
        "clause": result.clause,
        "point": result.point,
        "hierarchy": {"article": result.article, "clause": result.clause, "point": result.point},
        "snippet": result.source_text or result.text,
        "effective_from": interval["from"],
        "effective_to": interval["to"],
        "interval": interval,
        "status": "EFFECTIVE",
        "page_number": result.page_number,
        "provenance": {
            "retrieval_sources": result.retrieval_sources,
            "source_id": result.source_id,
            "document_version_id": result.document_version_id,
        },
    }


def _build_retriever(mode: str) -> Any:
    client = _default_client()
    if mode == "sparse":
        return SparseRetriever(client, BM25SparseEncoder(), top_k=100)
    embedder = get_embedding_provider(get_embedding_settings())
    if mode == "dense":
        return DenseRetriever(client, embedder, top_k=100)
    return HybridRetriever(client, embedder, BM25SparseEncoder())


def _retrieve(request: SearchRequest) -> CandidateSet:
    retriever = _build_retriever(request.mode)
    query_date = request.effective_date or date.today()
    if request.mode == "hybrid":
        return retriever.retrieve(
            request.query, query_date=query_date, vehicle_type=request.vehicle_type
        )
    # Dense/sparse adapters accept Qdrant filters; temporal filtering is owned
    # by the shared index contract and therefore remains active for every mode.
    from app.retrieval.filters import build_temporal_filter

    return retriever.search(
        request.query,
        query_filter=build_temporal_filter(query_date, vehicle_type=request.vehicle_type),
        limit=100,
    )


@router.post("/search", response_model=None)
def search(request: Annotated[SearchRequest, Body()]) -> dict[str, Any]:
    """Search indexed provisions without invoking the generator."""
    trace_id = uuid.uuid4().hex
    candidates = _retrieve(request)
    items = candidates.results
    if request.document_type:
        wanted = request.document_type.casefold()
        items = [item for item in items if wanted in item.document_number.casefold()]
    size = request.page_size or request.top_k
    start = (request.page - 1) * size
    page_items = items[start : start + size]
    return {
        "results": [_serialize(item) for item in page_items],
        "page": request.page,
        "page_size": size,
        "total": len(items),
        "trace_id": trace_id,
    }
