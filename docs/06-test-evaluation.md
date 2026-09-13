# 06. Test and Evaluation

> **Status: UNVERIFIED / NOT RELEASE-READY (13 September 2026).** This is the executable evaluation guide for the audited MVP. It describes the current FastAPI/Next.js runtime and the checked-in evaluation artifacts; target or historical architecture is not treated as implemented.

## 1. Scope and non-negotiable release contract

The runtime under evaluation is:

- FastAPI `POST /api/v1/chat`, health/readiness, auth, user-owned chat, bookmarks, feedback, and legal explorer routes;
- Supabase Auth/REST for authentication and application persistence;
- Qdrant hybrid retrieval with OpenRouter-compatible dense embeddings and FastEmbed BM25, including exact metadata and temporal filtering plus bounded expansion;
- deterministic evidence/status/citation checks and one configured OpenRouter generator;
- Markdown/JSONL source loading from `data/sources/manifest.json` and `data/corpus/mds`, with derived chunks in `data/processed/chunks.jsonl`.

Query-time retrieval is corpus-only. Do not substitute web search, another model, another datastore, or a silent provider fallback when a dependency is unavailable.

The release gate uses a reviewed **40-case** fixture spanning exactly eight categories: `exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, and `out_of_scope`. Coverage is limited and no fixed numeric metric thresholds are imposed. Release still requires complete artifacts, semantic review, and safety/citation/operational gates.

Do not describe Parser Router/Docling/MinerU, Canonical IR, a legal relation database, PostgreSQL source of truth, Redis/Dramatiq, MinIO, LangGraph, Langfuse, production reranking, a six-verifier stack, upload/reviewer flows, or their test suites as active runtime checks. They are target or historical material only.

## 2. Setup and active smoke checks

Run from the repository root with the existing toolchains. These commands do not add services:

```bash
# Focused backend contract and regression suite
uv run --project backend pytest backend/tests -q

# Start the API in another terminal
uv run --project backend uvicorn app.main:app --host 127.0.0.1 --port 8000

# Liveness/readiness
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health/ready

# Frontend checks when frontend files are in the release scope
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Readiness must report the actual Supabase/Qdrant dependency state. A live chat requires the configured provider credentials and an authenticated Supabase token:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/chat \
  -H "Authorization: Bearer $TEST_BEARER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"question":"Xe máy vượt đèn đỏ bị phạt bao nhiêu?","top_k":5}'
```

Keep tokens and provider secrets out of artifacts. Record unavailable dependency/provider checks as unavailable; never turn them into a pass.

## 3. Active checks by layer

### 3.1 Deterministic backend and API checks

The maintained tests under `backend/tests/` cover the implemented ingestion metadata, reference parsing, temporal/evidence behavior, citation and response contracts, retrieval behavior, auth/session ownership, Supabase persistence, and route registration. Boundary cases include exact Điều/Khoản/Điểm references (including `d)` versus `đ)`), current/historical dates, cross-reference and follow-up questions, multi-intent and insufficient evidence, out-of-scope/provider failures, numeric claims, duplicate or malformed citation metadata, and user isolation.

The authenticated end-to-end contract check is:

```bash
uv run --project backend python backend/scripts/verify_release_authenticated.py
```

It uses configured test users and exercises legal list/provisions/search, authenticated chat, persisted transcript, rename/search/delete, and cross-user concealment. Treat missing credentials or external-service failure as an unavailable check, not as a successful substitute.

### 3.2 Corpus loading and Qdrant retrieval

The active source/index path is Markdown/JSONL:

```bash
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/index.py
```

`backend/scripts/ingest.py` is not a general PDF extractor; it fails when a PDF checkpoint is absent and directs operators to the tracked Markdown fetch path. After indexing, the retrieval probe can be run against a question fixture:

```bash
uv run --project backend python backend/scripts/eval.py <questions.json> --top-k 8
```

Record collection name, source/chunk hashes, embedding model and dimensions, sparse encoder, Qdrant endpoint/path, and provider reachability. Check exact-reference priority, temporal filtering, hybrid fusion, diversity, bounded expansion, and empty/insufficient-evidence outcomes. Qdrant is derived state, not the legal source of truth.

### 3.3 Browser smoke

When frontend evidence is claimed, manually exercise the existing chat, conversation/history, citation/source viewer, legal search, auth, saved-item, and LIKE/DISLIKE flows against the API build tested above. Record route, HTTP status, readiness state, redacted console error, and trace ID for every failure. A browser smoke does not replace the full gold gate.

## 4. Diagnostic 40-case evaluation

The checked-in 40-case fixture is exactly:

```text
data/evaluation/thesis-gold-40.json
```

It contains 40 cases, five in each of the runner's eight categories: `exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, and `out_of_scope`. It is a limited-coverage diagnostic fixture; it is the release evaluation fixture, but cannot be interpreted as comprehensive legal-question coverage.

Run the HTTP diagnostic from a live authenticated API:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --top-k 5 \
  --timeout 300 \
  --output-dir data/evaluation/thesis-run
```

The runner obtains a test token when `TEST_BEARER_TOKEN` is absent. To score an existing prediction JSONL instead of calling the API:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --predictions path/to/predictions.jsonl \
  --output-dir data/evaluation/thesis-score
```

