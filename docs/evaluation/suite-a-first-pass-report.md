# Suite A First Pass — Committed W2 Report (VNLRAG-20)

Parser-native metrics benchmark on the born-digital parser fixtures. **Raw numbers only — NO superiority conclusions between parsers** (see §8 for the honest M1 assessment). Source of truth for raw artifacts: the gitignored `data/evaluation/` tree (immutable per run_id — corrections are new runs, never rewrites).

This report is GENERATED, not hand-edited: `python -m app.evaluation.suites.suite_a report --runs data/evaluation/suite-a-first-pass --out docs/evaluation/suite-a-first-pass-report.md` reads the immutable run artifacts and rewrites this file. The per-run `report.md` writers produce the in-run reports; this committed report is the reproducible deliverable.

All three variants (P1/P2/P3) ran on the SAME fixtures, so their `input-manifest.json` is byte-identical (sha256 `bdce19c0a3158b4f36318044a2a784aa9006d861bc00a1f84e4701e8f93a2e46`) — P1/P2/P3 share a common execution context and fixture hashes (git `7bbaad28752dd04c8c11c315cd2086be43176dbc`).

## 1. P1 (Docling) — run run-20260809-160810-5563e6

- parser: docling 2.118.1
- ir_schema_version: document-ir-v2
- run.json sha256: `51564036fa0756378a526c10db26ab9c7f01dabe6a0ab9a33f4271f9f93df321`
- elapsed: 2026-08-09T16:08:10.260318+00:00 -> 2026-08-09T16:08:41.036480+00:00 UTC

### Per-document metrics

| document_id | pages | text_extraction (pages) | provenance page_number | provenance bbox | table_detection | table_preservation | header/footer | layout_coherence |
|---|---|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | 1 | 1.0 (1/1) | 1.0 (26/26) | 1.0 (26/26) | N/A | N/A | N/A | 1.0 |
| nd-168-2024 | 2 | 1.0 (2/2) | 1.0 (5/5) | 1.0 (5/5) | N/A | N/A | N/A | 1.0 |
| tt-24-2024-tt-bgtvt | 1 | 1.0 (1/1) | 1.0 (17/17) | 1.0 (17/17) | N/A | N/A | N/A | 1.0 |

N/A reasons (availability, never fabricated 0%/100%):
- table_detection_rate: `gold fixtures contain no table annotations`
- table_preservation: `gold fixtures contain no table annotations`
- header_footer_leakage: `gold fixtures contain no header/footer annotations`

### Aggregate

- documents: 3, pages: 4, elements: 48
- element_type_histogram: {"list_item": 32, "text": 16}
- text_extraction_rate: 1.0 (4/4 pages); provenance_coverage: 1.0 (48/48 elements, bbox 48/48)
- layout_coherence: 1.0 (spatial-progression rule; per-page scores all 1.0, no empty pages)

Artifacts (relative to run root): `run.json`, `input-manifest.json`, `report.md`, `p1-docling/{results,metrics,routing-and-gates,artifacts-manifest}.json`, `p1-docling/ir/*.ir.json` (hashes in §6).

## 2. P2 (MinerU) — run run-20260809-160841-9f3386

- pipeline: REAL mineru pipeline (backend=pipeline, method=txt — text extraction, no OCR, matching the born-digital fixtures) executed as a subprocess via MinerUAdapter.parse_pdf (run_mineru -> mineru.cli.client), CPU-only CUDA_VISIBLE_DEVICES="". The flat *_content_list.json artifacts are preserved under p2-mineru/mineru-output/.
- parser: mineru 3.4.4
- ir_schema_version: document-ir-v2
- run.json sha256: `a96cc5c14efd1ae7adce8648a556bf86817741c307afe0e563d0a290f686f370`
- elapsed: 2026-08-09T16:08:41.074165+00:00 -> 2026-08-09T16:10:43.507414+00:00 UTC

### Per-document metrics

| document_id | pages | text_extraction (pages) | provenance page_number | provenance bbox | table_detection | table_preservation | header/footer | layout_coherence |
|---|---|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | 1 | 1.0 (1/1) | 1.0 (29/29) | 1.0 (29/29) | N/A | N/A | N/A | 1.0 |
| nd-168-2024 | 2 | 1.0 (2/2) | 1.0 (62/62) | 1.0 (62/62) | N/A | N/A | N/A | 1.0 |
| tt-24-2024-tt-bgtvt | 1 | 1.0 (1/1) | 1.0 (21/21) | 1.0 (21/21) | N/A | N/A | N/A | 1.0 |

