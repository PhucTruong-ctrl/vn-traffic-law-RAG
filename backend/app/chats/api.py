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
from app.rag.service import RAGService

rag_service = RAGService()


def _answer(question: str, **kwargs):
    return rag_service.answer(question, **kwargs)


router = APIRouter(prefix="/api/v1", tags=["chats"])


def uid(user: dict) -> str:
    return str(user.get("id") or user.get("user_id") or user["sub"])


def _token(credentials: HTTPAuthorizationCredentials) -> str:
    return credentials.credentials


def deps(credentials: HTTPAuthorizationCredentials = Depends(bearer)):  # noqa: B008
    return _token(credentials)


@router.get("/chats", response_model=SessionListResponse)
@router.get("/conversations", response_model=SessionListResponse)
def sessions(
    query: str | None = Query(None),  # noqa: B008
    limit: int = Query(50, ge=1, le=100),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    items = list_sessions(client, uid(user), query, limit, token)
    return {"items": items, "next_cursor": None}


@router.post("/chats", status_code=201)
@router.post("/conversations", status_code=201)
def create(
    payload: SessionCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return create_session(client, uid(user), payload.title, token)


@router.get("/chats/{session_id}")
@router.get("/conversations/{session_id}")
def get(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return get_session(client, uid(user), session_id, token)


@router.patch("/chats/{session_id}")
@router.patch("/conversations/{session_id}")
def rename(
    session_id: str,
    payload: SessionRename,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return rename_session(client, uid(user), session_id, payload.title, token)


@router.delete("/chats/{session_id}")
@router.delete("/conversations/{session_id}")
def remove(
    session_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    delete_session(client, uid(user), session_id, token)
    return Response(status_code=204)


@router.post("/chats/{session_id}/messages", status_code=201)
@router.post("/conversations/{session_id}/messages", status_code=201)
def message(
    session_id: str,
    payload: MessageCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return add_message(client, uid(user), session_id, payload.model_dump(), token)


@router.post("/chats/{session_id}/messages/{message_id}/feedback")
def feedback(
    session_id: str,
    message_id: str,
    payload: FeedbackCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return add_feedback(client, uid(user), session_id, message_id, payload.model_dump(), token)


@router.post("/feedback")
def feedback_alias(
    payload: FeedbackCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    data = payload.model_dump()
    message_id = data.pop("message_id")
    session_id = data.pop("session_id")
    return add_feedback(client, uid(user), session_id, message_id, data, token)


@router.post("/chats/{session_id}/bookmarks")
@router.post("/conversations/{session_id}/bookmarks")
def bookmark(
    session_id: str,
    payload: BookmarkCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return save_bookmark(
        client, uid(user), session_id, payload.model_dump(exclude_none=True), token
    )


@router.get("/saved")
@router.get("/bookmarks")
def saved(
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return {"items": list_bookmarks(client, uid(user), token)}


@router.get("/saved/{assistant_message_id}/status")
@router.get("/bookmarks/{assistant_message_id}/status")
def saved_status(
    assistant_message_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return get_bookmark_status(client, uid(user), assistant_message_id, token)


@router.post("/saved/{session_id}", status_code=201)
@router.post("/bookmarks/{session_id}", status_code=201)
def save(
    session_id: str,
    payload: BookmarkCreate,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    return save_bookmark(
        client, uid(user), session_id, payload.model_dump(exclude_none=True), token
    )


@router.delete("/saved/{assistant_message_id}", status_code=204)
@router.delete("/bookmarks/{assistant_message_id}", status_code=204)
def unsave(
    assistant_message_id: str,
    user: dict = Depends(get_current_user),  # noqa: B008
    client: SupabaseClient = Depends(get_db),  # noqa: B008
    token: str = Depends(deps),  # noqa: B008
):
    delete_bookmark(client, uid(user), assistant_message_id, token)
    return Response(status_code=204)
