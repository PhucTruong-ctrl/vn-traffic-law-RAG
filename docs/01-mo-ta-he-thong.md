# XÂY DỰNG HỆ THỐNG RAG NHẬN BIẾT CẤU TRÚC
# VÀ THỜI GIAN HIỆU LỰC ĐỂ HỖ TRỢ TRA CỨU
# PHÁP LUẬT GIAO THÔNG VIỆT NAM
# VỚI TRÍCH DẪN CÓ THỂ KIỂM CHỨNG

**Tên tiếng Anh:** *A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations*

## 0. Mục đích và trạng thái tài liệu

Tài liệu này mô tả hệ thống VN Traffic Law RAG và phải được đọc cùng [tài liệu phạm vi và quyết định thiết kế](00-scope-and-decisions.md). Nội dung được chia thành ba lớp: phạm vi đã khóa, kiến trúc mục tiêu và runtime đã kiểm chứng. Kiến trúc mục tiêu không được trình bày như chức năng đã triển khai.

Audit runtime gần nhất ngày 13/09/2026 kết luận trạng thái release là **UNVERIFIED / NOT RELEASE-READY**. Artifact `docs/evaluation/thesis-api-subset-32-20260913.md` mới chạy 32/40 case qua API, có 3 lỗi API, retrieval hit@5 là 19,05%, citation validity là 65,52%, abstention accuracy là 44,83%, P95 là 84,0 giây và chưa review semantic correctness.

## 1. Bối cảnh và bài toán

Người dùng tra cứu pháp luật giao thông đường bộ Việt Nam thường phải đối chiếu nhiều văn bản, phiên bản và điều kiện áp dụng. Cùng một hành vi có thể có kết quả khác nhau theo loại phương tiện và thời điểm. RAG thông thường theo chuỗi PDF--chunk--vector--LLM dễ bỏ sót định danh pháp lý, trộn phiên bản, tạo citation không tồn tại hoặc trả lời một phần câu hỏi đa bằng chứng.

Hệ thống mục tiêu giải quyết các vấn đề sau:

- bảo toàn cấu trúc Chương, Mục, Điều, Khoản và Điểm, bao gồm nhãn Điểm tiếng Việt `đ)`;
- áp dụng khoảng hiệu lực `[effective_from, effective_to)` và quan hệ sửa đổi, thay thế, bãi bỏ;
- truy xuất chính xác theo số hiệu văn bản, Điều, Khoản, Điểm và cụm từ pháp lý;
- mở rộng tham chiếu chéo, quy định cha, sibling và penalty companion trong giới hạn;
- kiểm tra đủ evidence trước khi sinh câu trả lời;
- không trả claim hoặc citation chưa kiểm chứng.

Câu hỏi nghiên cứu trung tâm là: làm thế nào để hệ thống truy xuất đúng đơn vị pháp lý, đúng phiên bản tại thời điểm được hỏi, mở rộng đúng quy định liên quan và chỉ trả kết luận có citation kiểm chứng được?

## 2. Phạm vi và nguyên tắc bất biến

Corpus release bị khóa ở đúng **14 PDF sau deduplicate theo document identity/file hash**, từ allowlist chính xác `datafiles.chinhphu.vn`. Query-time chỉ dùng corpus/index đã phục vụ; không có open-web search hoặc web fallback để sinh câu trả lời pháp lý.

MVP không có upload endpoint, admin/reviewer role, approval UI/API hoặc human approval. Deployment giới hạn ở localhost/private network. Runtime hiện tại có Supabase Auth và persistence theo user; “single-user” mô tả boundary triển khai, không mô tả API không có authentication.

Các nguyên tắc không được hạ chuẩn:

1. UDEF bị loại bỏ khỏi pipeline.
2. Citation do code dựng từ metadata tin cậy; LLM không tự gõ citation tự do.
3. Evidence Completeness Gate chạy trước generator.
4. Verified-or-abstain; mục tiêu bất biến là Returned Invalid Citation Rate bằng 0.
5. Không mô tả hệ thống là autonomous agent.
6. Gold set final đóng băng; feedback không phải release gate.
7. Metric chưa chạy không được báo cáo là kết quả đạt.

## 3. Kiến trúc mục tiêu

