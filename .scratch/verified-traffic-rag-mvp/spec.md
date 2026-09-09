# Verified traffic-law RAG MVP recovery

## Problem Statement

Người dùng nhập câu hỏi pháp luật giao thông hợp lệ nhưng app thường trả `INSUFFICIENT_EVIDENCE`, kể cả khi serving index có điều khoản liên quan. Input ngoài pháp luật như `Hello gemini` cũng bị gán cùng mã lỗi. Corpus metadata, PDF local, PostgreSQL và Qdrant chưa có một trạng thái serving được reconcile end-to-end; evidence gate còn phụ thuộc wording literal; feedback API/UI chưa khớp quyết định MVP tối giản. App chưa có hợp đồng nhất quán cho corpus coverage, greeting, out-of-scope, vận hành single-user và ingestion tự động.

## Solution

Khôi phục MVP corpus-bounded và verified-or-abstain:

- Chốt corpus MVP là 14 PDF local, deduplicate theo document identity/file hash, chỉ từ `datafiles.chinhphu.vn`.
- Ingest bằng manual CLI; worker nền chỉ là implementation detail sau CLI trigger. Snapshot/hash bất biến, auto quality/provenance/temporal gates, chỉ `ACCEPTED` mới được index; index cũ giữ đến khi rebuild mới pass và alias switch nguyên tử.
- Reconcile manifest → PDF → parser → PostgreSQL → embedding → Qdrant → serving alias.
- Tách `GREETING`, `OUT_OF_SCOPE`, `CORPUS_NOT_COVERED`, `INSUFFICIENT_EVIDENCE` và lỗi vận hành; không dùng web ở query-time.
- Giữ legal-boundary retrieval units, exact lookup + sparse + dense + RRF + context expansion; sửa canonical terminology/evidence classification để statutory wording như “không chấp hành hiệu lệnh…” được nhận diện cho câu “vượt đèn đỏ”.
- Dùng local embedding candidates đã cài/cache, benchmark nhỏ trên gold/regression rồi rebuild collection theo model/version manifest; không trộn vector space.
- Giữ UI chat + search serving corpus + citation/passage metadata + anonymous LIKE/DISLIKE tối thiểu. Feedback không phải legal truth, không tự thay đổi corpus/index/model và không phải release gate.

## User Stories

1. As a single-user, I want to ask a Vietnamese traffic-law question, so that I receive a verified answer or a precise abstention.
2. As a single-user, I want greetings recognized separately, so that `Hello gemini` does not appear as missing legal evidence.
3. As a single-user, I want out-of-domain questions identified separately, so that I know the app only covers its declared legal domain.
4. As a single-user, I want traffic questions missing from the 14-PDF corpus labeled `CORPUS_NOT_COVERED`, so that coverage limits are distinguishable from retrieval failure.
5. As a single-user, I want insufficient evidence reported with the missing evidence type, so that an abstention is actionable.
6. As a single-user, I want workflow/provider failures reported as operational errors, so that infrastructure failures are not misrepresented as legal uncertainty.
7. As a user asking about a current rule, I want today’s date applied and shown, so that the answer is temporally explicit.
8. As a user asking about a year, I want the canonical 01/07 date policy applied when no in-year effect change exists, so that year-only queries are deterministic.
9. As a user asking without naming a vehicle, I want every evidenced vehicle/actor case listed separately, so that differing penalties are not incorrectly merged.
10. As a user using colloquial language, I want canonical legal synonyms resolved, so that common phrases retrieve statutory wording.
11. As a user asking for a penalty, I want violation, monetary, points, suspension, condition, exception, and procedure evidence planned according to the question, so that the answer is not silently partial.
12. As a user, I want legal provisions retrieved at their legal boundaries, so that citations identify real Điều/Khoản/Điểm units.
13. As a user, I want parent context and penalty-companion provisions included when required, so that short points remain understandable.
14. As a user, I want amendment and effective-date relations respected, so that historical and current answers use the correct provision version.
15. As a user, I want every claim tied to verifiable provision metadata, so that citations cannot be fabricated.
16. As a user, I want citation passages to show document, Điều, Khoản, Điểm, page, source URL, and snapshot/hash metadata, so that I can inspect the basis.
17. As a user, I want search to cover only serving documents/provisions, so that pending or rejected artifacts are never presented as law.
18. As a single-user operator, I want no admin/reviewer login or approval UI, so that ingestion does not require a second person to monitor buttons.
19. As a single-user operator, I want manual CLI ingestion from the exact allowlist, so that source acquisition is controlled and reproducible.
20. As a single-user operator, I want failed snapshots retained with immutable gate reports, so that failures are diagnosable without replacing the current index.
21. As a single-user operator, I want a failed rebuild to leave the old alias serving, so that users never see a partially rebuilt index.
22. As a single-user operator, I want embedding model/version metadata recorded, so that vector spaces are reproducible and never mixed.
23. As a user, I want to like or dislike an answer with one button, so that I can signal perceived usefulness without writing a comment.
24. As a single-user operator, I want feedback stored as minimal anonymous telemetry linked to a trace, so that I can investigate quality without collecting unnecessary PII.
25. As a single-user operator, I want feedback excluded from automatic training, corpus mutation, gold-set mutation, and release gates, so that noisy preference signals do not become legal truth.
26. As a maintainer, I want a fixed 200-question gold set across 17 risk-weighted categories, so that release quality is measured consistently.
27. As a maintainer, I want all 200 gold questions run before release, so that the declared coverage has actual evidence.
28. As a maintainer, I want retrieval, evidence, temporal, citation, numeric, and abstention metrics reported separately, so that failures are attributable to the right pipeline seam.
29. As a maintainer, I want existing chat workflow seams reused for classification, retrieval, response mapping, and feedback, so that tests observe consumer behavior rather than implementation details.
30. As a maintainer, I want existing API and workflow tests extended for the new status taxonomy, so that regressions in verified-or-abstain behavior are caught.

