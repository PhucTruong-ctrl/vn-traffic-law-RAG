# VN Traffic Law RAG (VNLRAG)

Runnable MVP for Vietnamese traffic-law questions. The active product combines a
dual-source legal explorer with grounded chat:

```text
Markdown manifest + local PDFs -> legal documents/provisions -> local Qdrant HYBRID
                                                        -> ChatOpenRouter -> citations
```

## Quick start

The one-command development stack runs the API, Next.js frontend, and their
local service dependencies through Docker Compose:

```bash
cp .env.example .env
# Fill the Supabase and OpenRouter values in .env.
docker compose --env-file .env up --build
```

Open `http://127.0.0.1:3000`. Supabase provides registration/login and stores
profiles, chat sessions, messages, feedback, and bookmarks. The browser uses
the publishable/anonymous Supabase key; the backend uses the service-role key
only for its server-side persistence operations. Never commit `.env` or keys.

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

The `/legal-sources` page lists the documents exposed by the legal API and
supports text, document-number, and article filtering. A document can be
opened at provision level. Markdown sources are rendered as structured legal
text; PDF sources are rendered in the in-app PDF viewer with page navigation,
zoom, and citation-coordinate highlighting when metadata is available. The
explorer is read-only: the manifest and derived Qdrant index remain the
ingestion/retrieval sources of truth.

## Grounded chat and citations

Set `OPENROUTER_API_KEY` and optionally `OPENROUTER_BASE_URL` in `.env`.
`GENERATION_MODEL` selects the ChatOpenRouter model; its default is
`deepseek/deepseek-v4-flash-0731`.

Chat requests retrieve legal chunks, apply deterministic reference and
evidence checks, then send the question and retrieved documents to the
configured model. Responses expose citations assembled from document metadata
(identity, article/clause/point, source, page, and effective-date information).
Selecting a citation opens the corresponding Markdown passage or PDF page in
the source viewer. When evidence is insufficient, the service abstains rather
than inventing facts or performing web retrieval.

## API routes

- `GET /api/v1/health`, `/api/v1/health/live`, `/api/v1/health/ready`
- `POST /api/v1/chat`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/chats`
- `GET/PATCH/DELETE /api/v1/chats/{session_id}`
- `POST /api/v1/chats/{session_id}/messages`
- `POST /api/v1/chats/{session_id}/messages/{message_id}/feedback`
- `POST /api/v1/chats/{session_id}/bookmarks`
- `GET /api/v1/legal-documents`
- `GET /api/v1/legal-documents/{document_id}`
- `GET /api/v1/legal-documents/{document_id}/provisions`
- `GET /api/v1/legal-search`

Chat payload:

```json
{"question":"...", "top_k":5, "effective_date":null}
```

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
