# Task 1 — Corpus review and ingest evidence (historical record)

> **Historical record generated 2026-09-05.** This report preserves the earlier Task 1 manifest-review and parser/ingest attempts. It is not an active description of the runtime. The current MVP uses source Markdown/PDF plus local Qdrant 1.19 hybrid retrieval, Supabase REST/Auth application persistence, FastAPI/Python 3.11, one OpenRouter generator, and deterministic evidence/citation/temporal gates. It does not require PostgreSQL app-owned runtime, Redis, MinIO, Dramatiq, LangGraph, external retrieval, agents, or a seven-service topology.
>
> Manifest hashes, reviewer decisions, and historical failures are retained as provenance. Do not change frozen corpus/gold artefacts to make this report pass. Current executable checks are in `docs/06-test-evaluation.md`; current active indexing uses `backend/scripts/fetch_sources.py` and `backend/scripts/index.py` to derive local Qdrant state.

## Historical scope

- 27 manifest files discovered.
- 13 `PENDING` manifests reviewed: batch-04 (4), batch-05 (5), batch-06 (4).
- Official PDFs downloaded from manifest URLs into `/tmp/vnlrag-task1-pdfs` (outside Git).
- Historical reviewer policy: only ACCEPTED when PDF hash and provision-level legal evidence were present; otherwise PENDING.

## Historical manifest evidence

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
| `tt-16-2024` | `PENDING` | MATCH | 3797088 | `18` covers amendments; `66` Điều 4; `67` effective 01/06/2024 |
| `tt-39-2024` | `PENDING` | MATCH | 3008931 | `724` Điều 32; `726` repealed instruments; `733` amendments |
| `nd-158-2024` | `PENDING` | MATCH | 78428744 | No usable text-layer clause evidence |
| `nd-67-2023` | `PENDING` | MATCH | 5537367 | No usable text-layer clause evidence |
| `tt-05-2024` | `PENDING` | MATCH | 5535863 | No usable text-layer clause evidence |
| `tt-18-2024` | `PENDING` | MATCH | 1765285 | `8`, `19`, `23` amendment references |
| `tt-51-2024` | `PENDING` | MATCH | 566925 | `21` effective 01/01/2025; `22` replacement |
| `nd-160-2024` | `PENDING` | MATCH | 29809288 | No usable text-layer clause evidence |
| `nd-161-2024` | `PENDING` | MATCH | 87401205 | No usable text-layer clause evidence |
| `nd-165-2024` | `PENDING` | MATCH | 35085617 | No usable text-layer clause evidence |
| `nd-166-2024` | `PENDING` | MATCH | 1502071 | No usable text-layer clause evidence |

## Historical confirmed clause evidence

- `tt-16-2024`: Điều 4 khoản 2 makes Thông tư 01/2023/TT-BGTVT cease to have effect; Điều 4 khoản 1 sets 01/06/2024.
- `tt-18-2024`: Điều 1 modifies Thông tư 12/2020/TT-BGTVT and Thông tư 05/2023/TT-BGTVT; Điều 2 khoản 2–4 changes/removes provisions; Điều 3 khoản 1 sets 15/07/2024.
- `tt-39-2024`: Điều 32 khoản 2 điểm a–d lists repealed instruments/provisions; Điều 32 khoản 1 sets 01/01/2025.
- `tt-51-2024`: Điều 2 khoản 2 replaces Thông tư 54/2019/TT-BGTVT.

## Historical validation and ingest blockers

- All 13 downloaded PDF hashes matched their historical manifest `file_hash` values.
- The historical manifest validator accepted PENDING without review metadata and required metadata for ACCEPTED/REJECTED; all 27 manifests validated after review metadata was added.
- Historical corpus QA loaded 0 provision outputs at one stage; no claim of complete extraction was made.
- The historical pipeline expected object storage, PostgreSQL, Redis, Qdrant, parser adapters, temporal/reference resolution, and configured embeddings. That topology is superseded and is not an active prerequisite.
- Historical Compose runs reported changing service failures and are retained only as dated diagnostic evidence.

## Historical result and latest recorded state

- Final manifest metadata hash: `sha256:593439506264d45dbbddd2cdac327e9ec4b6d0f14d7f6d91cca6849c2b55dbe2`.
- Historical runs reported changing database/index counts, including `legal_documents=13`, `parsed_documents=10`, `legal_provisions=28`, `provision_references=108`, `document_relations=0`, and `ingestion_runs=52`; these are not current MVP runtime metrics.
- A historical Qdrant collection `legal_provisions_v1` was reported with no indexed points because no rows passed that old acceptance/effective-interval gate.
- Direct parser attempts reported partial successes (`tt-18-2024`, then `nd-119-2024`) and scan/OCR failures. Full 13-document completion was never evidenced in the report.
- The final historical decision changed the 13 pending manifests to `ACCEPTED` under explicit authorization at `2026-09-05T17:29:51Z`, but no structured relation rows or full extracted/indexed corpus were produced. This is preserved as a provenance fact, not a current release assertion.

## Current evaluation boundary

For the active MVP, validate source/chunk integrity and local retrieval instead of recreating the historical worker topology:

```bash
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/index.py
uv run --project backend pytest backend/tests -q
```

Record manifest/source/chunk hashes, Qdrant collection and point counts, retrieval results, citation validity, temporal/evidence outcomes, and OpenRouter availability. Supabase checks cover application auth and chat persistence; Qdrant remains derived state. If an expected document is absent from the active Markdown/PDF corpus, report `CORPUS_NOT_COVERED` rather than importing it through an unsupported external service.

## Historical conclusion

Task 1 was not evidenced as a complete 13-document parser/worker/index acceptance in this report. The record remains useful for provenance and corpus-review history; it must not be used to claim current architecture, current corpus completeness, or active release readiness.
