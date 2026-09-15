# 06. Test and evaluation

> **Status: RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME (14 September 2026).**
> This guide describes the current FastAPI/Next.js runtime and checked artifacts.
> It does not claim complete legal coverage or full human semantic certification.

## 1. Scope and non-negotiable release contract

The runtime under evaluation is:

- FastAPI `POST /api/v1/chat`, health/readiness, auth, user-owned chat, bookmarks, feedback, and legal explorer routes;
- Supabase Auth/REST for authentication and application persistence;
- Qdrant tìm kiếm kết hợp (hybrid) with OpenRouter-compatible dense embeddings and FastEmbed BM25, including exact metadata and temporal filtering plus bounded expansion;
- kiểm tra tất định gồm phân loại route (legal/chitchat/out-of-scope), từ chối trả lời trước generation theo taxonomy, và làm sạch trích dẫn citation/claim ở đầu ra;
- Markdown/JSONL source loading from `data/sources/manifest.json` and `data/corpus/mds`, with derived đoạn dữ liệus in `data/processed/chunks.jsonl`.

Query-time truy xuất is corpus-only. Do not substitute web search, another model, another datastore, or a silent nhà cung cấp mô hình phương án dự phòng when a dependency is unavailable.

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

Readiness must report the actual Supabase/Qdrant dependency state. A live chat requires the configured nhà cung cấp mô hình credentials and an authenticated Supabase token:

```bash
curl -fsS http://127.0.0.1:8000/api/v1/chat \
  -H "Authorization: Bearer $TEST_BEARER_TOKEN" \
  -H 'Content-Type: application/json' \
  --data '{"question":"Xe máy vượt đèn đỏ bị phạt bao nhiêu?","top_k":5}'
```

Keep tokens and nhà cung cấp mô hình secrets out of artifacts. Record unavailable dependency/nhà cung cấp mô hình checks as unavailable; never turn them into a pass.

## 3. Active checks by layer

### 3.1 Deterministic backend and API checks

The maintained tests under `backend/tests/` cover the implemented ingestion metadata, reference parsing, temporal behavior, citation and response contracts, truy xuất behavior, auth/session ownership, Supabase persistence, and route registration. Runtime deterministic checks consist of route classification (`legal`/`chitchat`/`out-of-scope`), taxonomy-based từ chối trả lời before generation, and output citation/claim làm sạch trích dẫn. The system may return a partial answer: it removes only citations or claims that do not match tìm kiếm căn cứd metadata, and refuses the whole response only when no relevant documents exist or the bộ sinh câu trả lời returns `CANONICAL_REFUSAL`. Boundary cases include exact Điều/Khoản/Điểm references (including `d)` versus `đ)`), current/historical dates, cross-reference and follow-up questions, multi-intent and insufficient evidence, out-of-scope/nhà cung cấp mô hình failures, numeric claims, duplicate or malformed citation metadata, and user isolation.

The authenticated end-to-end contract check is:

```bash
uv run --project backend python backend/scripts/verify_release_authenticated.py
```

It uses configured test users and exercises legal list/provisions/search, authenticated chat, persisted transcript, rename/search/delete, and cross-user concealment. Treat missing credentials or external-service failure as an unavailable check, not as a successful substitute.

### 3.2 Corpus loading and Qdrant truy xuất

The active source/index path is Markdown/JSONL:

```bash
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/index.py
```

`backend/scripts/ingest.py` is not a general PDF extractor; it fails when a PDF checkpoint is absent and directs operators to the tracked Markdown fetch path. After indexing, the truy xuất probe can be run against a question fixture:

```bash
uv run --project backend python backend/scripts/eval.py <questions.json> --top-k 8
```

Record collection name, source/đoạn dữ liệu hashes, embedding model and dimensions, sparse encoder, Qdrant endpoint/path, and nhà cung cấp mô hình reachability. Check exact-reference priority, temporal filtering, hybrid fusion, diversity, bounded expansion, and empty/insufficient-evidence outcomes. Qdrant is derived state, not the legal source of truth.

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
- **API `ERROR`, `FAILED`, or `TIMEOUT`**: the request did not produce a completed prediction. Keep the error and case ID in raw/error artifacts; do not infer answer status, citations, từ chối trả lời, or correctness.
- **Abstention độ chính xác**: the runner treats `INSUFFICIENT_EVIDENCE` and `OUT_OF_SCOPE` as từ chối trả lời. Other statuses are non-từ chối trả lời. A timeout/error is `null`.
- **Citation validity**: it is `null` for timeout/error; otherwise citations must exist when gold provisions are expected and each citation must resolve to a canonical coordinate. An empty citation list is valid only when no provision is expected.
- **`answer_correctness_manual`**: always starts `null` and becomes boolean only through a documented human semantic review. The diagnostic runner never infers it from generated text or citation flags.

Metrics must be reported with their observed denominators and broken down by category/status. Never infer comprehensive legal coverage, semantic correctness, or release readiness from this runner; no fixed numeric threshold is defined in the release contract.

## 5. Kết quả lần chạy 15/09/2026 (pipeline v2)

Run4 dùng pipeline v2 với `GENERATION_MODEL=ANALYZER_MODEL=google/gemini-2.5-flash-lite`, `top_k=5`, run ID `20260915T075654Z`, aggregate tại `data/evaluation/rebuild-20260915-run4/20260915T075654Z.aggregate.json`. Có 40 case, trong đó 34 case được corpus bao phủ; sáu case bị loại vì corpus chưa bao phủ: `thesis-gold-40-00`, `thesis-gold-40-15`, `thesis-gold-40-16`, `thesis-gold-40-17`, `thesis-gold-40-18`, `thesis-gold-40-19`.

| Chỉ số run4                  |     Giá trị |
| ---------------------------- | ----------: |
| count                        |          40 |
| covered_count                |          34 |
| truy xuất_hit_at_k           |        0.25 |
| document_độ chính xác        |        0.50 |
| article_độ chính xác         |      0.4167 |
| clause_độ chính xác          |      0.3846 |
| point_độ chính xác           |         0.0 |
| citation_validity            |      0.8824 |
| từ chối trả lời_độ chính xác |      0.7059 |
| answer_correctness_manual    |   chưa chấm |
| độ trễ mean                  |   8304.6 ms |
| độ trễ p50                   |  8359.09 ms |
| độ trễ p95                   | 11577.15 ms |

Tài liệu chỉ ghi kết quả của lần chạy mới nhất; artifact: `data/evaluation/rebuild-20260915-run4/20260915T075654Z.aggregate.json`.

## 6. Release integrity and gate

Release artifacts must preserve raw outputs, corpus coverage classification,
metric denominators, configuration, code revision, and reproduction command.
Do not modify the frozen gold set or count missing-corpus rows as truy xuất
successes or failures. Public deployment hardening and full semantic review are
outside the current MVP release claim.

## 7. Historical and optional material

Reports under `docs/evaluation/` may preserve parser benchmarks, RAGFlow comparisons, or earlier experiment outputs. Cite them as dated provenance only. They do not establish current runtime capabilities or release gates. Optional semantic/judge experiments may supplement deterministic evidence when actually run, but nhà cung cấp mô hình failure is unavailable and no external evaluator replaces the 40-case gate.
