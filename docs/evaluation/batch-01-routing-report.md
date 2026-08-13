# Batch 01 Routing Report — VNLRAG-35 (W3, routing-only)

- Artifact: `data/ingestion/batch-01-routing.json` (version `batch-01-routing-v1`)
- Generated at: `2026-08-13T22:30:22.440197+00:00` (UTC)
- Command: `cd backend && uv run python scripts/run_batch01_routing.py`
- Base commit: `22e740d9c737c068802b1d4f3733f8cb808d51f5`

## 1. Scope — W3 routing-only, NO indexing

This run executes the batch-01 ingestion pipeline **up to review routing only** (doc 05 §5.6, 09/08 row: “Chạy pipeline ingestion tới quality gate và review routing trên batch 01; accept+index E2E chưa chốt vì resolver có từ W4”). **NO indexing was performed**; Gate M2 (accept+index E2E) is **not** closed and is deferred to VNLRAG-154/W4 (doc 05 §5.6 Gate M2 note). No provision may be indexed without a resolver-derived effective interval (VNLRAG-136, W4); ACCEPTED routing decisions here are provisional and stay PENDING for indexing until the W4 resolvers assign final intervals.

## 2. Inputs and method

Real OCR of the scan-only batch-01 PDFs (1-bit CCITT, no text layer) is infeasible for this W3 run (≈30 s/page at 300 DPI, 100+ page documents; VNLRAG-20/97). Per the ticket, the pipeline ran on the **committed fixture text / extracted IR where real OCR is infeasible — the exact input used per document is recorded in the artifact (`extraction_input`) and in the table below.** Only `luat-36-2024-qh15` has a born-digital text layer; its fixture is a genuine excerpt of that text. `nd-168-2024`’s fixture is a curated excerpt stand-in (NOT real OCR output), so its routing Group A is marked failed on extraction/provenance grounds (scan-review policy, `docs/parser_router.yaml`) → `LOW_OCR_COVERAGE`.

| document_id | source PDF | extraction input | notes |
|---|---|---|---|
| `nd-168-2024` | scan-only 1-bit CCITT (no text layer) | `fixture_text_excerpt` (`backend/tests/fixtures/parser_benchmark/documents/nd/nd-168-2024-fixture.pdf.txt`) | 2025-01-01 → ∞ |
| `nd-100-2019` | scan-only 1-bit CCITT (no text layer) | `none_available` | 2020-01-01 → ∞ |
| `luat-36-2024-qh15` | born-digital text layer | `fixture_text_excerpt` (`backend/tests/fixtures/parser_benchmark/documents/luat/luat-traffic-2024-fixture.pdf.txt`) | 2025-01-01 → ∞ |
| `tt-79-2024` | scan-only 1-bit CCITT (no text layer) | `none_available` | 2025-01-01 → ∞ |
| `tt-24-2023` | scan-only 1-bit CCITT (no text layer) | `none_available` | 2023-08-15 → 2025-01-01 |

## 3. Per-document routing summary

| document_id | Group A (routing basis) | Group B | provisions | ACCEPTED | NEEDS_REVIEW | DROPPED | decision | reason codes |
|---|---|---|---|---|---|---|---|---|
| `nd-168-2024` | failed | passed | 58 | 0 | 58 | 0 | **NEEDS_REVIEW** | LOW_OCR_COVERAGE, D_D_AMBIGUITY |
| `nd-100-2019` | n/a | n/a | 0 | 0 | 0 | 0 | **NEEDS_REVIEW** | LOW_OCR_COVERAGE |
| `luat-36-2024-qh15` | passed | passed | 25 | 22 | 3 | 0 | **NEEDS_REVIEW** | POINT_LABEL_AMBIGUOUS, D_D_AMBIGUITY |
| `tt-79-2024` | n/a | n/a | 0 | 0 | 0 | 0 | **NEEDS_REVIEW** | LOW_OCR_COVERAGE |
| `tt-24-2023` | n/a | n/a | 0 | 0 | 0 | 0 | **NEEDS_REVIEW** | LOW_OCR_COVERAGE |

