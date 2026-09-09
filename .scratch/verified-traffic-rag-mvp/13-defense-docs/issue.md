# 13: Documentation và defense package

**What to build:** Đồng bộ toàn bộ source-of-truth docs/tracker/README và tạo bộ artifact reproducible để chạy demo và bảo vệ khóa luận.

**Blocked by:** 01-query-status/issue.md; 02-serving-state/issue.md; 03-corpus-snapshot/issue.md; 04-full-ingestion/issue.md; 05-local-embedding/issue.md; 06-qdrant-promotion/issue.md; 07-legal-evidence/issue.md; 08-citation-passage/issue.md; 09-serving-search/issue.md; 10-feedback/issue.md; 11-gold-freeze/issue.md; 12-release-evaluation/issue.md.

**Status:** ready-for-agent

- [ ] README, SCOPE, ARCHITECTURE, CONTEXT and docs/00-08 agree on 14-PDF corpus, CLI ingestion, auto gates, no reviewer/auth, local embedding benchmark and 200-question release gate.
- [ ] Historical superseded claims are explicitly labeled and cannot be mistaken for active contracts.
- [ ] One tracker directory contains a map, master spec and all feature-slug tickets with unambiguous dependencies.
- [ ] Release manifest records corpus snapshot/hash, accepted IDs, active alias, embedding manifest, gold hash, metrics and code commit.
- [ ] Defense runbook starts services, verifies corpus health, runs demo queries/search/citation/feedback and points to evaluation/rollback evidence.
- [ ] Working tree and documentation artifacts are committed coherently without discarding unrelated user changes.
