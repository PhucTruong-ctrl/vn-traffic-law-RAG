"""Supabase JWT verification and Bearer token helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def decode_access_token(token: str) -> dict[str, object]:
    try:
        header, payload, signature = token.split(".")
        claims = json.loads(_decode(payload))
        if not _SECRET or claims.get("exp", 0) <= time.time():
            raise ValueError("expired token")
        expected = (
            base64.urlsafe_b64encode(
                hmac.new(_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        return claims
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise ValueError("invalid token") from None