Aggregate: 5/5 documents routed; provisions {'ACCEPTED': 22, 'NEEDS_REVIEW': 61, 'DROPPED': 0}.

The document-level decision mirrors the quality-gate actor job outcome (`actors/quality_gate.py`): any NEEDS_REVIEW provision -> document NEEDS_REVIEW (PENDING_REVIEW — embed/index never runs); else any DROPPED -> DROPPED; else all ACCEPTED -> ACCEPTED. A document can therefore carry ACCEPTED provisions and still route NEEDS_REVIEW as a whole.

## 4. Extraction quality stats

Per-document stats below reuse the corpus QA metrics (`app.evaluation.corpus_qa.run_corpus_qa`, 16 FR-10 metrics) plus Group B structural metrics. **Caveat:** metrics are measured on the extraction input actually used (fixture excerpt or empty); they do not certify the scan-only source PDFs.

| document_id | provisions (A/C/P) | point-label detection | đ) detection | provenance coverage | parent-context coverage | short-point retention |
|---|---|---|---|---|---|---|
| `nd-168-2024` | 58 (3/11/44) | 1.000 | 0.114 | 1.000 | 0.948 | 0.000 |
| `nd-100-2019` | 0 (0/0/0) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `luat-36-2024-qh15` | 25 (4/8/13) | 0.923 | 0.154 | 1.000 | 1.000 | 1.000 |
| `tt-79-2024` | 0 (0/0/0) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |
| `tt-24-2023` | 0 (0/0/0) | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

Highlights:

- `luat-36-2024-qh15` extracts cleanly from born-digital text (Group A passed, Group B passed); {luat_states['ACCEPTED']}/25 provisions route ACCEPTED (auto-accept), the exceptions being the d/đ-ambiguous bare `d)` labels (`D_D_AMBIGUITY`, 2) and the out-of-primary-run `g)` label (`POINT_LABEL_AMBIGUOUS`, 1).
- `nd-168-2024` measures 1.0 on the fixture IR but the source is scan-only: every provision routes NEEDS_REVIEW (`LOW_OCR_COVERAGE`, 58; plus `D_D_AMBIGUITY` on the 6 bare `d)` points).
- `nd-100-2019`, `tt-79-2024`, `tt-24-2023`: no extraction input in this W3 run — zero provisions, document-level NEEDS_REVIEW (`LOW_OCR_COVERAGE`).

## 5. Review backlog summary

**61 provisions route NEEDS_REVIEW** in batch 01 (the would-be `ReviewItem` rows, status PENDING, that the quality-gate actor (`actors/quality_gate.py`) creates in the queue flow; no database is touched by this W3 script). They are reviewed with the review CLI (`backend/scripts/review_item.py`, VNLRAG-155) once the queue flow persists them. Full item list (provision_id + reason codes) is in the artifact (`documents.<id>.review_backlog.items`).

| document_id | review items | reason histogram |
|---|---|---|
| `nd-168-2024` | 58 | {'D_D_AMBIGUITY': 6, 'LOW_OCR_COVERAGE': 58} |
| `nd-100-2019` | 0 | — |
| `luat-36-2024-qh15` | 3 | {'D_D_AMBIGUITY': 2, 'POINT_LABEL_AMBIGUOUS': 1} |
| `tt-79-2024` | 0 | — |
| `tt-24-2023` | 0 | — |

## 6. Manifest update (sidecar)

