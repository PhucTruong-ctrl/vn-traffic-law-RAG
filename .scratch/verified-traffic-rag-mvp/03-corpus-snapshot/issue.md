# 03: Corpus snapshot và full reconciliation

**What to build:** Tạo immutable 14-PDF corpus snapshot và báo cáo đầy đủ từ source file tới active serving readiness.

**Blocked by:** None (can start immediately).

**Status:** ready-for-agent

- [ ] Exactly 14 local PDF document identities are selected after document/hash deduplication, including one `nd-168-2024` copy.
- [ ] Exact `datafiles.chinhphu.vn` source allowlist and SHA-256 are recorded for every target.
- [ ] Stage counts and identity sets are reported for snapshot, parse, IR, provisions, PostgreSQL, embeddings, Qdrant points and active alias.
- [ ] Every mismatch, missing artifact and rejected document has explicit status and reason.
- [ ] Reconciliation is reproducible from immutable snapshot/hash metadata.
- [ ] The report proves rejected/non-serving records are absent from search.
