from __future__ import annotations

import pytest

from app.auth.api import AuthRequest
from app.auth.service import current_user
from app.chats.schemas import FeedbackCreate, MessageCreate, SessionCreate
from app.chats.service import get_session, list_sessions


def test_auth_request_rejects_short_password_and_extra_fields() -> None:
    with pytest.raises(ValueError):
        AuthRequest(email="person@example.com", password="short")
    with pytest.raises(ValueError):
        AuthRequest(email="person@example.com", password="long-enough", role="admin")


def test_current_user_rejects_invalid_token_without_supabase_request(supabase_client) -> None:
    with pytest.raises(Exception) as exc:
        current_user(supabase_client, "not-a-jwt")
    assert getattr(exc.value, "status_code", None) == 401
    assert supabase_client.calls == []


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
    assert get_session(supabase_client, "user-1", "s-1") == {"id": "s-1"}
    assert supabase_client.calls[-1]["params"] == {
        "id": "eq.s-1",
        "user_id": "eq.user-1",
        "deleted": "eq.false",
        "select": "*",
    }


def test_active_request_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValueError):
        SessionCreate(title="Chat", unexpected=True)
    with pytest.raises(ValueError):
        MessageCreate(content="hello", role="system")
    with pytest.raises(ValueError):
        FeedbackCreate(rating=5, unexpected=True)
