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

    def request(self, method: str, table: str, **kwargs: Any) -> Any:
        self.calls.append({"method": method, "table": table, **kwargs})
        return self.responses.pop(0) if self.responses else []


@pytest.fixture
def fake_supabase() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def supabase_client(monkeypatch: pytest.MonkeyPatch, fake_supabase: FakeSupabase) -> FakeSupabase:
    monkeypatch.setattr(SupabaseClient, "request", fake_supabase.request)
    return fake_supabase
