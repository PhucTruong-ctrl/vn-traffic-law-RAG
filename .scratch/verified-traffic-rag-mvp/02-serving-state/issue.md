# 02: Serving-state migration

**What to build:** Toàn bộ runtime dùng auto-gated `ACCEPTED | REJECTED` thay cho review-oriented states, upload API và reviewer approval.

**Blocked by:** 01-query-status/issue.md — Status taxonomy và response contract.

**Status:** ready-for-agent

- [ ] Persistence constraints, actors, reconciliation, retrieval filters and verification use accepted serving state.
- [ ] Active production paths no longer depend on `PENDING`, `NEEDS_REVIEW`, `PENDING_REVIEW`, `DROPPED` or reviewer identity.
- [ ] Arbitrary PDF upload and approval endpoints are removed from MVP serving path.
- [ ] Rejected artifacts retain immutable reason/hash metadata and never index.
- [ ] Existing state, API and index tests pass against the new contract.
