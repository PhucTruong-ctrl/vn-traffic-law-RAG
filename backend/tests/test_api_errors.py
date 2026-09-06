"""Focused contract tests for API error taxonomy and trace propagation."""

from __future__ import annotations

import re

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.db import get_db
from app.api.errors import ABSTENTION, INTERNAL_ERROR, ProviderError, error_response
from app.main import app

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def test_trace_id_is_propagated_to_success_and_error_responses() -> None:
    app.dependency_overrides[get_db] = lambda: type("DB", (), {"scalar": lambda self, stmt: None})()
    client = TestClient(app)
    supplied = "trace-client-42"

    success = client.get("/api/v1/health/live", headers={"X-Trace-ID": supplied})
    assert success.status_code == 200
    assert success.headers["X-Trace-ID"] == supplied

    missing = client.get("/api/v1/jobs/missing", headers={"X-Trace-ID": supplied})
    assert missing.status_code == 404
    assert missing.headers["X-Trace-ID"] == supplied
    assert missing.json()["error"]["trace_id"] == supplied
    app.dependency_overrides.clear()


def test_generated_trace_id_is_shared_by_error_body_and_header() -> None:
    app.dependency_overrides[get_db] = lambda: type("DB", (), {"scalar": lambda self, stmt: None})()
    response = TestClient(app).get("/api/v1/jobs/missing")
    trace_id = response.json()["error"]["trace_id"]
    assert _TRACE_ID_RE.fullmatch(trace_id)
    assert response.headers["X-Trace-ID"] == trace_id
    app.dependency_overrides.clear()


def test_provider_error_is_distinct_and_safe() -> None:
    @app.get("/__test_provider_error", include_in_schema=False)
    def provider_error() -> None:
        raise ProviderError("upstream unavailable")

    response = TestClient(app, raise_server_exceptions=False).get("/__test_provider_error")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "PROVIDER_ERROR"
    assert response.json()["error"]["message"] == "upstream unavailable"


def test_abstention_payload_never_exposes_draft_or_citations() -> None:
    response = error_response(200, ABSTENTION, "Insufficient verified evidence.")
    payload = response.body.decode()
    assert "draft" not in payload.lower()
    assert "citation" not in payload.lower()
    assert b'"code":"ABSTENTION"' in response.body


def test_http_not_found_does_not_become_internal_error() -> None:
    @app.get("/__test_not_found", include_in_schema=False)
    def not_found() -> None:
        raise HTTPException(status_code=404, detail="missing")

    response = TestClient(app).get("/__test_not_found")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"
    assert response.json()["error"]["code"] != INTERNAL_ERROR
