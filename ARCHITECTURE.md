# Architecture — VN Traffic Law RAG MVP

This document describes the implementation that is currently served by this repository.

# Data, source seam, and ingestion

- **Canonical inputs:** `data/sources/manifest.json` identifies legal documents; the active local corpus is under `data/corpus/mds/`, and processed chunks are written to `data/processed/chunks.jsonl`.
- **Ingestion ownership:** `backend/app/ingestion/markdown.py` loads the manifest and Markdown into LangChain `Document` objects with article/clause/point, source, and effective-date metadata. `backend/app/ingestion/source.py` normalizes the viewer-facing `source_kind` (`markdown` or `pdf`) without rewriting provenance. `backend/app/ingestion/pdf.py` is a metadata adapter; PDF extraction/chunking remains owned by the ingestion scripts.
- **Corpus/viewer seam:** `backend/app/legal/corpus.py` provides read-only chunk loading, metadata filtering, and text search. `backend/app/legal/api.py` and `backend/app/legal/schemas.py` expose the legal-document/provision/search viewer contract and preserve Markdown/PDF source provenance.
- **Chunk command:**

  ```bash
  uv run --project backend python backend/scripts/fetch_sources.py
  ```

  Defaults are `data/sources/manifest.json`, `data/corpus/mds/`, and `data/processed/chunks.jsonl`. Override them with `--manifest`, `--local-dir`, and `--output`.

The source seam is deliberately narrow: adapters normalize source metadata for the legal API/viewer, while legal structure and chunking remain owned by the established ingestion pipeline. The rule engine under `backend/src/rule_engine/` remains domain-agnostic; traffic-law values belong in domain-specific specifications/plugins, not in that engine.

## Retrieval and question analysis

`backend/scripts/index.py` creates a fresh local Qdrant collection from the chunk JSONL. `backend/app/rag/retrieval.py` owns the persistent LangChain Qdrant hybrid retriever:

- dense OpenRouter embeddings with 768 dimensions;
- sparse FastEmbed BM25 (`Qdrant/bm25`);
- Qdrant local persistence at `QDRANT_PATH` (default `backend/data/processed/qdrant` in application settings);
- collection name from `QDRANT_COLLECTION` (default `traffic_law`).

The index is derived data. Rebuild it from the manifest and chunks rather than treating it as the source of truth. Retrieval uses exact legal-reference matching where supplied, then bounded sibling-sanction completion and cross-reference expansion from `backend/app/rag/cross_refs.py`. `backend/app/rag/service.py` decomposes compound questions with `backend/app/rag/analyzer.py`, retrieves each legal intent, and merges ranked lists with reciprocal-rank fusion (RRF), followed by document-level diversity limits.

## Grounded generation, verification, and abstention

`backend/app/rag/router.py` classifies requests as legal, chitchat, web, or out-of-scope without fetching external sources. `backend/app/rag/references.py` parses and matches explicit Điều/Khoản/Điểm and document-number references. `backend/app/rag/evidence.py` applies deterministic evidence gates. Only supported evidence reaches `backend/app/rag/generator.py`, whose configured ChatOpenRouter model generates from the supplied context; citations are assembled from stored metadata in `backend/app/rag/service.py`. Missing or insufficient evidence returns an abstention instead of fabricated legal content or web retrieval.

The request path is therefore:

```text
manifest + source files
  -> ingestion adapters / normalized metadata
  -> chunks.jsonl
  -> local Qdrant hybrid retrieval
  -> analyzer intent decomposition
  -> per-intent retrieval + RRF + sibling/cross-reference expansion
  -> reference/evidence verification
  -> configured ChatOpenRouter generation
  -> metadata-derived citations or abstention
```

`GENERATION_MODEL` selects the configured model (default: `deepseek/deepseek-v4-flash-0731`). `OPENROUTER_API_KEY` and `OPENROUTER_BASE_URL` configure the provider.

## Supabase application persistence

Supabase stores application data, not the local retrieval corpus. `backend/app/database/models.py` names the application tables: `profiles`, `chat_sessions`, `messages`, `feedback`, and `bookmarks`. The auth and chat services/routes own authentication, sessions, messages, feedback, and bookmarks; Qdrant holds derived vectors/sparse terms and the manifest/Markdown remain ingestion inputs.

## HTTP API, readiness, and traceability

FastAPI mounts the active routers from `backend/app/main.py`:

- `backend/app/rag/api.py`: `POST /api/v1/chat` for grounded legal chat (`question`, `top_k`, optional `effective_date`);
- `backend/app/auth/api.py`: register, login, and current-user endpoints backed by Supabase auth;
- `backend/app/chats/api.py`: chat sessions, messages, feedback, and bookmarks;
- `backend/app/legal/api.py`: legal documents, provisions, and metadata search.

`backend/app/main.py` also provides `GET /api/v1/health/live` and `GET /api/v1/health/ready`. Readiness checks Supabase and the configured Qdrant collection. Trace middleware accepts or creates `X-Trace-ID`, returns it on the response, and logs method, path, status, and duration.

Run the API from the repository root:

```bash
uv run --project backend uvicorn app.main:app --reload
```

## Thesis evaluation interfaces

The provider-independent schemas and deterministic metrics live in `backend/app/evaluation/schemas.py` and `backend/app/evaluation/metrics.py`. `backend/scripts/run_thesis_evaluation.py` validates a 40-case dataset (five cases per category), invokes `POST /api/v1/chat` or scores saved prediction JSONL, and reports retrieval/citation/coordinate/abstention/latency metrics without inferring manual answer correctness. `backend/scripts/review_thesis_answers.py` is the manual-review interface for answer correctness. The evaluation runner covers exact references, natural-language and penalty questions, multi-intent/cross-reference/follow-up cases, insufficient evidence, and out-of-scope behavior.

## P2 paused scope

P2 work is paused. It is not part of the active runtime contract: no additional ingestion orchestration, external retrieval, autonomous agent workflow, or expanded review platform should be inferred from this MVP.

