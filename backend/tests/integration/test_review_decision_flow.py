"""Integration tests for current review decision persistence."""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.persistence.models import IngestionRun, LegalDocument
from app.persistence.repositories.review_items import ReviewItemNotFoundError, ReviewItemRepository

try:
    from conftest import clean_transaction
except ImportError:
    from tests.integration.conftest import clean_transaction

pytestmark = pytest.mark.integration


def _seed(session: Session) -> tuple[IngestionRun, LegalDocument]:
    document = LegalDocument(
        document_id=f"doc-{uuid.uuid4().hex[:10]}",
        document_number="168/2024",
        document_title="Nghị định 168/2024/NĐ-CP",
        document_type="DECREE",
        file_hash=uuid.uuid4().hex,
        status="PUBLISHED",
    )
    session.add(document)
    session.flush()
    run = IngestionRun(
        job_id=f"job-{uuid.uuid4().hex[:10]}",
        document_id=document.document_id,
        manifest_json={},
        file_hash=uuid.uuid4().hex,
        status="COMPLETED",
    )
    session.add(run)
    session.flush()
    return run, document


def test_review_decision_persists_audit_fields(upgraded_engine: Engine) -> None:
    with clean_transaction(upgraded_engine) as connection, Session(bind=connection) as session:
        run, document = _seed(session)
        repository = ReviewItemRepository(session)
        item = repository.create(
            ingestion_run_id=run.id,
            document_id=document.document_id,
            target_type="PROVISION",
            target_id="nd-168-2024__dieu-7",
            reason_code="LOW_OCR_COVERAGE",
            description="verify",
            evidence={"coverage": 0.42},
        )
        updated = repository.record_decision(
            item.id, "ACCEPTED", reviewer="cli-tester", reason="approved"
        )
        assert updated.status == "ACCEPTED"
        assert updated.reviewer == "cli-tester"
        assert updated.reviewed_at is not None
        assert updated.reviewed_at.tzinfo is UTC
        session.expire_all()
        persisted = repository.get(item.id)
        assert persisted is not None
        assert persisted.status == "ACCEPTED"
        assert persisted.reviewer == "cli-tester"


def test_review_decision_missing_item_fails_closed(upgraded_engine: Engine) -> None:
    with clean_transaction(upgraded_engine) as connection, Session(bind=connection) as session:
        with pytest.raises(ReviewItemNotFoundError, match="not found"):
            ReviewItemRepository(session).record_decision(
                uuid.uuid4(), "REJECTED", reviewer="cli-tester"
            )
