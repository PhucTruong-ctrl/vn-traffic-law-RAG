# VN Traffic Law RAG (VNLRAG)

Runnable MVP for Vietnamese traffic-law questions. The active product combines a
dual-source legal explorer with grounded chat:

```text
Markdown manifest + local PDFs -> legal documents/provisions -> local Qdrant HYBRID
                                                        -> ChatOpenRouter -> citations
```

## Quick start

Canonical local startup uses `dev.sh`:

```bash
cp .env.example .env
# Fill server and public Supabase/OpenRouter values in .env.
./dev.sh
```

Open `http://127.0.0.1:3000`. Supabase provides registration/login and stores
profiles, chat sessions, messages, feedback, and bookmarks. Browser receives
only public Supabase values; backend requires service-role credentials. Never
commit `.env` or keys.

Docker Compose is optional deployment tooling and currently starts only the
frontend, backend, and Qdrant services:

```bash
docker compose --env-file .env -f deploy/compose/compose.release.yml up --build
```

Supabase/PostgreSQL and OpenRouter remain external dependencies when configured;
worker, Redis, MinIO, and parser services are not part of the active MVP runtime.

For ingestion or a backend-only development loop, install the backend and run
the existing scripts directly:

```bash
uv sync --project backend
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/index.py
uv run --project backend uvicorn app.main:app --reload
```

`fetch_sources.py` reads `data/sources/manifest.json`, resolves each entry to a
Markdown file under `data/corpus/mds/`, and writes
`data/processed/chunks.jsonl`. Use `--manifest`, `--local-dir`, and `--output`
to override those paths. `index.py` creates a fresh local Qdrant collection
from that JSONL. Retrieval combines dense OpenRouter embeddings with sparse
FastEmbed BM25 (`Qdrant/bm25`) using LangChain Qdrant `HYBRID` mode. Qdrant
path and collection are configured by `QDRANT_PATH` and `QDRANT_COLLECTION`.

## Legal source explorer

The `/legal-sources` page lists documents exposed by the legal API and supports
text, document-number, and article filtering. API-backed search is available at
`GET /api/v1/legal-search?q=...` with optional `document_id`, `article`, `clause`,
`point`, and bounded `limit` filters. Document and provision routes, together with
citation metadata, provide deep links to a provision or its Markdown/PDF passage.
Markdown sources are rendered as structured legal text; PDF sources are rendered
in the in-app PDF viewer with page navigation, zoom, and citation-coordinate
highlighting when metadata is available. The explorer is read-only and corpus-only:
it does not perform query-time web retrieval.


## Grounded chat and citations

Set `OPENROUTER_API_KEY` and optionally `OPENROUTER_BASE_URL` in `.env`.
`GENERATION_MODEL` selects the configured ChatOpenRouter model.

Chat requests retrieve legal chunks, apply the exact deterministic evidence-completeness
gate, then send only supported context to the configured model. The public response
statuses are `VERIFIED`, `GREETING`, `OUT_OF_SCOPE`, `CORPUS_NOT_COVERED`,
`INSUFFICIENT_EVIDENCE`, and `WORKFLOW_UNAVAILABLE`; they are not collapsed into one
generic failure. `CORPUS_NOT_COVERED` means a traffic-law question is outside the
serving corpus, not that the service will search the web. Insufficient evidence
abstains rather than inventing facts. Responses expose citations assembled from
document metadata, and selecting one opens the corresponding source passage.
The browser bounds a chat request to 120 seconds by default; set
`NEXT_PUBLIC_CHAT_TIMEOUT_MS` to override that limit.


## API routes

- `GET /api/v1/health`, `/api/v1/health/live`, `/api/v1/health/ready`
- `POST /api/v1/chat`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/chats`
- `GET/PATCH/DELETE /api/v1/chats/{session_id}`
- `POST /api/v1/chats/{session_id}/messages`
- `POST /api/v1/chats/{session_id}/messages/{message_id}/feedback`
- `POST /api/v1/chats/{session_id}/bookmarks` (saved Q&A snapshot)
- `GET /api/v1/saved` (also `/bookmarks`), bookmark status, and deletion routes
- `GET /api/v1/legal-documents`
- `GET /api/v1/legal-documents/{document_id}`
- `GET /api/v1/legal-documents/{document_id}/provisions`
- `GET /api/v1/legal-search`
## Thesis evaluation (40 cases)

The reproducible thesis set is `data/evaluation/thesis-gold-40.json` (40
cases). The runner scores retrieval, expected legal locations, citation
validity, and abstention behavior; semantic answer correctness is deliberately
left for a human reviewer. It writes raw JSONL and an aggregate JSON report and
does not contain or infer a score until predictions are supplied.

Run against the local chat endpoint:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --output-dir data/evaluation/thesis-run
```

Or score an existing prediction JSONL:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --predictions path/to/predictions.jsonl \
  --output-dir data/evaluation/thesis-run
```

Review the generated raw JSONL interactively:

```bash
uv run --project backend python backend/scripts/review_thesis_answers.py \
  data/evaluation/thesis-run/<run-id>.jsonl \
  --output data/evaluation/thesis-run/<run-id>.reviews.jsonl
```

For scripted review, pass `--non-interactive --input review-decisions.jsonl`;
each input row contains `case_id`, `answer_correctness_manual` (`pass` or
`fail`), and optional `notes`. Use `--help` on both scripts for the complete,
authoritative option list. No evaluation scores are claimed here.

## Checks

```bash
uv run --project backend python backend/scripts/smoke.py
```

## P2 paused scope

P2 is paused and is not an active runtime dependency. This MVP does not promise
additional ingestion orchestration, external retrieval, autonomous agents, or
a broader review platform. The supported path is the dual-source explorer,
Markdown manifest, LangChain Documents, local Qdrant HYBRID retrieval,
configured ChatOpenRouter generation with citations, and Supabase application
persistence/authentication.

## License

MIT License — open source for academic use.
