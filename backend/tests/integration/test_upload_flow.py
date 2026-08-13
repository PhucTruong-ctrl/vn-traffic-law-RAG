"""Integration test: upload API end-to-end (VNLRAG-135, doc 03 §3.28.3).

Exercises the real request path against live PostgreSQL (scratch database,
migrated by the conftest fixtures), live MinIO (``source-pdfs`` bucket) and a
reachable Redis (the queue dependency). Skipped automatically when any of
those services is unreachable or unconfigured.

The ``_enqueue`` hook is monkeypatched to a recorder: the real implementation
is provided by VNLRAG-133 (``app.ingestion.actors.enqueue_parse``, deferred
import) and this worktree does not yet contain that package. The
``ingestion_runs`` row is created lazily by the parse actor (VNLRAG-133
contract), so the test simulates that bootstrap to verify
``GET /api/v1/jobs/{job_id}``, and asserts the documented 404 before it.

Cleanup deletes the uploaded object and the created rows, leaving the scratch
database empty between tests (conftest convention).
"""

from __future__ import annotations

import hashlib
import os
import uuid

import pytest
import redis as redis_lib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.api import db as api_db
from app.api import documents as documents_module
from app.main import app
from app.persistence.models import IngestionRun, LegalDocument
from app.storage import get_object_storage

pytestmark = pytest.mark.integration


def _pg_reachable(url: str) -> bool:
    """True when a PostgreSQL server answers at ``url``."""
    try:
        probe = create_engine(url, connect_args={"connect_timeout": 3})
        with probe.connect():
            pass
        probe.dispose()
        return True
    except Exception:
        return False


def _minio_reachable() -> bool:
    """True when the configured MinIO answers and has ``source-pdfs``.

    The settings/storage singletons may have been cached earlier in the
    process by unit tests (which isolate MINIO_* env); clear them so the
    environment read here is fresh.
    """
    from app.config import get_object_storage_settings
    from app.storage import get_object_storage

    get_object_storage_settings.cache_clear()
    get_object_storage.cache_clear()
    try:
        storage = get_object_storage()
        return bool(storage.bucket_exists("source-pdfs"))
    except Exception:
        return False


def _redis_reachable() -> bool:
    """True when a Redis server answers at ``REDIS_URL`` (or localhost)."""
    url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        return bool(redis_lib.Redis.from_url(url, socket_timeout=3).ping())
    except Exception:
        return False


def test_upload_flow(
    monkeypatch: pytest.MonkeyPatch, migration_db_url: str, upgraded_engine: Engine
) -> None:
    """Real upload -> stored object -> job status lifecycle + cleanup."""
    # ``upgraded_engine`` (dependency) guarantees the scratch schema is
    # migrated to head; the plain-string URL keeps the password intact.
    db_url = migration_db_url
    if make_url(db_url).get_backend_name() != "postgresql" or not _pg_reachable(db_url):
        pytest.skip("PostgreSQL not reachable; skipping upload flow integration test")
    if not _minio_reachable():
        pytest.skip("MinIO source-pdfs not reachable; skipping upload flow integration test")
    if not _redis_reachable():
        pytest.skip("Redis not reachable; skipping upload flow integration test")

    # Point the API's session factory at the migrated scratch database.
    monkeypatch.setenv("DATABASE_URL", db_url)
    api_db.get_engine.cache_clear()

    enqueue_calls: list[tuple[str, str, str | None]] = []

    def fake_enqueue(job_id: str, object_key: str, *, document_id: str | None = None) -> str:
        enqueue_calls.append((job_id, object_key, document_id))
        return f"msg-{job_id}"

    monkeypatch.setattr(documents_module, "_enqueue", fake_enqueue)

    storage = get_object_storage()
    doc_id = f"documents/it-{uuid.uuid4().hex[:10]}"
    file_name = f"{uuid.uuid4().hex[:10]}.pdf"
    payload = b"%PDF-1.4\n%% integration upload fixture\n%%EOF\n"
    file_hash = hashlib.sha256(payload).hexdigest()
    expected_key = f"{doc_id}/source/{file_hash}.pdf"
    job_id: str | None = None
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/documents",
            files={"file": (file_name, payload, "application/pdf")},
            data={"document_id": doc_id},
        )
        assert response.status_code == 202, response.text
        body = response.json()
        assert set(body) == {"ingestion_job_id", "status"}
        assert body["status"] == "queued"
        job_id = body["ingestion_job_id"]
        assert isinstance(job_id, str) and job_id.startswith("job_")

        # The message carries exactly job_id + object_key + document_id.
        assert enqueue_calls == [(job_id, expected_key, doc_id)]

        # The PDF is stored content-addressed in source-pdfs.
        assert expected_key in storage.list("source-pdfs", prefix=f"{doc_id}/")
        assert storage.get("source-pdfs", expected_key) == payload

        # Before the parse actor bootstraps the run row, the job is unknown.
        missing = client.get(f"/api/v1/jobs/{job_id}")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"

        # Simulate the parse-actor bootstrap (VNLRAG-133 creates the
        # ingestion_runs row lazily) and read it back through the API.
        with Session(api_db.get_engine()) as session:
            run = IngestionRun(
                job_id=job_id,
                document_id=doc_id,
                manifest_json={},
                file_hash=file_hash,
                status="queued",
            )
            session.add(run)
            session.commit()

        status_response = client.get(f"/api/v1/jobs/{job_id}")
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["ingestion_job_id"] == job_id
        assert status_body["status"] == "queued"
        assert status_body["current_stage"] is None
        assert status_body["created_at"] is not None
    finally:
        if job_id is not None:
            storage.delete("source-pdfs", expected_key)
            with Session(api_db.get_engine()) as session:
                session.execute(delete(IngestionRun).where(IngestionRun.job_id == job_id))
                session.execute(
                    delete(LegalDocument).where(LegalDocument.document_id == doc_id)
                )
                session.commit()
        assert storage.list("source-pdfs", prefix=f"{doc_id}/") == []