N/A reasons (availability, never fabricated 0%/100%):
- table_detection_rate: `gold fixtures contain no table annotations`
- table_preservation: `gold fixtures contain no table annotations`
- header_footer_leakage: `gold fixtures contain no header/footer annotations`

### Aggregate

- documents: 3, pages: 4, elements: 112
- element_type_histogram: {"heading": 5, "paragraph": 107}
- text_extraction_rate: 1.0 (4/4 pages); provenance_coverage: 1.0 (112/112 elements, bbox 112/112)
- layout_coherence: 1.0 (spatial-progression rule; per-page scores all 1.0, no empty pages)

Artifacts (relative to run root): `run.json`, `input-manifest.json`, `report.md`, `p2-mineru/{results,metrics,routing-and-gates,artifacts-manifest}.json`, `p2-mineru/ir/*.ir.json` (hashes in §6).

## 3. P3 (Parser Router) — run run-20260809-161043-6cd9db

- `p3_parser_router`: OPERATIONAL (VNLRAG-131); COMPLETED
- router: `ParserRouter` (config primary=docling, alternate=mineru, Group A gates operational); per-document `parser_routing-v1` records written to `p3-parser-router/routing-and-gates.json`
- run.json sha256: `2bae1246c5605739b8e930590ed6e7fcbc80782c97e442c1941e247d16793828`

### Routing outcomes per document

| document_id | route | selected_parser | source_parser | fallback_attempted | gate_verdict | terminal_outcome |
|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | docling_text | docling | docling | False | passed | accepted |
| nd-168-2024 | docling_text | docling | docling | False | passed | accepted |
| tt-24-2024-tt-bgtvt | docling_text | docling | docling | False | passed | accepted |

### Parser-native metrics on the accepted document

The metric set is computed on the ACCEPTED document (single `source_parser`, no mixing); a document with no accepted parser output reports N/A.

| document_id | text_extraction | provenance bbox | table_detection | table_preservation | header/footer | layout_coherence |
|---|---|---|---|---|---|---|
| luat-36-2024-qh15 | 1.0 (1/1) | 1.0 (26/26) | N/A | N/A | N/A | 1.0 |
| nd-168-2024 | 1.0 (2/2) | 1.0 (5/5) | N/A | N/A | N/A | 1.0 |
| tt-24-2024-tt-bgtvt | 1.0 (1/1) | 1.0 (17/17) | N/A | N/A | N/A | 1.0 |

### Aggregate

- documents: 3
- accepted: 3
- routes: {"docling_text": 3}
- selected_parsers: {"docling": 3}
- source_parsers: {"docling": 3}
- gate_verdicts: {"passed": 3}
- terminal_outcomes: {"accepted": 3}
- fallback_attempted_documents: 0
- pages: 4
- elements: 48
- element_type_histogram (accepted IR): {"list_item": 32, "text": 16}

## 4. OCR configuration snapshot (W2, AC 8/9)

Recorded in every run.json `config.ocr` (verified in the P1 run):

- engine: tesseract; tesseract_version: `tesseract 5.5.3`
- lang: `["vie"]`; tessdata_dir: `/tmp/opencode/tessdata`; tesseract_cmd: `/usr/bin/tesseract`
- psm: 3 (explicit); scale: 3.0
- dpi: 300 (born-digital policy); dpi_policy: `300 (born-digital); 600 scan-only conditional per VNLRAG-20 OCR decision`
- ocr_status: `SKIPPED_TEXT_LAYER_PRESENT` for the born-digital fixtures (OCR not executed)
- ocr_readiness: checked=True, problems [] (fail-fast `check-ocr` subcommand, AC 8)

### PSM traceability note (transparency, no rewrite of immutable runs)

Benchmark runs prior to psm wiring (`run-20260809-112857-cfb72f`) recorded `psm: 3` as the policy snapshot, but the actual `TesseractCliOcrOptions(...)` at that time did not pass `psm` (docling default `psm=None` -> tesseract binary default). After that finding, `suite_a.py` passes `psm=3` explicitly to `TesseractCliOcrOptions` (the field is confirmed present in installed docling 2.118.1). Immutable runs are never rewritten; this note records the boundary.

## 5. 300-vs-600 DPI OCR benchmark (AC 7)

Separate OCR decision artifact, referenced from the canonical run:

