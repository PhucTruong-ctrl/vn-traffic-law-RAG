# Domain Docs

How engineering agents should consume this repository's domain documentation while
exploring the current Vietnamese traffic-law RAG MVP.

## Current architecture

- Frontend: Next.js 16 + React 19, including the Markdown/PDF legal explorer.
- Backend: FastAPI on Python 3.11.
- Persistence: Supabase REST/Auth for application users, sessions, messages, and feedback.
- Retrieval: Qdrant 1.19 hybrid dense embeddings through OpenRouter plus FastEmbed BM25.
- Answering: one OpenRouter generator, protected by a deterministic evidence gate and citations.
- Ingestion: supported corpus PDFs are parsed into canonical IR and legal provisions; uncertain
  OCR/structure is quarantined or reviewed before indexing.

There is no active external web retrieval, agent/LangGraph workflow, Redis, MinIO, application-owned
PostgreSQL runtime, or seven-service topology. If an older document describes one of those, label it
historical rather than treating it as an implementation requirement.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root, when present.
- **`docs/adr/`**: read ADRs touching the area being changed; preserve their decision history.
- The relevant current source under `backend/app/`, `frontend/`, `templates/`, and `data/`.

If a referenced file does not exist, proceed silently. Do not propose creating it merely to satisfy
this guide; domain-modeling creates context artifacts lazily when terms or decisions are resolved.

## File structure

This is a single repository context. Prefer actual paths over generic examples:

```text
/
├── backend/
├── frontend/
├── data/
├── templates/
└── docs/
```

## Use the glossary's vocabulary

When output names a domain concept, use the term defined in `CONTEXT.md` and current schemas.
Prefer canonical IR, legal provision, evidence gate, citation, Qdrant hybrid retrieval, Supabase
REST/Auth, and OpenRouter generator. Do not invent synonyms that obscure ownership or flow.

If a needed concept is absent from the glossary, note the gap for `/domain-modeling` rather than
inventing a parallel model.

## Flag ADR conflicts

If output contradicts an ADR, surface it explicitly rather than silently overriding it:

> _Contradicts ADR-0007, but worth reopening because…_
