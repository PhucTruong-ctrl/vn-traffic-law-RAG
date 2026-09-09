"""Behavior tests for the verified chat API."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import chat as chat_api
from app.api import feedback as feedback_api
from app.main import app
from app.observability.query_trace import QueryTrace as ObservabilityQueryTrace
from app.persistence.models import QueryFeedback, QueryTrace
from app.workflow.graph import GraphServices


def test_chat_accepts_only_question() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/chat", json={"question": "   "}).status_code == 422
    assert client.post("/api/v1/chat", json={"question": "x", "extra": 1}).status_code == 422
    assert client.post("/api/v1/chat", json={"question": 1}).status_code == 422
    assert client.post("/api/v1/chat", json={"question": None}).status_code == 422

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
        clause="Khoản 2",
        point="a",
        parent_context="Khoản 2. Phạt tiền từ 1 đến 2 triệu đồng.",
        source_url="https://example.test",
        source_text="a) Cited point text.",
        text="a) Cited point text.",
        page_number=1,
        bbox={"left": 10, "top": 20, "right": 100, "bottom": 40},
    )

    class Graph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            assert state["question"] == "hello"
            assert state["query_date"] == date.today()
            assert "vehicle_type" not in state
            return {
                "verification_result": verification,
                "final_response": {
                    "answer_summary": "answer",
                    "claims": [{"provision_ids": ["p-1"]}],
                },
                "expanded_context": [context],
            }

    monkeypatch.setattr(chat_api, "build_query_graph", lambda _services: Graph())

    app.dependency_overrides[chat_api._optional_db] = lambda: None
    try:
        response = TestClient(app).post("/api/v1/chat", json={"question": "hello"})
    finally:
        app.dependency_overrides.pop(chat_api._optional_db, None)
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected
    assert payload["disclaimer"] == chat_api.DISCLAIMER
    assert len(payload["trace_id"]) == 32
    if expected == "ABSTAINED":
        assert payload["citations"] == []
    else:
        assert payload["citations"] == [{
            "provision_id": "p-1",
            "document_id": "d-1",
            "document_number": "12/2024",
            "article": "Điều 1",
            "clause": "Khoản 2",
            "point": "a",
            "parent_context": "Khoản 2. Phạt tiền từ 1 đến 2 triệu đồng.",
            "source_url": "https://example.test",
            "source_text": "a) Cited point text.",
            "page_number": 1,
            "legal_context": "Khoản 2. Phạt tiền từ 1 đến 2 triệu đồng.\n\na) Cited point text.",
            "bbox": {"left": 10.0, "top": 20.0, "right": 100.0, "bottom": 40.0},
        }]
        assert payload["answer"] == "answer"

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

    app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(app).post(
            "/api/v1/chat", json={"question": "hello"}
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 200
    assert response.json()["status"] == "ABSTAINED"


class ChatFeedbackSession:
    """Fake request session shared by chat and feedback calls."""

    def __init__(self) -> None:
        self.traces: dict[str, object] = {}
        self.added: list[object] = []
        self.persistence_traces: dict[str, object] = {}
        self.committed = False
        self._filtered_trace_id: str | None = None

    def add(self, row: object) -> None:
        self.added.append(row)
        if isinstance(row, (QueryTrace, ObservabilityQueryTrace)):
            if not hasattr(row, "id") or row.id is None:
                row.id = uuid.uuid4()
            self.traces[row.trace_id] = row
        elif isinstance(row, QueryFeedback):
            row.id = uuid.uuid4()

    def commit(self) -> None:
        self.committed = True

    def query(self, model: object) -> ChatFeedbackSession:
        assert model is QueryTrace
        return self

    def filter(self, expression: object) -> ChatFeedbackSession:
        self._filtered_trace_id = expression.right.value
        return self

    def first(self) -> object | None:
        return self.traces.get(self._filtered_trace_id)

    def refresh(self, row: object) -> None:
        assert getattr(row, "id", None) is not None
def test_chat_never_returns_verified_without_serialized_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Graph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            return {
                "verification_result": {"status": "VALID"},
                "final_response": {
                    "answer_summary": "answer",
                    "claims": [{"provision_ids": ["missing"]}],
                },
                "expanded_context": [],
            }

    monkeypatch.setattr(chat_api, "build_query_graph", lambda _services: Graph())
    app.dependency_overrides[chat_api._optional_db] = lambda: None
    try:
        payload = TestClient(app).post("/api/v1/chat", json={"question": "hello"}).json()
    finally:
        app.dependency_overrides.pop(chat_api._optional_db, None)
    assert payload["status"] != "VERIFIED"
    assert payload["citations"] == []


def test_chat_trace_is_available_to_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    class Graph:
        async def ainvoke(self, state: dict[str, object]) -> dict[str, object]:
            return {"verification_result": {"status": "ABSTAIN"}, "final_response": {}}

    session = ChatFeedbackSession()
    monkeypatch.setattr(chat_api, "build_query_graph", lambda _services: Graph())
    app.dependency_overrides[chat_api._optional_db] = lambda: session
    app.dependency_overrides[feedback_api.get_db] = lambda: session
    try:
        client = TestClient(app)
        chat_response = client.post("/api/v1/chat", json={"question": "hello"})
        assert chat_response.status_code == 200
        trace_id = chat_response.json()["trace_id"]
        assert trace_id in session.traces

        feedback_response = client.post(
            "/api/v1/feedback",
            json={"trace_id": trace_id, "correctness": "correct"},
        )
    finally:
        app.dependency_overrides.pop(chat_api._optional_db, None)
        app.dependency_overrides.pop(feedback_api.get_db, None)
    assert feedback_response.status_code == 201
    assert feedback_response.json()["trace_id"] == trace_id
    assert session.committed


def test_chat_rejects_duplicate_claim_citations(monkeypatch: pytest.MonkeyPatch) -> None:
    record = SimpleNamespace(
        provision_id="p-1",
        document_id="d",
        document_number="n",
        article="1",
        source_text="x",
        page_number=1,
        review_status="ACCEPTED",
    )
    class Graph:
        async def ainvoke(self, state):
            return {
                "verification_result": {"status": "VALID"},
                "final_response": {
                    "answer_summary": "x",
                    "claims": [{"provision_ids": ["p-1", "p-1"]}],
                },
                "expanded_context": [record],
            }
    monkeypatch.setattr(chat_api, "build_query_graph", lambda _: Graph())
    app.dependency_overrides[chat_api._optional_db] = lambda: None
    try:
        payload = TestClient(app).post("/api/v1/chat", json={"question": "hello"}).json()
    finally:
        app.dependency_overrides.pop(chat_api._optional_db, None)
    assert payload["status"] == "ABSTAINED"
    assert payload["citations"] == []
