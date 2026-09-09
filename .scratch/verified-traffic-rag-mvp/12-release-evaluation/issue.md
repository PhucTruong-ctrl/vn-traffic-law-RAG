# 12: Full 200-question evaluation và release gate

**What to build:** Chạy toàn bộ 200 gold questions trên serving runtime và tạo release report chứng minh verified-or-abstain.

**Blocked by:** 01-query-status/issue.md; 02-serving-state/issue.md; 03-corpus-snapshot/issue.md; 05-local-embedding/issue.md; 06-qdrant-promotion/issue.md; 07-legal-evidence/issue.md; 08-citation-passage/issue.md; 09-serving-search/issue.md; 11-gold-freeze/issue.md.

**Status:** ready-for-agent

- [ ] All 200 records execute against actual serving runtime, not fixture-only adapters.
- [ ] Per-question outputs persist query, status, retrieved IDs, evidence coverage, citations, latency and errors.
- [ ] Report separates retrieval recall, evidence completeness, temporal validity, citation validity, numeric grounding, verified-answer rate and abstention taxonomy.
- [ ] Current, year-only, historical, comparison, colloquial, penalty and vehicle-unspecified scenarios are represented.
- [ ] Invalid citation rate is 0; rejected/non-serving provisions never support output.
- [ ] Any failed hard gate blocks release and creates named remediation evidence.
- [ ] LIKE/DISLIKE telemetry is explicitly non-gating.
