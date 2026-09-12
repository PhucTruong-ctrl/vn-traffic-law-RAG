# 06. Kiểm Thử và Đánh Giá (Test and Evaluation)

> **Active MVP baseline, 12/09/2026.** This document is the executable evaluation guide for the current rescue MVP. The runtime is a Next.js 16 / React 19 frontend, a FastAPI backend on Python 3.11, Supabase REST/Auth for application persistence, local Qdrant 1.19 hybrid retrieval (OpenRouter dense embeddings + FastEmbed BM25), one configured OpenRouter generator, deterministic evidence/citation/temporal gates, and a Markdown/PDF legal explorer. The query path is corpus-only: no web or external retrieval, autonomous agents, LangGraph, Redis, MinIO, PostgreSQL app-owned runtime, or seven-service topology.
>
> **Historical material.** Thesis plans, old reports, and design notes may mention other providers, worker queues, RAGFlow, Langfuse, PostgreSQL, or larger suites. Those passages provide historical or deferred context only, not active release requirements. Never rewrite frozen gold-set data or historical raw results; label their status instead.

## 1. Active release contract

The active release evidence consists of the checked-in corpus, deterministic evaluation fixtures, focused backend tests, API smoke tests, and the available 40-case thesis evaluator. Do not claim a full 200-question or 14-document run unless raw artefacts and outputs exist for that run. Report unavailable metrics as `N/A`/unavailable; never turn missing evidence into a score.

The active correctness contract is:

- `POST /api/v1/chat` is the grounded legal-query route.
- `GET /api/v1/health`, `/api/v1/health/live`, and `/api/v1/health/ready` expose liveness/readiness without credentials.
- Retrieval is local Qdrant hybrid search: OpenRouter dense embeddings plus FastEmbed BM25, fused with RRF and bounded expansion.
- The generator receives only evidence accepted by deterministic checks.
- Returned citations are metadata-derived and must identify supported provisions; unsupported, temporally invalid, or unaccepted citations are blocked.
- Missing evidence, unsupported corpus questions, out-of-scope requests, and provider failures fail closed with the implemented status/reason code rather than an invented answer.
- Supabase is the application persistence/auth boundary for profiles, chat sessions, messages, feedback, and bookmarks. Qdrant is derived retrieval state; source Markdown/PDF and manifest artefacts remain the corpus inputs.
- The frontend consumes the API and provides chat plus Markdown/PDF legal-source exploration; browser checks are smoke checks, not a prerequisite for backend unit metrics.

## 2. Executable setup and smoke checks

Run commands from the repository root. Use the repository's existing `uv` and npm toolchains. Do not add services to make a check pass.

```bash
# Backend focused tests
uv run --project backend pytest backend/tests -q

# Backend API (separate terminal)
uv run --project backend uvicorn app.main:app --host 127.0.0.1 --port 8000

# Health checks
curl -fsS http://127.0.0.1:8000/api/v1/health
curl -fsS http://127.0.0.1:8000/api/v1/health/live
curl -fsS http://127.0.0.1:8000/api/v1/health/ready

# Frontend type/build checks, when frontend changes are in scope
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

The ready response reports Supabase/Qdrant dependency status. A configured OpenRouter key is required for a live generation/embedding smoke, and provider errors must remain fail-closed. For an authenticated chat smoke, obtain a Supabase access token through the configured auth flow and send it as `Authorization: Bearer <token>`:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/chat \
  -H "Authorization: Bearer $TEST_BEARER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"question":"Xe máy vượt đèn đỏ bị phạt bao nhiêu?","top_k":5}'
```

Use only non-secret redacted output in reports. If the local corpus or provider is unavailable, record the smoke as unavailable; do not substitute web search, another model, or another datastore.

## 3. Test layers

### 3.1 Unit and deterministic tests

Unit tests cover manifest/source metadata, Markdown/PDF ingestion adapters, legal-reference parsing, chunk metadata, temporal intervals, evidence planning, citation validation, abstention/status mapping, and metric calculations. Deterministic modules provide the main correctness evidence. A scoped coverage run may be used for the currently implemented modules, but the old blanket 80% claim is not an active release gate unless the repository's current test configuration explicitly enables it.

Required boundary cases include:

- exact `Điều`/`Khoản`/`Điểm` references and Vietnamese `d)` versus `đ)` labels;
- current and historical `effective_date` queries;
- compound questions requiring multiple evidence types;
- cross-reference and follow-up questions;
- `CORPUS_NOT_COVERED`, `OUT_OF_SCOPE`, `INSUFFICIENT_EVIDENCE`, and provider-unavailable outcomes;
- duplicate citation IDs, missing citation metadata, unaccepted provisions, and temporally invalid provisions;
- numeric grounding for monetary penalties, licence points, dates, ages, durations, and quantities.

