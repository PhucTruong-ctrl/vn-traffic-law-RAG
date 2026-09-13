# 13: Documentation và defense package

**What to build:** Đồng bộ toàn bộ source-of-truth docs/tracker/README và tạo bộ artifact reproducible để chạy demo và bảo vệ khóa luận.

**Blocked by:** 01-query-status/issue.md; 02-serving-state/issue.md; 03-corpus-snapshot/issue.md; 04-full-ingestion/issue.md; 05-local-embedding/issue.md; 06-qdrant-promotion/issue.md; 07-legal-evidence/issue.md; 08-citation-passage/issue.md; 09-serving-search/issue.md; 10-feedback/issue.md; 11-gold-freeze/issue.md; 12-release-evaluation/issue.md.

**Status:** implemented-docs-pending-runtime-evidence

- [x] README, SCOPE, ARCHITECTURE and CONTEXT expose the active 14-PDF / CLI / automatic-gate / no-auth-reviewer / embedding-benchmark / 200-question contract.
- [x] Historical superseded claims are explicitly labeled in top-level source-of-truth docs.
- [x] One tracker directory contains the map, master spec and all feature-slug tickets with unambiguous dependencies.
- [x] Release manifest template records corpus snapshot/hash, accepted IDs, active alias, embedding manifest, gold hash, metrics and code commit without fabricating values.
- [x] Defense runbook documents startup, health, CLI ingestion, demo statuses, serving search/citation, feedback, evaluation and rollback evidence.
- [ ] Runtime evidence and gate results must be filled by the release/evaluation owners; this documentation package does not claim unverified success.
