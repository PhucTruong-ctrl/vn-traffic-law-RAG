"""Supabase REST client for application persistence."""

from __future__ import annotations

import os
from typing import Any

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


def get_supabase_client() -> SupabaseClient:
    return SupabaseClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY)


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url, self.key = url, key

    def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        if not self.url or not self.key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_ANON_KEY are required")
        request_headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        request_headers.update(headers or {})
        response = httpx.request(
            method,
            f"{self.url}/rest/v1/{table}",
            params=params,
            json=data,
            headers=request_headers,
            timeout=15,
        )
        response.raise_for_status()
        return response.json() if response.content else None


def get_db():
    yield get_supabase_client()
