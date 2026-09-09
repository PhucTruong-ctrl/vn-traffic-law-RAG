# 08: Citation và passage contract

**What to build:** Mọi verified claim hiển thị được source passage và metadata đủ để kiểm chứng đúng provision trong serving corpus.

**Blocked by:** 02-serving-state/issue.md; 06-qdrant-promotion/issue.md.

**Status:** ready-for-agent

- [ ] Citation exposes document, Điều/Khoản/Điểm, page, exact source URL and snapshot/hash metadata.
- [ ] Passage viewer distinguishes immutable `source_text` from parent legal context.
- [ ] Source host validation is exact `datafiles.chinhphu.vn`.
- [ ] Rejected/non-serving provision IDs cannot be cited or opened.
- [ ] Existing L2 citation verification and API/frontend contracts agree.
- [ ] Valid and invalid citation behavior has external API/UI tests.