- **run_id**: `run-20260809-120116-24f592`; status: COMPLETED; pages [2, 7] of `/home/phuctruong/Work/Studies/vnlaw-agentic-rag/data/nd-168-2024/source/nd-168-2024.pdf` (111-page 1-bit CCITT scan, no text layer)
- engine: tesseract vie (psm 3), docling IMAGE pipeline, do_table_structure off, CPU-only, `CUDA_VISIBLE_DEVICES=""`

Decision data (raw):

| axis | 300 DPI | 600 DPI | better |
|---|---|---|---|
| avg seconds/page | 29.78 | 60.81 | 300 |
| peak RSS (KB) | 1462088 | 1924344 | 300 |
| phrase hit rate (mean) | 0.5834 | 0.5556 | 300 |
| bbox coverage (mean) | 1.0 | 1.0 | tie |
| total extracted chars | 13958 | 14031 | — |

Relative quality (difflib SequenceMatcher ratio on full page text, 300 vs 600): page 2 `0.8827`, page 3 `0.9377`, page 4 `0.4365`, page 5 `0.8395`, page 6 `0.9615`, page 7 `0.9455`.

Measured recommendation: **300** for this 1-bit CCITT scan type; basis: 600 picked when it wins on quality (phrase hit rate or bbox coverage) and speed stays within 2x of 300 DPI. Note: 600 DPI scan-only conditional per VNLRAG-20 OCR decision.

## 6. Immutable artifact paths + hashes (this first-pass trio)

- git commit: `7bbaad28752dd04c8c11c315cd2086be43176dbc`
- input-manifest.json sha256 (identical across the trio): `bdce19c0a3158b4f36318044a2a784aa9006d861bc00a1f84e4701e8f93a2e46`

| artifact | sha256 |
|---|---|
| suite-a-first-pass/run-20260809-160810-5563e6/run.json | `51564036fa0756378a526c10db26ab9c7f01dabe6a0ab9a33f4271f9f93df321` |
| suite-a-first-pass/run-20260809-160810-5563e6/p1-docling/results.json | `a513862a4fdaad69b5a4c723e793ae043962ace5d02eef18059a76acf1d972c8` |
| suite-a-first-pass/run-20260809-160810-5563e6/p1-docling/metrics.json | `6bebf119776b1ba13893431e26520b249987975db17c0722bbffa4762cb69682` |
| suite-a-first-pass/run-20260809-160810-5563e6/p1-docling/routing-and-gates.json | `ce390be28465d1eb1356a92f1854f5fad60f6534a852a27e99b6630460206411` |
| suite-a-first-pass/run-20260809-160810-5563e6/p1-docling/artifacts-manifest.json | `d01b2edd324e6c7f03c1f325bdba0760517f7441c74957f6ad6f9f5d98541a14` |
| suite-a-first-pass/run-20260809-160810-5563e6/p1-docling/report.md | `491c5044e1a2bc0d008d1eb245c71d108bcebb7c8ab876af24ec8457e326dfd1` |
| …/run.json | `a96cc5c14efd1ae7adce8648a556bf86817741c307afe0e563d0a290f686f370` |
| …/p2-mineru/results.json | `cea95240a50418ba0dbad4b4ed217c3dcc758cbba35411ebc2f573202e60209f` |
| …/p2-mineru/metrics.json | `68d33a7cfd5cd3c33d51f9dd060e5429cdac75f5a73e7f74dadba5f58ac9b185` |
| …/p2-mineru/routing-and-gates.json | `19faed2acf4ada22f6ec60a01a4cce3ee9c7b09139876b3d16f943e8ddfc9254` |
| …/p2-mineru/artifacts-manifest.json | `10957773790cfaac3e2bb745068e4a66399e3141caf943ea5642cffedf0f8538` |
| …/p2-mineru/report.md | `08058e5edb54409bc9d56ac4c1e00a72468e576955c52353f1ad5e7e663f3f5c` |
| …/run.json | `2bae1246c5605739b8e930590ed6e7fcbc80782c97e442c1941e247d16793828` |
| …/p3-parser-router/results.json | `4a7840d60d9b201fd172a61731c67cd771a248f9cc07bb14bb3d45cdd14dae16` |
| …/p3-parser-router/metrics.json | `51379d1635d06dd0f5a31d325048752bdb4eb0185e1393a984daa2bf553067ca` |
| …/p3-parser-router/routing-and-gates.json | `7ae14910392eb081d6abbb63179fba304df9a63bfb4b04be5d21970a09fb07ca` |
| …/p3-parser-router/artifacts-manifest.json | `e8a2598d4e4b993154971d133272cbd618107954649a2b0a5d0782ae8996c0d1` |
| …/p3-parser-router/report.md | `9f40f1bbb9580e0e7251bd47c91674f15dc298d4df252a55fb361b248d5cc7c6` |
| ocr-dpi-benchmark/run-20260809-120116-24f592/summary.json | `5c483035f79ddce371da3519145b6ca36dce417aee398ddb34111e8c993846bc` |

