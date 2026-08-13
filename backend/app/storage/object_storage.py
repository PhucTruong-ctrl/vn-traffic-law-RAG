"""S3-compatible object storage: port, MinIO adapter, key conventions (VNLRAG-134).

Implements FR-08 / doc 03 §3.12: PostgreSQL stores object keys and metadata;
the file content itself lives in S3-compatible object storage (MinIO in the
docker-compose environment, doc 04 §4.15).

Bucket layout (§3.12.1) — bucket names contain no ``/`` (S3/MinIO rule):

=================== ==========================================================
Bucket              Content
=================== ==========================================================
source-pdfs         validated source PDFs
parser-outputs      raw parser output (Docling JSON, MinerU JSON/Markdown)
page-images         page images for review and the passage viewer
ingestion-artifacts IR JSON, quality-gate reports
review-artifacts    review evidence, screenshots, provenance
evaluation-artifacts raw evaluation output and artifacts
=================== ==========================================================

Object-key convention (§3.12.2):

    {key} = {document_id}/{subpath}/{file}

* ``document_id`` is the owning entity path, e.g. ``documents/nd-168-2024``
  (source PDFs), ``review-{id}`` (review evidence) or ``run-{run_id}``
  (evaluation artifacts).
* ``subpath`` is the optional producer/version segment, e.g. ``source`` for
  validated source PDFs or ``docling-2.1.0`` for parser output.
* ``file`` is a system-generated internal filename — never a user-supplied
  path; :func:`object_key` rejects path components and ``..`` segments. When a
  ``content_hash`` is supplied the stored name is ``{content_hash}{ext}``
  (e.g. ``<sha256>.pdf``), so source PDFs are content-addressed.

Callers build keys exclusively through :func:`object_key`.

Backup (doc 03 §3.12.3) is server-side replication or ``mc mirror`` to an
independent store — NOT ILM tiering, which only moves data between tiers of
the same system. The integration test ``test_independent_backup_replication``
verifies the replication semantics (the copy must survive deleting the
source).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import timedelta
from functools import lru_cache
from io import BytesIO
from pathlib import PurePosixPath
from typing import Protocol, runtime_checkable

from minio import Minio

from app.config import get_object_storage_settings

__all__ = [
    "BUCKETS",
    "ObjectStoragePort",
    "S3ObjectStorage",
    "get_object_storage",
    "object_key",
]

# --- Buckets (doc 03 §3.12.1) -------------------------------------------------

#: Canonical bucket set. Bucket names contain no ``/`` (S3/MinIO rule); the
#: docker-compose ``MINIO_BUCKETS`` bootstrap list must stay in sync with this
#: (pinned by tests/test_object_storage.py).
BUCKETS = frozenset(
    {
        "source-pdfs",
        "parser-outputs",
        "page-images",
        "ingestion-artifacts",
        "review-artifacts",
        "evaluation-artifacts",
    }
)


# --- Port ---------------------------------------------------------------------


@runtime_checkable
class ObjectStoragePort(Protocol):
    """Minimal S3-compatible object storage contract (doc 03 §3.12).

    Implementations must be safe for concurrent use. Failures (unreachable or
    misconfigured storage, missing buckets/objects) surface as exceptions from
    the underlying client; ``delete`` is idempotent; ``list`` returns object
    keys only; ``ensure_buckets`` creates any configured bucket that is
    missing.
    """

    def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None: ...

    def get(self, bucket: str, key: str) -> bytes: ...

    def delete(self, bucket: str, key: str) -> None: ...

    def list(self, bucket: str, prefix: str = "") -> list[str]: ...

    def presigned_get(self, bucket: str, key: str, expires_seconds: int = 3600) -> str: ...

    def bucket_exists(self, bucket: str) -> bool: ...

    def ensure_buckets(self) -> None: ...


# --- Key conventions (doc 03 §3.12.2) -----------------------------------------


def object_key(
    bucket: str,
    *,
    document_id: str,
    file_name: str,
    content_hash: str | None = None,
    subpath: str | None = None,
) -> str:
    """Build an object key per doc 03 §3.12.2: ``{document_id}/{subpath}/{file}``.

    ``document_id`` and ``subpath`` are slash-separated paths (e.g.
    ``documents/nd-168-2024`` and ``docling-2.1.0``); ``file_name`` must be a
    bare filename. When ``content_hash`` is given, the stored name becomes
    ``{content_hash}{ext}`` (extension preserved from ``file_name``), e.g.
    ``<sha256>.pdf`` for content-addressed source PDFs.

    Raises :class:`ValueError` for unknown buckets, empty segments, ``.`` /
    ``..`` segments, or filenames containing path separators (path traversal
    is rejected — filenames are system-generated per §3.12.2).
    """
    if bucket not in BUCKETS:
        raise ValueError(f"unknown bucket {bucket!r}; expected one of {sorted(BUCKETS)}")
    if content_hash is not None and not content_hash.strip():
        raise ValueError("content_hash must be non-empty")
    name = file_name.strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        raise ValueError(
            f"invalid file_name {file_name!r}: must be a bare filename without path components"
        )
    if content_hash is not None:
        name = f"{content_hash.strip()}{PurePosixPath(name).suffix}"
    segments: list[str] = []
    for label, value in (("document_id", document_id), ("subpath", subpath)):
        if value is None:
            continue
        normalized = value.strip().strip("/")
        if not normalized or any(seg in ("", ".", "..") for seg in normalized.split("/")):
            raise ValueError(
                f"invalid {label} {value!r}: must be a non-empty slash-separated "
                "path without '.' or '..' segments"
            )
        segments.append(normalized)
    segments.append(name)
    return "/".join(segments)


# --- MinIO adapter ------------------------------------------------------------


def _strip_scheme(endpoint: str) -> str:
    """Drop an ``http(s)://`` scheme; TLS is controlled by ``use_ssl`` only."""
    for scheme in ("https://", "http://"):
        if endpoint.startswith(scheme):
            return endpoint[len(scheme) :].rstrip("/")
    return endpoint.rstrip("/")


