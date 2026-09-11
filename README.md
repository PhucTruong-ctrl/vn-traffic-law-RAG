# VN Traffic Law RAG (VNLRAG)

Runnable MVP for Vietnamese traffic-law questions. The active pipeline is:

```text
Markdown manifest -> LangChain Documents -> local Qdrant HYBRID -> ChatOpenRouter -> citations
```

## Quick start

```bash
cp .env.example .env
uv sync --project backend

# Build chunks from the Markdown manifest.
uv run --project backend python backend/scripts/fetch_sources.py

# Build the local hybrid retrieval collection.
uv run --project backend python backend/scripts/index.py

# Start the API.
uv run --project backend uvicorn app.main:app --reload
```

`fetch_sources.py` reads `data/sources/manifest.json`, resolves each entry to a Markdown file under `data/corpus/mds/`, and writes `data/processed/chunks.jsonl`. Use `--manifest`, `--local-dir`, and `--output` to override those paths.

`index.py` creates a fresh local Qdrant collection from that JSONL. Retrieval combines dense 768-dimensional OpenRouter embeddings with sparse FastEmbed BM25 (`Qdrant/bm25`) using LangChain Qdrant `HYBRID` mode. Qdrant path and collection are configured by `QDRANT_PATH` and `QDRANT_COLLECTION`.

## Generation and grounded answers

Set `OPENROUTER_API_KEY` and optionally `OPENROUTER_BASE_URL` in `.env`. `GENERATION_MODEL` selects the ChatOpenRouter model; its default is `deepseek/deepseek-v4-flash-0731`.

Chat requests retrieve legal chunks, apply deterministic reference and evidence checks, then send the question and retrieved documents to the configured model. Citations are assembled from document metadata (identity, article/clause/point, source, and effective-date information). When evidence is insufficient, the service abstains rather than inventing facts or performing web retrieval.

Active legal intelligence includes structured Vietnamese legal locations, source provenance, explicit effective-date queries, metadata filtering/search, grounded generation, and evidence-aware abstention.

## Application persistence

Supabase stores application data: profiles/authentication, chat sessions, messages, feedback, and bookmarks. The Markdown manifest is the ingestion input, and local Qdrant is derived retrieval data; neither is replaced by Supabase application tables.

## API routes

- `GET /api/v1/health`
- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- `POST /api/v1/chat`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
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

## Checks and evaluation

```bash
uv run --project backend python backend/scripts/smoke.py
uv run --project backend python backend/scripts/run_release_evaluation.py --help
```

## P2 paused scope

P2 is paused and is not an active runtime dependency. This MVP does not promise additional ingestion orchestration, external retrieval, autonomous agents, or a broader review platform. The supported path is the Markdown manifest, LangChain Documents, local Qdrant HYBRID retrieval, configured ChatOpenRouter generation, and Supabase application persistence.

## License

MIT License — open source for academic use.
