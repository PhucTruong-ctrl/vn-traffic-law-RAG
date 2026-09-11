"""Supabase chat persistence with explicit owner filters and caller JWTs."""

from __future__ import annotations

from fastapi import HTTPException

from app.database.models import BOOKMARKS_TABLE, FEEDBACK_TABLE, MESSAGES_TABLE, SESSIONS_TABLE
from app.database.session import SupabaseClient


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _one(
    client: SupabaseClient, table: str, params: dict[str, str], token: str | None = None
) -> dict:
    rows = client.request("GET", table, params={**params, "select": "*"}, headers=_headers(token))
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows[0]


def list_sessions(
    client: SupabaseClient, user_id: str, query: str | None = None, token: str | None = None
) -> list[dict]:
    params = {"user_id": f"eq.{user_id}", "deleted": "eq.false", "order": "updated_at.desc"}
    if query:
        params["title"] = f"ilike.*{query.strip()}*"
    return client.request("GET", SESSIONS_TABLE, params=params, headers=_headers(token))


def create_session(
    client: SupabaseClient, user_id: str, title: str, token: str | None = None
) -> dict:
    rows = client.request(
        "POST",
        SESSIONS_TABLE,
        data={"user_id": user_id, "title": title.strip()},
        headers={**_headers(token), "Prefer": "return=representation"},
    )
    return rows[0]


def get_session(
    client: SupabaseClient, user_id: str, session_id: str, token: str | None = None
) -> dict:
    return _one(
        client,
        SESSIONS_TABLE,
        {"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "deleted": "eq.false"},
        token,
    )


def rename_session(
    client: SupabaseClient, user_id: str, session_id: str, title: str, token: str | None = None
) -> dict:
    get_session(client, user_id, session_id, token)
    rows = client.request(
        "PATCH",
        SESSIONS_TABLE,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        data={"title": title.strip()},
        headers={**_headers(token), "Prefer": "return=representation"},
    )
    return rows[0]


def delete_session(
    client: SupabaseClient, user_id: str, session_id: str, token: str | None = None
) -> None:
    get_session(client, user_id, session_id, token)
    client.request(
        "PATCH",
        SESSIONS_TABLE,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        data={"deleted": True},
        headers=_headers(token),
    )


def add_message(
    client: SupabaseClient, user_id: str, session_id: str, data: dict, token: str | None = None
) -> dict:
    get_session(client, user_id, session_id, token)
    rows = client.request(
        "POST",
        MESSAGES_TABLE,
        data={**data, "session_id": session_id, "user_id": user_id},
        headers={**_headers(token), "Prefer": "return=representation"},
    )
    return rows[0]


def add_feedback(
    client: SupabaseClient,
    user_id: str,
    session_id: str,
    message_id: str,
    data: dict,
    token: str | None = None,
) -> dict:
    _one(
        client,
        MESSAGES_TABLE,
        {"id": f"eq.{message_id}", "session_id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        token,
    )
    rows = client.request(
        "POST",
        FEEDBACK_TABLE,
        data={**data, "message_id": message_id, "user_id": user_id},
        headers={**_headers(token), "Prefer": "return=representation,resolution=merge-duplicates"},
    )
    return rows[0]


def add_bookmark(
    client: SupabaseClient, user_id: str, session_id: str, message_id: str, token: str | None = None
) -> dict:
    _one(
        client,
        MESSAGES_TABLE,
        {"id": f"eq.{message_id}", "session_id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        token,
    )
    rows = client.request(
        "POST",
        BOOKMARKS_TABLE,
        data={"message_id": message_id, "user_id": user_id},
        headers={**_headers(token), "Prefer": "return=representation,resolution=merge-duplicates"},
    )
    return rows[0]
