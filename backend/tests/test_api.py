"""Unit tests: upload + job status API (VNLRAG-135, doc 03 §3.28.3/§3.28.4).

Everything external (object storage, the enqueue hook, PostgreSQL sessions)
is faked or monkeypatched: the API contract is exercised through
``fastapi.testclient.TestClient`` against the real FastAPI app.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import documents as documents_module
from app.api.db import get_db
from app.config import UploadSettings
from app.main import app
from app.persistence.models import IngestionRun, LegalDocument

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


# --- Upload validation -------------------------------------------------------


def test_upload_rejects_non_pdf_extension(api_client: object) -> None:
    client, _, _, _ = api_client
    response = client.post(
        "/api/v1/documents",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415
    _assert_error_shape(response.json(), 415, "UNSUPPORTED_MEDIA_TYPE")


def test_upload_accepts_uppercase_pdf_extension(api_client: object) -> None:
    client, _, enqueue_calls, _ = api_client
    response = client.post(
        "/api/v1/documents",
        files={"file": ("LAW.PDF", PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 202
    assert enqueue_calls


def test_upload_rejects_unexpected_content_type(api_client: object) -> None:
    client, _, _, _ = api_client
    response = client.post(
        "/api/v1/documents",
        files={"file": ("document.pdf", PDF_BYTES, "text/plain")},
    )
    assert response.status_code == 400
    _assert_error_shape(response.json(), 400, "INVALID_CONTENT_TYPE")


def test_upload_rejects_oversized_file(api_client: object, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _, _ = api_client
    monkeypatch.setattr(
        documents_module, "get_upload_settings", lambda: UploadSettings(max_size_mb=1)
    )
    response = client.post(
        "/api/v1/documents",
        files={"file": ("big.pdf", b"x" * (2 * 1024 * 1024), "application/pdf")},
    )
    assert response.status_code == 413
    _assert_error_shape(response.json(), 413, "FILE_TOO_LARGE")


class ChunkedFakeFile:
    """Duck-typed ``UploadFile`` yielding fixed-size chunks; records reads.

    ``size`` is None so the handler takes the bounded chunked-read path
    (rather than the early ``UploadFile.size`` short-circuit).
    """

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self.reads = 0
        self.filename = "big.pdf"
        self.content_type = "application/pdf"
        self.size: int | None = None

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        if not self._chunks:
            return b""
        chunk = self._chunks.pop(0)
        return chunk[:size] if 0 < size < len(chunk) else chunk


def test_upload_aborts_read_when_chunks_exceed_limit(
    api_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Oversized uploads are rejected mid-stream, not fully consumed."""
    _, session, _, _ = api_client
    monkeypatch.setattr(
        documents_module, "get_upload_settings", lambda: UploadSettings(max_size_mb=1)
    )
    mega = 1024 * 1024
    fake = ChunkedFakeFile([b"a" * mega, b"b" * mega, b"c" * mega, b"d" * mega])

    response = asyncio.run(documents_module.upload_document(file=fake, db=session))

    assert response.status_code == 413
    _assert_error_shape(json.loads(response.body), 413, "FILE_TOO_LARGE")
    # Two 1 MiB chunks crossed the 1 MiB limit; the remaining body was not read.
    assert fake.reads == 2
    assert len(fake._chunks) == 2
    assert session.added == []  # nothing persisted for a rejected upload


def test_upload_missing_file_yields_422_standard_shape(api_client: object) -> None:
    client, _, _, _ = api_client
    response = client.post("/api/v1/documents")
    assert response.status_code == 422
    _assert_error_shape(response.json(), 422, "VALIDATION_ERROR")


def test_upload_rejects_malformed_document_id(api_client: object) -> None:
    client, session, _, _ = api_client
    response = client.post(
        "/api/v1/documents",
        files={"file": ("document.pdf", PDF_BYTES, "application/pdf")},
        data={"document_id": "../evil"},
    )
    assert response.status_code == 400
    _assert_error_shape(response.json(), 400, "INVALID_DOCUMENT_ID")
    assert session.added == []  # nothing persisted for a rejected id


