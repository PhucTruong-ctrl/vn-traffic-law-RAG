"""Human review API for corpus quality-gate items."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import NOT_FOUND, APIError
from app.persistence.models import ReviewItem
from app.persistence.repositories.review_items import ReviewItemRepository

router = APIRouter(prefix="/api/v1", tags=["review"])


class ReviewItemResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    document_id: str
    target_type: str
    target_id: str
    reason_code: str
    description: str | None
    evidence: dict[str, object] | None
    status: str
    reviewer: str | None
    reviewed_at: datetime | None
    created_at: datetime
    trace_id: str


class ReviewDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["ACCEPTED", "REJECTED"]
    reviewer: str = Field(min_length=1, max_length=256)
    evidence: dict[str, object] = Field(min_length=1)


def _response(row: ReviewItem, trace_id: str | None = None) -> ReviewItemResponse:
    payload = ReviewItemResponse.model_validate(row, from_attributes=True).model_dump()
    payload["trace_id"] = trace_id or uuid.uuid4().hex
    return ReviewItemResponse.model_validate(payload)


@router.get("/review/items", response_model=list[ReviewItemResponse])
def list_review_items(
    db: Annotated[Session, Depends(get_db)],
    request: Request,
    status: Annotated[str, Query()] = "PENDING",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ReviewItemResponse]:
    """List pending items by default; callers may explicitly request a status."""
    return [
        _response(row, request.headers.get("X-Trace-ID"))
        for row in ReviewItemRepository(db).list(status=status, limit=limit)
    ]


@router.get("/review/items/{item_id}", response_model=ReviewItemResponse)
def get_review_item(
    item_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], request: Request
) -> ReviewItemResponse:
    row = ReviewItemRepository(db).get(item_id)
    if row is None:
        raise APIError(NOT_FOUND, "Review item was not found.", status_code=404)
    return _response(row, request.headers.get("X-Trace-ID"))


@router.post("/review/items/{item_id}/decision", response_model=ReviewItemResponse)
def decide_review_item(
    item_id: uuid.UUID,
    request: Annotated[ReviewDecisionRequest, Body()],
    db: Annotated[Session, Depends(get_db)],
    http_request: Request,
) -> ReviewItemResponse:
    """Record an explicit human decision; no decision is inferred or defaulted."""
    row = ReviewItemRepository(db).get(item_id)
    if row is None:
        raise APIError(NOT_FOUND, "Review item was not found.", status_code=404)
    row.evidence = {**(row.evidence or {}), "review_decision": request.evidence}
    ReviewItemRepository(db).record_decision(item_id, request.decision, request.reviewer)
    db.commit()
    db.refresh(row)
    return _response(row, http_request.headers.get("X-Trace-ID"))
