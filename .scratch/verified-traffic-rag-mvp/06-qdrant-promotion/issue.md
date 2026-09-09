# 06: Versioned Qdrant rebuild và promotion

**What to build:** Dựng dense+sparse serving collection từ PostgreSQL accepted snapshot, kiểm định trước alias switch và rollback được khi fail.

**Blocked by:** 02-serving-state/issue.md; 03-corpus-snapshot/issue.md; 04-full-ingestion/issue.md; 05-local-embedding/issue.md.

**Status:** ready-for-agent

- [ ] New collection carries corpus snapshot, embedding manifest, sparse vocabulary and chunking metadata.
- [ ] Every accepted provision has dense and sparse vectors with matching versions/dimensions.
- [ ] Reconciliation confirms PostgreSQL/Qdrant identity equality before promotion.
- [ ] Retrieval smoke/regression passes before atomic serving-alias switch.
- [ ] Failed promotion leaves old alias and collection serving.
- [ ] Active alias and rollback target are recorded in release manifest.
