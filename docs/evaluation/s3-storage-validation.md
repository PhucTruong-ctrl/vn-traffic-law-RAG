# S3-Compatible Object Storage — Validation Spike (VNLRAG-152)

Spike that validates the live MinIO endpoint against the `ObjectStoragePort`
surface designed in doc 04 §4.15 (S3-compatible implementation behind the
abstraction; buckets and key conventions in doc 03 §3.12). The deliverable is
the compat script `backend/scripts/validate_s3_compat.py` and this record of
what the pinned MinIO release actually does over the S3 API, plus the
implementation comparison that ADR-021 summarizes.

## 1. Run context

- **Ticket**: VNLRAG-152 — Validate S3-Compatible Object Storage + record ADR
- **Image tested**: `minio/minio:RELEASE.2025-09-07T16-13-09Z` (date-tagged
  community release, pinned in `docker-compose.yml`; both services
  `vnlaw-minio` and `extraction-core-minio` run this tag — verified via
  `docker ps` on 2026-08-14)
- **Endpoint**: `http://localhost:9000` (service `vnlaw-minio`, healthy);
  `secure=False` (local, plain HTTP)
- **Client**: `minio 7.2.20` from the backend venv (pyproject `minio>=7`),
  Python 3.11.9 (uv-managed, pyproject `requires-python >=3.11,<3.12`)
- **Run command** (from `backend/`):
  `uv run python -m scripts.validate_s3_compat --endpoint http://localhost:9000`
- **Result**: `RESULT: PASS (11/11)`, exit 0
- **Config source**: credentials resolved from the repository-root `.env`
  (`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY`, with Compose aliases
  `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` as fallback; doc 07 §7.3.3
  convention, same loader shape as `alembic/env.py`); buckets from
  `MINIO_BUCKETS` (the six buckets of doc 03 §3.12.1). Credentials are never
  printed by the script.
- **Isolation**: the probe used a THROWAWAY object key
  `_compat_check_<utc-timestamp>.bin` in the first bucket
  (`source-pdfs`); the object is removed on exit (verified: zero
  `_compat_check_*` objects remain after the run). Production objects were
  never touched.

## 2. Compat results — verbatim script output

```
endpoint: localhost:9000 (secure=False)
credentials: resolved from MINIO_* env/.env (never printed)
buckets (6): source-pdfs, parser-outputs, page-images, ingestion-artifacts, review-artifacts, evaluation-artifacts
object key: _compat_check_20260813T193839Z.bin (throwaway — removed before exit)
probe payload: 616 bytes, sha256 151e018556ba8f1b04396d4d4630d1d928ea981861f413bcb342a701c4b46025

[1/11] bucket exists source-pdfs: PASS
[2/11] bucket exists parser-outputs: PASS
[3/11] bucket exists page-images: PASS
[4/11] bucket exists ingestion-artifacts: PASS
[5/11] bucket exists review-artifacts: PASS
[6/11] bucket exists evaluation-artifacts: PASS
[7/11] PUT object (source-pdfs/_compat_check_20260813T193839Z.bin): PASS (etag 91335a3df7333d8d5ac83a1c5482f153)
[8/11] GET object round-trip: PASS (616 bytes, sha256 151e018556ba8f1b04396d4d4630d1d928ea981861f413bcb342a701c4b46025)
[9/11] LIST objects (prefix '_compat_check_20260813T193839Z.bin'): PASS
[10/11] presigned GET URL: PASS (signed URL served the object)
[11/11] DELETE object: PASS (stat -> NoSuchKey)

RESULT: PASS (11/11)
EXIT=0
```

Unreachable-endpoint behavior (guarded like the PG integration fixtures in
`tests/integration/conftest.py`): every check is reported as `[skip]` and the
script exits 2 (matching the VNLRAG-42 spike convention) — verified against a
dead port (`RESULT: SKIP — endpoint unreachable, no check ran`).

## 3. ObjectStoragePort surface coverage

| Port operation (VNLRAG-134) | S3 API | minio client call | Result |
|---|---|---|---|
| bucket_exists | HeadBucket | `bucket_exists` × 6 buckets | PASS (6/6) |
| put_object | PutObject | `put_object` | PASS (etag returned) |
| get_object | GetObject | `get_object` read-back | PASS (byte-identical, sha256 match) |
| list_objects | ListObjectsV2 | `list_objects(prefix=key, recursive=True)` | PASS (key listed) |
| presigned_get | presigned GetObject URL | `presigned_get_object` + HTTP GET | PASS (URL served the object) |
| remove_object | DeleteObject | `remove_object` + `stat_object` → `NoSuchKey` | PASS (deletion verified) |

The byte-identical GET round-trip and presigned-GET checks used a 616-byte
UTF-8 payload containing Vietnamese text (`đối tượng`), so byte fidelity for
non-ASCII content is covered. `stat_object` after delete confirms the object
is actually gone (not just marked).

