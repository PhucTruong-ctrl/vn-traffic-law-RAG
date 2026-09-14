"""Small Supabase REST/Auth client used by the FastAPI application."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_supabase_settings


class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url
        self.key = key

    def _config(self) -> None:
        if not self.url:
            raise RuntimeError("SUPABASE_URL is required")
        if not self.key:
            raise RuntimeError("SUPABASE_ANON_KEY or SUPABASE_SERVICE_ROLE_KEY is required")

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Any = None,
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = False,
        token: str | None = None,
    ) -> Any:
        self._config()
        request_headers = {"apikey": self.key, "Content-Type": "application/json"}
        request_headers["Authorization"] = (
            f"Bearer {token or self.key}" if auth else f"Bearer {self.key}"
        )
        request_headers.update(headers or {})
        response = httpx.request(
            method,
            f"{self.url}/{path.lstrip('/')}",
            params=params,
            json=data,
            headers=request_headers,
            timeout=15,
        )
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"Supabase request failed ({response.status_code}): {detail}",
                request=response.request,
                response=response,
            )
        return response.json() if response.content else None

    def request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        auth: bool = False,
        token: str | None = None,
    ) -> Any:
        return self._request(
            method,
            f"{'auth/v1' if auth else 'rest/v1'}/{table}",
            params=params,
            data=data,
            headers=headers,
            auth=auth,
            token=token,
        )

    def auth_request(
        self,
        method: str,
        path: str,
        *,
        data: Any = None,
        token: str | None = None,
    ) -> Any:
        return self._request(method, f"auth/v1/{path}", data=data, auth=True, token=token)


def get_db():
    settings = get_supabase_settings()
    yield SupabaseClient(
        settings.url,
        settings.service_role_key or settings.anon_key,
    )
