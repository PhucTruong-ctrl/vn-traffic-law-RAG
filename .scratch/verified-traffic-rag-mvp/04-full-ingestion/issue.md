# 04: Full 14-PDF ingestion

**What to build:** Ingest toàn bộ snapshot 14 PDF qua parser, Canonical Document IR, legal structure, relation, temporal và automatic gates mà không silently skip document.

**Blocked by:** 02-serving-state/issue.md; 03-corpus-snapshot/issue.md.

**Status:** ready-for-agent

- [ ] CLI target includes all 14 approved PDFs and deduplicates by document/hash.
- [ ] Searchable and scanned PDFs use the configured parser/OCR route with recorded outcome.
- [ ] Every document produces parse, structure, relation, temporal and quality gate results.
- [ ] Accepted provisions have resolver-derived effective intervals before indexing.
- [ ] Failed documents remain retained as rejected/non-serving artifacts with actionable reasons.
- [ ] PostgreSQL accepted rows reconcile with the immutable snapshot report.
