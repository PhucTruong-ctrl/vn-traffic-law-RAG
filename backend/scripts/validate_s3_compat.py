"""VNLRAG-152 spike: validate live S3-compatible storage for ObjectStoragePort.

Usage (from backend/):

    uv run python -m scripts.validate_s3_compat [--endpoint ...] [--buckets ...]

Connects to a live S3-compatible endpoint (MinIO by default) and verifies the
ObjectStoragePort surface end to end (doc 04 §4.15, VNLRAG-134):

    bucket existence (the six buckets from MINIO_BUCKETS, doc 03 §3.12.1)
    PUT object         (minio put_object)
    GET round-trip     (minio get_object, byte-identical read-back)
    LIST objects       (minio list_objects sees the key)
    presigned GET URL  (presigned_get_object — GETting the URL serves the object)
    DELETE object      (minio remove_object, verified via stat_object -> NoSuchKey)

The probe uses a THROWAWAY object key ``_compat_check_<utc-timestamp>.bin`` in
the first bucket and removes it before exiting (best-effort ``finally``);
production objects are never touched.

Configuration comes from the environment, then the repository-root ``.env``
(doc 07 §7.3.3, same convention as alembic/env.py):

- endpoint: ``MINIO_ENDPOINT`` (default ``http://localhost:9000``); an explicit
  ``https://``/``http://`` scheme wins over ``MINIO_USE_SSL``;
- credentials: ``MINIO_ACCESS_KEY``/``MINIO_SECRET_KEY``, falling back to the
  Compose aliases ``MINIO_ROOT_USER``/``MINIO_ROOT_PASSWORD`` — NEVER printed;
- buckets: comma-separated ``MINIO_BUCKETS``.

Exit codes: 0 = every check PASS, 1 = one or more checks FAIL,
2 = endpoint unreachable (every check reported as [skip], matching the
VNLRAG-42 spike convention).
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import os
import sys
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import urllib3
from minio import Minio, S3Error
from urllib3.util import Timeout

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
ENV_FILE = REPO_ROOT / ".env"

#: The six buckets from doc 03 §3.12.1 / the repo .env MINIO_BUCKETS value.
DEFAULT_BUCKETS = (
    "source-pdfs,parser-outputs,page-images,ingestion-artifacts,"
    "review-artifacts,evaluation-artifacts"
)
#: Throwaway probe payload — these exact bytes must round-trip unchanged.
PROBE_PAYLOAD = (
    "vnlaw s3 compat probe (VNLRAG-152) — đối tượng put/get round-trip v1\n".encode() * 8
)
#: Fixed checks after the per-bucket existence checks (kept in run order).
OBJECT_CHECKS = [
    "PUT object",
    "GET object round-trip",
    "LIST objects",
    "presigned GET URL",
    "DELETE object",
]


def _load_repo_env() -> None:
    """Load KEY=VALUE lines from the repo-root .env, never overriding the env.

    Same line format as alembic/env.py (doc 07 §7.3.3): the repository-root
    .env is the last-resort source after the process environment.
    """
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip("'\"")


def _resolve_endpoint(override: str | None = None) -> tuple[str, bool]:
    """Return ``(host[:port], secure)`` from $MINIO_ENDPOINT / $MINIO_USE_SSL."""
    raw = (override or os.environ.get("MINIO_ENDPOINT") or "http://localhost:9000").strip()
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        return parsed.netloc or parsed.path, parsed.scheme.lower() == "https"
    use_ssl = os.environ.get("MINIO_USE_SSL", "").strip().lower()
    return raw, use_ssl in {"1", "true", "yes", "on"}


def _resolve_credentials() -> tuple[str | None, str | None]:
    """Return ``(access_key, secret_key)`` from the MINIO_* env/.env contract."""
    return (
        os.environ.get("MINIO_ACCESS_KEY") or os.environ.get("MINIO_ROOT_USER"),
        os.environ.get("MINIO_SECRET_KEY") or os.environ.get("MINIO_ROOT_PASSWORD"),
    )


def _resolve_buckets(override: str | None = None) -> list[str]:
    """Parse the comma-separated bucket list (doc 03 §3.12.1)."""
    source = override or os.environ.get("MINIO_BUCKETS") or DEFAULT_BUCKETS
    buckets = [bucket.strip() for bucket in source.split(",") if bucket.strip()]
    if not buckets:
        raise SystemExit("FAIL: no buckets configured (MINIO_BUCKETS is empty)")
    return buckets


def s3_reachable(client: Minio) -> bool:
    """True when the endpoint answers a trivial authenticated call."""
    try:
        client.list_buckets()
        return True
    except Exception:
        return False


def run_checks(client: Minio, buckets: list[str], key: str) -> int:
    """Run the ObjectStoragePort surface checks; return the number of failures."""
    total = len(buckets) + len(OBJECT_CHECKS)
    failures = 0
    payload = PROBE_PAYLOAD
    payload_sha = hashlib.sha256(payload).hexdigest()
    bucket = buckets[0]  # object-level checks run in the first bucket only

    idx = 0
    # Bucket existence — doc 03 §3.12.1, one PASS/FAIL line per bucket.
    for name in buckets:
        idx += 1
        try:
            exists = client.bucket_exists(name)
        except Exception as exc:
            failures += 1
            print(f"[{idx}/{total}] bucket exists {name}: FAIL ({exc})")
            continue
        if exists:
            print(f"[{idx}/{total}] bucket exists {name}: PASS")
        else:
            failures += 1
            print(f"[{idx}/{total}] bucket exists {name}: FAIL (bucket missing)")

    # PUT — minio put_object.
    idx += 1
    try:
        result = client.put_object(
            bucket,
            key,
            io.BytesIO(payload),
            len(payload),
            content_type="application/octet-stream",
        )
    except Exception as exc:
        failures += 1
        print(f"[{idx}/{total}] {OBJECT_CHECKS[0]} ({bucket}/{key}): FAIL ({exc})")
    else:
        etag = getattr(result, "etag", None) or ""
        print(f"[{idx}/{total}] {OBJECT_CHECKS[0]} ({bucket}/{key}): PASS (etag {etag})")

    # GET — get_object round-trip must return the exact probe bytes.
    idx += 1
    try:
        response = client.get_object(bucket, key)
        try:
            body = response.read()
        finally:
            response.close()
    except Exception as exc:
        failures += 1
        print(f"[{idx}/{total}] {OBJECT_CHECKS[1]}: FAIL ({exc})")
    else:
        if body == payload:
            print(
                f"[{idx}/{total}] {OBJECT_CHECKS[1]}: PASS "
                f"({len(body)} bytes, sha256 {payload_sha})"
            )
        else:
            failures += 1
            print(
                f"[{idx}/{total}] {OBJECT_CHECKS[1]}: FAIL "
                f"(content mismatch: got {len(body)} bytes)"
            )

    # LIST — list_objects with the key as prefix must include the key.
    idx += 1
    try:
        found = any(
            item.object_name == key
            for item in client.list_objects(bucket, prefix=key, recursive=True)
        )
    except Exception as exc:
        failures += 1
        print(f"[{idx}/{total}] {OBJECT_CHECKS[2]}: FAIL ({exc})")
    else:
        if found:
            print(f"[{idx}/{total}] {OBJECT_CHECKS[2]} (prefix {key!r}): PASS")
        else:
            failures += 1
            print(f"[{idx}/{total}] {OBJECT_CHECKS[2]} (prefix {key!r}): FAIL (key not listed)")

    # Presigned GET — GETting the signed URL must serve the object bytes.
    idx += 1
    try:
        url = client.presigned_get_object(bucket, key)
        with urllib.request.urlopen(url, timeout=15) as response:
            body = response.read()
    except Exception as exc:
        failures += 1
        print(f"[{idx}/{total}] {OBJECT_CHECKS[3]}: FAIL ({exc})")
    else:
        if body == payload:
            print(f"[{idx}/{total}] {OBJECT_CHECKS[3]}: PASS (signed URL served the object)")
        else:
            failures += 1
            print(f"[{idx}/{total}] {OBJECT_CHECKS[3]}: FAIL (content mismatch)")

    # DELETE — remove_object, then stat_object must raise NoSuchKey.
    idx += 1
    try:
        client.remove_object(bucket, key)
        client.stat_object(bucket, key)
    except S3Error as exc:
        if exc.code == "NoSuchKey":
            print(f"[{idx}/{total}] {OBJECT_CHECKS[4]}: PASS (stat -> NoSuchKey)")
        else:
            failures += 1
            print(f"[{idx}/{total}] {OBJECT_CHECKS[4]}: FAIL ({exc})")
    except Exception as exc:
        failures += 1
        print(f"[{idx}/{total}] {OBJECT_CHECKS[4]}: FAIL ({exc})")
    else:
        failures += 1
        print(f"[{idx}/{total}] {OBJECT_CHECKS[4]}: FAIL (object still present after remove)")

    return failures


def _print_skip(buckets: list[str]) -> None:
    """Report every check as [skip] (endpoint unreachable)."""
    total = len(buckets) + len(OBJECT_CHECKS)
    idx = 0
    for name in buckets:
        idx += 1
        print(f"[{idx}/{total}] bucket exists {name}: [skip]")
    for name in OBJECT_CHECKS:
        idx += 1
        print(f"[{idx}/{total}] {name}: [skip]")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VNLRAG-152 spike: validate live S3-compatible storage for the "
            "ObjectStoragePort surface (PUT/GET/DELETE/LIST/presigned GET + buckets)."
        )
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="S3 endpoint (default: $MINIO_ENDPOINT or http://localhost:9000)",
    )
    parser.add_argument(
        "--buckets",
        default=None,
        help=(
            "comma-separated bucket names (default: $MINIO_BUCKETS or the six from doc 03 §3.12.1)"
        ),
    )
    args = parser.parse_args(argv)

    _load_repo_env()
    endpoint, secure = _resolve_endpoint(args.endpoint)
    access_key, secret_key = _resolve_credentials()
    buckets = _resolve_buckets(args.buckets)

    if not access_key or not secret_key:
        print(
            "FAIL: credentials missing — set MINIO_ACCESS_KEY/MINIO_SECRET_KEY "
            "(or the Compose aliases MINIO_ROOT_USER/MINIO_ROOT_PASSWORD) in the "
            "environment or the repository-root .env",
            file=sys.stderr,
        )
        return 1

    http_client = urllib3.PoolManager(timeout=Timeout(connect=5, read=15), maxsize=10)
    client = Minio(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        secure=secure,
        http_client=http_client,
    )

    total = len(buckets) + len(OBJECT_CHECKS)
    key = f"_compat_check_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.bin"
    print(f"endpoint: {endpoint} (secure={secure})")
    print("credentials: resolved from MINIO_* env/.env (never printed)")
    print(f"buckets ({len(buckets)}): {', '.join(buckets)}")
    print(f"object key: {key} (throwaway — removed before exit)")
    probe_sha = hashlib.sha256(PROBE_PAYLOAD).hexdigest()
    print(f"probe payload: {len(PROBE_PAYLOAD)} bytes, sha256 {probe_sha}")
    print()

    if not s3_reachable(client):
        _print_skip(buckets)
        print()
        print("RESULT: SKIP — endpoint unreachable, no check ran", file=sys.stderr)
        return 2

    try:
        failures = run_checks(client, buckets, key)
    finally:
        # Best-effort cleanup: the DELETE check already removes the key, so an
        # exception here is expected after a failed DELETE and ignored.
        with contextlib.suppress(Exception):
            client.remove_object(buckets[0], key)

    passed = total - failures
    print()
    if failures == 0:
        print(f"RESULT: PASS ({passed}/{total})")
        return 0
    print(f"RESULT: FAIL ({passed}/{total})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
