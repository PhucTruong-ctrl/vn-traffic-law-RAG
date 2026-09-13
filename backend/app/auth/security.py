"""Bearer token validation through Supabase Auth, not locally guessed JWT secrets."""

from __future__ import annotations

import httpx
from fastapi import HTTPException

from app.database.session import SupabaseClient


def decode_access_token(client: SupabaseClient, token: str) -> dict[str, object]:
    if not token.strip():
        raise ValueError("invalid token")
    try:
        user = client.auth_request("GET", "user", token=token)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise ValueError("invalid token") from None
        raise
    except Exception as exc:
        raise ValueError("invalid token") from exc
    if not isinstance(user, dict) or not user.get("id"):
        raise ValueError("invalid token")
    return user


def require_access_token(client: SupabaseClient, token: str) -> dict[str, object]:
    try:
        return decode_access_token(client, token)
    except (RuntimeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token") from None
