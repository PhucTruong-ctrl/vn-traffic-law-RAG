"""Behavior tests for the verified chat API."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.main import app
from app.workflow.graph import GraphServices


def test_chat_rejects_blank_and_unknown_fields() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/chat", json={"question": "   "}).status_code == 422
    assert client.post("/api/v1/chat", json={"question": "x", "extra": 1}).status_code == 422


@pytest.mark.parametrize(
    "verification, expected",
    [
        ({"status": "VALID"}, "VERIFIED"),
        ({"status": "INVALID", "reason_code": "NO_SUPPORT"}, "ABSTAINED"),
    ],
)
def test_chat_disclaimer_trace_citations_and_abstention(
    monkeypatch: pytest.MonkeyPatch, verification: dict[str, str], expected: str
) -> None:
    context = SimpleNamespace(
        provision_id="p-1",
        document_id="d-1",
        document_number="12/2024",
        article="Điều 1",
        source_url="https://example.test",
        source_text="Legal text supporting the claim.",
        page_number=1,
        bbox={"left": 10, "top": 20, "right": 100, "bottom": 40},
    )

    class Graph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            assert state["question"] == "hello"
            assert state["query_date"] == date(2024, 1, 2)
            return {
                "verification_result": verification,
                "final_response": {
                    "answer_summary": "answer",
                    "claims": [{"provision_ids": ["p-1"]}],
                },
                "expanded_context": [context],
            }

    monkeypatch.setattr(chat_api, "build_query_graph", lambda _services: Graph())
    from app.api.db import get_db

    app.dependency_overrides[get_db] = lambda: iter([object()])
    try:
        response = TestClient(app).post(
            "/api/v1/chat",
            json={"question": "hello", "query_date": "2024-01-02"},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected
    assert payload["disclaimer"] == chat_api.DISCLAIMER
    assert len(payload["trace_id"]) == 32
    if expected == "ABSTAINED":
        assert payload["citations"] == []
        assert payload["answer"] is None
        assert payload["abstention"]["reason_code"] == "NO_SUPPORT"
    else:
        assert payload["citations"] == [
            {
                "provision_id": "p-1",
                "document_id": "d-1",
                "document_number": "12/2024",
                "article": "Điều 1",
                "source_url": "https://example.test",
                "source_text": "Legal text supporting the claim.",
                "page_number": 1,
                "bbox": {"left": 10, "top": 20, "right": 100, "bottom": 40},
            }
        ]
        assert payload["answer"] == "answer"
        assert payload["abstention"] is None


def test_chat_uses_injected_production_composition(monkeypatch: pytest.MonkeyPatch) -> None:
    class Analyzer:
        def analyze(self, question, **kwargs):
            return SimpleNamespace(
                intent="CURRENT",
                effective_date=date(2024, 1, 2),
                normalized_query=question,
                missing_query_information=[],
                vehicle_type=None,
            )

    class Temporal:
        def resolve(self, plan, **kwargs):
            return date(2024, 1, 2)

    class Expander:
        def expand(self, plan, **kwargs):
            return []

    class Retriever:
        def retrieve(self, query, **kwargs):
            return []

    class Fusion:
        def fuse(self, candidates):
            return candidates

    class Reranker:
        def rerank(self, question, candidates):
            return candidates

    class Context:
        def build(self, candidates):
            return "evidence"

    class Generator:
        def generate(self, question, context):
            return {"should_abstain": True, "claims": []}

    services = GraphServices(
        analyzer=Analyzer(),
        temporal=Temporal(),
        expander=Expander(),
        retriever=Retriever(),
        dense_retriever=Retriever(),
        fusion=Fusion(),
        reranker=Reranker(),
        context_expander=Expander(),
        context_builder=Context(),
        generator=Generator(),
    )
    monkeypatch.setattr(chat_api, "production_services", lambda session: services)
    from app.api.db import get_db

    def override_db():
        yield object()

    from app.main import app

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/chat", json={"question": "hello", "query_date": "2024-01-02"}
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    assert response.json()["status"] == "ABSTAINED"
