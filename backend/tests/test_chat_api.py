"""Behavior tests for the verified chat API."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.main import app


def test_chat_rejects_blank_and_unknown_fields() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/chat", json={"question": "   "}).status_code == 422
    assert client.post("/api/v1/chat", json={"question": "x", "extra": 1}).status_code == 422


@pytest.mark.parametrize("verification, expected", [
    ({"status": "VALID"}, "VERIFIED"),
    ({"status": "INVALID", "reason_code": "NO_SUPPORT"}, "ABSTAINED"),
])
def test_chat_disclaimer_trace_citations_and_abstention(
    monkeypatch: pytest.MonkeyPatch, verification: dict[str, str], expected: str
) -> None:
    context = SimpleNamespace(
        provision_id="p-1", document_id="d-1", document_number="12/2024", article="Điều 1", source_url="https://example.test"
    )

    class Graph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            assert state["question"] == "hello"
            assert state["query_date"] == date(2024, 1, 2)
            return {"verification_result": verification, "final_response": {"answer_summary": "answer", "claims": [{"provision_ids": ["p-1"]}]}, "expanded_context": [context]}

    monkeypatch.setattr(chat_api, "build_query_graph", lambda: Graph())
    response = TestClient(app).post("/api/v1/chat", json={"question": "hello", "query_date": "2024-01-02"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected
    assert payload["disclaimer"] == chat_api.DISCLAIMER
    assert len(payload["trace_id"]) == 32
    assert payload["citations"][0]["provision_id"] == "p-1"
    if expected == "ABSTAINED":
        assert payload["answer"] is None
        assert payload["abstention"]["reason_code"] == "NO_SUPPORT"
    else:
        assert payload["answer"] == "answer"
        assert payload["abstention"] is None
