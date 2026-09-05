"""Persist user feedback for a query trace."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import NOT_FOUND, APIError, new_trace_id
from app.persistence.models import QueryFeedback, QueryTrace

router = APIRouter(prefix="/api/v1", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """Validated, deliberately bounded feedback payload.

    Feedback is metadata only: callers identify an existing trace and may not
    submit answer text or arbitrary trace contents for storage.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    trace_id: str = Field(min_length=1, max_length=128)
    correctness: Literal["correct", "incorrect"]
    comment: str | None = Field(default=None, max_length=2_000)

    @field_validator("trace_id", "comment")
    @classmethod
    def reject_sensitive_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        lowered = value.casefold()
        sensitive_markers = (
            "password",
            "secret",
            "api_key",
            "apikey",
            "access_token",
            "bearer ",
            "private key",
        )
        if any(marker in lowered for marker in sensitive_markers):
            raise ValueError("sensitive content is not accepted")
        return value


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: uuid.UUID
    trace_id: str
    trace_id_request: str


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    request: Annotated[FeedbackRequest, Body()],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackResponse:
    """Store correctness feedback without retaining answer or trace payloads."""
    request_trace_id = new_trace_id()
    trace = db.query(QueryTrace).filter(QueryTrace.trace_id == request.trace_id).first()
    if trace is None:
        raise APIError(
            "Query trace was not found.", status_code=404, code=NOT_FOUND,
        )
    row = QueryFeedback(
        query_trace_id=trace.id,
        useful=request.correctness == "correct",
        comment=request.comment,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FeedbackResponse(
        feedback_id=row.id, trace_id=trace.trace_id, trace_id_request=request_trace_id
    )
