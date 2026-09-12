# Implementation audit

This is a snapshot of verified implementation work in the active MVP architecture:
Next.js 16/React 19 frontend; FastAPI/Python 3.11 backend; Supabase REST/Auth persistence;
Qdrant 1.19 hybrid dense OpenRouter + FastEmbed BM25 retrieval; deterministic evidence gate;
one OpenRouter generator; citations; and Markdown/PDF legal exploration.

## Resolved

| Area | Finding | Resolution | Evidence |
| --- | --- | --- | --- |
| UI | Chat shell lost layout styles | Restored responsive shell, thread, composer, citation, drawer, and PDF viewer styles | Frontend lint, typecheck, build pass |
| UI | Citation drawer inerted its ancestor | Inert only sidebar and main panel; restore prior state | SourceDrawer inspection |
| UI | PDF retry was cosmetic | Retry token reloads PDF document | PdfCitationViewer inspection |
| UI | Follow-up replaced prior turn | Ordered ConversationTurn list appends responses | Frontend typecheck/build pass |
| UI | Mobile navigation hidden | Accessible mobile drawer/toggle with Escape and backdrop | Sidebar inspection |
| Retrieval | OCR provenance dropped bbox/source URL | Persisted metadata in indexed payload and retrieval contract | Qdrant payload code inspection |
| Workflow | Exhausted evidence could generate answer | Exhausted incomplete evidence routes to abstention | Backend gate tests |
| Workflow | Multi-case evidence mixed | Case-scoped plans and partitioned fusion/reranking | Agentic regression tests |
| Model | Prompt omitted structured multi-case constraints | Added Vietnamese answer structure, citations, uncertainty limits, and next step | Generation tests |
| API | Source endpoint lacked cached official PDF | HTTPS-only download, PDF/hash/size validation, cache | Document source tests and live source response |
| API | Streaming chat had no documented contract | `GET /api/v1/chat/events` emits workflow progress events followed by one result event; client cancellation cancels the workflow task | `backend/app/api/chat.py` implementation and focused chat API coverage |
| Provenance | Official PDF source could be treated as arbitrary remote content | Source retrieval accepts only exact HTTPS URLs on `datafiles.chinhphu.vn`, rejects credentials/fragments and redirects, validates PDF signature/size, verifies SHA-256 against the accepted corpus hash, then caches the verified bytes in `source-pdfs` | `backend/app/api/documents.py` source endpoint and source validation tests |

## Verification

- Full backend suite: 1491+ passed (historical executed result recorded at audit time).
- Focused current results: agentic/evidence and query-analyzer coverage passed; chat API coverage verifies question-only input, verified/abstained response shaping, citation serialization, and fail-closed citation handling.
- Frontend lint, typecheck, and production build pass after final UI repair.
- These are recorded evidence, not a claim of current release readiness. Rerun release gates before shipping.

## Intentional exclusions

- Sidebar suggestions are intentionally excluded from this implementation audit and release scope.
- Future session context is intentionally excluded. Current chat requests and Supabase-backed sessions do not imply an agent memory layer.
- External retrieval, Redis, MinIO, application-owned PostgreSQL, LangGraph, and multi-agent orchestration are not active components.

## Remaining release blockers

- A full backend pass does not by itself prove clean-room deployment, final evaluation, or defense rehearsal. Those remain separate release gates.
- Frontend Playwright and live model scenario matrix still require execution when those gates are run.
