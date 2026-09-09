# 05: Local embedding benchmark

**What to build:** Benchmark bounded installed/cached local embedding candidates and publish one versioned selection manifest for the serving rebuild.

**Blocked by:** 03-corpus-snapshot/issue.md.

**Status:** ready-for-agent

- [ ] Only installed/cached local candidates within bounded scope are evaluated.
- [ ] Benchmark uses approved retrieval regression/gold data and reports quality and throughput.
- [ ] Selected model/revision/dimensions/prefix/device and benchmark hash are recorded.
- [ ] Sparse encoder vocabulary version is recorded alongside dense model metadata.
- [ ] Any model/dimension/version change requires a new collection rebuild.
- [ ] No vectors from incompatible model spaces are mixed.
