# VN Traffic Law RAG (VNLRAG)

Runnable thesis MVP for Vietnamese traffic-law question answering. The active path is intentionally small and local-first: PDFs are parsed into legal metadata chunks, retrieved lexically, and answered with grounded metadata-only citations.

## Active MVP path

1. Place source PDFs under the canonical `data/corpus/pdfs/` directory (the ingest script searches recursively).
   For GPU-accelerated OCR ingestion, explicitly enable CUDA:
   `OCR_USE_CUDA=1 uv run --project backend python backend/scripts/ingest.py --pdf-dir data/corpus/pdfs/`
2. `backend/scripts/ingest.py` extracts pages with **PyMuPDF4LLM**, splits legal provisions, and writes deterministic JSONL chunks containing document/article/clause/point/page/source metadata.
3. `backend/scripts/index.py` builds the persistent local lexical index. Ranking is BM25-compatible and requires no external service. Qdrant is an optional deployment backend; OpenRouter is optional for hosted embeddings/generation.
4. The API retrieves top chunks, sends only their text to the configured generator (default **Gemini 2.5 Flash** through OpenRouter), and constructs citations from chunk metadata. The model is not trusted to invent citation fields.

Generated files are disposable: `data/processed/`, `data/index/`, and local Qdrant data are not source corpus and should not be committed.

## Quick start

```bash
cp .env.example .env
uv sync --project backend

# From the repository root:
uv run --project backend python backend/scripts/ingest.py
uv run --project backend python backend/scripts/index.py
uv run --project backend python backend/scripts/smoke.py

uv run --project backend uvicorn app.main:app --reload
```

The default chunk output is `data/processed/chunks.jsonl`; the default local index is `backend/data/qdrant`. Override either path with `--output`, `--chunks`, or `--index-path`. Set `OPENROUTER_API_KEY` (and, optionally, `GENERATION_MODEL`) for hosted generation; without a key the deterministic local fallback still returns retrieved context.

## Request flow and API

- `GET /api/v1/health` — lightweight health response.
- `GET /api/v1/health/live` and `GET /api/v1/health/ready` — liveness/readiness probes.
- `POST /api/v1/chat` — JSON body `{ "question": "...", "top_k": 5, "effective_date": null }`.

A chat request is validated, retrieved against the local index, generated from retrieved context, and returned with citations containing only stored metadata such as document identity, article/clause/point, page, source file, and excerpt. No query-time web search is performed.

## Evaluation

```bash
uv run --project backend python backend/scripts/run_release_evaluation.py --help
```

Use the evaluation script with the repository's configured gold set and output directory when those artifacts are available. `backend/scripts/smoke.py` is the quick runnable check for retrieval, generation, and citation shape.

## Historical design documents

The detailed v2 design and ADRs remain useful historical context, but are not the active MVP contract:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [SCOPE.md](SCOPE.md)
- [docs/](docs/)
- [docs/adr/](docs/adr/)

## References

- [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [Qdrant](https://qdrant.tech/documentation/)
- [OpenRouter](https://openrouter.ai/docs)
- [Gemini API](https://ai.google.dev/gemini-api/docs)

## License

MIT License — open source for academic use.
