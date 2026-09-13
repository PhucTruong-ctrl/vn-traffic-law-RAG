# Suite A Final Report (VNLRAG-97) — Historical Parser Benchmark

> **Historical record (2026-08-13; preserved unchanged in substance).** This report records the immutable Suite A parser benchmark from the earlier parser/ingestion research architecture. It is not an active MVP release gate and does not describe the current runtime topology. The active system is Next.js 16 + React 19, FastAPI/Python 3.11, Supabase REST/Auth persistence, local Qdrant 1.19 hybrid retrieval (OpenRouter dense + FastEmbed BM25), one OpenRouter generator, deterministic evidence/citation/temporal checks, and Markdown/PDF legal exploration. No external retrieval, agents, LangGraph, Redis, MinIO, PostgreSQL app-owned runtime, or seven-service topology is implied.
>
> The raw numbers and hashes below are frozen provenance. Do not rewrite them to make them resemble current MVP metrics. The benchmark's parser commands are historical and may be unavailable in the active rescue checkout; run current evaluation with `backend/scripts/run_thesis_evaluation.py` and the commands in `docs/06-test-evaluation.md` instead.

The shared parser-benchmark fixtures support a nine-metric benchmark (Luật, Nghị định, Thông tư, all born-digital PDFs with a text layer): P1 (Docling), P2 (MinerU real pipeline), and P3 (Parser Router). **Raw numbers only — no superiority claim between parsers where any result is incomplete** (FR-01). The gitignored immutable `data/evaluation/` tree is the source of truth (per run_id; corrections are new runs, never rewrites).

In its originating historical environment, this report was GENERATED rather than hand-edited: `python -m app.evaluation.suites.suite_a final-report --runs data/evaluation/suite-a-final --out docs/evaluation/suite-a-final-report.md --sample docs/evaluation/nd-168-ocr-regression-sample.json` reads immutable run artifacts and rewrites this file. The command remains provenance only, not an active release command.

All three variants ran on the SAME fixtures. `input-manifest.json` is byte-identical (sha256 `6848465ff958bc577b10b7fb77a5aa10bdd50a50af76198003803a508271728b`), with git `318e34f48b0c0f4fe24cec825cb66830fd3e63b0`. Runs: P1 `run-20260813-225051-5cca72`, P2 `run-20260813-225124-0dda71`, P3 `run-20260813-225310-521006`.

## Historical result: P1 (Docling) — run run-20260813-225051-5cca72

- parser: docling 2.118.1
- ir_schema_version: document-ir-v2
- elapsed: 2026-08-13T22:50:51.797927+00:00 -> 2026-08-13T22:51:24.822977+00:00 UTC
- run.json sha256: `9dfa92100c498ea42463d8014cea91e24aab4366ae34b2b9f2fd5f4994c961f0`

### Nine metrics per document (shared fixtures)

| metric | luat-36-2024-qh15 | nd-168-2024 | tt-24-2024-tt-bgtvt | aggregate |
|---|---|---|---|---|
| Article P/R/F1 | 0.8571 (P 1.0000/R 0.7500) | 0.0000 (P None/R 0.0000) | 1.0000 (P 1.0000/R 1.0000) | 0.7500 (P 1.0000/R 0.6000) |
| Clause P/R/F1 | 0.5455 (P 1.0000/R 0.3750) | 0.0000 (P None/R 0.0000) | 0.6667 (P 1.0000/R 0.5000) | 0.4286 (P 1.0000/R 0.2727) |
| Point P/R/F1 | 0.3158 (P 0.3000/R 0.3333) | 0.0000 (P None/R 0.0000) | 0.8000 (P 0.8000/R 0.8000) | 0.3793 (P 0.5500/R 0.2895) |
| Short Point Recall | 1.0000 (3/3) | 0.0000 (0/3) | 1.0000 (1/1) | 0.5714 (4/7) |
| Vietnamese đ) Recall | 0.5000 (1/2) | 0.0000 (0/4) | 1.0000 (1/1) | 0.2857 (2/7) |
| Parent Context Completeness | 0.2308 (3/13) | N/A | 0.2308 (3/13) | 0.2308 (6/26) |
| Table Preservation | N/A | N/A | N/A | N/A |
| Header/Footer Leakage | N/A | N/A | N/A | N/A |
| Provenance Coverage | 1.0000 (26/26) bbox 1.0000 | 1.0000 (5/5) bbox 1.0000 | 1.0000 (17/17) bbox 1.0000 | 1.0000 (48/48) |

N/A reasons (availability — never fabricated 0%/100%):
- Table Preservation: `gold fixtures contain no table annotations`
- Header/Footer Leakage: `gold fixtures contain no header/footer annotations`

## Historical result: P2 (MinerU) — run run-20260813-225124-0dda71

- parser: mineru 3.4.4
- ir_schema_version: document-ir-v2
- elapsed: 2026-08-13T22:51:24.855071+00:00 -> 2026-08-13T22:53:10.375846+00:00 UTC
- run.json sha256: `d04299adb3078df69ead451a6aad2f58d4485d7424335fc6d1bafb2d47856078`

