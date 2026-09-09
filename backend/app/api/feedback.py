"""Persist minimal anonymous feedback for a query trace."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import NOT_FOUND, APIError, new_trace_id
from app.persistence.models import QueryFeedback, QueryTrace

router = APIRouter(prefix="/api/v1", tags=["feedback"])


class FeedbackRequest(BaseModel):
    """A bounded, anonymous rating referring only to an existing trace."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    trace_id: str = Field(min_length=1, max_length=128)
    message_id: str | None = Field(default=None, min_length=1, max_length=128)
    rating: Literal["LIKE", "DISLIKE"]


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: uuid.UUID
    trace_id: str
    message_id: str | None
    trace_id_request: str


@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
def create_feedback(
    request: Annotated[FeedbackRequest, Body()],
    db: Annotated[Session, Depends(get_db)],
) -> FeedbackResponse:
    """Store only the rating and references; never mutate legal/release data."""
    request_trace_id = new_trace_id()
    trace = db.query(QueryTrace).filter(QueryTrace.trace_id == request.trace_id).first()
    if trace is None:
        raise APIError(NOT_FOUND, "Query trace was not found.", status_code=404)
    row = QueryFeedback(
        query_trace_id=getattr(trace, "id", uuid.uuid4()),
        message_id=request.message_id,
        rating=request.rating,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return FeedbackResponse(
        feedback_id=row.id,
        trace_id=trace.trace_id,
        message_id=row.message_id,
        trace_id_request=request_trace_id,
    )