class S3ObjectStorage:
    """S3-compatible object storage via the MinIO SDK (doc 03 §3.12).

    Implements :class:`ObjectStoragePort`. ``endpoint`` may be given with or
    without an ``http(s)://`` scheme (the scheme is ignored; TLS is controlled
    by ``use_ssl``). When ``buckets`` is omitted the canonical doc 03 §3.12.1
    set (:data:`BUCKETS`) is used. ``client`` is a test seam allowing a fake
    MinIO client to be injected.
    """

    def __init__(
        self,
        *,
        endpoint: str = "localhost:9000",
        access_key: str = "",
        secret_key: str = "",
        use_ssl: bool = False,
        buckets: Iterable[str] | None = None,
        client: Minio | None = None,
    ) -> None:
        self._buckets = frozenset(buckets) if buckets is not None else BUCKETS
        if client is not None:
            self._client = client
        else:
            self._client = Minio(
                _strip_scheme(endpoint),
                access_key=access_key or None,
                secret_key=secret_key or None,
                secure=use_ssl,
            )

    def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        self._client.put_object(
            bucket,
            key,
            BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
            metadata=dict(metadata) if metadata else None,
        )

    def get(self, bucket: str, key: str) -> bytes:
        response = self._client.get_object(bucket, key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def delete(self, bucket: str, key: str) -> None:
        self._client.remove_object(bucket, key)

    def list(self, bucket: str, prefix: str = "") -> list[str]:
        return [
            obj.object_name
            for obj in self._client.list_objects(bucket, prefix=prefix or None, recursive=True)
        ]

    def presigned_get(self, bucket: str, key: str, expires_seconds: int = 3600) -> str:
        return self._client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=expires_seconds)
        )

    def bucket_exists(self, bucket: str) -> bool:
        return self._client.bucket_exists(bucket)

    def ensure_buckets(self) -> None:
        for bucket in sorted(self._buckets):
            if not self._client.bucket_exists(bucket):
                self._client.make_bucket(bucket)


# --- Factory ------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_object_storage() -> S3ObjectStorage:
    """Return the process-wide object storage singleton (cached until cleared).

    The MinIO client is created lazily on first call, never at import time.
    """
    settings = get_object_storage_settings()
    return S3ObjectStorage(
        endpoint=settings.endpoint,
        access_key=settings.access_key,
        secret_key=settings.secret_key,
        use_ssl=settings.use_ssl,
        buckets=settings.buckets,
    )
