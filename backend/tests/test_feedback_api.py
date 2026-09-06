"""Focused behavior tests for the feedback API (VNLRAG-145)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.db import get_db
from app.main import app
from app.persistence.models import QueryFeedback, QueryTrace


class FeedbackSession:
    """Small query/add/commit fake matching the feedback endpoint contract."""

    def __init__(self, trace: QueryTrace | None) -> None:
        self.trace = trace
        self.added: list[QueryFeedback] = []
        self.committed = False

    def query(self, model: object) -> FeedbackSession:
        assert model is QueryTrace
        return self

    def filter(self, expression: object) -> FeedbackSession:
        return self

    def first(self) -> QueryTrace | None:
        return self.trace

    def add(self, row: QueryFeedback) -> None:
        row.id = uuid.uuid4()
        self.added.append(row)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, row: QueryFeedback) -> None:
        assert row.id is not None


@pytest.fixture()
def feedback_client() -> Iterator[tuple[TestClient, FeedbackSession, QueryTrace]]:
    trace = QueryTrace(
        id=uuid.uuid4(),
        trace_id="trace-145",
        question="What is the speed limit?",
        intent="GENERAL",
        response_status="SUCCESS",
    )
    session = FeedbackSession(trace)
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session, trace
    finally:
        app.dependency_overrides.clear()


def _assert_error(response: object, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    payload = response.json()
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["trace_id"], str)


def test_feedback_persists_and_returns_201(feedback_client: object) -> None:
    client, session, trace = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={"trace_id": trace.trace_id, "correctness": "correct", "comment": "Helpful"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert uuid.UUID(payload["feedback_id"])
    assert payload["trace_id"] == trace.trace_id
    assert uuid.UUID(payload["trace_id_request"])
    assert session.committed
    assert len(session.added) == 1
    assert session.added[0].useful is True
    assert session.added[0].comment == "Helpful"


def test_feedback_unknown_trace_returns_standard_404(feedback_client: object) -> None:
    client, session, _ = feedback_client
    session.trace = None

    response = client.post(
        "/api/v1/feedback",
        json={"trace_id": "missing-trace", "correctness": "incorrect"},
    )

    _assert_error(response, 404, "NOT_FOUND")
    assert session.added == []
    assert not session.committed


def test_feedback_rejects_sensitive_comment(feedback_client: object) -> None:
    client, session, trace = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": trace.trace_id,
            "correctness": "incorrect",
            "comment": "The API key was exposed",
        },
    )

    _assert_error(response, 422, "VALIDATION_ERROR")
    assert session.added == []


def test_feedback_rejects_extra_fields(feedback_client: object) -> None:
    client, session, trace = feedback_client

    response = client.post(
        "/api/v1/feedback",
        json={
            "trace_id": trace.trace_id,
            "correctness": "correct",
            "answer": "unexpected payload",
        },
    )

    _assert_error(response, 422, "VALIDATION_ERROR")
    assert session.added == []
