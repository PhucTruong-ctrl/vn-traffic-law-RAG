# Suite A Final Report (VNLRAG-97)

Nine-metric parser benchmark on the shared parser-benchmark fixtures (Luật, Nghị định, Thông tư — born-digital PDFs with a text layer): P1 (Docling), P2 (MinerU real pipeline), P3 (Parser Router). **Raw numbers only — no superiority claim between parsers where any result is incomplete** (FR-01). Source of truth: the gitignored immutable `data/evaluation/` tree (per run_id; corrections are new runs, never rewrites).

This report is GENERATED, not hand-edited: `python -m app.evaluation.suites.suite_a final-report --runs data/evaluation/suite-a-final --out docs/evaluation/suite-a-final-report.md --sample docs/evaluation/nd-168-ocr-regression-sample.json` reads the immutable run artifacts and rewrites this file.

All three variants ran on the SAME fixtures — `input-manifest.json` is byte-identical (sha256 `6848465ff958bc577b10b7fb77a5aa10bdd50a50af76198003803a508271728b`), git `318e34f48b0c0f4fe24cec825cb66830fd3e63b0`. Runs: P1 `run-20260813-225051-5cca72`, P2 `run-20260813-225124-0dda71`, P3 `run-20260813-225310-521006`.

## 1. P1 (Docling) — run run-20260813-225051-5cca72

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

## 2. P2 (MinerU) — run run-20260813-225124-0dda71

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

## 3. P3 (Parser Router) — run run-20260813-225310-521006

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
- routes: {"docling_text": 3}
- source_parsers: {"docling": 3}
- gate_verdicts: {"passed": 3}
- terminal_outcomes: {"accepted": 3}

## Aggregate comparison (9 metrics x P1/P2/P3)

Pooled aggregates over the SAME fixtures. Raw numbers only — NO superiority conclusion where any parser's result is incomplete.

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

## NĐ 168 OCR regression (300 vs 600 DPI)

Tesseract vie (psm 3) via the docling IMAGE pipeline on a real scan-only 1-bit CCITT document (no text layer), 6 pages, CPU-only. Quality axes: phrase hit rate, Vietnamese point-label (d)/đ)) evidence, s/page, peak RAM, bbox coverage. The reviewed sample (Article/Clause/Point + d/đ labels from `nd-gold.json` + the nd fixture text) is the regression reference.

- sample: `/home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase17/docs/evaluation/nd-168-ocr-regression-sample.json` (sha256 `29ca933f11aad43169b5f3010126c6a97b6bc75befb1ba948150a2db8a001065`)
- schema_version: nd-168-ocr-regression-sample-v1
- basis: Manual review reference built from backend/tests/fixtures/parser_benchmark/gold/nd-gold.json (reviewed Article/Clause/Point structure incl. point_label d) vs đ) per docs/03 §3.8.5) and the nd-168-2024-fixture.pdf.txt excerpt text.
- page_range: [2, 7]
- expected: {"articles": ["Điều 5", "Điều 7", "Điều 9"], "clause_count": 8, "point_count": 19, "point_labels_d": ["a)", "b)", "c)", "d)"], "point_labels_dd": ["đ)"], "dd_label_count": 4, "d_label_count": 4, "dd_provisions": ["nd-168-2024__dieu-5__khoan-1__diem-đ", "nd-168-2024__dieu-7__khoan-1__diem-đ", "nd-168-2024__dieu-7__khoan-2__diem-đ", "nd-168-2024__dieu-9__khoan-1__diem-đ"]}

- run: `ocr-dpi-benchmark/run-20260813-225424-def3b7` (status COMPLETED); pdf /home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase17/data/evaluation/suite-a-final/nd-168-2024.pdf

| axis | 300 DPI | 600 DPI | better |
|---|---|---|---|
| avg seconds/page | 23.05 | 49.12 | 300 |
| peak RSS (KB) | 1433536 | 1899176 | 300 |
| phrase hit rate (mean) | 0.5834 | 0.5834 | tie |
| bbox coverage (mean) | 1.0 | 1.0 | tie |
| total extracted chars | 13970 | 14079 | — |
| total d) labels | 0 | 0 | — |
| total đ) labels | 3 | 3 | — |

Relative quality (difflib SequenceMatcher ratio, 300 vs 600): page 2 `0.7732`, page 3 `0.745`, page 4 `0.4286`, page 5 `0.7758`, page 6 `0.6099`, page 7 `0.7558`.

DPI decision: **300** for this 1-bit CCITT scan type; basis: 600 picked when it wins on quality (phrase hit rate or bbox coverage) and speed stays within 2x of 300 DPI. Note: 600 DPI scan-only conditional per VNLRAG-20 OCR decision. (Kept at 300 unless this measurement changed the first-pass evidence.)

## Scan corpus status

- The shared parser-benchmark fixtures are born-digital (text layer) — P1/P2/P3 ran on all three (luat/nd/tt).
- Real scan-only corpus (nd-168, nd-100, tt-79, tt-24 — 1-bit CCITT, no text layer): not parsed through P1/P2/P3 in this run — full-scan parsing is the routing/quality-gate execution lane; the NĐ 168 OCR regression section above benchmarks the scan-OCR decision on a 6-page sample of nd-168 instead.

## Skips and reasons

