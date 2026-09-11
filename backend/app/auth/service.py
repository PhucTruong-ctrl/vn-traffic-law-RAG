"""Supabase authentication service."""

from __future__ import annotations

from fastapi import HTTPException

from app.auth.security import decode_access_token
from app.database.session import SupabaseClient


def register(client: SupabaseClient, email: str, password: str) -> dict:
    return client.request("POST", "rpc/register_user", data={"email": email, "password": password})


def login(client: SupabaseClient, email: str, password: str) -> dict:
    return client.request("POST", "rpc/login_user", data={"email": email, "password": password})


def current_user(client: SupabaseClient, token: str) -> dict[str, object]:
    try:
        claims = decode_access_token(token)
        user_id = claims.get("sub")
        if not user_id:
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid token") from None
    rows = client.request("GET", "profiles", params={"id": f"eq.{user_id}", "select": "*"})
    if not rows:
        raise HTTPException(status_code=401, detail="User not found")
    return rows[0]