# --- Upload success path -----------------------------------------------------


def test_upload_success_202_shape_and_enqueue(api_client: object) -> None:
    client, session, enqueue_calls, storage = api_client
    response = _upload(client)
    assert response.status_code == 202
    payload = response.json()
    assert set(payload) == {"ingestion_job_id", "status"}
    assert payload["status"] == "queued"
    job_id = payload["ingestion_job_id"]
    assert isinstance(job_id, str) and job_id.startswith("job_")

    assert len(enqueue_calls) == 1
    enqueued_job_id, object_key, document_id = enqueue_calls[0]
    assert enqueued_job_id == job_id
    assert isinstance(document_id, str)

    file_hash = hashlib.sha256(PDF_BYTES).hexdigest()
    assert object_key == f"{document_id}/source/{file_hash}.pdf"
    assert storage.list("source-pdfs") == [object_key]
    assert storage.get("source-pdfs", object_key) == PDF_BYTES
    assert session.committed


def test_upload_uses_provided_document_id(api_client: object) -> None:
    client, _, enqueue_calls, storage = api_client
    response = _upload(client, document_id="nd-168-2024")
    assert response.status_code == 202
    _, object_key, document_id = enqueue_calls[0]
    assert document_id == "nd-168-2024"
    assert object_key.startswith("nd-168-2024/source/")
    assert storage.list("source-pdfs", prefix="nd-168-2024/") == [object_key]


def test_upload_creates_legal_document_row(api_client: object) -> None:
    client, session, _, _ = api_client
    response = _upload(client, document_id="nd-135-test")
    assert response.status_code == 202
    assert len(session.added) == 1
    row = session.added[0]
    assert row.document_id == "nd-135-test"
    assert row.file_hash == hashlib.sha256(PDF_BYTES).hexdigest()
    assert row.status == "UPLOADED"


def test_upload_deduplicates_bytes_by_file_hash(api_client: object) -> None:
    client, session, enqueue_calls, storage = api_client
    session.scalar_result = LegalDocument(
        document_id="nd-135-existing",
        document_number="nd-135-existing",
        document_title="existing",
        document_type="UNKNOWN",
        file_hash=hashlib.sha256(PDF_BYTES).hexdigest(),
        status="UPLOADED",
    )
    response = _upload(client, document_id="nd-135-dup")
    assert response.status_code == 202
    assert session.added == []  # reused the existing row, created nothing
    _, object_key, document_id = enqueue_calls[0]
    assert document_id == "nd-135-existing"  # canonical row wins
    assert object_key.startswith("nd-135-existing/source/")
    assert storage.list("source-pdfs", prefix="nd-135-existing/") == [object_key]


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


def test_internal_error_handler_500_shape(
    api_client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _, _, _ = api_client

    def boom(job_id: str, object_key: str, *, document_id: str | None = None) -> str:
        raise RuntimeError("queue unreachable")

    monkeypatch.setattr(documents_module, "_enqueue", boom)
    # Starlette's TestClient re-raises unhandled endpoint exceptions by
    # default even though the app responds with the 500 JSON body; disable
    # that to assert on the wire response.
    quiet = TestClient(app, raise_server_exceptions=False)
    response = _upload(quiet)
    assert response.status_code == 500
    _assert_error_shape(response.json(), 500, "INTERNAL_ERROR")


def test_error_trace_ids_are_unique_per_request(api_client: object) -> None:
    client, _, _, _ = api_client
    first = client.get("/api/v1/jobs/unknown-1").json()["error"]["trace_id"]
    second = client.get("/api/v1/jobs/unknown-2").json()["error"]["trace_id"]
    assert first != second
    assert uuid.UUID(hex=first)