- Table Preservation / Table Detection: the v1 fixtures carry no table annotations (`gold fixtures contain no table annotations`) -> N/A (never a fabricated percentage).
- Header/Footer Leakage: the v1 fixtures carry no header/footer annotations -> N/A.
- Parent Context Completeness on nd-168: the accepted parser output extracts no POINT/CLAUSE provisions -> N/A for that document (measured on luat/tt; see §1–§3).
- Scan corpus: skipped as above.

## Reproducibility

Exact commands (run in the worktree root, branch `feat/VNLRAG-97-suite-a-final`):

```bash
CUDA_VISIBLE_DEVICES="" python -m app.evaluation.suites.suite_a run \
    --fixtures-dir backend/tests/fixtures/parser_benchmark/documents \
    --run-dir data/evaluation/suite-a-final --variants p1 p2 p3

python -m app.evaluation.suites.suite_a bench-ocr-dpi \
    --pdf data/evaluation/suite-a-final/nd-168-2024.pdf \
    --pages 6 --out data/evaluation/ocr-dpi-benchmark \
    --sample docs/evaluation/nd-168-ocr-regression-sample.json

python -m app.evaluation.suites.suite_a final-report \
    --runs data/evaluation/suite-a-final \
    --out docs/evaluation/suite-a-final-report.md \
    --sample docs/evaluation/nd-168-ocr-regression-sample.json \
    --tests-log data/evaluation/suite-a-final/tests-output.txt
```

Focused unit tests (new metric-computation helpers):

```text
...............................................................          [100%]
63 passed in 4.85s
```

## Immutable artifacts (sha256)

- git commit (recorded in run.json): `318e34f48b0c0f4fe24cec825cb66830fd3e63b0`
- input-manifest.json sha256 (identical across the trio): `6848465ff958bc577b10b7fb77a5aa10bdd50a50af76198003803a508271728b`

| artifact | sha256 |
|---|---|
| suite-a-final/run-20260813-225051-5cca72/run.json | `9dfa92100c498ea42463d8014cea91e24aab4366ae34b2b9f2fd5f4994c961f0` |
| suite-a-final/run-20260813-225051-5cca72/p1-docling/results.json | `a513862a4fdaad69b5a4c723e793ae043962ace5d02eef18059a76acf1d972c8` |
| suite-a-final/run-20260813-225051-5cca72/p1-docling/metrics.json | `b91b26037ab3d663c5b5b8d3284a1405252c167c34db4af32db8a75cb7800c73` |
| suite-a-final/run-20260813-225051-5cca72/p1-docling/routing-and-gates.json | `ce390be28465d1eb1356a92f1854f5fad60f6534a852a27e99b6630460206411` |
| suite-a-final/run-20260813-225051-5cca72/p1-docling/artifacts-manifest.json | `44374c3a905f337368cdd3257c1cab6d98f0555672c6948e83ef965bdce1cdec` |
| suite-a-final/run-20260813-225051-5cca72/p1-docling/report.md | `868c8d5a5c1edf7a4b7ddfac1eada68a75e758eed5ddcdae70c2ee4007f10c6b` |
| …/run.json | `d04299adb3078df69ead451a6aad2f58d4485d7424335fc6d1bafb2d47856078` |
| …/p2-mineru/results.json | `cea95240a50418ba0dbad4b4ed217c3dcc758cbba35411ebc2f573202e60209f` |
| …/p2-mineru/metrics.json | `99c69acd739e59d7ad5a9b4c14f18cb14200b2619885247f66dda8baaf960d81` |
| …/p2-mineru/routing-and-gates.json | `19faed2acf4ada22f6ec60a01a4cce3ee9c7b09139876b3d16f943e8ddfc9254` |
| …/p2-mineru/artifacts-manifest.json | `aae3270ebed36493286c837ded329010cd0ec3e2f2d3c8e044246265048b58d3` |
| …/p2-mineru/report.md | `17c27a626b461d7aa170fbea096bd6d9aecdad67c020b16a9189f9514a44cbea` |
| …/run.json | `165cb5ef47bc119e4608c8f411880e6a0ec17a32a4661f649680b35b86161ae7` |
| …/p3-parser-router/results.json | `4a7840d60d9b201fd172a61731c67cd771a248f9cc07bb14bb3d45cdd14dae16` |
| …/p3-parser-router/metrics.json | `0c0c4cfdcda976c8f689c74cf6a383b3f806f16ae835f8d208409ea3191eaa11` |
| …/p3-parser-router/routing-and-gates.json | `7ae14910392eb081d6abbb63179fba304df9a63bfb4b04be5d21970a09fb07ca` |
| …/p3-parser-router/artifacts-manifest.json | `a03aa25c4d0b80c4a593d9a6bb241e11aab9c1033fdadfb4b23054ff468b8a61` |
| …/p3-parser-router/report.md | `e5df4cf54c15f0a39bb9f83fe3344135e7b2a12d2a4f0cce39ab71ef78ddc826` |
| ocr-dpi-benchmark/run-20260813-225424-def3b7/summary.json | `97516e2b87b36eff4e597785623e7736e157455a9f9721c893cec55ea66131bc` |
| ocr-dpi-benchmark/run-20260813-225424-def3b7/detail.json | `c6a248175a621eee24431acce63b44b3e9382b944d030391c0d96fb9febca20f` |

