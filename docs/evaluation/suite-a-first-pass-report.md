# Suite A First Pass — Historical W2 Report (VNLRAG-20)

> **Historical record (2026-08-09; preserved raw result).** This first-pass parser report belongs to the superseded parser/ingestion research architecture. It is not an active MVP release gate and does not imply PostgreSQL-owned ingestion, Redis/Dramatiq, MinIO, LangGraph, agents, external retrieval, or a seven-service topology. The active runtime is Next.js 16 + React 19, FastAPI/Python 3.11, Supabase REST/Auth, local Qdrant 1.19 hybrid retrieval (OpenRouter dense + FastEmbed BM25), one OpenRouter generator, deterministic gates, and Markdown/PDF legal exploration.
>
> The run IDs, metrics, hashes, and historical conclusions below are frozen provenance. Do not rewrite them. Current evaluation instructions are in `docs/06-test-evaluation.md`; current end-to-end scoring uses `backend/scripts/run_thesis_evaluation.py` against `POST /api/v1/chat`.

Parser-native metrics benchmark on the born-digital parser fixtures. **Raw numbers only — NO superiority conclusions between parsers** (see §8 for the historical M1 assessment). Source of truth for raw artifacts: the gitignored `data/evaluation/` tree (immutable per run_id — corrections are new runs, never rewrites).

This report was generated in its originating environment by `python -m app.evaluation.suites.suite_a report --runs data/evaluation/suite-a-first-pass --out docs/evaluation/suite-a-first-pass-report.md`. That command is retained as historical provenance, not as an active release command.

All three variants (P1/P2/P3) ran on the SAME fixtures, so their `input-manifest.json` is byte-identical (sha256 `bdce19c0a3158b4f36318044a2a784aa9006d861bc00a1f84e4701e8f93a2e46`) — P1/P2/P3 share a common execution context and fixture hashes (git `7bbaad28752dd04c8c11c315cd2086be43176dbc`).

## Historical P1 (Docling) — run run-20260809-160810-5563e6

- parser: docling 2.118.1
- ir_schema_version: document-ir-v2
- run.json sha256: `51564036fa0756378a526c10db26ab9c7f01dabe6a0ab9a33f4271f9f93df321`
- elapsed: 2026-08-09T16:08:10.260318+00:00 -> 2026-08-09T16:08:41.036480+00:00 UTC

### Per-document metrics

| document_id | pages | text_extraction (pages) | provenance page_number | provenance bbox | table_detection | table_preservation | header/footer | layout_coherence |
|---|---:|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | 1 | 1.0 (1/1) | 1.0 (26/26) | 1.0 (26/26) | N/A | N/A | N/A | 1.0 |
| nd-168-2024 | 2 | 1.0 (2/2) | 1.0 (5/5) | 1.0 (5/5) | N/A | N/A | N/A | 1.0 |
| tt-24-2024-tt-bgtvt | 1 | 1.0 (1/1) | 1.0 (17/17) | 1.0 (17/17) | N/A | N/A | N/A | 1.0 |

N/A reasons: table annotations and header/footer annotations were absent from the frozen fixtures; no percentage was fabricated.

### Historical aggregate

- documents: 3, pages: 4, elements: 48
- text_extraction_rate: 1.0 (4/4 pages); provenance_coverage: 1.0 (48/48 elements, bbox 48/48)
- layout_coherence: 1.0

## Historical P2 (MinerU) — run run-20260809-160841-9f3386

- pipeline: real MinerU pipeline (`backend=pipeline`, `method=txt`, no OCR) executed in the historical environment; CPU-only.
- parser: mineru 3.4.4
- ir_schema_version: document-ir-v2
- run.json sha256: `a96cc5c14efd1ae7adce8648a556bf86817741c307afe0e563d0a290f686f370`
- elapsed: 2026-08-09T16:08:41.074165+00:00 -> 2026-08-09T16:10:43.507414+00:00 UTC

### Historical per-document metrics

| document_id | pages | text_extraction (pages) | provenance page_number | provenance bbox | table_detection | table_preservation | header/footer | layout_coherence |
|---|---:|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | 1 | 1.0 (1/1) | 1.0 (29/29) | 1.0 (29/29) | N/A | N/A | N/A | 1.0 |
| nd-168-2024 | 2 | 1.0 (2/2) | 1.0 (62/62) | 1.0 (62/62) | N/A | N/A | N/A | 1.0 |
| tt-24-2024-tt-bgtvt | 1 | 1.0 (1/1) | 1.0 (21/21) | 1.0 (21/21) | N/A | N/A | N/A | 1.0 |

### Historical aggregate

- documents: 3, pages: 4, elements: 112
- text_extraction_rate: 1.0 (4/4 pages); provenance_coverage: 1.0 (112/112 elements, bbox 112/112)
- layout_coherence: 1.0

## Historical P3 (Parser Router) — run run-20260809-161043-6cd9db

- `p3_parser_router`: operational in the historical run; completed.
- router: `ParserRouter` with historical primary Docling and alternate MinerU; Group A gates were operational in that run.
- run.json sha256: `2bae1246c5605739b8e930590ed6e7fcbc80782c97e442c1941e247d16793828`

### Historical routing outcomes

| document_id | route | selected_parser | source_parser | fallback_attempted | gate_verdict | terminal_outcome |
|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | docling_text | docling | docling | False | passed | accepted |
| nd-168-2024 | docling_text | docling | docling | False | passed | accepted |
| tt-24-2024-tt-bgtvt | docling_text | docling | docling | False | passed | accepted |

Historical aggregate: 3 accepted documents, 4 pages, 48 elements, route `{"docling_text": 3}`, no fallback documents.

## Historical OCR configuration and DPI result

The historical runs recorded Tesseract `5.5.3`, Vietnamese language data, `psm=3`, CPU-only processing, and a 300 DPI born-digital policy. The separate historical OCR decision artifact was `run-20260809-120116-24f592`, using pages 2 and 7 of the scan-only NĐ 168 PDF.

| axis | 300 DPI | 600 DPI | better |
|---|---:|---:|---|
| avg seconds/page | 29.78 | 60.81 | 300 |
| peak RSS (KB) | 1462088 | 1924344 | 300 |
| phrase hit rate (mean) | 0.5834 | 0.5556 | 300 |
| bbox coverage (mean) | 1.0 | 1.0 | tie |
| total extracted chars | 13958 | 14031 | — |

Historical recommendation: 300 DPI for that 1-bit CCITT scan type. This is parser provenance only; it is not an active release claim.

## Historical routing recommendation and M1 assessment

The historical P3 run recommended Docling for searchable PDFs, Docling OCR then MinerU fallback for scans, parser comparison for complex tables, and review for ambiguous/low-provenance OCR. Those routes were not all exercised by the born-digital fixtures. The historical report claimed M1 on its then-defined parser-foundation gate; that claim must not be read as current MVP release readiness.

## Historical immutable artefacts

- git commit: `7bbaad28752dd04c8c11c315cd2086be43176dbc`
- input-manifest.json sha256: `bdce19c0a3158b4f36318044a2a784aa9006d861bc00a1f84e4701e8f93a2e46`
- Raw run artefacts and per-run hashes remain under `data/evaluation/suite-a-first-pass`; corrections are new run IDs and never rewrites.

For the current executable smoke/evaluation procedure, use `docs/06-test-evaluation.md`.
