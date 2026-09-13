# 02. Phân tích và đặc tả yêu cầu

> **Trạng thái release:** **UNVERIFIED / NOT RELEASE-READY**
>
> Tài liệu này là yêu cầu canonical của VN Traffic Law RAG. Mỗi yêu cầu ghi rõ trạng thái `TARGET`, `PARTIAL`, `VERIFIED` hoặc `UNVERIFIED`; target không phải là năng lực runtime đã triển khai.
>
> **Nguồn quyết định:** [00-scope-and-decisions.md](00-scope-and-decisions.md)

## 2.1. Mục tiêu và ranh giới

Hệ thống hỗ trợ tra cứu pháp luật giao thông đường bộ Việt Nam trên corpus được kiểm chứng, với truy xuất nhận biết cấu trúc, hiệu lực thời gian, bằng chứng đầy đủ và citation có thể kiểm chứng. Query-time chỉ dùng corpus/index đã phục vụ: **không open-web search, crawl ngoài allowlist hoặc web fallback**.

### Release contract

- Bộ đánh giá release là `data/evaluation/thesis-gold-40.json`, gồm đúng 40 case và đúng 8 category: `exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, `out_of_scope`.
- Đây là bộ có coverage giới hạn, không đại diện toàn bộ câu hỏi pháp luật giao thông. Không khóa ngưỡng số trước thực nghiệm; mọi lỗi API, timeout, null và case chưa review phải được ghi riêng.
- Ingestion/rebuild manual CLI, fail closed; gate fail không thay index đang phục vụ.
- Không upload endpoint, admin/reviewer role, approval UI/API, human approval hoặc review queue trong MVP.
- Verified-or-abstain, corpus-only, không web fallback; không dùng UDEF hoặc autonomous multi-agent.
- Không dùng UDEF, autonomous multi-agent, tư vấn pháp lý cá nhân hóa hoặc corpus ngoài frozen scope.

### Runtime boundary đã audit

Runtime hiện có FastAPI, Supabase Auth và persistence theo user/session; Qdrant hybrid dense/sparse retrieval (OpenRouter-compatible embeddings và FastEmbed BM25), exact metadata filtering, temporal filtering, bounded sibling/cross-reference expansion, deterministic evidence checks và Markdown generation. Chat UI có lịch sử, citation/passage, legal sources, saved items và LIKE/DISLIKE.

Runtime **chưa chứng minh** Parser Router/Docling/MinerU, Canonical Document IR, legal relation database, PostgreSQL source of truth, Redis/Dramatiq queue, MinIO, LangGraph, Langfuse, production reranker, sáu verifier độc lập đầy đủ hoặc failure-aware repair graph. Loader hiện đọc Markdown/JSONL với manifest 17 entries; điều này không chứng minh release đã có 14-PDF snapshot.

## 2.2. Actors và use cases

| ID | Actor | Use cases |
|---|---|---|
| A1 | Authenticated user | UC-01 hỏi hiện hành; UC-02 hỏi lịch sử; UC-03 so sánh; UC-04 exact lookup; UC-05 xem citation/passage; UC-06 nhận abstention; UC-07 gửi LIKE/DISLIKE; UC-08 xem lịch sử session của mình |
| A2 | Manual CLI operator | UC-09 sync/gate/rebuild; UC-10 chạy evaluation/release report |
| A3 | Allowlisted official source | Cung cấp PDF offline trong allowlist cho UC-09 |
| A4 | External model/provider | Embedding và generation theo cấu hình runtime |

Authentication không bị loại bỏ: user phải có bearer token hợp lệ; session, user message, assistant response, citation và feedback được lưu/đọc theo user ownership. Không có reviewer/admin actor trong MVP.

## 2.3. Functional requirements (P0)

Mỗi ID là duy nhất.

### FR-01 — Corpus và provenance snapshot

- **Yêu cầu:** Chấp nhận đúng 14 PDF allowlisted, deduplicate theo identity/hash và lưu manifest immutable với document identity, source URL, file hash, issued/effective dates, status, relation notes và provenance.
- **Acceptance:** Snapshot phải có 14 PDF, hash tái lập được, thiếu identity/provenance/temporal metadata thì không index. **[TARGET]**
- **Runtime:** Manifest hiện có 17 Markdown/JSONL entries; chưa có bằng chứng 14-PDF snapshot. **[UNVERIFIED]**

### FR-02 — Manual ingestion và fail-closed publish

- **Yêu cầu:** Sync/rebuild chỉ qua manual CLI; quality, provenance và temporal gates chạy trước publish; gate fail giữ index cũ.
- **Acceptance:** Một artifact lỗi không được thay thế corpus/index đang phục vụ. **[TARGET]**
- **Runtime:** `scripts/fetch_sources.py` và `scripts/index.py` là path active; full publish gate chưa được chứng minh. **[PARTIAL]**

### FR-03 — Parser Router và Canonical Document IR

- **Yêu cầu mục tiêu:** Router Docling/MinerU tạo parser-neutral IR, giữ page, bbox, reading order, parent, parser/version/confidence và raw reference.
- **Acceptance:** Adapter parser mới không buộc sửa Legal Structure Extractor; provenance đến element/page/bbox tái truy nguyên được. **[TARGET]**
- **Runtime:** Chưa có implementation active; Markdown loader là path hiện tại. **[UNVERIFIED]**

### FR-04 — Legal structure và stable provision identity

- **Yêu cầu mục tiêu:** Nhận diện Chương/Mục/Điều/Khoản/Điểm, bảng và điều khoản liên quan; giữ nguyên `d)` và `đ)`, short-Point và source text; tạo provision identity deterministic.
- **Acceptance:** Boundary provision trùng boundary citation; `d)` và `đ)` không va chạm. **[TARGET]**
- **Runtime:** Markdown loader nhận diện Điều/Khoản/Điểm bằng regex và tạo `chunk_id`; stable `provision_id` theo target chưa được chứng minh. **[PARTIAL]**

### FR-05 — Parent context và legal relations

- **Yêu cầu mục tiêu:** Bổ sung context cha và mô hình hóa cross-reference, amendment, replacement, repeal, penalty/license/remedy relations với nguồn và depth bounded.
- **Acceptance:** Mọi relation có source identity, relation type và lý do expansion; không mở rộng vô hạn. **[TARGET]**
- **Runtime:** Có bounded sibling/cross-reference expansion nhưng chưa có legal relation DB/source-of-truth. **[PARTIAL]**

### FR-06 — Temporal và amendment resolution

- **Yêu cầu:** Current, historical và comparison query áp dụng interval `[effective_from,effective_to)`; thiếu ngày không được suy diễn nguy hiểm; year-only tuân date policy và có thể trả `MISSING_QUERY_DATE`.
- **Acceptance:** Chỉ dùng provision thỏa `effective_from <= d` và (`effective_to` null hoặc `d < effective_to`), đồng thời không leakage phiên bản. **[TARGET]**
- **Runtime:** Có temporal filtering theo metadata; versioned provision store và amendment resolver đầy đủ chưa được chứng minh. **[PARTIAL]**

### FR-07 — Corpus-only query boundary

- **Yêu cầu:** Retrieval và generation chỉ sử dụng corpus đã phục vụ; câu hỏi ngoài corpus trả `CORPUS_NOT_COVERED` hoặc `OUT_OF_SCOPE`, không web fallback.
- **Acceptance:** Không có request web ở query-time và không fabricate khi thiếu evidence. **[VERIFIED]**
- **Runtime:** RAG runtime dùng Qdrant corpus; không có web fallback trong release path đã audit. **[VERIFIED]**

### FR-08 — Exact, dense, sparse retrieval và bounded expansion

- **Yêu cầu:** Hỗ trợ exact metadata lookup, dense embeddings, sparse BM25, hybrid merge/diversity và expansion có giới hạn.
- **Acceptance:** Reference, article/clause/point, vehicle taxonomy và multi-document evidence được lọc/ghép theo metadata, không suy diễn nhóm xe thiếu evidence. **[TARGET]**
- **Runtime:** Qdrant hybrid dense/sparse, exact reference filtering, RRF-like merge và bounded expansion đang active. **[VERIFIED]**

### FR-09 — Query understanding và evidence plan

- **Yêu cầu mục tiêu:** Phân loại intent/date/reference/evidence types, giữ original query, lập evidence plan trước generation.
- **Acceptance:** Current/historical/comparison, exact reference, cross-reference và multi-provision query có plan tương ứng. **[TARGET]**
- **Runtime:** Có analyze_question và bounded intent/vehicle fan-out; evidence plan đầy đủ chưa được chứng minh. **[PARTIAL]**

### FR-10 — Evidence Completeness Gate

- **Yêu cầu:** Không generate kết luận nếu required evidence thiếu; thiếu evidence phải abstain với reason chuẩn.
- **Acceptance:** `INSUFFICIENT_EVIDENCE` được phân biệt với out-of-scope và lỗi workflow; gate chạy trước generator. **[TARGET]**
- **Runtime:** Có deterministic `assess_evidence` trước generation; full contract và mọi evidence type chưa được chứng minh. **[PARTIAL]**

### FR-11 — Verified citation và claim grounding

- **Yêu cầu:** Citation dựng từ metadata/provision identity tin cậy, gắn source passage/page khi có; verifier chặn citation invalid, unsupported claim và numeric mismatch.
- **Acceptance:** Invalid citation rate mục tiêu bằng 0; response không trả claim chưa được evidence hỗ trợ. **[TARGET]**
- **Runtime:** Citation từ `chunk_id`, document/article/clause/point metadata và deterministic checks; audit ghi nhận citation validity 65,52% trên API subset, chưa đạt gate. **[UNVERIFIED]**

### FR-12 — Answer, abstention và disclaimer UI

- **Yêu cầu:** UI hiển thị answer hoặc abstention, citation/passage, applied date, reason và disclaimer; không hiển thị tư vấn pháp lý cá nhân hóa như kết luận chắc chắn.
- **Acceptance:** Người dùng mở được passage nguồn và ngày áp dụng; mọi answer có disclaimer. **[TARGET]**
- **Runtime:** Next.js chat/citation viewer/legal sources và Markdown answer đang active; manual browser acceptance chưa hoàn tất. **[PARTIAL]**

### FR-13 — Authentication, session isolation và persistence

- **Yêu cầu:** Xác thực bearer qua Supabase Auth; tạo/load session theo user; lưu user message, assistant response, citations, feedback và bookmark; chỉ user sở hữu đọc được history.
- **Acceptance:** Token được truyền tới persistence; user A không đọc được session của user B; assistant response tồn tại sau request. **[TARGET]**
- **Runtime:** Supabase Auth/REST và user-owned chat persistence đang active theo audit. **[VERIFIED]**

### FR-14 — Minimal feedback

- **Yêu cầu:** Chỉ LIKE/DISLIKE tối thiểu; feedback không chứa comment/category/raw prompt-answer/PII và không là release gate, không dùng để sửa frozen gold/corpus.
- **Acceptance:** Rating được lưu cùng user/message ownership, không làm thay đổi retrieval hoặc release decision. **[TARGET]**
- **Runtime:** LIKE/DISLIKE UI/API đã có; full privacy/release isolation chưa được chứng minh. **[PARTIAL]**

### FR-15 — Evaluation và release gate

- **Yêu cầu:** Chạy full 200 gold cases / 17 categories, lưu immutable run manifest gồm corpus/index hash, gold hash, model/version, prompt/config, commit, outputs, errors và analysis.
- **Acceptance:** Không release nếu thiếu full gold run, provenance artifact, semantic review hoặc safety/citation gate. **[TARGET]**
- **Runtime:** Chỉ có API subset 32/40; 3 lỗi, hit@5 0,1905, citation validity 0,6552, abstention accuracy 0,4483, P95 84s; semantic review chưa có. **[UNVERIFIED]**

## 2.4. Non-functional requirements

### NFR-01 — Correctness, safety and abstention

Không trả citation/claim không kiểm chứng; preserve source text; fail closed khi evidence, temporal hoặc identity không hợp lệ. **[TARGET]**

### NFR-02 — Performance

Đo P50/P95 latency, token usage, cost, ingestion/indexing time trên môi trường cố định; ngưỡng chỉ là mục tiêu kỹ thuật, không phải kết quả đã đạt. **[TARGET]**

### NFR-03 — Availability and safe rebuild

Service giữ index đang phục vụ khi fetch/parse/index/gate thất bại; rebuild phải tái lập bằng hash/version. **[TARGET]**

### NFR-04 — Security and privacy

Auth boundary, user/session isolation, secret configuration và private-network deployment phải được kiểm chứng; không lưu PII/raw prompt-answer ngoài contract feedback. **[PARTIAL]**

### NFR-05 — Maintainability and domain boundary

`backend/src/rule_engine/` domain-agnostic; business values nằm trong RuleSpec; API dùng FastAPI/Pydantic v2; không hardcode model ID trong domain logic. **[TARGET]**

### NFR-06 — Testability and reproducibility

Invariant pháp lý, citation, temporal filtering, auth isolation và persistence phải có kiểm chứng phù hợp; evaluation run versioned/hash và replayable. **[TARGET]**

### NFR-07 — Observability (target only)

Langfuse tracing, queue/background processing và production reranker chỉ là target architecture; không coi là runtime dependency hoặc acceptance đã đạt khi chưa có code/deployment evidence. **[UNVERIFIED]**

## 2.5. Target architecture explicitly not runtime

Các thành phần sau được giữ để traceability nghiên cứu nhưng **không được mô tả là active**: Parser Router (Docling/MinerU), Canonical Document IR, legal relation database, PostgreSQL legal source of truth, Redis/Dramatiq, MinIO, LangGraph controlled workflow, Langfuse, production reranker và six-layer verification/repair graph. Khi chưa có implementation và evidence tương ứng, trạng thái là `TARGET` hoặc `UNVERIFIED`.

## 2.6. Acceptance criteria cấp hệ thống

1. Đúng 14 PDF allowlisted, deduplicate và immutable hash manifest. **[TARGET]**
2. Manual CLI ingestion fail closed; gate fail giữ corpus/index cũ. **[TARGET]**
3. Provision boundary, provenance, reference và temporal semantics có thể kiểm chứng. **[TARGET]**
4. Query current/historical/comparison chỉ dùng corpus; không web fallback. **[VERIFIED]**
5. Exact/dense/sparse retrieval và bounded expansion không bỏ sót reference hợp lệ hoặc thêm evidence vô căn cứ. **[PARTIAL]**
6. Evidence gate chạy trước generation; invalid citation, unsupported claim, numeric mismatch và thiếu evidence dẫn đến block/abstain. **[PARTIAL]**
7. Authenticated session persistence và user-only history hoạt động end-to-end. **[VERIFIED]**
8. UI hiển thị answer/abstention, citation/passage, applied date, disclaimer và LIKE/DISLIKE. **[PARTIAL]**
9. Full 200-gold / 17-category gate, provenance artifact và semantic review hoàn tất trước release. **[UNVERIFIED]**
10. Status release chỉ chuyển khỏi `UNVERIFIED / NOT RELEASE-READY` sau khi mọi gate bắt buộc có evidence. **[UNVERIFIED]**

## 2.7. Traceability matrix

| Research objective | Requirements | Evidence / evaluation | Status |
|---|---|---|---|
| Frozen corpus and provenance | FR-01, FR-02 | 14-PDF manifest/hash, source allowlist, fail-closed rebuild | **UNVERIFIED** |
| Structure-aware retrieval | FR-03, FR-04, FR-08 | Parser/structure metrics, hierarchy and Point recall, provenance coverage | **PARTIAL** |
| Cross-reference completeness | FR-05, FR-08, FR-09, FR-10 | Relation resolution, multi-hop completeness, required evidence recall | **PARTIAL** |
| Temporal correctness | FR-06, FR-09 | Validity accuracy, leakage, current/historical/comparison separation | **PARTIAL** |
| Verified generation | FR-10, FR-11, FR-12 | Citation precision/recall/F1, invalid citation rate, claim support, numeric grounding | **UNVERIFIED** |
| Safe abstention | FR-10, FR-11 | Abstention precision/recall/F1; distinct reason codes | **UNVERIFIED** |
| Auth and persistence | FR-13, NFR-04 | Token propagation, user isolation, persisted assistant responses | **VERIFIED** |
| Reproducible release evaluation | FR-15, NFR-06 | 200 cases, 17 categories, immutable run manifest and hashes | **UNVERIFIED** |
| Runtime usability | FR-12, FR-14, NFR-02 | Browser verification, latency and feedback behavior | **PARTIAL** |

> Tài liệu liên quan: [00-scope-and-decisions.md](00-scope-and-decisions.md), [06-test-evaluation.md](06-test-evaluation.md), [07-deployment.md](07-deployment.md).