Do not describe a LangGraph repair workflow, Dramatiq actor, Redis retry queue, MinIO bucket round-trip, or PostgreSQL migration test as active: those are superseded design material.

### 3.2 Qdrant retrieval checks

The active retrieval smoke uses the local Qdrant 1.19 client and the configured collection (default `traffic_law`, path from `QDRANT_PATH`). Rebuild derived vectors with the repository indexing script after regenerating chunks:

```bash
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/index.py
```

Verify dense OpenRouter vectors, FastEmbed BM25 sparse vectors, payload metadata, temporal filtering, exact-reference priority, RRF fusion, document diversity, and empty/insufficient-evidence behavior. Record the Qdrant version, collection name, source/chunk hash, embedding model/dimensions, sparse encoder version, and whether OpenRouter was reachable.

### 3.3 Supabase persistence and auth checks

Supabase REST/Auth is the only application persistence boundary. Focused checks must cover registration/login/current-user behavior, bearer-token enforcement, session/message ownership, feedback, bookmark save/list/status/delete, and response/citation/metadata JSON payload persistence. Do not call these PostgreSQL application-runtime tests; Supabase may use PostgreSQL internally, but the application contract is Supabase REST/Auth.

### 3.4 API and frontend smoke checks

Exercise `/api/v1/chat`, the health/readiness routes, auth routes, chat-session routes, bookmark routes, and legal explorer/search routes exposed by `backend/app/main.py`. Confirm that the Next.js frontend resolves its API base, sends the bearer token, renders verified/abstention states, and opens Markdown/PDF source links. Report a browser failure with its route, HTTP status, readiness state, redacted console error, and backend trace ID. Do not hide it by retrying another route.

## 4. Frozen evaluation data and metrics

Frozen corpus manifests, source hashes, parser fixtures, and gold-set files are inputs, not tuning targets. Align predictions by `question_id`; preserve every failure in raw output and error analysis. Active deterministic metrics include retrieval hit/Recall@k where gold IDs exist, citation validity/precision/recall, evidence completeness, temporal validity, abstention/status accuracy, numeric grounding, and latency. Break metrics down by category and status; an aggregate must not conceal historical, comparison, out-of-scope, or insufficient-evidence failures.

The checked-in thesis interface is executable for the available dataset:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/gold-sets/thesis-evaluation.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --top-k 5 \
  --output-dir data/evaluation/thesis
```

The runner stores append-only JSONL and aggregate JSON output. It can instead score a complete prediction JSONL with `--predictions`; missing predictions are an error, not an omitted case. The active runner's dataset size and schema are authoritative. Do not infer a 200-question release result from a 40-case run.

### 4.1 Suite A parser reports

Suite A reports under `docs/evaluation/` are historical parser benchmarks over immutable fixtures. They provide provenance for parser behavior and OCR observations, but they do not show that the current MVP has a seven-service ingestion pipeline or that a parser benchmark is a release gate. Re-run only when the corresponding suite implementation and immutable artefacts are present; use the command recorded in that report and label the run date, fixture hash, parser versions, and unavailable lanes.

### 4.2 Optional semantic metrics

Ragas, online judges, Langfuse, and external RAGFlow comparisons are optional thesis experiments. They are not required for the active MVP and do not replace deterministic evidence/citation/temporal gates; provider failure is reported unavailable. There is one active OpenRouter generator. Do not report multiple-generator routing or silent provider fallback.

## 5. Acceptance gates

A release candidate is supported only when the following evidence exists:

1. Focused backend tests pass for deterministic contracts and the implemented API routes.
2. Qdrant hybrid retrieval returns expected local-corpus provisions for the checked-in smoke cases.
3. Supabase auth/persistence checks pass for ownership and saved-Q&A payloads.
4. `/api/v1/chat` returns verified answers with valid citations or a truthful fail-closed status; invalid citation rate at the API boundary is zero for the exercised cases.
5. Temporal and evidence gates block unsupported or wrong-period claims.
6. Provider failures are observable and fail closed without substituting a different provider.
7. Frontend type/build and a representative browser chat/legal-explorer smoke pass when frontend release evidence is claimed.
8. Corpus, source, chunk, and frozen-gold hashes are recorded; no frozen artefact is rewritten.

Do not make Docker clean-start, PostgreSQL/Redis/MinIO snapshots, worker queues, external retrieval, agent workflows, RAGFlow, Langfuse, or a full 14-document/200-question suite acceptance blockers. If historical documents list them as gates, retain them as dated historical claims and supersede them here.

## 6. Historical provenance note

Older sections and reports in this repository were written for a thesis architecture with Parser P1–P3, embedding/retrieval/generation ablations, PostgreSQL-owned ingestion state, Redis/Dramatiq, MinIO, LangGraph repair, RAGFlow, Langfuse, and seven-service Compose. Those records remain for provenance. They do not describe the active runtime and must be read with the current baseline at the top of this document.
