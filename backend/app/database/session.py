"""Small Supabase REST/Auth client used by the FastAPI application."""

from __future__ import annotations

import os
from typing import Any

import httpx

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key

    def _config(self) -> None:
        if not self.url:
            raise RuntimeError("SUPABASE_URL is required")
        if not self.key:
            raise RuntimeError("SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY is required")

    def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        self._config()
        request_headers = {"apikey": self.key, "Authorization": f"Bearer {self.key}"}
        request_headers.update(headers or {})
        response = httpx.request(
            method,
            f"{self.url}/rest/v1/{table.lstrip('/')}",
            params=params,
            json=data,
            headers=request_headers,
            timeout=15,
        )
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"Supabase REST request failed ({response.status_code}): {detail}",
                request=response.request,
                response=response,
            )
        return response.json() if response.content else None

    def auth_request(
        self,
        method: str,
        path: str,
        *,
        data: Any = None,
        token: str | None = None,
    ) -> Any:
        self._config()
        headers = {"apikey": self.key, "Content-Type": "application/json"}
        headers["Authorization"] = f"Bearer {token or self.key}"
        response = httpx.request(
            method,
            f"{self.url}/auth/v1/{path.lstrip('/')}",
            json=data,
            headers=headers,
            timeout=15,
        )
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"Supabase Auth request failed ({response.status_code}): {detail}",
                request=response.request,
                response=response,
            )
        return response.json() if response.content else None


def get_supabase_client() -> SupabaseClient:
    return SupabaseClient(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY)


def get_db():
    yield get_supabase_client()
