# Architecture — VN Traffic Law RAG MVP

This document describes the active implementation served by this repository.
Historical v1/v2 designs (including seven-service ingestion topologies) are not
runtime claims; deployment authority is `deploy/compose/compose.release.yml`.

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

`backend/app/rag/router.py` classifies requests without external I/O; the canonical public chat statuses are `VERIFIED`, `GREETING`, `OUT_OF_SCOPE`, `CORPUS_NOT_COVERED`, `INSUFFICIENT_EVIDENCE`, and `WORKFLOW_UNAVAILABLE`. `backend/app/rag/references.py` parses and matches explicit Điều/Khoản/Điểm and document-number references. `backend/app/rag/evidence.py` applies the exact evidence-completeness gate before generation: every evidence type required by the query plan must be supported by the retrieved context, otherwise the service abstains. Only supported evidence reaches `backend/app/rag/generator.py`; citations are assembled from stored metadata in `backend/app/rag/service.py`. The query path is corpus-only: it never performs web retrieval, and traffic-law questions unsupported by the serving corpus are classified as `CORPUS_NOT_COVERED`.


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

Supabase stores application data, not the local retrieval corpus. `backend/app/database/models.py`
names application tables: `profiles`, `chat_sessions`, `messages`, `feedback`, and `bookmarks`.
Auth and chat services own authentication, sessions, messages, feedback, and saved Q&A snapshots.
Saving a bookmark persists the user question, answer, citations, response payload, and source message
IDs; saved items can be listed, checked, and deleted. Qdrant holds derived vectors; manifest and
Markdown remain ingestion inputs.


## HTTP API, readiness, and traceability

FastAPI mounts the active routers from `backend/app/main.py`:

- `backend/app/rag/api.py`: `POST /api/v1/chat` for grounded legal chat (`question`, `top_k`, optional `effective_date`);
- `backend/app/auth/api.py`: register, login, and current-user endpoints backed by Supabase auth;
- `backend/app/chats/api.py`: chat sessions, messages, feedback, and saved Q&A bookmark snapshots;
- `backend/app/legal/api.py`: legal documents, provisions, and `GET /api/v1/legal-search` text search with optional `document_id`, `article`, `clause`, `point`, and bounded `limit` filters.

Legal explorer deep links use `/legal-sources` and citation metadata to open a document/provision or
source passage; the API preserves Markdown/PDF provenance for that viewer. Saved Q&A routes include
`POST /api/v1/chats/{session_id}/bookmarks`, `GET /api/v1/saved` (also `/bookmarks`), status lookup,
and deletion. `backend/app/main.py` also provides `GET /api/v1/health/live` and
## Implementation status notes

The documented runtime contract is limited to the implemented local corpus and APIs.
Saved Q&A persistence, Legal Explorer search/deep links, canonical chat statuses,
the exact evidence gate, and bounded browser timeout are implemented behavior.
Remote corpus migration/manual UI work and final evaluation evidence remain pending;
this document does not claim release readiness or evaluation completion.

Run the API from the repository root:

```bash
uv run --project backend uvicorn app.main:app --reload
```

## Thesis evaluation interfaces

The provider-independent schemas and deterministic metrics live in `backend/app/evaluation/schemas.py` and `backend/app/evaluation/metrics.py`. `backend/scripts/run_thesis_evaluation.py` validates a 40-case dataset (five cases per category), invokes `POST /api/v1/chat` or scores saved prediction JSONL, and reports retrieval/citation/coordinate/abstention/latency metrics without inferring manual answer correctness. `backend/scripts/review_thesis_answers.py` is the manual-review interface for answer correctness. The evaluation runner covers exact references, natural-language and penalty questions, multi-intent/cross-reference/follow-up cases, insufficient evidence, and out-of-scope behavior.

## P2 paused scope

P2 work is paused. It is not part of the active runtime contract: no additional ingestion orchestration, external retrieval, autonomous agent workflow, or expanded review platform should be inferred from this MVP.

