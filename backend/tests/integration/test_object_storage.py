"""Integration tests: S3-compatible object storage against live MinIO (VNLRAG-134).

Guarded by MinIO reachability (``MINIO_ENDPOINT`` env or repo-root ``.env``,
default ``http://localhost:9000`` — the ``vnlaw-minio`` docker-compose
service); the whole module is skipped when MinIO is not reachable.

All objects are written under the ``itest-vnlrag134/`` document prefix inside
the six canonical buckets (doc 03 §3.12.1) and removed on teardown; no
pre-existing data is touched. Verifies, per the ticket: put/get round-trip
for every bucket, list/delete behavior, presigned-GET fetch, idempotent
``ensure_buckets``, and the independent-backup guarantee (replication/mirror
semantics — the copy must survive deleting the source, which ILM tiering
would not satisfy, doc 03 §3.12.3).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import suppress

import httpx
import pytest

from app.config import get_object_storage_settings
from app.storage import BUCKETS, S3ObjectStorage, object_key

pytestmark = pytest.mark.integration

#: Document-id prefix reserved for these tests; swept on teardown.
TEST_PREFIX = "itest-vnlrag134"


@pytest.fixture(scope="module")
def object_storage() -> Iterator[S3ObjectStorage]:
    """S3ObjectStorage for the module; skipped when MinIO is unreachable."""
    settings = get_object_storage_settings()
    storage = S3ObjectStorage(
        endpoint=settings.endpoint,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        use_ssl=settings.use_ssl,
        buckets=settings.buckets,
    )
    try:
        storage.bucket_exists("source-pdfs")
    except Exception:
        pytest.skip(
            f"MinIO not reachable at {settings.endpoint} — skipping (start the "
            "vnlaw-minio docker-compose service to run these tests)"
        )
    yield storage


@pytest.fixture(autouse=True)
def _cleanup_test_objects(object_storage: S3ObjectStorage) -> Iterator[None]:
    """Best-effort removal of any objects left under the test prefix."""
    yield
    for bucket in sorted(BUCKETS):
        try:
            keys = object_storage.list(bucket, prefix=f"{TEST_PREFIX}/")
        except Exception:
            continue
        for key in keys:
            with suppress(Exception):
                object_storage.delete(bucket, key)


def _test_document_id() -> str:
    return f"{TEST_PREFIX}/{uuid.uuid4().hex[:12]}"


@pytest.mark.parametrize("bucket", sorted(BUCKETS))
def test_round_trip_list_delete_every_bucket(object_storage: S3ObjectStorage, bucket: str) -> None:
    document_id = _test_document_id()
    key = object_key(bucket, document_id=document_id, file_name="payload.bin", subpath="t134")
    payload = bytes(range(256))  # every byte value, including NUL
    try:
        object_storage.put(bucket, key, payload, content_type="application/octet-stream")
        assert object_storage.get(bucket, key) == payload
        assert key in object_storage.list(bucket, prefix=document_id)
    finally:
        object_storage.delete(bucket, key)
    assert key not in object_storage.list(bucket, prefix=document_id)


def test_presigned_get_fetches_object(object_storage: S3ObjectStorage) -> None:
    bucket = "source-pdfs"
    document_id = _test_document_id()
    key = object_key(
        bucket, document_id=document_id, file_name="evidence.pdf", content_hash="a" * 64
    )
    payload = b"%PDF-1.7 fake evidence bytes\x00\x01"
    try:
        object_storage.put(bucket, key, payload, content_type="application/pdf")
        url = object_storage.presigned_get(bucket, key, expires_seconds=300)
        assert bucket in url
        assert key in url
        with httpx.Client(timeout=15) as client:
            response = client.get(url)
        assert response.status_code == 200
        assert response.content == payload
    finally:
        object_storage.delete(bucket, key)


def test_ensure_buckets_idempotent(object_storage: S3ObjectStorage) -> None:
    object_storage.ensure_buckets()
    assert all(object_storage.bucket_exists(bucket) for bucket in BUCKETS)
    object_storage.ensure_buckets()  # second call must not raise
    assert all(object_storage.bucket_exists(bucket) for bucket in BUCKETS)


def test_independent_backup_replication(object_storage: S3ObjectStorage) -> None:
    """Source -> backup via get+put; the copy must outlive the source.

    Verifies replication/mirror semantics (doc 03 §3.12.3): deleting the
    source leaves the independent copy intact. Tiering, which only moves data
    within one system, would leave nothing behind.
    """
    source_bucket = "source-pdfs"
    backup_bucket = "parser-outputs"
    document_id = _test_document_id()
    source_key = object_key(
        source_bucket, document_id=document_id, file_name="doc.pdf", content_hash="b" * 64
    )
    backup_key = object_key(
        backup_bucket, document_id=document_id, file_name="backup.pdf", subpath="backup"
    )
    payload = b"%PDF-1.7 independent backup payload"
    try:
        object_storage.put(source_bucket, source_key, payload, content_type="application/pdf")
        # Replication: read the source, write an independent copy.
        object_storage.put(
            backup_bucket,
            backup_key,
            object_storage.get(source_bucket, source_key),
            content_type="application/pdf",
        )
        assert object_storage.get(backup_bucket, backup_key) == payload
        # Tiering would move the data; replication must leave the copy behind.
        object_storage.delete(source_bucket, source_key)
        assert object_storage.get(backup_bucket, backup_key) == payload
    finally:
        object_storage.delete(source_bucket, source_key)
        object_storage.delete(backup_bucket, backup_key)