The frozen schema `templates/corpus-manifest.schema.json` uses `additionalProperties: false` and does not allow ingestion-result fields, so the manifests are **unchanged** and the ingestion results live in the sidecar artifact `data/ingestion/batch-01-routing.json` (per the ticket: “if the schema doesn’t allow ingestion-result fields, add a separate sidecar … and note why; do NOT change the frozen schema”). All five manifests still validate:

    `uv run python -m scripts.validate_manifest ../data/manifests/batch-01/nd-168-2024.manifest.json` → PASS
    `uv run python -m scripts.validate_manifest ../data/manifests/batch-01/nd-100-2019.manifest.json` → PASS
    `uv run python -m scripts.validate_manifest ../data/manifests/batch-01/luat-36-2024-qh15.manifest.json` → PASS
    `uv run python -m scripts.validate_manifest ../data/manifests/batch-01/tt-79-2024.manifest.json` → PASS
    `uv run python -m scripts.validate_manifest ../data/manifests/batch-01/tt-24-2023.manifest.json` → PASS

## 7. Reproducibility

```bash
# 1. Run the pipeline (regenerates artifact + this report)
cd backend && uv run python scripts/run_batch01_routing.py
# 2. Tests for the script’s pure helpers
cd backend && uv run pytest tests/test_run_batch01_routing.py --no-cov -q
```

- Routing artifact: `data/ingestion/batch-01-routing.json`
- Report: `docs/evaluation/batch-01-routing-report.md` (this file, generated)
- Script: `backend/scripts/run_batch01_routing.py`
- Tests: `backend/tests/test_run_batch01_routing.py`

### Verification (recorded at commit time)

- Test output verbatim (14/14 passed, `cd backend && uv run pytest tests/test_run_batch01_routing.py --no-cov -v`):

```
============================= test session starts ==============================
platform linux -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0 -- /home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase16/backend/.venv/bin/python
cachedir: .pytest_cache
rootdir: /home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase16/backend
configfile: pyproject.toml
plugins: langsmith-0.10.17, anyio-4.14.2, asyncio-1.4.0, cov-7.1.0, Faker-40.36.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 14 items

tests/test_run_batch01_routing.py::test_build_ir_from_lines_creates_valid_document PASSED [  7%]
tests/test_run_batch01_routing.py::test_build_ir_from_lines_preserves_given_lines PASSED [ 14%]
tests/test_run_batch01_routing.py::test_apply_manifest_interval_effective_is_uniform PASSED [ 21%]
tests/test_run_batch01_routing.py::test_apply_manifest_interval_partial_and_expired_untouched PASSED [ 28%]
tests/test_run_batch01_routing.py::test_apply_manifest_interval_missing_from_untouched PASSED [ 35%]
tests/test_run_batch01_routing.py::test_certifying_group_a_born_digital_passes_through PASSED [ 42%]
tests/test_run_batch01_routing.py::test_certifying_group_a_scan_only_fails_extraction_gates PASSED [ 50%]
tests/test_run_batch01_routing.py::test_aggregate_routing_counts_states_and_reasons PASSED [ 57%]
tests/test_run_batch01_routing.py::test_aggregate_routing_empty PASSED   [ 64%]
tests/test_run_batch01_routing.py::test_document_level_decision_mirrors_actor_outcome PASSED [ 71%]
tests/test_run_batch01_routing.py::test_document_level_decision_no_provisions_routes_review PASSED [ 78%]
tests/test_run_batch01_routing.py::test_quality_stats_for_computes_ticket_metrics PASSED [ 85%]
tests/test_run_batch01_routing.py::test_quality_stats_for_empty_provision_set PASSED [ 92%]
tests/test_run_batch01_routing.py::test_render_report_contains_required_content PASSED [100%]

============================== 14 passed in 0.10s ==============================
```

- Dependent-module sanity (routing/gates/corpus-qa/enricher, unchanged code): `uv run pytest tests/test_review_routing.py tests/test_quality_gates.py tests/test_corpus_qa.py tests/test_context_enricher.py --no-cov -q` → `122 passed in 1.47s`.
- Manifest validation (unchanged manifests, `cd backend && uv run python -m scripts.validate_manifest ../data/manifests/batch-01/<id>.manifest.json`): PASS × 5 (see §6).
- Commit hash: recorded after commit (see the final line of this report).

- Final commit hash: `(filled after commit)`
