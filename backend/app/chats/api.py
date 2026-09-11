"""Authenticated chat session, message, feedback, and bookmark endpoints."""

from fastapi import APIRouter, Depends, Query, Response

from app.auth.api import get_current_user
from app.chats.schemas import (
    BookmarkCreate,
    FeedbackCreate,
    MessageCreate,
    SessionCreate,
    SessionRename,
)
from app.chats.service import (
    add_bookmark,
    add_feedback,
    add_message,
    create_session,
    delete_session,
    get_session,
    list_sessions,
    rename_session,
)
from app.database.session import SupabaseClient, get_db

router = APIRouter(prefix="/api/v1/chats", tags=["chats"])


def uid(user: dict) -> str:
    return str(user.get("id") or user.get("user_id") or user["sub"])


@router.get("")
def sessions(
    query: str | None = Query(None),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return list_sessions(client, uid(user), query)


@router.post("", status_code=201)
def create(
    payload: SessionCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return create_session(client, uid(user), payload.title)


def get(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return get_session(client, uid(user), session_id)


@router.patch("/{session_id}")
def rename(
    session_id: str,
    payload: SessionRename,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return rename_session(client, uid(user), session_id, payload.title)


def remove(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    delete_session(client, uid(user), session_id)
    return Response(status_code=204)


@router.post("/{session_id}/messages", status_code=201)
def message(
    session_id: str,
    payload: MessageCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return add_message(client, uid(user), session_id, payload.model_dump())


@router.post("/{session_id}/messages/{message_id}/feedback")
def feedback(
    session_id: str,
    message_id: str,
    payload: FeedbackCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return add_feedback(client, uid(user), session_id, message_id, payload.model_dump())


@router.post("/{session_id}/bookmarks")
def bookmark(
    session_id: str,
    payload: BookmarkCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
):
    return add_bookmark(client, uid(user), session_id, payload.message_id)
