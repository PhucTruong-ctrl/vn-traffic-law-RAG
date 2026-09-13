"""Supabase authentication service."""

from __future__ import annotations

from fastapi import HTTPException

from app.auth.security import require_access_token
from app.database.session import SupabaseClient


def register(client: SupabaseClient, email: str, password: str) -> dict:
    try:
        return client.auth_request("POST", "signup", data={"email": email, "password": password})
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Registration failed") from exc


def login(client: SupabaseClient, email: str, password: str) -> dict:
    try:
        return client.auth_request(
            "POST",
            "token?grant_type=password",
            data={"email": email, "password": password},
        )
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid email or password") from exc


def current_user(client: SupabaseClient, token: str) -> dict[str, object]:
    user = require_access_token(client, token)
    user_id = str(user["id"])
    try:
        rows = client.request(
            "GET",
            "profiles",
            params={"id": f"eq.{user_id}", "select": "*"},
            headers={"Authorization": f"Bearer {token}"},
        )
    except Exception:
        rows = []
    return rows[0] if rows else user
    return rows[0]
