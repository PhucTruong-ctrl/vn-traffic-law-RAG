"""Supabase chat persistence with explicit owner filters."""

from __future__ import annotations

from fastapi import HTTPException

from app.database.models import BOOKMARKS_TABLE, FEEDBACK_TABLE, MESSAGES_TABLE, SESSIONS_TABLE
from app.database.session import SupabaseClient


def _one(client: SupabaseClient, table: str, params: dict[str, str]) -> dict:
    rows = client.request("GET", table, params={**params, "select": "*"})
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows[0]


def list_sessions(client: SupabaseClient, user_id: str, query: str | None = None) -> list[dict]:
    params = {"user_id": f"eq.{user_id}", "deleted": "eq.false", "order": "updated_at.desc"}
    if query:
        params["title"] = f"ilike.*{query.strip()}*"
    return client.request("GET", SESSIONS_TABLE, params=params)


def create_session(client: SupabaseClient, user_id: str, title: str) -> dict:
    rows = client.request(
        "POST",
        SESSIONS_TABLE,
        data={"user_id": user_id, "title": title.strip()},
        headers={"Prefer": "return=representation"},
    )
    return rows[0]


def get_session(client: SupabaseClient, user_id: str, session_id: str) -> dict:
    return _one(
        client,
        SESSIONS_TABLE,
        {"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "deleted": "eq.false"},
    )


def rename_session(client: SupabaseClient, user_id: str, session_id: str, title: str) -> dict:
    get_session(client, user_id, session_id)
    rows = client.request(
        "PATCH",
        SESSIONS_TABLE,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        data={"title": title.strip()},
        headers={"Prefer": "return=representation"},
    )
    return rows[0]


def delete_session(client: SupabaseClient, user_id: str, session_id: str) -> None:
    get_session(client, user_id, session_id)
    client.request(
        "PATCH",
        SESSIONS_TABLE,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}"},
        data={"deleted": True},
    )


def add_message(client: SupabaseClient, user_id: str, session_id: str, data: dict) -> dict:
    get_session(client, user_id, session_id)
    rows = client.request(
        "POST",
        MESSAGES_TABLE,
        data={**data, "session_id": session_id, "user_id": user_id},
        headers={"Prefer": "return=representation"},
    )
    return rows[0]


def add_feedback(
    client: SupabaseClient, user_id: str, session_id: str, message_id: str, data: dict
) -> dict:
    add_message_owner = {
        "id": f"eq.{message_id}",
        "session_id": f"eq.{session_id}",
        "user_id": f"eq.{user_id}",
    }
    _one(client, MESSAGES_TABLE, add_message_owner)
    rows = client.request(
        "POST",
        FEEDBACK_TABLE,
        data={**data, "message_id": message_id, "user_id": user_id},
        headers={"Prefer": "return=representation,resolution=merge-duplicates"},
    )
    return rows[0]


def add_bookmark(client: SupabaseClient, user_id: str, session_id: str, message_id: str) -> dict:
    add_feedback(client, user_id, session_id, message_id, {})
    rows = client.request(
        "POST",
        BOOKMARKS_TABLE,
        data={"message_id": message_id, "user_id": user_id},
        headers={"Prefer": "return=representation"},
    )
    return rows[0]
