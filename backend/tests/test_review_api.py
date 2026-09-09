"""Observable contract tests for corpus review API."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from app.api.db import get_db
from app.main import app
from app.persistence.models import IngestionRun, LegalProvision, ReviewItem


class Session:
    def __init__(self, row: ReviewItem, provision: LegalProvision) -> None:
        self.row = row
        self.provision = provision
        self.run = IngestionRun(
            id=row.ingestion_run_id,
            job_id="job-1",
            document_id=row.document_id,
            manifest_json={},
            file_hash="hash",
            status="PENDING_REVIEW",
            current_stage="QUALITY_CHECK",
        )
        self.committed = False
        self.outbox_events: list[object] = []

    def add(self, event: object) -> None:
        self.outbox_events.append(event)

    def get(self, model: object, key: object) -> object:
        return self.run

    def scalar_one_or_none(self, statement: object) -> object:
        return self.run

    def scalars(self, statement: object) -> list[ReviewItem]:
        return [self.row] if self.row.status == "PENDING" else []

    def scalar(self, statement: object) -> ReviewItem | LegalProvision | IngestionRun | None:
        entity = statement.column_descriptions[0].get("entity")
        if entity is LegalProvision:
            return self.provision
        if entity is IngestionRun:
            return self.run
        criterion = statement.whereclause
        requested_id = criterion.right.value
        return self.row if self.row.id == requested_id else None

    def commit(self) -> None:
        self.committed = True

    def refresh(self, row: ReviewItem) -> None:
        return None

    def flush(self) -> None:
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, Session, ReviewItem]]:
    provision = LegalProvision(
        id=uuid.uuid4(),
        provision_id="p-1",
        version=1,
        document_version_id=uuid.uuid4(),
        source_text="text",
        retrieval_text="text",
        status="EFFECTIVE",
        page_number=1,
        content_hash="hash",
        effective_from=date.today(),
    )
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
    row.created_at = datetime.now(UTC)
    session = Session(row, provision)
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


def test_missing_review_item_returns_standard_404(client: object) -> None:
    http, _, _ = client
    response = http.get(f"/api/v1/review/items/{uuid.uuid4()}")
    assert response.status_code == 404
    payload = response.json()
    assert payload["error"]["code"] == "NOT_FOUND"
    assert payload["error"]["message"] == "Review item was not found."
    assert isinstance(payload["error"]["trace_id"], str)


def test_decision_requires_reviewer_and_evidence(client: object) -> None:
    http, session, _ = client
    response = http.post("/api/v1/review/items/x/decision", json={"decision": "ACCEPTED"})
    assert response.status_code == 422
    assert not session.committed


def test_accept_records_explicit_audit_fields(client: object) -> None:
    http, session, row = client
    response = http.post(
        f"/api/v1/review/items/{row.id}/decision",
        json={
            "decision": "ACCEPTED",
            "reviewer": "alice",
            "evidence": {"verified": True},
            "effective_from": "2025-01-01",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ACCEPTED"
    assert row.reviewer == "alice"
    assert row.reviewed_at is not None
    assert row.evidence["review_decision"] == {"verified": True}
    assert session.committed
    assert session.run.status == "QUALITY_CHECK"
    assert len(session.outbox_events) == 1
