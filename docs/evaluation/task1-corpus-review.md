# Task 1 — Corpus review and ingest evidence

Generated: 2026-09-05T17:13:19.246718+00:00

## Scope

- 27 manifest files discovered.
- 13 `PENDING` manifests reviewed: batch-04 (4), batch-05 (5), batch-06 (4).
- Official PDFs downloaded from the manifest URLs into `/tmp/vnlrag-task1-pdfs` (outside Git).
- Reviewer decision policy: only ACCEPTED when PDF hash and provision-level legal evidence are present; otherwise PENDING.

## Manifest evidence

| Document | Review | SHA-256 | Local bytes | Relation evidence |
|---|---|---|---:|---|
| `luat-36-2024-qh15` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `nd-100-2019` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `nd-168-2024` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `tt-24-2023` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `tt-79-2024` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `luat-35-2024-qh15` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `tt-35-2024` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `vbhn-49-2026-vpqh` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `vbhn-55-2026-vpqh` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `nd-151-2024` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `nd-236-2026` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `nd-238-2026` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `tt-37-2026` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `tt-51-2025` | `ACCEPTED` | MISMATCH/MISSING | - | No usable text-layer clause evidence |
| `nd-119-2024` | `PENDING` | MATCH | 1267313 | No usable text-layer clause evidence |
| `nd-44-2024` | `PENDING` | MATCH | 3890765 | No usable text-layer clause evidence |
| `tt-16-2024` | `PENDING` | MATCH | 3797088 | `18` phủ sửa đổi, bổ sung một số điều của Nghị định số 32/2014/NĐ-CP ngày 22 tháng; `66` Điều 4. Hiệu lực thi hành; `67` 1. Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 6 năm 2024. |
| `tt-39-2024` | `PENDING` | MATCH | 3008931 | `724` Điều 32. Hiệu lực thi hành; `726` 2. Bãi bỏ các Thông tư sau:; `733` của Bộ trưởng Bộ Giao thông vận tải sửa đổi, bổ sung một số điều của các |
| `nd-158-2024` | `PENDING` | MATCH | 78428744 | No usable text-layer clause evidence |
| `nd-67-2023` | `PENDING` | MATCH | 5537367 | No usable text-layer clause evidence |
| `tt-05-2024` | `PENDING` | MATCH | 5535863 | No usable text-layer clause evidence |
| `tt-18-2024` | `PENDING` | MATCH | 1765285 | `8` Sửa đổi, bổ sung một số điều của Thông tư số 12/2020/TT-BGTVT; `19` Chính phủ sửa đổi, bổ sung một số điều Nghị định số 10/2020/NĐ-CP ngày 17; `23` Chính phủ sửa đổi, bổ sung một số điều của các Nghị định liên quan đến quản |
| `tt-51-2024` | `PENDING` | MATCH | 566925 | `21` 1. Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2025.; `22` 2. Thông tư này thay thế Thông tư số 54/2019/TT-BGTVT ngày 31 tháng |
| `nd-160-2024` | `PENDING` | MATCH | 29809288 | No usable text-layer clause evidence |
| `nd-161-2024` | `PENDING` | MATCH | 87401205 | No usable text-layer clause evidence |
| `nd-165-2024` | `PENDING` | MATCH | 35085617 | No usable text-layer clause evidence |
| `nd-166-2024` | `PENDING` | MATCH | 1502071 | No usable text-layer clause evidence |

## Confirmed clause evidence

- `tt-16-2024`: Điều 4 khoản 2 makes Thông tư 01/2023/TT-BGTVT cease to have effect; Điều 4 khoản 1 sets 01/06/2024.
- `tt-18-2024`: Điều 1 modifies Thông tư 12/2020/TT-BGTVT and Thông tư 05/2023/TT-BGTVT; Điều 2 khoản 2–4 changes/removes specified provisions; Điều 3 khoản 1 sets 15/07/2024.
- `tt-39-2024`: Điều 32 khoản 2 điểm a–d lists repealed instruments/provisions; Điều 32 khoản 1 sets 01/01/2025.
- `tt-51-2024`: Điều 2 khoản 2 replaces Thông tư 54/2019/TT-BGTVT.

## Validation and ingest blockers

- All 13 downloaded PDF hashes match the corresponding manifest `file_hash`.
- The existing manifest validator accepts PENDING without review metadata and requires review metadata for ACCEPTED/REJECTED; all 27 manifests validate after review metadata was added.
- Corpus QA ran successfully but loaded 0 provision outputs: no real extraction/provision artifacts exist under the supported data paths.
- No manifest-to-PDF ingestion command exists. The runtime pipeline accepts PDFs through object storage/upload API and then requires PostgreSQL, Redis, MinIO, Qdrant, parser adapters, temporal/reference resolution and (for indexing) configured embedding provider.
- Compose service verification: MinIO and Qdrant became healthy; PostgreSQL exits because the hardened read-only compose configuration cannot chmod/create its data directories; Redis exits because append-only persistence is denied under the read-only configuration. A delegated fix review made no change because `docker-compose.yml` contains pre-existing uncommitted user changes.

## Final corpus state

- Final manifest metadata hash: `sha256:593439506264d45dbbddd2cdac327e9ec4b6d0f14d7f6d91cca6849c2b55dbe2`.
- PostgreSQL counts after migration and smoke: `legal_documents=0`, `document_versions=0`, `parsed_documents=0`, `document_elements=0`, `legal_provisions=0`, `document_relations=0`, `ingestion_runs=0`.
- Qdrant health endpoint responds successfully; collection list is empty.
- The 13 official PDFs are present in local MinIO under `source-pdfs/task1/`, but the worker smoke did not persist ingestion rows.

## Runtime result

- Local runtime was reset as explicitly authorized. PostgreSQL, Redis, Qdrant and MinIO all report healthy.
- Database migrations completed through Alembic head `0003`.
- All 13 PDFs were uploaded to MinIO `source-pdfs/task1/<document>.pdf`.
- Twelve ingestion jobs were submitted through the real Dramatiq queue; no documents, parsed documents, provisions, or Qdrant points were persisted before the worker run ended.
- Therefore no ingest/index completion is claimed.

## Current decisions

- All 13 previously pending manifests were changed to `ACCEPTED` under explicit user authorization at 2026-09-05T17:29:51Z using reviewer identity `Phuc Truong <phuctruong@student>`; README candidate relations were accepted per that authorization.
- Delegated review confirmed the existing validator already conditionally requires review metadata only for ACCEPTED/REJECTED; focused schema tests report 38 passed.
- README candidate relations were accepted as review metadata by explicit user instruction; no structured relation rows were inserted because the manifest schema has no relation array and database ingestion was not completed.
- Ingest/index count report remains unavailable: services are healthy and migrations are complete, but no provision extraction output was persisted and Qdrant has zero collections.
