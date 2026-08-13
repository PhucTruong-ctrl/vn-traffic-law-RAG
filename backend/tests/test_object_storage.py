"""Unit tests: S3-compatible object storage port and MinIO adapter (VNLRAG-134).

The port contract is exercised against an in-memory implementation; the
``S3ObjectStorage`` adapter itself is exercised against a duck-typed fake
MinIO client. No live storage is required.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from datetime import timedelta

import pytest

from app.config import ObjectStorageSettings, get_object_storage_settings
from app.storage import BUCKETS, ObjectStoragePort, S3ObjectStorage, get_object_storage, object_key

#: Canonical buckets per doc 03 §3.12.1 and the repo .env MINIO_BUCKETS value.
DOC_BUCKETS = {
    "source-pdfs",
    "parser-outputs",
    "page-images",
    "ingestion-artifacts",
    "review-artifacts",
    "evaluation-artifacts",
}


class MemoryObjectStorage:
    """In-memory ObjectStoragePort implementation for contract tests.

    ``configured`` holds the buckets the store knows about; ``existing`` holds
    the buckets that physically exist. Mirrors the real adapter: operations on
    a non-existing bucket raise :class:`KeyError`, ``delete`` is idempotent,
    ``ensure_buckets`` creates the configured buckets.
    """

    def __init__(self, buckets: Iterable[str] | None = None) -> None:
        self.configured = set(buckets) if buckets is not None else set(BUCKETS)
        self.existing = set(self.configured)
        self._objects: dict[tuple[str, str], bytes] = {}
        self._content_types: dict[tuple[str, str], str | None] = {}
        self._metadata: dict[tuple[str, str], Mapping[str, str]] = {}

    def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> None:
        if bucket not in self.existing:
            raise KeyError(bucket)
        self._objects[(bucket, key)] = bytes(data)
        self._content_types[(bucket, key)] = content_type
        if metadata is not None:
            self._metadata[(bucket, key)] = dict(metadata)

    def get(self, bucket: str, key: str) -> bytes:
        if bucket not in self.existing:
            raise KeyError(bucket)
        try:
            return self._objects[(bucket, key)]
        except KeyError:
            raise KeyError(key) from None

    def delete(self, bucket: str, key: str) -> None:
        if bucket not in self.existing:
            raise KeyError(bucket)
        self._objects.pop((bucket, key), None)
        self._content_types.pop((bucket, key), None)
        self._metadata.pop((bucket, key), None)

    def list(self, bucket: str, prefix: str = "") -> list[str]:
        if bucket not in self.existing:
            raise KeyError(bucket)
        return sorted(key for (b, key) in self._objects if b == bucket and key.startswith(prefix))

    def presigned_get(self, bucket: str, key: str, expires_seconds: int = 3600) -> str:
        if bucket not in self.existing:
            raise KeyError(bucket)
        if (bucket, key) not in self._objects:
            raise KeyError(key)
        return (
            f"https://storage.example/{bucket}/{key}"
            f"?X-Amz-Expires={expires_seconds}&X-Amz-Signature=fake"
        )

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self.existing

    def ensure_buckets(self) -> None:
        self.existing.update(self.configured)


class _FakeObject:
    """Duck-typed ``minio.datatypes.Object`` (only ``object_name`` is used)."""

    def __init__(self, object_name: str) -> None:
        self.object_name = object_name


class _FakeResponse:
    """Duck-typed urllib3 response returned by ``get_object``."""

    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class FakeMinioClient:
    """Duck-typed MinIO client: in-memory objects, recording adapter calls."""

    def __init__(self, buckets: Iterable[str] | None = None) -> None:
        self._buckets = set(buckets) if buckets is not None else set()
        self._objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict[str, object]] = []
        self.presigned_calls: list[dict[str, object]] = []

    def bucket_exists(self, bucket: str) -> bool:
        return bucket in self._buckets

    def make_bucket(self, bucket: str, **_: object) -> None:
        self._buckets.add(bucket)

    def put_object(
        self,
        bucket: str,
        object_name: str,
        data: object,
        length: int,
        content_type: str = "application/octet-stream",
        metadata: Mapping[str, str] | None = None,
        **_: object,
    ) -> None:
        self._objects[(bucket, object_name)] = data.read()  # type: ignore[attr-defined]
        self.put_calls.append(
            {
                "bucket": bucket,
                "object_name": object_name,
                "length": length,
                "content_type": content_type,
                "metadata": metadata,
            }
        )

    def get_object(self, bucket: str, object_name: str, **_: object) -> _FakeResponse:
        return _FakeResponse(self._objects[(bucket, object_name)])

    def remove_object(self, bucket: str, object_name: str, **_: object) -> None:
        self._objects.pop((bucket, object_name), None)

    def list_objects(
        self, bucket: str, prefix: str | None = None, recursive: bool = False, **_: object
    ) -> Iterator[_FakeObject]:
        keys = sorted(
            key
            for (b, key) in self._objects
            if b == bucket and (prefix is None or key.startswith(prefix))
        )
        for key in keys:
            yield _FakeObject(key)

    def presigned_get_object(
        self,
        bucket: str,
        object_name: str,
        expires: timedelta | None = None,
        **_: object,
    ) -> str:
        self.presigned_calls.append(
            {"bucket": bucket, "object_name": object_name, "expires": expires}
        )
        return (
            f"https://storage.example/{bucket}/{object_name}"
            f"?X-Amz-Expires={expires.total_seconds()}&X-Amz-Signature=fake"
        )


# --- Port contract (in-memory implementation) ---------------------------------


def test_port_round_trip_preserves_bytes() -> None:
    store = MemoryObjectStorage()
    payload = b"\x00\x01\xff binary \x00 payload"
    store.put("source-pdfs", "documents/x/doc.pdf", payload, content_type="application/pdf")
    assert store.get("source-pdfs", "documents/x/doc.pdf") == payload
    assert store._content_types[("source-pdfs", "documents/x/doc.pdf")] == "application/pdf"


def test_port_get_missing_raises() -> None:
    store = MemoryObjectStorage()
    with pytest.raises(KeyError):
        store.get("source-pdfs", "documents/x/missing.pdf")


def test_port_delete_is_idempotent_and_removes() -> None:
    store = MemoryObjectStorage()
    store.put("source-pdfs", "documents/x/doc.pdf", b"data")
    store.delete("source-pdfs", "documents/x/doc.pdf")
    assert store.list("source-pdfs") == []
    store.delete("source-pdfs", "documents/x/doc.pdf")  # no raise


def test_port_list_filters_by_prefix() -> None:
    store = MemoryObjectStorage()
    for key in ("a/one.bin", "a/two.bin", "b/three.bin"):
        store.put("page-images", key, b"x")
    assert store.list("page-images") == ["a/one.bin", "a/two.bin", "b/three.bin"]
    assert store.list("page-images", prefix="a/") == ["a/one.bin", "a/two.bin"]
    assert store.list("page-images", prefix="a/two") == ["a/two.bin"]


def test_port_presigned_get_url_encodes_target_and_expiry() -> None:
    store = MemoryObjectStorage()
    store.put("review-artifacts", "review-1/evidence.json", b"{}")
    url = store.presigned_get("review-artifacts", "review-1/evidence.json", expires_seconds=900)
    assert "review-artifacts/review-1/evidence.json" in url
    assert "X-Amz-Expires=900" in url


def test_port_bucket_exists_and_ensure_buckets() -> None:
    store = MemoryObjectStorage(buckets=["source-pdfs", "parser-outputs"])
    store.existing.clear()
    assert not store.bucket_exists("source-pdfs")
    store.ensure_buckets()
    assert store.bucket_exists("source-pdfs")
    assert store.bucket_exists("parser-outputs")
    store.ensure_buckets()  # idempotent
    assert store.bucket_exists("parser-outputs")


def test_implementations_satisfy_port() -> None:
    assert isinstance(MemoryObjectStorage(), ObjectStoragePort)
    assert isinstance(S3ObjectStorage(), ObjectStoragePort)


# --- S3ObjectStorage adapter (duck-typed fake MinIO client) -------------------


def _adapter(client: FakeMinioClient, **kwargs: object) -> S3ObjectStorage:
    return S3ObjectStorage(client=client, **kwargs)


def test_adapter_put_streams_bytes_with_length_and_content_type() -> None:
    client = FakeMinioClient(buckets=BUCKETS)
    store = _adapter(client)
    payload = b"\x00\xff binary payload"
    store.put("source-pdfs", "documents/x/doc.pdf", payload, content_type="application/pdf")
    assert client._objects[("source-pdfs", "documents/x/doc.pdf")] == payload
    call = client.put_calls[-1]
    assert call["length"] == len(payload)
    assert call["content_type"] == "application/pdf"


def test_adapter_put_default_content_type_and_metadata() -> None:
    client = FakeMinioClient(buckets=BUCKETS)
    store = _adapter(client)
    store.put(
        "parser-outputs",
        "documents/x/parsed.json",
        b"{}",
        metadata={"parser": "docling-2.1.0"},
    )
    call = client.put_calls[-1]
    assert call["content_type"] == "application/octet-stream"
    assert call["metadata"] == {"parser": "docling-2.1.0"}


def test_adapter_get_reads_and_closes_response() -> None:
    client = FakeMinioClient(buckets=BUCKETS)
    store = _adapter(client)
    payload = b"\x00\x01\x02"
    store.put("page-images", "documents/x/page-001.png", payload)
    assert store.get("page-images", "documents/x/page-001.png") == payload


def test_adapter_delete_removes_object() -> None:
    client = FakeMinioClient(buckets=BUCKETS)
    store = _adapter(client)
    store.put("page-images", "documents/x/page-001.png", b"img")
    store.delete("page-images", "documents/x/page-001.png")
    assert store.list("page-images") == []


def test_adapter_list_uses_recursive_scan_with_prefix() -> None:
    client = FakeMinioClient(buckets=BUCKETS)
    store = _adapter(client)
    for key in ("documents/x/a.png", "documents/x/b.png", "other/c.png"):
        store.put("page-images", key, b"img")
    assert store.list("page-images", prefix="documents/x/") == [
        "documents/x/a.png",
        "documents/x/b.png",
    ]


def test_adapter_presigned_converts_seconds_to_timedelta() -> None:
    client = FakeMinioClient(buckets=BUCKETS)
    store = _adapter(client)
    store.put("review-artifacts", "review-1/evidence.json", b"{}")
    url = store.presigned_get("review-artifacts", "review-1/evidence.json", expires_seconds=900)
    assert client.presigned_calls[-1]["expires"] == timedelta(seconds=900)
    assert "X-Amz-Expires=900" in url


def test_adapter_ensure_buckets_creates_missing_idempotently() -> None:
    client = FakeMinioClient()  # starts with no buckets
    store = _adapter(client, buckets=BUCKETS)
    store.ensure_buckets()
    assert client._buckets == set(BUCKETS)
    store.ensure_buckets()
    assert client._buckets == set(BUCKETS)


def test_adapter_endpoint_scheme_is_stripped() -> None:
    for endpoint, use_ssl in (
        ("http://localhost:9000", False),
        ("https://minio.example.com:9000", True),
        ("localhost:9000", False),
    ):
        store = S3ObjectStorage(endpoint=endpoint, use_ssl=use_ssl)
        assert store._client._base_url.host == endpoint.split("//")[-1].rstrip("/")
        assert store._client._base_url.is_https is use_ssl


# --- Object-key conventions (doc 03 §3.12.2) ----------------------------------


def test_object_key_source_pdfs_content_addressed() -> None:
    digest = "a" * 64
    assert (
        object_key(
            "source-pdfs",
            document_id="documents/nd-168-2024",
            subpath="source",
            file_name="original.pdf",
            content_hash=digest,
        )
        == f"documents/nd-168-2024/source/{digest}.pdf"
    )


def test_object_key_parser_outputs_parser_version_subpath() -> None:
    assert (
        object_key(
            "parser-outputs",
            document_id="documents/nd-168-2024",
            subpath="docling-2.1.0",
            file_name="parsed.json",
        )
        == "documents/nd-168-2024/docling-2.1.0/parsed.json"
    )


def test_object_key_page_images_no_subpath() -> None:
    assert (
        object_key("page-images", document_id="documents/nd-168-2024", file_name="page-012.png")
        == "documents/nd-168-2024/page-012.png"
    )


def test_object_key_review_and_evaluation() -> None:
    assert (
        object_key("review-artifacts", document_id="review-42", file_name="evidence.json")
        == "review-42/evidence.json"
    )
    assert (
        object_key(
            "evaluation-artifacts",
            document_id="run-7",
            file_name="question-3.jsonl",
        )
        == "run-7/question-3.jsonl"
    )


def test_object_key_doc_examples() -> None:
    digest = "a" * 64
    source_key = object_key(
        "source-pdfs",
        document_id="documents/nd-168-2024",
        subpath="source",
        file_name="x.pdf",
        content_hash=digest,
    )
    expected_source = f"s3://source-pdfs/documents/nd-168-2024/source/{digest}.pdf"
    assert f"s3://source-pdfs/{source_key}" == expected_source
    parser_key = object_key(
        "parser-outputs",
        document_id="documents/nd-168-2024",
        subpath="docling-2.1.0",
        file_name="parsed.json",
    )
    assert f"s3://parser-outputs/{parser_key}" == (
        "s3://parser-outputs/documents/nd-168-2024/docling-2.1.0/parsed.json"
    )


def test_object_key_rejects_unknown_bucket() -> None:
    with pytest.raises(ValueError, match="unknown bucket"):
        object_key("not-a-bucket", document_id="x", file_name="y.pdf")


def test_object_key_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="file_name"):
        object_key("source-pdfs", document_id="x", file_name="../evil.pdf")
    with pytest.raises(ValueError, match="file_name"):
        object_key("source-pdfs", document_id="x", file_name="a/b.pdf")
    with pytest.raises(ValueError, match="file_name"):
        object_key("source-pdfs", document_id="x", file_name="..")
    with pytest.raises(ValueError, match="document_id"):
        object_key("source-pdfs", document_id="../etc", file_name="y.pdf")
    with pytest.raises(ValueError, match="subpath"):
        object_key("source-pdfs", document_id="x", subpath="a/../b", file_name="y.pdf")
    with pytest.raises(ValueError, match="content_hash"):
        object_key("source-pdfs", document_id="x", file_name="y.pdf", content_hash="  ")


def test_object_key_accepts_lowercase_hex_sha256() -> None:
    digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    assert (
        object_key("source-pdfs", document_id="x", file_name="doc.pdf", content_hash=digest)
        == f"x/{digest}.pdf"
    )


def test_object_key_rejects_invalid_content_hash() -> None:
    # Traversal/separator payloads must not reach the key.
    for bad in ("../../etc/passwd", "a/b", "..", ".", "a\\b", " ", "  a" * 32):
        with pytest.raises(ValueError, match="content_hash"):
            object_key("source-pdfs", document_id="x", file_name="y.pdf", content_hash=bad)
    # Wrong length.
    with pytest.raises(ValueError, match="content_hash"):
        object_key("source-pdfs", document_id="x", file_name="y.pdf", content_hash="abc")
    with pytest.raises(ValueError, match="content_hash"):
        object_key("source-pdfs", document_id="x", file_name="y.pdf", content_hash="a" * 63)
    # Not lowercase hex.
    with pytest.raises(ValueError, match="content_hash"):
        object_key("source-pdfs", document_id="x", file_name="y.pdf", content_hash="A" * 64)
    with pytest.raises(ValueError, match="content_hash"):
        object_key("source-pdfs", document_id="x", file_name="y.pdf", content_hash="g" * 64)


# --- Bucket constants vs doc / env / settings ---------------------------------


def test_buckets_constant_matches_doc_and_env() -> None:
    assert BUCKETS == DOC_BUCKETS
    assert frozenset(ObjectStorageSettings().buckets) == BUCKETS, (
        "default settings buckets must mirror BUCKETS"
    )


def test_object_key_accepts_every_canonical_bucket() -> None:
    for bucket in sorted(BUCKETS):
        assert object_key(bucket, document_id="x", file_name="f.bin").startswith("x/")


# --- Settings parsing ---------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_minio_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit settings tests must not see host or repo MINIO_* variables."""
    for key in list(
        {
            "MINIO_ENDPOINT",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
            "MINIO_ROOT_USER",
            "MINIO_ROOT_PASSWORD",
            "MINIO_ACCESS",
            "MINIO_SECRET",
            "MINIO_USE_SSL",
            "MINIO_BUCKETS",
        }
    ):
        monkeypatch.delenv(key, raising=False)