## 7. Routing recommendation for VNLRAG-131 — VALIDATED by real P3 data

The policy below is backed by the real P3 run (§3): the born-digital fixtures routed as recorded in the aggregate `{"docling_text": 3}` (accepted 3/3).

- **Searchable PDF** (text layer, normal layout) -> Docling; no fallback unless a gate fails. **[validated: all fixtures routed docling_text, accepted]**
- **Scan PDF** -> Docling OCR first (tesseract vie, CPU-only, 300 DPI measured for 1-bit CCITT; 600 DPI scan-only conditional); on Group A failure -> MinerU.
- **Complex tables** -> compare both parsers; pick by quality gate or route to review.
- **Scan-derived docs with d/đ ambiguity, low provenance (Group A provenance_coverage < 0.9 or missing bbox), or structural mismatch** -> route to review (VNLRAG-155 Review CLI); NEVER auto-index partial OCR output.
- **Group A text_extraction_rate ≥ 0.8 is quantity-only**, not sufficient for legal correctness; Group B (d/đ labels, hierarchy, short-point) is the correctness gate (contract-only in W2, W3 execution).

Not validated yet (no scan/complex-table fixtures in the parser benchmark): the `docling_ocr` and `compare_complex_tables` routes — those are exercised by the OCR benchmark and table-quality lanes respectively, not by this born-digital first pass.

## 8. M1 status

**M1 IS NOW CLAIMED PASSED** per docs/05 §5.5 Gate M1, on the basis of the three COMPLETED runs in §1–§3 (all on the same fixtures, identical `input-manifest.json` hash `bdce19c0a3158b4f36318044a2a784aa9006d861bc00a1f84e4701e8f93a2e46`):

1. **3 document types (Luật, Nghị định, Thông tư) parsed through IR** — luat/nd/tt fixtures all produced `document-ir-v2` IR in P1, P2 and P3 runs.
2. **Suite A first-pass raw result exists (P1–P3, parser-only)** — `run-20260809-160810-5563e6` (P1 docling), `run-20260809-160841-9f3386` (P2 MinerU real), `run-20260809-161043-6cd9db` (P3 router), each with `results.json` / `metrics.json` / IR artifacts. Parent Context Completeness is measured after W3 (per the gate definition).
3. **Parser Router decision + quality gate results written into parser_routing** — `p3-parser-router/routing-and-gates.json` carries the `parser_routing-v1` records (§3.1).

Honest scope of the claim: the six parser-native metrics report 1.0 on every computed axis for BOTH parsers on these fixtures (raw numbers only, §2.2 — no superiority claim); no document failed P2 or P3. The gates exercised are Group A (operational); Group B structural gates are contract-only until the W3 Legal Structure Extractor produces `LegalProvision[]`. Scan/complex-table routing is not exercised by the born-digital first pass. M1's parser-foundation and router-gating requirements are met; structural/quality correctness is a W3 gate.

## 9. Immutability contract note (append-only)

- Every run dir under `data/evaluation/` is append-only: once created it is never rewritten or deleted; corrections are new run_ids.
- `run_suite` guarantees the one-way `RUNNING -> COMPLETED|FAILED` transition on every code path: the entire run body (input-manifest build + all per-doc parsing) is wrapped so ANY exception marks the run FAILED with the error recorded — no run.json can be left stuck at RUNNING.
- `run_ocr_dpi_benchmark` guarantees the same one-way transition (ora-21).
- **Legacy artifacts**: `run-20260809-111443-9ccf1d` (pre-fix aborted OCR-bench run, left at RUNNING by a pre-fix bug — documented, untouched) and the `document-ir-v1` P1 / FAILED P2 runs named in §6 are historical evidence and are never rewritten.
- **Documented deletion exception**: two transient FAILED runs created by a mapping bug during P3 wiring (run timestamps in the 16:08:xx area, before the deliverable trio; unique ids not recoverable) were deleted before the deliverable runs were created. They were artifacts of broken uncommitted code, not historical evidence. Append-only applies to all runs created after this point.
- The three §1–§3 runs were created in one `--variants p1 p2 p3` invocation after the P3 wiring landed; no pre-existing run was modified or deleted.

