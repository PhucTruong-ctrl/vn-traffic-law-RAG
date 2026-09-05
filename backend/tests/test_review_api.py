"""Observable contract tests for corpus review API."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.db import get_db
from app.main import app
from app.persistence.models import ReviewItem


class Session:
    def __init__(self, row: ReviewItem) -> None:
        self.row = row
        self.committed = False

    def scalars(self, statement: object) -> list[ReviewItem]:
        return [self.row] if self.row.status == "PENDING" else []

    def scalar(self, statement: object) -> ReviewItem | None:
        return self.row

    def commit(self) -> None:
        self.committed = True

    def refresh(self, row: ReviewItem) -> None:
        return None

    def flush(self) -> None:
        return None


@pytest.fixture()
def client() -> Iterator[tuple[TestClient, Session, ReviewItem]]:
    row = ReviewItem(
        id=uuid.uuid4(),
        ingestion_run_id=uuid.uuid4(),
        document_id="doc-1",
        target_type="PROVISION",
        target_id="p-1",
        reason_code="OCR",
        description="check",
        evidence={"source": "scan"},
        status="PENDING",
    )
    row.created_at = __import__("datetime").datetime.now(__import__("datetime").UTC)
    session = Session(row)
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session, row
    finally:
        app.dependency_overrides.clear()


def test_list_pending_items(client: object) -> None:
    http, _, row = client
    response = http.get("/api/v1/review/items")
    assert response.status_code == 200
    assert response.json()[0]["id"] == str(row.id)


def test_decision_requires_reviewer_and_evidence(client: object) -> None:
    http, session, _ = client
    response = http.post("/api/v1/review/items/x/decision", json={"decision": "ACCEPTED"})
    assert response.status_code == 422
    assert not session.committed


def test_accept_records_explicit_audit_fields(client: object) -> None:
    http, session, row = client
    response = http.post(
        f"/api/v1/review/items/{row.id}/decision",
        json={"decision": "ACCEPTED", "reviewer": "alice", "evidence": {"verified": True}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert row.reviewer == "alice"
    assert row.reviewed_at is not None
    assert row.evidence["review_decision"] == {"verified": True}
    assert session.committed
