# ARCHITECTURE — VN Traffic Law RAG MVP

This document describes the **active runnable MVP**. The larger v2 design is retained in linked documents as historical context only; it is not the primary serving contract.

## Runtime components

- **Corpus:** every `*.pdf` below the canonical `data/corpus/pdfs/` directory, searched recursively.
-
- **Ingestion:** `backend/scripts/ingest.py` uses PyMuPDF4LLM to extract page text, then splits legal provisions into deterministic chunks. Each JSONL record carries legal and provenance metadata (document identity, article/clause/point, page, source file, and source URL when present).
- **Index:** `backend/scripts/index.py` persists a local lexical index with BM25-compatible tokenization and scoring. This is the default retrieval path and works without PostgreSQL, Redis, or a vector service. Qdrant may be enabled as an optional index/deployment backend; it is not required by the MVP.
- **API:** FastAPI exposes health and chat routes under `/api/v1`.
- **Generation:** the default configured model is `google/gemini-2.5-flash`, called through the OpenRouter-compatible chat-completions API when `OPENROUTER_API_KEY` is set. With no key, the local fallback returns retrieved context instead of pretending a hosted model ran.

## Offline flow

```text
PDFs under data/corpus/pdfs/
  -> PyMuPDF4LLM page extraction
  -> legal provision splitting + metadata
  -> data/processed/chunks.jsonl
  -> local BM25-compatible index (or optional Qdrant)
```

Run it from the repository root:

```bash
uv sync --project backend
OCR_USE_CUDA=1 uv run --project backend python backend/scripts/ingest.py --pdf-dir data/corpus/pdfs/
uv run --project backend python backend/scripts/index.py
```

`OCR_USE_CUDA=1` explicitly selects the CUDA OCR path; no benchmark or performance claim is implied. `ingest.py` accepts `--pdf-dir` and `--output`. `index.py` accepts a chunks JSONL positional path plus `--index-path`. Generated JSONL/index artifacts are disposable and ignored; the PDFs under `data/corpus/pdfs/` remain the source corpus.

## Online request flow

```text
POST /api/v1/chat
  -> validate question/top_k/effective_date
  -> lexical retrieval over indexed chunks
  -> concatenate retrieved text as bounded context
  -> Gemini 2.5 Flash via optional OpenRouter
  -> return answer + metadata-only citations
```

The generator receives the question and retrieved context. Citation objects are built by the service from stored chunk metadata; model prose cannot create or alter document, provision, or page fields. There is no query-time web retrieval. An empty or unavailable hosted generation path uses the local fallback and still exposes the retrieved metadata.

## HTTP surface

- `GET /api/v1/health` — simple `{ "status": "ok" }` response.
- `GET /api/v1/health/live` — liveness probe.
- `GET /api/v1/health/ready` — readiness/dependency report.
- `POST /api/v1/chat` — body: `{ "question": "...", "top_k": 5, "effective_date": null }`.

Start the server with:

```bash
uv run --project backend uvicorn app.main:app --reload
```

## Smoke and evaluation

```bash
uv run --project backend python backend/scripts/smoke.py
uv run --project backend python backend/scripts/run_release_evaluation.py --help
```

The smoke script exercises the local retrieval, answer, and citation path with representative questions. The evaluation script is the available batch runner; supply the repository's configured gold-set and output arguments when running an evaluation.

## Legacy design

The former architecture described Docling/MinerU routing, canonical IR, PostgreSQL as a legal source of truth, mandatory Qdrant, background workers, review states, LangGraph verification, and release gates. Those documents and ADRs are preserved for historical/design reference only:

- [SCOPE.md](SCOPE.md)
- [docs/03-thiet-ke-he-thong.md](docs/03-thiet-ke-he-thong.md)
- [docs/04-tech-stack-llm-research.md](docs/04-tech-stack-llm-research.md)
- [docs/adr/](docs/adr/)
