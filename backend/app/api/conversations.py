"""Owner-scoped conversation history API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import NOT_FOUND, APIError
from app.persistence.models import Conversation, Message

router = APIRouter(prefix="/api/v1", tags=["conversations"])
OWNER_COOKIE = "vnlaw_owner"
COOKIE_MAX_AGE = 60 * 60 * 24 * 365
TITLE_LIMIT = 80


def owner_key(response: Response, owner: str | None) -> str:
    if owner:
        return owner
    value = uuid.uuid4().hex
    response.set_cookie(OWNER_COOKIE, value, httponly=True, samesite="lax", max_age=COOKIE_MAX_AGE)
    return value


def _title(value: str, limit: int = TITLE_LIMIT) -> str:
    return " ".join(value.split()).strip()[:limit]


def _conversation(db: Session, ident: uuid.UUID, owner: str) -> Conversation:
    row = (
        db.query(Conversation)
        .filter(
            Conversation.id == ident,
            Conversation.owner_key == owner,
            Conversation.deleted_at.is_(None),
        )
        .first()
    )
    if row is None:
        raise APIError(NOT_FOUND, "Conversation was not found.", 404)
    return row


class RenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("title must not be blank")
        return value


class ConversationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    title: str
    title_manual: bool
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime


def _summary(row: Conversation) -> dict[str, object]:
    return {
        k: getattr(row, k)
        for k in ("id", "title", "title_manual", "created_at", "updated_at", "last_activity_at")
    }


def _message(row: Message) -> dict[str, object]:
    return {
        "id": row.id,
        "role": row.role,
        "status": row.status,
        "content": row.content,
        "created_at": row.created_at,
        "query_trace_id": row.query_trace_id,
    }


@router.get("/conversations")
def list_conversations(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    owner: Annotated[str | None, Cookie(alias=OWNER_COOKIE)] = None,
    search: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, object]:
    key = owner_key(response, owner)
    query = db.query(Conversation).filter(
        Conversation.owner_key == key, Conversation.deleted_at.is_(None)
    )
    if search and search.strip():
        needle = f"%{search.strip().casefold()}%"
        query = (
            query.outerjoin(Message)
            .filter(
                or_(
                    Conversation.title.ilike(needle),
                    (Message.role == "user") & Message.content.ilike(needle),
                )
            )
            .distinct()
        )
    rows = (
        query.order_by(Conversation.last_activity_at.desc(), Conversation.id.desc())
        .limit(limit + 1)
        .all()
    )
    next_cursor = str(rows[-1].id) if len(rows) > limit else None
    return {"items": [_summary(row) for row in rows[:limit]], "next_cursor": next_cursor}


@router.get("/conversations/{conversation_id}")
def get_conversation(
    conversation_id: uuid.UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    owner: Annotated[str | None, Cookie(alias=OWNER_COOKIE)] = None,
) -> dict[str, object]:
    row = _conversation(db, conversation_id, owner_key(response, owner))
    return {
        **_summary(row),
        "messages": [_message(message) for message in row.messages if message.status != "FAILED"],
    }


@router.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: uuid.UUID,
    request: RenameRequest,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    owner: Annotated[str | None, Cookie(alias=OWNER_COOKIE)] = None,
) -> dict[str, object]:
    row = _conversation(db, conversation_id, owner_key(response, owner))
    row.title, row.title_manual, row.updated_at = request.title, True, datetime.now(UTC)
    db.commit()
    return _summary(row)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: uuid.UUID,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    owner: Annotated[str | None, Cookie(alias=OWNER_COOKIE)] = None,
) -> Response:
    row = _conversation(db, conversation_id, owner_key(response, owner))
    row.deleted_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)


__all__ = ["OWNER_COOKIE", "router", "_title", "_conversation", "owner_key"]
