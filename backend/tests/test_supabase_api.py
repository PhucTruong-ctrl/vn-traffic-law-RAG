from __future__ import annotations

import pytest

from app.auth.api import AuthRequest
from app.auth.service import current_user
from app.chats.schemas import FeedbackCreate, MessageCreate, SessionCreate, SessionRename
from app.chats.service import get_session, list_sessions


def test_auth_request_rejects_short_password_and_extra_fields() -> None:
    with pytest.raises(ValueError):
        AuthRequest(email="person@example.com", password="short")
    with pytest.raises(ValueError):
        AuthRequest(email="person@example.com", password="long-enough", role="admin")


def test_current_user_rejects_invalid_token_after_supabase_validation(supabase_client) -> None:
    with pytest.raises(Exception) as exc:
        current_user(supabase_client, "not-a-jwt")
    assert getattr(exc.value, "status_code", None) == 401
    assert supabase_client.calls == [
        {"method": "GET", "path": "user", "data": None, "token": "not-a-jwt"}
    ]


def test_current_user_queries_profile_by_token_subject(supabase_client) -> None:
    token = "user-token"
    supabase_client.auth_request = lambda method, path, **kwargs: {
        "id": "user-1",
        "email": "person@example.com",
    }
    supabase_client.responses.append([{"id": "user-1", "email": "person@example.com"}])
    user = current_user(supabase_client, token)
    assert user["id"] == "user-1"
    assert supabase_client.calls[0] == {
        "method": "GET",
        "table": "profiles",
        "params": {"id": "eq.user-1", "select": "*"},
        "headers": {"Authorization": f"Bearer {token}"},
    }


def test_session_queries_include_owner_and_not_deleted(supabase_client) -> None:
    supabase_client.responses.append([])
    list_sessions(supabase_client, "user-1", "  traffic  ")
    assert supabase_client.calls[-1]["params"] == {
        "user_id": "eq.user-1",
        "deleted": "eq.false",
        "order": "updated_at.desc",
        "title": "ilike.*traffic*",
    }
    supabase_client.responses.append([{"id": "s-1"}])
    supabase_client.responses.append([])
    assert get_session(supabase_client, "user-1", "s-1") == {"id": "s-1", "messages": []}
    assert supabase_client.calls[-2]["params"] == {
        "id": "eq.s-1",
        "user_id": "eq.user-1",
        "deleted": "eq.false",
        "select": "*",
    }
    assert supabase_client.calls[-1]["params"] == {
        "user_id": "eq.user-1",
        "session_id": "eq.s-1",
        "order": "created_at.asc",
        "select": "*",
    }


def test_active_request_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValueError):
        SessionCreate(title="Chat", unexpected=True)
    with pytest.raises(ValueError):
        SessionRename(title="Chat", unexpected=True)
    with pytest.raises(ValueError):
        MessageCreate(content="hello", role="system")
    with pytest.raises(ValueError):
        FeedbackCreate(rating=1, message_id="m1", session_id="s1", unexpected=True)


def test_feedback_accepts_binary_ratings_and_requires_ids() -> None:
    assert FeedbackCreate(rating=0, message_id="m1", session_id="s1").rating == 0
    assert FeedbackCreate(rating=1, message_id="m1", session_id="s1").rating == 1
    for rating in (-1, 2):
        with pytest.raises(ValueError):
            FeedbackCreate(rating=rating, message_id="m1", session_id="s1")
    for field in ("message_id", "session_id"):
        with pytest.raises(ValueError):
            FeedbackCreate(
                rating=1,
                message_id="m1" if field == "session_id" else "",
                session_id="s1" if field == "message_id" else "",
            )


def test_message_schema_exposes_response_citations_and_metadata_snapshot() -> None:
    payload = MessageCreate(
        content="Theo quy định.",
        role="assistant",
        response="Theo quy định.",
        citations=[{"document": "Nghị định 100", "source_file": "nd100.md", "excerpt": "..."}],
        metadata={"effective_date": "2026-01-01"},
    )
    assert payload.model_dump()["response"] == "Theo quy định."
    assert payload.model_dump()["citations"][0]["document"] == "Nghị định 100"
    assert payload.model_dump()["metadata"] == {"effective_date": "2026-01-01"}