## Implementation Decisions

- Extend the existing chat workflow/query-plan seam to classify greeting, out-of-scope, corpus-not-covered, and legal queries before retrieval. Preserve `ConfigDict(extra="forbid")` contracts.
- Make response mapping preserve distinct status/reason codes instead of defaulting every non-verified response to `INSUFFICIENT_EVIDENCE`.
- Use the existing `QueryAnalyzer`, `EvidenceCompletenessGate`, `HybridRetriever`, legal context expansion, and verification boundary as the primary runtime seams. Do not add a parallel retrieval pipeline.
- Replace literal-only evidence scoping with canonical legal concept matching and terminology expansion. Candidate text may contain statutory terms while the query uses colloquial terms; both map to one concept.
- Keep one retrieval unit per legal provision. `source_text` remains immutable; `retrieval_text` may include parent context.
- Define serving readiness as an end-to-end invariant: every indexed provision belongs to an accepted snapshot, has resolver-derived temporal interval, has embedding metadata, and is reachable through the active alias.
- Ingestion accepts only the 14 deduplicated PDF identities and exact HTTPS `datafiles.chinhphu.vn` source URLs. No arbitrary upload endpoint and no query-time web fetch.
- Automatic gate outcomes are `ACCEPTED` and `REJECTED`; rejected artifacts remain non-serving with reasons and hashes. No human approval state is required.
- Rebuild uses a new versioned Qdrant collection and atomic alias switch. The old serving collection remains available for rollback.
- Local embedding selection uses a small benchmark of installed/cached local candidates on retrieval regression data. The selected provider/model/revision/dimensions and benchmark hash are recorded in a manifest; any change requires a rebuild.
- Feedback accepts only `LIKE` or `DISLIKE` associated with a trace/message. Store minimal anonymous metadata such as event ID, trace ID, rating, timestamp, workflow/index/model version, provision/citation IDs, and latency/error state. Do not store comments, raw prompt/answer, identity, IP, device, or PII by default.
- Preserve the existing conversation and feedback persistence seams, but align request/response schema and frontend controls with the two-value feedback contract.
- Keep single-user deployment on localhost/private network with no app authentication or admin/reviewer role.
- Search UI queries only the serving corpus and opens passage metadata, not live web content.

## Testing Decisions

- Tests assert external API/UI behavior: status, answer presence, abstention reason, citations, applied date, serving-corpus boundaries, and persisted minimal feedback. They do not assert private helper implementation or regex/source text.
- Extend existing chat API behavior tests for greeting, `OUT_OF_SCOPE`, `CORPUS_NOT_COVERED`, `INSUFFICIENT_EVIDENCE`, `WORKFLOW_UNAVAILABLE`, and verified citation invariants.
- Extend existing workflow/evidence tests with colloquial-to-statutory equivalence cases for red-light violations, phone use, helmet use, and penalty amounts.
- Test that a legal query with a relevant retrieval hit but missing required evidence abstains with the specific gap, while a complete multi-provision context verifies.
- Test current-date and year-only date behavior, including in-year effect-change abstention.
- Test vehicle-unspecified output lists independently evidenced vehicle/actor cases rather than merging incompatible penalties.
- Test serving reconciliation counts and rejection behavior at the ingestion/index seam: rejected or unresolved artifacts never appear in Qdrant/search results; failed rebuild preserves the old alias.
- Test local embedding manifest/version changes force a new collection/rebuild and never mix vector dimensions or model versions.
- Adapt existing feedback API tests from correctness/comment payloads to only `LIKE`/`DISLIKE`, unknown trace handling, extra-field rejection, and anonymous minimal persistence.
- Add frontend behavior coverage for one-time thumbs buttons, accessible labels, and citation/passage metadata; no comment form.
- Run the full 200-question evaluation before release. Report retrieval recall, evidence completeness, temporal correctness, citation validity, numeric grounding, verified-answer rate, and abstention taxonomy separately.

## Out of Scope

- Admin/reviewer roles, authentication, approval UI/API, human-in-the-loop ingestion, and manual accept/reject actions.
- Arbitrary PDF upload or sources outside exact `datafiles.chinhphu.vn` allowlist.
- Query-time web search, open-web fallback, or using unverified source candidates as answer evidence.
- Automatically training or fine-tuning Gemini/any provider from thumbs feedback.
- Automatic corpus/index/prompt/gold-set mutation from feedback.
- Feedback comments, reason categories, identity, IP/device tracking, raw prompt/answer retention, and PII collection.
- Full Vietnamese law or traffic domains outside the 14-PDF serving corpus.
- Local LLM generation, multi-agent orchestration, Neo4j, Kubernetes, mobile, voice, and personalized legal advice.
- Replacing the legal-boundary chunk model with arbitrary token chunks.

## Further Notes

- Current repository code still contains legacy documentation/runtime references that must be aligned before implementation is considered complete; this spec is the target contract, not a claim that all behavior already passes.
- The highest test seam is the existing public chat/feedback API plus injected workflow services. This keeps classification, retrieval, verification, persistence, and UI contracts observable without coupling tests to private helpers.
- `LIKE`/`DISLIKE` is a noisy user-perceived quality signal, not legal correctness. It supports offline error analysis and regression prioritization only.
- Official provider documentation shows that consumer thumbs feedback may include conversation context and may be used for provider improvement; VNLRAG deliberately avoids reproducing that data-collection scope.
