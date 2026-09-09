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

## Verification

- Backend focused agentic/evidence tests: 23 passed.
- Query analyzer tests plus agentic tests: 35 passed.
- Frontend lint, typecheck, and production build pass after final UI repair.
- Full backend suite: 1471 passed, 19 failed, 30 skipped; failures exposed existing contract regressions still requiring repair before release.

## Remaining release blockers

- Full backend suite currently reports hierarchy-validation/indexing contract failures and workflow integration expectation failures.
- Frontend Playwright and live model scenario matrix still require execution after backend blockers are repaired.
