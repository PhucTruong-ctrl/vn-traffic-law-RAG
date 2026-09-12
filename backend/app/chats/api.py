"""Authenticated chat session, message, feedback, and bookmark endpoints."""

from fastapi import APIRouter, Depends, Query, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.api import bearer, get_current_user
from app.chats.schemas import (
    BookmarkCreate,
    FeedbackCreate,
    MessageCreate,
    SessionCreate,
    SessionListResponse,
    SessionRename,
)
from app.chats.service import (
    add_feedback,
    add_message,
    create_session,
    delete_bookmark,
    delete_session,
    get_bookmark_status,
    get_session,
    list_bookmarks,
    list_sessions,
    rename_session,
    save_bookmark,
)
from app.database.session import SupabaseClient, get_db

router = APIRouter(prefix="/api/v1", tags=["chats"])


def uid(user: dict) -> str:
    return str(user.get("id") or user.get("user_id") or user["sub"])


@router.get("/chats", response_model=SessionListResponse)
def sessions(
    query: str | None = Query(None),  # noqa: B008
    limit: int = Query(50, ge=1, le=100),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    items = list_sessions(client, uid(user), query, limit, credentials.credentials)
    return {"items": items, "next_cursor": None}


@router.post("/chats", status_code=201)
def create(
    payload: SessionCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return create_session(client, uid(user), payload.title, credentials.credentials)


@router.get("/chats/{session_id}")
def get(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return get_session(client, uid(user), session_id, credentials.credentials)


@router.patch("/chats/{session_id}")
def rename(
    session_id: str,
    payload: SessionRename,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return rename_session(client, uid(user), session_id, payload.title, credentials.credentials)


@router.delete("/chats/{session_id}")
def remove(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    delete_session(client, uid(user), session_id, credentials.credentials)
    return Response(status_code=204)


@router.post("/chats/{session_id}/messages", status_code=201)
def message(
    session_id: str,
    payload: MessageCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return add_message(client, uid(user), session_id, payload.model_dump(), credentials.credentials)


@router.post("/chats/{session_id}/messages/{message_id}/feedback")
def feedback(
    session_id: str,
    message_id: str,
    payload: FeedbackCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return add_feedback(
        client,
        uid(user),
        session_id,
        message_id,
        payload.model_dump(),
        credentials.credentials,
    )


@router.get("/bookmarks")
def saved(
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return {"items": list_bookmarks(client, uid(user), credentials.credentials)}


@router.get("/bookmarks/{assistant_message_id}/status")
def saved_status(
    assistant_message_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return get_bookmark_status(client, uid(user), assistant_message_id, credentials.credentials)


@router.post("/bookmarks/{session_id}", status_code=201)
def save(
    session_id: str,
    payload: BookmarkCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    return save_bookmark(
        client,
        uid(user),
        session_id,
        payload.model_dump(exclude_none=True),
        credentials.credentials,
    )


@router.delete("/bookmarks/{assistant_message_id}", status_code=204)
def unsave(
    assistant_message_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    credentials: HTTPAuthorizationCredentials = Depends(bearer),  # noqa: B008
):
    delete_bookmark(client, uid(user), assistant_message_id, credentials.credentials)
    return Response(status_code=204)
