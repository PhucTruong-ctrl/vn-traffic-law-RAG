from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.database.session import SupabaseClient
from app.main import app


@dataclass
class FakeSupabase:
    responses: list[Any] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    auth_users: dict[str, dict[str, Any]] = field(default_factory=dict)
    auth_response: dict[str, Any] | None = None

    def request(self, method: str, table: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "table": table, **kwargs})
        return self.responses.pop(0) if self.responses else []

    def auth_request(
        self, method: str, path: str, *, data: Any = None, token: str | None = None
    ) -> Any:
        self.calls.append({"method": method, "path": path, "data": data, "token": token})
        if self.auth_response is not None:
            return self.auth_response
        if path == "user" and token in self.auth_users:
            return self.auth_users[token]
        if path == "token":
            email = (data or {}).get("email")
            user = next(
                (item for item in self.auth_users.values() if item.get("email") == email), None
            )
            if user:
                return {
                    "access_token": next(
                        key for key, value in self.auth_users.items() if value is user
                    ),
                    **user,
                }
        return {}


@pytest.fixture
def fake_supabase() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def supabase_client(monkeypatch: pytest.MonkeyPatch, fake_supabase: FakeSupabase) -> FakeSupabase:
    monkeypatch.setattr(SupabaseClient, "request", fake_supabase.request)
    monkeypatch.setattr(SupabaseClient, "auth_request", fake_supabase.auth_request)
    return fake_supabase
