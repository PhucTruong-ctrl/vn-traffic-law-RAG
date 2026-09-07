"""Human review API for corpus quality-gate items."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import NOT_FOUND, APIError
from app.ingestion.actors.embed import embed_actor
from app.persistence.models import IngestionRun, LegalProvision, ReviewItem
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
    document_version_id: uuid.UUID | None
    target_version: int | None
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
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def validate_interval(self) -> ReviewDecisionRequest:
        if self.decision == "ACCEPTED" and self.effective_from is None:
            raise ValueError("effective_from is required when accepting a review item")
        if (
            self.effective_from is not None
            and self.effective_to is not None
            and self.effective_to <= self.effective_from
        ):
            raise ValueError("effective_to must be later than effective_from")
        return self


def _response(row: ReviewItem, trace_id: str | None = None) -> ReviewItemResponse:
    payload = ReviewItemResponse.model_validate(
        {
            **{
                field: getattr(row, field)
                for field in ReviewItemResponse.model_fields
                if field != "trace_id"
            },
            "trace_id": trace_id or uuid.uuid4().hex,
        }
    ).model_dump()
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
    repository = ReviewItemRepository(db)
    row = repository.get(item_id)
    if row is None:
        raise APIError(NOT_FOUND, "Review item was not found.", status_code=404)
    if row.status != "PENDING":
        if row.status == request.decision and row.reviewer == request.reviewer:
            return _response(row, http_request.headers.get("X-Trace-ID"))
        raise APIError(
            "REVIEW_ALREADY_DECIDED", "Review item is already terminal.", status_code=409
        )
    evidence = {**(row.evidence or {}), "review_decision": request.evidence}
    if request.effective_from is not None:
        evidence["effective_from"] = request.effective_from.isoformat()
        evidence["effective_to"] = (
            request.effective_to.isoformat() if request.effective_to else None
        )
    row.evidence = evidence
    try:
        repository.record_decision(item_id, request.decision, request.reviewer)
        if request.effective_from is not None and row.document_version_id is not None:
            target = db.scalar(
                select(LegalProvision).where(
                    LegalProvision.document_version_id == row.document_version_id,
                    LegalProvision.provision_id == row.target_id,
                    LegalProvision.version == row.target_version,
                )
            )
            if target is not None:
                target.effective_from = request.effective_from
                target.effective_to = request.effective_to
                target.review_status = "ACCEPTED"
        continue_run = repository.continue_run_after_decision(item_id, request.decision)
        run = db.get(IngestionRun, row.ingestion_run_id)
        resume_job_id = run.job_id if run is not None else None
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise APIError("REVIEW_CONFLICT", str(exc), status_code=409) from exc
    db.refresh(row)
    if continue_run and resume_job_id is not None:
        embed_actor.send(resume_job_id)
    return _response(row, http_request.headers.get("X-Trace-ID"))
