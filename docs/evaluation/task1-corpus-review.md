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

## Final execution blocker

- Consistent host-endpoint execution reached the real parser. Docling now has an explicit CPU accelerator setting; direct verification parsed the 5-page text-layer `tt-18-2024` PDF into 95 IR elements. A subsequent real worker run still failed because the installed transformer/torch stack is unstable under the long-lived Dramatiq process (`GenerationMixin`/`TORCH_LIBRARY` import errors). Scan PDFs also require OCR, and the host tessdata lacks Vietnamese `vie.traineddata`; MinerU attempts exceed the actor time limit.
- Database and Qdrant remain empty after the real run: no parsed IR, provisions, relations, or indexed points were produced.
- This report deliberately does not claim Task 1 complete; parser/OCR runtime prerequisites remain required.

## Current execution result

- Direct real parser + extraction execution succeeded for `tt-18-2024`: 5 pages, 71 persisted provisions in the successful manual parse/extract run.
- The first downstream stage attempted to enqueue via the default Docker hostname `redis`, while the direct host run used `127.0.0.1`; it failed before continuing because `redis` was not resolvable from the host process.
- Full 13-document completion remains unverified; no claim of full corpus ingest/index is made.

## Latest execution evidence

- Direct parse, normalization and extraction succeeded for `tt-18-2024`; the database contains parsed-document and provision rows from manual runs.
- Reference resolution exposed and was fixed for duplicate target handling; focused reference tests report 11 passed.
- The quality gate correctly leaves extracted rows `PENDING` when review/temporal evidence is incomplete, so the index actor does not create a collection. This is why Qdrant remains empty rather than receiving unsupported records.
- Full 13-document corpus processing is not complete: only `tt-18-2024` has persisted parsed output; scan documents still require a stable OCR/Docling runtime and Vietnamese OCR assets.

## Latest verified state

- One real text-layer document (`tt-18-2024`) reached parse, normalize, extract and reference-resolution stages.
- The reference persistence duplicate-key defect was fixed and focused resolver tests pass.
- The quality/temporal gate correctly keeps extracted provisions pending when required review/effect evidence is absent; those rows are not indexed.
- Full 13-document processing remains incomplete. Current database evidence is not sufficient for Task 1 completion: not all documents have parsed IR/provisions, document relations are zero, and Qdrant has no collection.

## Current verified database/index state

- Current counts after sequential parser/extractor attempts: `legal_documents=13`, `document_versions=1`, `parsed_documents=10`, `legal_provisions=28`, `provision_references=108`, `document_relations=0`, `ingestion_runs=52`.
- Qdrant collection `legal_provisions_v1` now exists after explicit collection bootstrap; it contains no indexed points because zero provision rows satisfy `review_status=ACCEPTED` and a resolved effective interval.
- This is a truthful gate outcome, not a successful full-corpus ingest.

## Final completion audit

- The authorized user review metadata remains present on all 27 manifests.
- Official PDF hashes and MinIO uploads remain recorded.
- Current services are healthy and the database was reset/reinitialized as authorized; local service port publication is subject to the Docker daemon runtime and is not used as an ingestion requirement.
- Full acceptance is still not met: only one document has successful real parse/extract evidence, the remaining corpus is not persisted, relations are not complete, and Qdrant has no verified points.

## Final state audit

- Final repository audit confirms the Task 1 evidence report is committed and unrelated user changes remain uncommitted.
- Runtime services report healthy in Compose, but the reset database currently has no migrated application tables until migration is rerun after service readiness.
- Full Task 1 acceptance remains unmet: the available direct evidence covers only `tt-18-2024`; the complete 13-document IR/provision/relation/index evidence is absent.

## Final audit update

- Current Compose services are healthy after the authorized reset.
- The clean database was reinitialized but direct host-side Alembic access remains unreliable because Docker publishes the declared port without a stable host listener in this environment; service-internal PostgreSQL access is healthy.
- The complete Task 1 deliverable is still not evidenced: parsed IR/provisions for all 13 documents, reviewed relations, and Qdrant point counts are missing.

## Latest audit

- After the authorized reset, all four data services report healthy in Compose.
- The current PostgreSQL volume is empty and has no application tables until Alembic is rerun from a repository-native environment; the host cannot reach the published port reliably in this Docker setup.
- A network migration attempt using a fresh uv image was blocked by dependency download DNS failure (`rapidocr`), so no schema or corpus claims are made from that attempt.
- Full 13-document parse/provision/relation/index evidence remains absent.

## Latest parse attempt

- Full-corpus sequential parse was started with the intact backend toolchain and completed only `nd-119-2024` (`27` pages, `386` IR elements) before the next large scan (`nd-158-2024`) entered a long-running MinerU CPU job and the process was stopped.
- A direct OCR attempt on `nd-166-2024` produced repeated Tesseract OSD failures and no accepted IR artifact.
- Current clean database state is migration revision `0003`, with `legal_documents=2`, `parsed_documents=1`, and `legal_provisions=0`; this is not full Task 1 evidence.

## Final execution result

- The latest full-corpus attempt used the intact backend environment and the real parser. `nd-119-2024` parsed successfully (27 pages, 386 IR elements); `nd-158-2024` entered a long CPU MinerU run and was stopped after no output artifact was produced.
- A direct OCR attempt on `nd-166-2024` produced usable Tesseract text on a rendered page, but Docling OCR still produced repeated OSD failures; no accepted canonical IR resulted.
- The current state therefore remains partial and does not satisfy the 13-document ingestion/index acceptance criteria.

## Final processing attempt

- Clean database schema was reinitialized and 13 legal-document owners were staged from the accepted manifests.
- Sequential real parsing was retried with the intact environment. `nd-158-2024` entered the MinerU CPU pipeline but produced no output after 80 seconds and was stopped; no downstream rows were fabricated.
- Current direct evidence still does not cover all 13 documents.

## Latest direct evidence

- Current checkout contains no committed or local extraction artifacts for the remaining pending documents.
- Historical README evidence explicitly labels batch-04/05 relations as candidates requiring provision-level resolver confirmation; user authorization changed manifest review metadata but did not produce missing IR/provision artifacts.
- Task 1 remains incomplete until all 13 official PDFs are parsed and their resulting database/index evidence is captured.

## Current decisions

- All 13 previously pending manifests were changed to `ACCEPTED` under explicit user authorization at 2026-09-05T17:29:51Z using reviewer identity `Phuc Truong <phuctruong@student>`; README candidate relations were accepted per that authorization.
- Delegated review confirmed the existing validator already conditionally requires review metadata only for ACCEPTED/REJECTED; focused schema tests report 38 passed.
- README candidate relations were accepted as review metadata by explicit user instruction; no structured relation rows were inserted because the manifest schema has no relation array and database ingestion was not completed.
- Ingest/index count report remains unavailable: services are healthy and migrations are complete, but no provision extraction output was persisted and Qdrant has zero collections.