The runner requires all 40 case IDs and writes append-only JSONL plus an aggregate JSON. Preserve raw output and errors; do not rewrite frozen fixture or prior run artifacts.

### Result semantics

- **`true` / `false`**: the metric was computable for that case and the observed outcome matched or did not match the gold expectation.
- **`null`**: the metric is not computable or not observed. This includes no gold IDs for a coordinate level, a timeout/error/failed request, and manual semantic correctness before human review. `null` is not zero and must not be counted as a pass or failure without an explicit denominator.
- **API `ERROR`, `FAILED`, or `TIMEOUT`**: the request did not produce a completed prediction. Keep the error and case ID in raw/error artifacts; do not infer answer status, citations, abstention, or correctness.
- **Abstention accuracy**: the runner treats `INSUFFICIENT_EVIDENCE` and `OUT_OF_SCOPE` as abstention. Other statuses are non-abstention. A timeout/error is `null`.
- **Citation validity**: it is `null` for timeout/error; otherwise citations must exist when gold provisions are expected and each citation must resolve to a canonical coordinate. An empty citation list is valid only when no provision is expected.
- **`answer_correctness_manual`**: always starts `null` and becomes boolean only through a documented human semantic review. The diagnostic runner never infers it from generated text or citation flags.

Metrics must be reported with their observed denominators and broken down by category/status. Never infer comprehensive legal coverage, semantic correctness, or release readiness from this runner; no fixed numeric threshold is defined in the release contract.

## 5. Current diagnostic evidence and disposition

The fresh full diagnostic run is identified by run ID `20260913T172158Z`. It exercised all 40 cases against `POST /api/v1/chat` with `top_k=5`; raw JSONL and aggregate artifacts are `/tmp/thesis-release-full/20260913T172158Z.jsonl` and `/tmp/thesis-release-full/20260913T172158Z.aggregate.json`.

| Metric | Fresh 40-case result |
|---|---:|
| Retrieval hit@5 | 0.0 |
| Document / article / clause / point accuracy | 0.0 / 0.0 / 0.0 / 0.0 |
| Citation validity | 0.7368 |
| Abstention accuracy | 0.6579 |
| Latency mean / P50 / P95 | 23096.09 / 11024.33 / 63738.4 ms |
| Timeout/null predictions | Cases 08 and 20 |

Manual semantic strict review found **19 correct, 9 partial, 8 incorrect, and 4 unavailable**. Relative to the earlier subset, the fixes improved API success and latency, but retrieval and legal-coordinate metrics remain zero, citation validity fails the hard gate, and incorrect/partial semantic outcomes remain. Disposition is **UNVERIFIED / NOT RELEASE-READY**; the active acceptance contract is unchanged.

The earlier 32/40 API subset report [`docs/evaluation/thesis-api-subset-32-20260913.md`](evaluation/thesis-api-subset-32-20260913.md) is retained as historical diagnostic evidence: 3 calls errored, retrieval hit@5 was `0.1905`, citation validity `0.6552`, abstention accuracy `0.4483`, and P95 latency `84,036.78 ms`; semantic review was not performed. It must not be merged with or used instead of the fresh run.

The separate 40-row report [`docs/evaluation/thesis-api-run-20260913T113553Z.md`](evaluation/thesis-api-run-20260913T113553Z.md) contains 39 predictions and one timeout. Its emitted aggregate is explicitly unreliable because of scorer identity/category aggregation defects; its independent recomputation is still only a recomputation of recorded flags, not semantic correctness. Disposition: `UNVERIFIED / NOT RELEASE-READY`.

The checked-in rerun manifest under `data/evaluation/final/release-20260912-rerun/` is also `AUTOMATED_FAIL`: three cases have no completed prediction and manual answer correctness is unmeasured. Preserve these artifacts as provenance; do not merge their numbers into a release score.

## 6. Release integrity and gate

The checked-in evaluation artifacts and runner must be used without modifying the frozen fixture. The run must execute all 40 cases against the pinned corpus/index, model/config/prompt and commit, preserve every response/error, and include deterministic metrics, category/status breakdowns, error analysis, required semantic review, and an immutable run manifest containing all relevant hashes.

A release is blocked unless all of the following evidence exists:

1. The frozen 14-PDF candidate corpus has verified identity/file hashes, allowlist provenance, and accepted publish evidence.
2. The complete 40-case run covers all eight categories and reports honest denominators and limited coverage.
3. Retrieval, evidence completeness, temporal validity, citation/claim/numeric grounding, abstention, and latency metrics are reported from preserved raw outputs.
4. Deterministic citation safety holds for the release run; unsupported or wrong-period claims fail closed.
5. All release-run errors are classified, required semantic review is complete, and manual browser/auth/session/persistence checks pass for the shipped build.

Missing any required artifact, review, or safety/citation gate keeps the status `UNVERIFIED / NOT RELEASE-READY`. No fixed numeric threshold substitutes for judgment across these gates.


## 7. Historical and optional material

Reports under `docs/evaluation/` may preserve parser benchmarks, RAGFlow comparisons, or earlier experiment outputs. Cite them as dated provenance only. They do not establish current runtime capabilities or release gates. Optional semantic/judge experiments may supplement deterministic evidence when actually run, but provider failure is unavailable and no external evaluator replaces the 40-case gate.