Kiến trúc nghiên cứu mục tiêu gồm Parser Router, Canonical Document IR, Legal Structure Extractor, relation/temporal resolver, retrieval đa tầng, evidence planning, deterministic verification và bounded repair. Đây là target architecture; runtime audit tại mục [4](#4-runtime-hiện-tại-đã-audit) mô tả phần đã có.

### Pipeline ingestion mục tiêu

```text
Allowlist 14 PDF
→ immutable snapshot/hash
→ manual CLI
→ Parser Router (Docling | MinerU)
→ Canonical Document IR
→ Legal Structure Extractor
→ context/reference/temporal enrichment
→ automatic gates
→ accepted corpus
→ Qdrant derived index
```

Snapshot, hash, parser output và gate report phải truy vết được. Snapshot/index mới chỉ được publish sau khi gate đạt; index đang phục vụ phải được giữ khi rebuild thất bại.

### Pipeline query mục tiêu

```text
Câu hỏi
→ Query Understanding
→ Temporal Resolution
→ Exact + Dense + Sparse Retrieval
→ Fusion/Reranking
→ Bounded Legal Context Expansion
→ Evidence Gate
→ Structured Generation
→ Verification
→ Verified Answer hoặc Abstention
```

Query expansion phải giữ câu hỏi gốc. Rewrite hoặc HyDE chỉ bật có điều kiện và có giới hạn. Mỗi expansion phải có nguồn, loại quan hệ và depth để tránh mở rộng vô hạn.

### Controlled workflow mục tiêu

```text
START → analyze → temporal → expand → retrieve → fuse → rerank
→ expand_context → check_evidence → generate → verify
→ finalize | bounded_repair | abstain → END
```

Workflow mục tiêu không phải autonomous multi-agent. Repair phải phân biệt thiếu evidence, claim không được hỗ trợ, schema lỗi và temporal conflict; hết số lần repair hữu hạn thì abstain.

## 4. Runtime hiện tại đã audit

### API, authentication và persistence

`backend/app/main.py` đăng ký router RAG, auth, chats và legal. `backend/app/auth/` xác thực bearer token qua Supabase Auth. `backend/app/chats/` lưu session, user/assistant messages, feedback và bookmark qua Supabase REST; request persistence truyền token người dùng.

Flow của `backend/app/rag/api.py` là:

```text
Bearer auth → user-owned session → history/follow-up
→ persist user message → RAGService.answer
→ persist assistant response/citations → return IDs
```

Frontend hiện có chat route, conversation route, legal sources, saved items, citation drawer/viewer và LIKE/DISLIKE UI. Các capability này là runtime hiện tại, không phải thiết kế cũ “không auth”.

### Retrieval, evidence và generation

`backend/app/rag/retrieval.py` hiện dùng Qdrant local hoặc remote, dense `OpenAIEmbeddings` qua cấu hình OpenAI-compatible/OpenRouter, FastEmbed sparse BM25, hybrid search, exact metadata filtering, temporal filtering và bounded sibling/cross-reference expansion.

`backend/app/rag/service.py` hiện thực hiện workflow Python đồng bộ:

```text
analyze question → bounded intent/vehicle fan-out → Retriever
→ RRF-like merge/diversity cap → structural/temporal filtering
→ evidence check → generator → citation assembly
```

`backend/app/rag/evidence.py` có các deterministic check cho identity, reference, content, intent, score và effective interval. Tuy nhiên audit chưa tìm thấy implementation active của LangGraph, production reranker, sáu verifier độc lập đầy đủ hoặc repair graph như target architecture.

Generator hiện dùng ChatOpenRouter với model lấy từ cấu hình. Prompt yêu cầu tiếng Việt và grounding theo nguồn, nhưng output hiện là text Markdown; không nên gọi đây là structured claim generation đầy đủ nếu chưa có schema validation tương ứng.

Citation runtime hiện dựng từ `chunk_id`, `document_id`, article/clause/point và source metadata trong `RAGService`. Chưa có bằng chứng toàn bộ citation đã chuyển sang stable `provision_id` với `review_status = ACCEPTED`.

### Ingestion và corpus

`backend/app/ingestion/markdown.py` là Markdown/JSONL loader: parse front matter, nhận diện Điều/Khoản/Điểm bằng regex, tạo metadata, `chunk_id` và `content_sha256`, rồi đọc các file Markdown dưới `data/corpus/mds` theo `data/sources/manifest.json`.

Manifest hiện có 17 entries, gồm tài liệu hiện hành và lịch sử. Con số này không chứng minh corpus release đúng 14 PDF. Audit chưa tìm thấy active pipeline PDF Parser Router--Canonical IR--accepted publish hoặc PostgreSQL legal source-of-truth. Riêng script `freeze_candidate_corpus.py` tạo artifact candidate 14 PDF accepted; artifact này không tự động trở thành nguồn mà active Markdown loader hoặc Qdrant index đang phục vụ sử dụng.

### Status, temporal và citation limitations

Runtime có temporal filtering theo khoảng ngày ở retrieval/service, nhưng `evidence.py` dùng boundary khác ở một nhánh kiểm tra (`effective_to` được xử lý inclusive thay vì exclusive). Runtime cũng chưa yêu cầu `review_status = ACCEPTED`. Đây là blocker cần sửa trước khi tuyên bố temporal gate hoàn chỉnh.

Service hiện phân biệt một số reason code, nhưng `CORPUS_NOT_COVERED` và workflow-failure status chưa được đảm bảo như status độc lập ở mọi path; `OUT_OF_SCOPE` được normalize thêm tại API layer. Generator trả Markdown tự do, không có structured claim schema hoặc independent six-layer verifier. Citation hiện dùng `chunk_id`; không được mô tả là stable `provision_id` citation đã verified.

### Frontend và deployment caveats

Chat requests, sessions, saved items, feedback và bookmarks dùng bearer token theo user. Legal-source listing và một số citation-detail fetches hiện không gửi bearer token vì các endpoint đó là public read paths. Chat client có timeout 120 giây và synthetic progress; không có streaming/SSE runtime contract.

`deploy/compose/compose.release.yml` chỉ có frontend, backend và Qdrant; Supabase là dịch vụ ngoài Compose. Public Supabase/API values được bake ở build time. Release compose không thiết lập `BACKEND_INTERNAL_URL`; `frontend/next.config.ts` có thể mặc định rewrite tới `127.0.0.1:8000` bên trong frontend container. Đây là deployment blocker cần kiểm tra bằng release build/run, không được bỏ qua trong release checklist.

## 5. Mô hình dữ liệu mục tiêu

Canonical Document IR mục tiêu gồm `ParsedDocument`, `ParsedPage` và `DocumentElement`; element có text, page, bounding box, reading order, parent và parser provenance.

LegalProvision mục tiêu có tối thiểu:

```text
provision_id, document_version_id, hierarchy, source_text, retrieval_text,
parent_context, temporal fields, status, page/bbox, source_element_ids,
hash và review status
```

`source_text` giữ nguyên nội dung pháp lý. `retrieval_text` có thể bổ sung parent context. Stable identity phải phân biệt `d)` và `đ)`, ví dụ `nd-168-2024__dieu-7__khoan-4__diem-b`.

Quan hệ mục tiêu gồm `PARENT_OF`, `REFERS_TO`, `SIBLING_OF`, `PENALTY_COMPANION` và document relations `AMENDS`, `REPEALS`, `SUPERSEDES`, `CORRECTS`, `GUIDES`, `RELATED_TO`. Runtime chưa chứng minh các quan hệ này được lưu trong PostgreSQL như mô hình mục tiêu.

Điều kiện temporal mục tiêu:

`effective_from ≤ d` and (`effective_to` is null or `d < effective_to`) and `review_status = ACCEPTED`.

## 6. Phạm vi chức năng và giới hạn

P0 release contract gồm:

1. corpus đúng 14 PDF allowlisted, deduplicate và snapshot/hash bất biến;
2. manual CLI ingestion, fail closed, không upload/admin/reviewer approval;
3. provision boundary, provenance, reference và temporal semantics kiểm chứng được;
4. exact/dense/sparse retrieval và bounded legal expansion;
5. evidence plan, completeness gate, structured claims và verified-or-abstain;
6. current, historical và comparison query;
7. trạng thái riêng cho `CORPUS_NOT_COVERED`, `OUT_OF_SCOPE`, thiếu evidence và workflow failure;
8. UI hiển thị answer, citation/passage, ngày áp dụng, disclaimer và LIKE/DISLIKE;
9. full gold gate 200 câu thuộc 17 category trước release.

Ngoài phạm vi: open-web answer fallback, upload API/UI, admin/reviewer workflow, human approval, feedback comment/category/PII, corpus ngoài 14 PDF, mobile, voice, autonomous multi-agent, Neo4j, fine-tuning, local LLM, microservices, Kubernetes và tư vấn pháp lý cá nhân hóa có tính kết luận.

## 7. Công nghệ và chính sách model

| Khu vực | Chính sách/runtime đã audit |
|---|---|
| Backend | Python 3.11, FastAPI, Pydantic v2 |
| Retrieval | Qdrant hybrid dense/sparse, FastEmbed sparse BM25 |
| Embedding | Cấu hình OpenAI-compatible/OpenRouter; chưa chốt production bằng benchmark |
| Generator | ChatOpenRouter, model lấy từ cấu hình |
| Auth/persistence | Supabase REST/Auth |
| Frontend | Next.js 16, React 19, TypeScript |
| Deployment | Docker Compose: frontend, backend, Qdrant |
| Workflow mục tiêu | Controlled workflow; LangGraph chưa có trong runtime audit |
| Parser mục tiêu | Parser Router/Docling/MinerU chưa có active path được chứng minh |
| Evaluation | Deterministic metrics headline; LLM judge thứ cấp |

Model ID phải nằm trong config, có version trong evaluation run và không được hardcode trong domain logic. Không tuyên bố embedding hoặc reranker cải thiện trước benchmark.

## 8. Đánh giá và release gate

Gold set mục tiêu gồm 200 câu: 40 development, 40 validation và 120 final test. 17 category là: CURRENT, HISTORICAL, COMPARISON, EXACT_REFERENCE, PENALTY, LICENSE_POINTS, CONDITION, EXCEPTION, PROCEDURE, CROSS_REFERENCE, MULTI_PROVISION, MULTI_DOCUMENT, COLLOQUIAL_QUERY, AMBIGUOUS, MISSING_INFORMATION, OUT_OF_SCOPE và ADVERSARIAL_CITATION.

Suite A đánh giá parser; Suite B đánh giá embedding; Suite C đánh giá retrieval ablation; Suite D đánh giá generation và verification. Metric chính gồm retrieval, evidence, temporal, citation, grounding, corpus, abstention và performance. Deterministic metrics là headline; LLM judge là nguồn thứ cấp.

Không release nếu thiếu full gold run, provenance artifact, semantic review cần thiết hoặc vi phạm safety/citation gate. Mỗi run phải lưu corpus/index hash, gold-set hash, model/prompt/config version, Git commit, raw output, error analysis và immutable run manifest.

## 9. Sản phẩm và thay đổi

Sản phẩm mục tiêu gồm mã nguồn backend/frontend, corpus manifest, retrieval và evidence pipeline, UI citation, evaluation artifacts và tài liệu kỹ thuật. Tuy nhiên chỉ những phần được code, deployment hoặc evaluation chứng minh mới được gọi là delivered.

Thay đổi phạm vi/kiến trúc cần bằng chứng kỹ thuật hoặc thực nghiệm, không được hạ frozen scope, phải cập nhật tài liệu liên quan và phải version hóa gold set/experiment matrix nếu bị ảnh hưởng. Các quyết định không được thay đổi âm thầm: không web fallback, không autonomous agent, UDEF không quay lại, citation chưa verified không được trả, Evidence Completeness Gate là điều kiện trước generation và metric chưa chạy không được báo cáo là đạt.

## 10. Tài liệu tham khảo

- Phạm vi và quyết định: `docs/00-scope-and-decisions.md`.
- Thiết kế hệ thống: `docs/03-thiet-ke-he-thong.md`.
- Đánh giá hiện tại: `docs/evaluation/thesis-api-subset-32-20260913.md`.
- [Qdrant hybrid queries](https://qdrant.tech/documentation/search/hybrid-queries/)
- [Supabase Auth](https://supabase.com/docs/guides/auth)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Next.js](https://nextjs.org/docs)
