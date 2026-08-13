"""Integration: review decision flow against real PostgreSQL (VNLRAG-155).

Exercises ``ReviewItemRepository`` and the ``review_item`` CLI end-to-end on
the migrated session scratch database (conftest.py): create -> accept/reject
-> ACCEPTED/REJECTED/DROPPED with reviewer + reviewed_at.  Repository tests
run in a transaction that is always rolled back; the CLI subprocess test
commits and then cleans up its own rows so the scratch database stays empty
between tests.  Skipped automatically when no PostgreSQL DATABASE_URL is
reachable (conftest fixtures) — same pattern as the other integration tests.
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from datetime import UTC
from pathlib import Path

import pytest
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from app.persistence.models import IngestionRun, LegalDocument, ReviewItem
from app.persistence.repositories.review_items import (
    ReviewItemNotFoundError,
    ReviewItemRepository,
)

try:  # pytest inserts the test dir on sys.path in non-package mode
    from conftest import clean_transaction
except ImportError:  # package mode: tests/__init__.py makes it importable
    from tests.integration.conftest import clean_transaction

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture()
def session(upgraded_engine: Engine) -> Iterator[Session]:
    """A session on the migrated scratch database; always rolled back."""
    with clean_transaction(upgraded_engine) as conn, Session(bind=conn) as session:
        yield session


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _seed_document(session: Session) -> LegalDocument:
    document = LegalDocument(
        document_id=_unique("doc"),
        document_number=_unique("168/2024"),
        document_title="Nghị định 168/2024/NĐ-CP",
        document_type="DECREE",
        file_hash=uuid.uuid4().hex,
        status="PUBLISHED",
    )
    session.add(document)
    session.flush()
    return document


def _seed_ingestion_run(session: Session, document: LegalDocument) -> IngestionRun:
    run = IngestionRun(
        job_id=_unique("job"),
        document_id=document.document_id,
        manifest_json={"manifest": "x"},
        file_hash=uuid.uuid4().hex,
        status="COMPLETED",
    )
    session.add(run)
    session.flush()
    return run


def _create_item(session: Session, run: IngestionRun, document: LegalDocument) -> ReviewItem:
    return ReviewItemRepository(session).create(
        ingestion_run_id=run.id,
        document_id=document.document_id,
        target_type="PROVISION",
        target_id=_unique("nd-168-2024__dieu-7"),
        reason_code="LOW_OCR_COVERAGE",
        description="OCR coverage 0.42 below the 0.8 threshold",
        evidence={"text_extraction_rate": 0.42},
    )


def test_create_pending_and_list(session: Session) -> None:
    document = _seed_document(session)
    run = _seed_ingestion_run(session, document)
    repository = ReviewItemRepository(session)
    item = _create_item(session, run, document)

    assert item.status == "PENDING"
    assert item.reviewer is None
    assert item.reviewed_at is None

    listed = repository.list()
    assert item.id in {row.id for row in listed}
    assert repository.list(status="PENDING") != []
    assert repository.list(status="ACCEPTED") == []
    assert repository.get(item.id) is item
    assert repository.get(uuid.uuid4()) is None


def test_accept_flow(session: Session) -> None:
    document = _seed_document(session)
    run = _seed_ingestion_run(session, document)
    repository = ReviewItemRepository(session)
    item = _create_item(session, run, document)

    updated = repository.record_decision(
        item.id, "ACCEPTED", reviewer="linh", reason="approved after manual check"
    )

    assert updated.status == "ACCEPTED"
    assert updated.reviewer == "linh"
    assert updated.reviewed_at is not None
    assert updated.reviewed_at.tzinfo is UTC
    assert updated.description == (
        "OCR coverage 0.42 below the 0.8 threshold\napproved after manual check"
    )
    # Persisted, not just mutated in memory.
    session.expire_all()
    assert repository.get(item.id).status == "ACCEPTED"


def test_needs_review_keeps_pending(session: Session) -> None:
    document = _seed_document(session)
    run = _seed_ingestion_run(session, document)
    repository = ReviewItemRepository(session)
    item = _create_item(session, run, document)

    updated = repository.record_decision(
        item.id, "NEEDS_REVIEW", reviewer="linh", reason="verify against official source"
    )

    # NEEDS_REVIEW is a decision, not a DB status: the row stays PENDING
    # (still in the review queue, never indexed) but the decision is audited.
    assert updated.status == "PENDING"
    assert updated.reviewer == "linh"
    assert updated.reviewed_at is not None
    assert "verify against official source" in updated.description


def test_reject_flow(session: Session) -> None:
    document = _seed_document(session)
    run = _seed_ingestion_run(session, document)
    repository = ReviewItemRepository(session)
    item = _create_item(session, run, document)

    updated = repository.record_decision(item.id, "REJECTED", reviewer="linh", reason="duplicate")

    # REJECTED/DROPPED -> dropped, never indexed (boundary enforced in VNLRAG-44).
    assert updated.status == "REJECTED"
    assert updated.reviewer == "linh"
    assert updated.reviewed_at is not None


def test_dropped_flow(session: Session) -> None:
    document = _seed_document(session)
    run = _seed_ingestion_run(session, document)
    repository = ReviewItemRepository(session)
    item = _create_item(session, run, document)

    updated = repository.record_decision(item.id, "DROPPED", reviewer="linh")

    assert updated.status == "DROPPED"
    assert updated.reviewer == "linh"
    assert updated.reviewed_at is not None


def test_record_decision_missing_item_raises(session: Session) -> None:
    with pytest.raises(ReviewItemNotFoundError, match="not found"):
        ReviewItemRepository(session).record_decision(uuid.uuid4(), "ACCEPTED", reviewer="linh")


def test_cli_accept_end_to_end(migration_db_url: str, upgraded_engine: Engine) -> None:
    """Run the real CLI script against PostgreSQL; the decision must persist."""
    # Seed through the engine directly (not the rolled-back clean_transaction
    # session) and commit, so the CLI subprocess — a separate connection —
    # can see the row.  The test cleans its rows up afterwards.
    with Session(upgraded_engine) as session:
        document = _seed_document(session)
        run = _seed_ingestion_run(session, document)
        item = _create_item(session, run, document)
        session.commit()
        item_id = item.id
        run_id = run.id
        document_id = document.document_id

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(BACKEND_DIR / "scripts" / "review_item.py"),
                "accept",
                str(item_id),
            ],
            cwd=BACKEND_DIR,
            env={**os.environ, "DATABASE_URL": migration_db_url, "REVIEWER": "cli-tester"},
            capture_output=True,
            text=True,
            timeout=120,
        )

        assert result.returncode == 0, result.stderr
        assert "ACCEPTED" in result.stdout

        with Session(upgraded_engine) as session:
            row = ReviewItemRepository(session).get(item_id)
            assert row is not None
            assert row.status == "ACCEPTED"
            assert row.reviewer == "cli-tester"
            assert row.reviewed_at is not None
    finally:
        with Session(upgraded_engine) as session:
            session.execute(delete(ReviewItem).where(ReviewItem.id == item_id))
            session.execute(delete(IngestionRun).where(IngestionRun.id == run_id))
            session.execute(delete(LegalDocument).where(LegalDocument.document_id == document_id))
            session.commit()