def test_settings_parses_minio_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_ROOT_USER", "root-user")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "root-pass")
    monkeypatch.setenv("MINIO_USE_SSL", "false")
    monkeypatch.setenv("MINIO_BUCKETS", "source-pdfs,parser-outputs")
    settings = ObjectStorageSettings()
    assert settings.endpoint == "minio:9000"
    assert settings.access_key == "root-user"
    assert settings.secret_key == "root-pass"
    assert settings.use_ssl is False
    assert settings.buckets == ["source-pdfs", "parser-outputs"]


def test_settings_accepts_sdk_key_spellings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_ACCESS_KEY", "sdk-user")
    monkeypatch.setenv("MINIO_SECRET_KEY", "sdk-pass")
    settings = ObjectStorageSettings()
    assert settings.access_key == "sdk-user"
    assert settings.secret_key == "sdk-pass"


def test_settings_accepts_repo_key_spellings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_ACCESS", "repo-user")
    monkeypatch.setenv("MINIO_SECRET", "repo-pass")
    settings = ObjectStorageSettings()
    assert settings.access_key == "repo-user"
    assert settings.secret_key == "repo-pass"


def test_settings_use_ssl_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINIO_USE_SSL", "true")
    assert ObjectStorageSettings().use_ssl is True


def test_settings_defaults_match_canonical_buckets() -> None:
    settings = ObjectStorageSettings()
    assert settings.endpoint == "localhost:9000"
    assert settings.use_ssl is False
    assert sorted(settings.buckets) == sorted(BUCKETS)


# --- Factory ------------------------------------------------------------------


def test_get_object_storage_uses_settings_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ObjectStorageSettings(endpoint="cache-test:9000", access_key="k", secret_key="s")
    monkeypatch.setattr(
        "app.storage.object_storage.get_object_storage_settings",
        lambda: settings,
    )
    get_object_storage.cache_clear()
    try:
        first = get_object_storage()
        second = get_object_storage()
        assert isinstance(first, S3ObjectStorage)
        assert first is second
        assert first._client._base_url.host == "cache-test:9000"
    finally:
        get_object_storage.cache_clear()


def test_get_object_storage_settings_is_cached() -> None:
    assert get_object_storage_settings() is get_object_storage_settings()