### Nine metrics per document (shared fixtures)

| metric | luat-36-2024-qh15 | nd-168-2024 | tt-24-2024-tt-bgtvt | aggregate |
|---|---|---|---|---|
| Article P/R/F1 | 1.0000 (P 1.0000/R 1.0000) | 1.0000 (P 1.0000/R 1.0000) | 1.0000 (P 1.0000/R 1.0000) | 1.0000 (P 1.0000/R 1.0000) |
| Clause P/R/F1 | 1.0000 (P 1.0000/R 1.0000) | 0.8889 (P 0.8000/R 1.0000) | 1.0000 (P 1.0000/R 1.0000) | 0.9565 (P 0.9167/R 1.0000) |
| Point P/R/F1 | 0.8182 (P 0.6923/R 1.0000) | 0.6333 (P 0.4634/R 1.0000) | 1.0000 (P 1.0000/R 1.0000) | 0.7451 (P 0.5938/R 1.0000) |
| Short Point Recall | 1.0000 (3/3) | 1.0000 (3/3) | 1.0000 (1/1) | 1.0000 (7/7) |
| Vietnamese đ) Recall | 1.0000 (2/2) | 1.0000 (4/4) | 1.0000 (1/1) | 1.0000 (7/7) |
| Parent Context Completeness | 1.0000 (21/21) | 1.0000 (51/51) | 1.0000 (16/16) | 1.0000 (88/88) |
| Table Preservation | N/A | N/A | N/A | N/A |
| Header/Footer Leakage | N/A | N/A | N/A | N/A |
| Provenance Coverage | 1.0000 (29/29) bbox 1.0000 | 1.0000 (62/62) bbox 1.0000 | 1.0000 (21/21) bbox 1.0000 | 1.0000 (112/112) |

N/A reasons (availability — never fabricated 0%/100%):
- Table Preservation: `gold fixtures contain no table annotations`
- Header/Footer Leakage: `gold fixtures contain no header/footer annotations`

## Historical result: P3 (Parser Router) — run run-20260813-225310-521006

- parser: Parser Router (VNLRAG-131); primary docling 2.118.1, alternate mineru 3.4.4
- ir_schema_version: document-ir-v2
- elapsed: 2026-08-13T22:53:10.398917+00:00 -> 2026-08-13T22:53:18.161919+00:00 UTC
- run.json sha256: `165cb5ef47bc119e4608c8f411880e6a0ec17a32a4661f649680b35b86161ae7`

### Nine metrics per document (shared fixtures)

| metric | luat-36-2024-qh15 | nd-168-2024 | tt-24-2024-tt-bgtvt | aggregate |
|---|---|---|---|---|
| Article P/R/F1 | 0.8571 (P 1.0000/R 0.7500) | 0.0000 (P None/R 0.0000) | 1.0000 (P 1.0000/R 1.0000) | 0.7500 (P 1.0000/R 0.6000) |
| Clause P/R/F1 | 0.5455 (P 1.0000/R 0.3750) | 0.0000 (P None/R 0.0000) | 0.6667 (P 1.0000/R 0.5000) | 0.4286 (P 1.0000/R 0.2727) |
| Point P/R/F1 | 0.3158 (P 0.3000/R 0.3333) | 0.0000 (P None/R 0.0000) | 0.8000 (P 0.8000/R 0.8000) | 0.3793 (P 0.5500/R 0.2895) |
| Short Point Recall | 1.0000 (3/3) | 0.0000 (0/3) | 1.0000 (1/1) | 0.5714 (4/7) |
| Vietnamese đ) Recall | 0.5000 (1/2) | 0.0000 (0/4) | 1.0000 (1/1) | 0.2857 (2/7) |
| Parent Context Completeness | 0.2308 (3/13) | N/A | 0.2308 (3/13) | 0.2308 (6/26) |
| Table Preservation | N/A | N/A | N/A | N/A |
| Header/Footer Leakage | N/A | N/A | N/A | N/A |
| Provenance Coverage | 1.0000 (26/26) bbox 1.0000 | 1.0000 (5/5) bbox 1.0000 | 1.0000 (17/17) bbox 1.0000 | 1.0000 (48/48) |

N/A reasons (availability — never fabricated 0%/100%):
- Table Preservation: `gold fixtures contain no table annotations`
- Header/Footer Leakage: `gold fixtures contain no header/footer annotations`
- accepted: 3
- routes: `{"docling_text": 3}`
- source_parsers: `{"docling": 3}`
- gate_verdicts: `{"passed": 3}`
- terminal_outcomes: `{"accepted": 3}`

## Historical aggregate comparison

These pooled aggregates use the SAME fixtures. Raw numbers only; make NO superiority conclusion where any parser result is incomplete.