## 4. Maintenance-path notes

- `minio/minio` was archived / made read-only on 2026-04-25 (issue
  minio/minio#21584, per doc 04 §4.15.2): the Community Edition is a
  **source-only** build with reduced maintenance compared to the actively
  developed period.
- This does not mean MinIO stops working — the pinned
  `RELEASE.2025-09-07T16-13-09Z` image is a stable, self-contained server
  binary — but it means a 2026 system design should treat "MinIO = selected"
  as a frozen decision, not an open one: pin an exact tested date-tagged tag
  and keep the swap path exercised (see §6–§7).
- Docs currently brand MinIO as "MinIO AIStor"; the community image used here
  is the plain `minio/minio` S3 server image.

## 5. Alternatives considered (implementation comparison)

Requirements context: stable Docker image availability, license compatible
with a graduation thesis project, the bucket/versioning/ILM/WORM features
listed in doc 04 §4.15.3, RAM budget on a 19 GB machine, and 2026 maintenance
reliability. Managed S3 is out of scope (local thesis deployment, doc 04
§4.15.1).

| Implementation | License | Maturity / maintenance (2026) | S3 compatibility | Fit for this project |
|---|---|---|---|---|
| **MinIO** (candidate) | GNU AGPLv3 (community, source-only) | Repo archived 2026-04-25, read-only; reduced but ongoing community release cadence | Full S3 API incl. versioning, ILM, WORM Object Lock; presigned URLs | Best fit today: already integrated (compose, buckets, `minio>=7` client), validated 11/11. AGPL acceptable for an unmodified standalone server. |
| **SeaweedFS** | Apache-2.0 (permissive) | Actively maintained, single-binary, low RAM | Broad S3 API (multipart, versioning, object lock, tags, presigned); some ops stubbed (replication, notifications) | Strong fallback on licensing grounds; different ops model (Filer + volume servers), would need a fresh integration + validation pass. |
| **Garage** | AGPLv3 | Actively maintained (Deuxfleurs), lightweight, small self-hosted geo-distributed clusters | S3 subset deliberately smaller — ACLs/policies not implemented; fine for basic put/get/list | Viable for basic object ops but feature gap (ACL/policy, WORM coverage) vs the doc 04 §4.15.3 feature list; not a drop-in. |
| **Ceph RGW** | Mostly LGPL-2.1/LGPL-3.0 (mixed tree) | Very mature, enterprise-grade | Broadest S3 feature set of the four | Overkill: requires MON/OSD/MGR daemons, high RAM, complex ops — poor fit for the 19 GB single-machine thesis deployment. |

S3-compatibility ranking (per provider docs): Ceph RGW > SeaweedFS ≈
MinIO > Garage. For THIS project the decisive axes are: already-integrated
compose/buckets/client, verified surface, and a lightweight single-service
footprint — all favor MinIO as the current candidate; SeaweedFS is the
documented fallback if the AGPL/copyleft or archive status ever becomes a
blocker.

## 6. Recommendation

**Adopt MinIO as the current S3-compatible implementation candidate for
`ObjectStoragePort` — explicitly NOT a permanent/irreversible choice**
(recorded in ADR-021). Basis:

- the full `ObjectStoragePort` surface validates green (11/11) against the
  pinned date-tagged image (this spike);
- the abstraction (`ObjectStoragePort` behind `S3ObjectStorage`) keeps the
  implementation config-level swappable (doc 04 §4.15.1);
- the swap path is a documented, cheap operation: swap the config, run
  `validate_s3_compat.py` against the new endpoint, re-run the storage tests.

## 7. Operational notes

- **Date-tagged image pinning**: production compose MUST pin an exact
  date-tagged release (currently
  `minio/minio:RELEASE.2025-09-07T16-13-09Z`); floating tags (`latest`,
  `alpine`, `main`) are prohibited (doc 07 §7.3.3 convention). Upgrades are
  deliberate: bump the tag, run this compat script, then promote.
- **Re-validation gate**: any image bump or endpoint change re-runs
  `backend/scripts/validate_s3_compat.py` before promotion (this script is the
  VNLRAG-134 test suite's live-endpoint twin).
- **Backup = replication, not tiering**: tiering/ILM/transition only moves
  data between tiers inside the same system and is NOT a backup; backup is
  server-side replication (async) or `mc mirror`/`mc cp` to an independent
  store (doc 03 §3.12.3, doc 04 §4.15.4).
- **Feature usage** (doc 04 §4.15.3): versioning, tagging, ILM expiry,
  WORM Object Locking (requires versioning, enabled at bucket creation via
  `mc mb --with-lock`) — all available on the pinned image; PostgreSQL remains
  the source of truth for object keys and metadata.
