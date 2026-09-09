# Implementation audit

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

- Full backend suite: 1491+ passed (current resolved result).
- Focused current results: agentic/evidence and query-analyzer coverage passed; chat API coverage verifies question-only input, verified/abstained response shaping, citation serialization, and fail-closed citation handling.
- Frontend lint, typecheck, and production build pass after final UI repair.
- The audit records executed evidence only; it does not assert a PR, merge, tag, or release readiness.

## Intentional exclusions

- Sidebar suggestions are intentionally excluded from this implementation audit and release scope.
- Future session context is intentionally excluded; the current chat contract remains a single `{question}` request without persisted conversational session context.

## Remaining release blockers

- Full backend pass does not by itself prove clean-room deployment, final evaluation, or defense rehearsal; those remain separate release gates.
- Frontend Playwright and live model scenario matrix still require execution when those gates are run.

