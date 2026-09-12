from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.database.models import BOOKMARKS_TABLE, FEEDBACK_TABLE, MESSAGES_TABLE, SESSIONS_TABLE
from app.database.session import SupabaseClient


def _is_schema_mismatch(exc: httpx.HTTPStatusError) -> bool:
    response = exc.response
    text = response.text.lower()
    return response.status_code in {400, 409, 422} and (
        "column" in text or "schema cache" in text or "does not exist" in text or "pgrst" in text
    )


def _raise_schema_mismatch(exc: httpx.HTTPStatusError) -> None:
    if _is_schema_mismatch(exc):
        raise HTTPException(
            status_code=503,
            detail=(
                "Bookmark storage is unavailable because the remote database schema is stale. "
                "Apply the latest Supabase migration, then retry."
            ),
        ) from exc
    raise exc


def _headers(token: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _is_feedback_duplicate(exc: httpx.HTTPStatusError) -> bool:
    response = exc.response
    text = response.text.lower()
    return response.status_code == 409 or "23505" in text or "duplicate" in text or "unique" in text


def _one(
    client: SupabaseClient, table: str, params: dict[str, str], token: str | None = None
) -> dict:
    rows = client.request("GET", table, params={**params, "select": "*"}, headers=_headers(token))
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows[0]


def list_sessions(
    client: SupabaseClient,
    user_id: str,
    query: str | None = None,
    limit: int | None = None,
    token: str | None = None,
) -> list[dict]:
    params = {"user_id": f"eq.{user_id}", "deleted": "eq.false", "order": "updated_at.desc"}
    if query:
        params["title"] = f"ilike.*{query.strip()}*"
    if limit is not None:
        params["limit"] = str(limit)
    return client.request("GET", SESSIONS_TABLE, params=params, headers=_headers(token))


def list_messages(
    client: SupabaseClient, user_id: str, session_id: str, token: str | None = None
) -> list[dict]:
    messages = client.request(
        "GET",
        MESSAGES_TABLE,
        params={
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "order": "created_at.asc",
            "select": "*",
        },
        headers=_headers(token),
    )
    if not messages:
        return messages

    feedback = client.request(
        "GET",
        FEEDBACK_TABLE,
        params={"user_id": f"eq.{user_id}", "select": "message_id,rating"},
        headers=_headers(token),
    )
    ratings = {row["message_id"]: row["rating"] for row in feedback or []}
    return [
        {**message, "feedback_rating": ratings[message["id"]]}
        if message.get("id") in ratings
        else message
        for message in messages
    ]


def recent_messages(
    client: SupabaseClient,
    user_id: str,
    session_id: str,
    token: str | None = None,
    limit: int = 6,
) -> list[dict]:
    get_session(client, user_id, session_id, token)
    rows = client.request(
        "GET",
        MESSAGES_TABLE,
        params={
            "user_id": f"eq.{user_id}",
            "session_id": f"eq.{session_id}",
            "order": "created_at.desc",
            "limit": str(limit),
            "select": "role,content",
        },
        headers=_headers(token),
    )
    return list(reversed(rows or []))


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


def touch_session(
    client: SupabaseClient, user_id: str, session_id: str, token: str | None = None
) -> dict:
    rows = client.request(
        "PATCH",
        SESSIONS_TABLE,
        params={"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "deleted": "eq.false"},
        data={"updated_at": "now()"},
        headers={**_headers(token), "Prefer": "return=representation"},
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Not found")
    return rows[0]


def get_session(
    client: SupabaseClient, user_id: str, session_id: str, token: str | None = None
) -> dict:
    session = _one(
        client,
        SESSIONS_TABLE,
        {"id": f"eq.{session_id}", "user_id": f"eq.{user_id}", "deleted": "eq.false"},
        token,
    )
    session["messages"] = list_messages(client, user_id, session_id, token)
    return session


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
    snapshot = {
        "content": data["content"],
        "role": data.get("role", "user"),
        "status": data.get("status", "complete"),
        "response": data.get("response"),
        "citations": data.get("citations", []),
        "metadata": data.get("metadata", {}),
        "session_id": session_id,
        "user_id": user_id,
    }
    rows = client.request(
        "POST",
        MESSAGES_TABLE,
        data=snapshot,
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
    try:
        rows = client.request(
            "POST",
            FEEDBACK_TABLE,
            data={**data, "message_id": message_id, "user_id": user_id},
            headers={**_headers(token), "Prefer": "return=representation"},
        )
    except httpx.HTTPStatusError as exc:
        if _is_feedback_duplicate(exc):
            raise HTTPException(
                status_code=409,
                detail="Feedback has already been submitted for this message.",
            ) from exc
        raise
    if not rows:
        raise HTTPException(
            status_code=409,
            detail="Feedback has already been submitted for this message.",
        )
    return rows[0]


def _bookmark_message_pair(
    client: SupabaseClient,
    user_id: str,
    session_id: str,
    data: dict,
    token: str | None,
) -> tuple[dict, dict]:
    assistant_id = data.get("assistant_message_id") or data.get("message_id")
    if not assistant_id:
        raise HTTPException(status_code=422, detail="assistant_message_id is required")
    assistant = _one(
        client,
        MESSAGES_TABLE,
        {
            "id": f"eq.{assistant_id}",
            "session_id": f"eq.{session_id}",
            "user_id": f"eq.{user_id}",
            "role": "eq.assistant",
        },
        token,
    )
    user_message_id = data.get("user_message_id")
    if user_message_id:
        user_message = _one(
            client,
            MESSAGES_TABLE,
            {
                "id": f"eq.{user_message_id}",
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "role": "eq.user",
            },
            token,
        )
    else:
        user_rows = client.request(
            "GET",
            MESSAGES_TABLE,
            params={
                "session_id": f"eq.{session_id}",
                "user_id": f"eq.{user_id}",
                "role": "eq.user",
                "created_at": f"lte.{assistant['created_at']}",
                "order": "created_at.desc",
                "limit": "1",
                "select": "*",
            },
            headers=_headers(token),
        )
        if not user_rows:
            raise HTTPException(status_code=404, detail="User message not found")
        user_message = user_rows[0]
    return user_message, assistant


def list_bookmarks(client: SupabaseClient, user_id: str, token: str | None = None) -> list[dict]:
    return client.request(
        "GET",
        BOOKMARKS_TABLE,
        params={"user_id": f"eq.{user_id}", "order": "created_at.desc", "select": "*"},
        headers=_headers(token),
    )


def get_bookmark_status(
    client: SupabaseClient,
    user_id: str,
    assistant_message_id: str,
    token: str | None = None,
) -> dict:
    rows = client.request(
        "GET",
        BOOKMARKS_TABLE,
        params={
            "user_id": f"eq.{user_id}",
            "assistant_message_id": f"eq.{assistant_message_id}",
            "select": "*",
            "limit": "1",
        },
        headers=_headers(token),
    )
    return {"saved": bool(rows), "item": rows[0] if rows else None}


def save_bookmark(
    client: SupabaseClient,
    user_id: str,
    session_id: str,
    data: dict,
    token: str | None = None,
) -> dict:
    user_message, assistant = _bookmark_message_pair(client, user_id, session_id, data, token)
    snapshot = {
        "user_id": user_id,
        "source_session_id": session_id,
        "user_message_id": user_message["id"],
        "assistant_message_id": assistant["id"],
        "question": data.get("question") or user_message["content"],
        "answer": data.get("answer") or assistant["content"],
        "citations": data.get("citations")
        if "citations" in data
        else assistant.get("citations", []),
        "response": data.get("response") if "response" in data else assistant.get("response"),
    }
    try:
        rows = client.request(
            "POST",
            BOOKMARKS_TABLE,
            data=snapshot,
            headers={
                **_headers(token),
                "Prefer": "return=representation,resolution=merge-duplicates",
            },
        )
    except httpx.HTTPStatusError as exc:
        _raise_schema_mismatch(exc)
    if rows:
        return rows[0]
    return _one(
        client,
        BOOKMARKS_TABLE,
        {
            "user_id": f"eq.{user_id}",
            "assistant_message_id": f"eq.{assistant['id']}",
        },
        token,
    )


def delete_bookmark(
    client: SupabaseClient,
    user_id: str,
    assistant_message_id: str,
    token: str | None = None,
) -> None:
    client.request(
        "DELETE",
        BOOKMARKS_TABLE,
        params={
            "user_id": f"eq.{user_id}",
            "assistant_message_id": f"eq.{assistant_message_id}",
        },
        headers=_headers(token),
    )
    return None


def add_bookmark(
    client: SupabaseClient, user_id: str, session_id: str, message_id: str, token: str | None = None
) -> dict:
    return save_bookmark(
        client,
        user_id,
        session_id,
        {"assistant_message_id": message_id},
        token,
    )
