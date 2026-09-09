# 09: Search serving corpus

**What to build:** Search UI tìm provisions/documents đã serving, giữ sparse vocabulary đúng corpus và mở passage metadata tương ứng.

**Blocked by:** 06-qdrant-promotion/issue.md; 08-citation-passage/issue.md.

**Status:** ready-for-agent

- [ ] Search uses active accepted corpus and correct persisted sparse vocabulary.
- [ ] Search excludes rejected, incomplete and non-serving records.
- [ ] Results expose stable document/provision metadata and source page.
- [ ] Selecting a result opens the corresponding citation/passage panel.
- [ ] Search never performs query-time web retrieval or fallback.
- [ ] Search behavior is covered by backend and frontend external behavior tests.
