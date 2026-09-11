"""Unit tests: upload + job status API (VNLRAG-135, doc 03 §3.28.3/§3.28.4).

Everything external (object storage, the enqueue hook, PostgreSQL sessions)
is faked or monkeypatched: the API contract is exercised through
``fastapi.testclient.TestClient`` against the real FastAPI app.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_module
from app.api.db import get_db
from app.main import app
from app.persistence.models import IngestionRun

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


class FakeSession:
    """Duck-typed ``sqlalchemy.orm.Session`` for repository calls."""

    def __init__(self, scalar_result: object = None) -> None:
        self.scalar_result = scalar_result
        self.added: list[object] = []
        self.committed = False

    def scalar(self, stmt: object) -> object:
        return self.scalar_result

    def add(self, obj: object) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        pass


class FakeObjectStorage:
    """In-memory ObjectStoragePort substitute recording puts."""

    def __init__(self) -> None:
        self._objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[tuple[str, str, bytes]] = []

    def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: object = None,
    ) -> None:
        self._objects[(bucket, key)] = bytes(data)
        self.put_calls.append((bucket, key, bytes(data)))

    def get(self, bucket: str, key: str) -> bytes:
        return self._objects[(bucket, key)]

    def list(self, bucket: str, prefix: str = "") -> list[str]:
        return sorted(key for (b, key) in self._objects if b == bucket and key.startswith(prefix))


@pytest.fixture()
def api_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, FakeSession, list[tuple[str, str, str | None]], FakeObjectStorage]]:
    """TestClient with the DB dependency overridden and the enqueue hook recorded.

    Returns ``(client, session, enqueue_calls, storage)`` where
    ``enqueue_calls`` is a mutable list appended with
    ``(job_id, object_key, document_id)`` per call and ``storage`` is the
    in-memory object storage the handler stores into.
    """
    session = FakeSession()
    storage = FakeObjectStorage()
    enqueue_calls: list[tuple[str, str, str | None]] = []

    def fake_enqueue(job_id: str, object_key: str, *, document_id: str | None = None) -> str:
        enqueue_calls.append((job_id, object_key, document_id))
        return f"msg-{job_id}"

    monkeypatch.setattr(documents_module, "get_object_storage", lambda: storage)
    monkeypatch.setattr(documents_module, "_enqueue", fake_enqueue)
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app), session, enqueue_calls, storage
    finally:
        app.dependency_overrides.clear()


def _upload(client: TestClient, **kwargs: object) -> object:
    """POST a PDF to /api/v1/documents with default fixtures."""
    files = kwargs.pop("files", None) or {"file": ("document.pdf", PDF_BYTES, "application/pdf")}
    return client.post("/api/v1/documents", files=files, data=kwargs)


def _assert_error_shape(payload: dict[str, object], status: int, code: str) -> str:
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["message"], str)
    trace_id = payload["error"]["trace_id"]
    assert isinstance(trace_id, str) and _TRACE_ID_RE.fullmatch(trace_id)
    return trace_id


def test_upload_is_disabled_by_public_contract(api_client: object) -> None:
    client, _, _, _ = api_client
    response = client.post(
        "/api/v1/documents",
        files={"file": ("document.pdf", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 410
    _assert_error_shape(response.json(), 410, "UPLOAD_DISABLED")


# --- Job status --------------------------------------------------------------


def _make_run(status: str = "queued", **overrides: object) -> IngestionRun:
    now = datetime.now(UTC)
    fields: dict[str, object] = {
        "job_id": "job_test123",
        "document_id": "documents/test",
        "manifest_json": {},
        "file_hash": "deadbeef",
        "status": status,
        "started_at": now,
        "updated_at": now,
    }
    fields.update(overrides)
    return IngestionRun(**fields)


def test_job_status_maps_run_fields(api_client: object) -> None:
    client, session, _, _ = api_client
    session.scalar_result = _make_run(
        status="PARSING", current_stage="parse", parser_routing={"parser": "DOCLING"}
    )
    response = client.get("/api/v1/jobs/job_test123")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ingestion_job_id"] == "job_test123"
    assert payload["status"] == "PARSING"
    assert payload["current_stage"] == "parse"
    assert payload["parser_routing"] == {"parser": "DOCLING"}
    assert payload["created_at"] is not None
    assert payload["updated_at"] is not None
    assert payload["error"] is None


def test_job_status_unknown_returns_404(api_client: object) -> None:
    client, _, _, _ = api_client
    response = client.get("/api/v1/jobs/does-not-exist")
    assert response.status_code == 404
    _assert_error_shape(response.json(), 404, "JOB_NOT_FOUND")


# --- Error handlers ----------------------------------------------------------
def test_error_trace_ids_are_unique_per_request(api_client: object) -> None:
    client, _, _, _ = api_client
    first = client.get("/api/v1/jobs/unknown-1").json()["error"]["trace_id"]
    second = client.get("/api/v1/jobs/unknown-2").json()["error"]["trace_id"]
    assert first != second
    assert uuid.UUID(hex=first)