| metric | P1 Docling | P2 MinerU | P3 Router |
|---|---|---|---|
| Article P/R/F1 | 0.7500 (P 1.0000/R 0.6000) | 1.0000 (P 1.0000/R 1.0000) | 0.7500 (P 1.0000/R 0.6000) |
| Clause P/R/F1 | 0.4286 (P 1.0000/R 0.2727) | 0.9565 (P 0.9167/R 1.0000) | 0.4286 (P 1.0000/R 0.2727) |
| Point P/R/F1 | 0.3793 (P 0.5500/R 0.2895) | 0.7451 (P 0.5938/R 1.0000) | 0.3793 (P 0.5500/R 0.2895) |
| Short Point Recall | 0.5714 (4/7) | 1.0000 (7/7) | 0.5714 (4/7) |
| Vietnamese đ) Recall | 0.2857 (2/7) | 1.0000 (7/7) | 0.2857 (2/7) |
| Parent Context Completeness | 0.2308 (6/26) | 1.0000 (88/88) | 0.2308 (6/26) |
| Table Preservation | N/A | N/A | N/A |
| Header/Footer Leakage | N/A | N/A | N/A |
| Provenance Coverage | 1.0000 (48/48) | 1.0000 (112/112) | 1.0000 (48/48) |

## Historical OCR regression: NĐ 168 (300 vs 600 DPI)

Tesseract vie (psm 3) via the docling IMAGE pipeline on a real scan-only 1-bit CCITT document (no text layer), 6 pages, CPU-only. Quality axes: phrase hit rate, Vietnamese point-label (d)/đ)) evidence, s/page, peak RAM, bbox coverage. The reviewed sample (Article/Clause/Point + d/đ labels from `nd-gold.json` + the nd fixture text) is the regression reference.

- sample: `/home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase17/docs/evaluation/nd-168-ocr-regression-sample.json` (sha256 `29ca933f11aad43169b5f3010126c6a97b6bc75befb1ba948150a2db8a001065`)
- schema_version: nd-168-ocr-regression-sample-v1
- basis: Manual review reference built from backend/tests/fixtures/parser_benchmark/gold/nd-gold.json (reviewed Article/Clause/Point structure incl. point_label d) vs đ) per docs/03 §3.8.5) and the nd-168-2024-fixture.pdf.txt excerpt text.
- page_range: [2, 7]
- expected: `{"articles": ["Điều 5", "Điều 7", "Điều 9"], "clause_count": 8, "point_count": 19, "point_labels_d": ["a)", "b)", "c)", "d)"], "point_labels_dd": ["đ)"], "dd_label_count": 4, "d_label_count": 4}`
- run: `ocr-dpi-benchmark/run-20260813-225424-def3b7` (status COMPLETED)

| axis | 300 DPI | 600 DPI | better |
|---|---:|---:|---|
| avg seconds/page | 23.05 | 49.12 | 300 |
| peak RSS (KB) | 1433536 | 1899176 | 300 |
| phrase hit rate (mean) | 0.5834 | 0.5834 | tie |
| bbox coverage (mean) | 1.0 | 1.0 | tie |
| total extracted chars | 13970 | 14079 | — |
| total d) labels | 0 | 0 | — |
| total đ) labels | 3 | 3 | —

Relative quality (difflib SequenceMatcher ratio, 300 vs 600): page 2 `0.7732`, page 3 `0.745`, page 4 `0.4286`, page 5 `0.7758`, page 6 `0.6099`, page 7 `0.7558`.

DPI decision in the historical run: **300** for this 1-bit CCITT scan type. This does not change the active MVP's corpus-only retrieval contract.

## Historical scan corpus status

The shared parser-benchmark fixtures were born-digital (text layer). Real scan-only corpus parsing was not completed in this report; the OCR sample above is a parser research artefact, not current release evidence.

## Historical skips and reasons

- Table Preservation / Table Detection: the v1 fixtures carry no table annotations -> N/A.
- Header/Footer Leakage: the v1 fixtures carry no header/footer annotations -> N/A.
- Parent Context Completeness on nd-168: no POINT/CLAUSE provisions in accepted parser output -> N/A.
- Scan corpus: not run in the historical trio.

The original command is retained only to identify the source run:

```bash
CUDA_VISIBLE_DEVICES="" python -m app.evaluation.suites.suite_a run \
  --fixtures-dir backend/tests/fixtures/parser_benchmark/documents \
  --run-dir data/evaluation/suite-a-final --variants p1 p2 p3
```

For current executable evaluation, use the active commands in `docs/06-test-evaluation.md` and `backend/scripts/run_thesis_evaluation.py`.

## Immutable historical artefacts

- git commit recorded in run.json: `318e34f48b0c0f4fe24cec825cb66830fd3e63b0`
- input-manifest.json sha256: `6848465ff958bc577b10b7fb77a5aa10bdd50a50af76198003803a508271728b`
- Raw per-run hashes remain the source of truth under `data/evaluation/suite-a-final`; this document does not rewrite them.
