> **MVP đã phê duyệt — 10/09/2026**: Phạm vi release là một corpus cố định gồm đúng **14 PDF đã khử trùng lặp theo tài liệu/hash**, lấy từ allowlist chính xác `datafiles.chinhphu.vn`. Hệ thống single-user, chạy localhost/private network, không auth, không admin/reviewer role/API/UI. Ingestion chỉ chạy thủ công qua CLI; quality/provenance/temporal gates là tự động, snapshot và hash bất biến, không có human approval. Query-time chỉ phục vụ corpus đã index, không web fallback. Gold gate gồm toàn bộ 200 câu risk-weighted thuộc 17 category; feedback chỉ là tín hiệu LIKE/DISLIKE ẩn danh tối thiểu và không phải release gate.
>
> **Model policy**: Tên model cụ thể không được hardcode trong phạm vi/yêu cầu. Embedding được chọn sau benchmark nhỏ giữa các ứng viên local đã cài hoặc cache; chỉ rebuild index sau khi chọn được ứng viên. Không ghi nhận model hoặc ngưỡng số cụ thể nếu chưa có bằng chứng thực nghiệm.
# 00. Phạm Vi và Quyết Định Thiết Kế

> **Tên dự án**: VN Traffic Law RAG  
> **Ngày tạo**: 16/06/2026  
> **Ngày baseline v1**: 19/07/2026  
> **Ngày thiết kế lại v2**: 08/08/2026  
> **Hạn hoàn thành / release candidate**: 16/09/2026  
> **Ngày báo cáo / bảo vệ**: 16/09/2026  
> **Trạng thái**: Baseline thiết kế đã chốt (bản thiết kế lại v2)  
> **Vai trò tài liệu**: Nguồn quyết định kiến trúc và phạm vi cao nhất của dự án

---

## 1. Tên đề tài

### Tiếng Việt

**Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng**

### Tiếng Anh

**A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations**

Tên đề tài không sử dụng từ **Agentic**. LangGraph được dùng như một controlled workflow có các nhánh xác định trước, không được mô tả như agent tự trị.

---

## 2. Bài toán nghiên cứu

Hệ thống phải trả lời câu hỏi pháp luật giao thông Việt Nam dựa trên corpus đã kiểm chứng, đồng thời giải quyết bảy vấn đề:

1. **Cấu trúc pháp lý**: Văn bản pháp luật có cấu trúc phân cấp gồm Chương, Mục, Điều, Khoản và Điểm, trong đó nhãn Điểm dùng bảng chữ cái tiếng Việt (a) b) c) d) đ) e) ...). Ranh giới pháp lý phải trùng khớp ranh giới trích dẫn, không thể cắt chunk tùy ý.
2. **Hiệu lực thời gian**: Một quy định chỉ đúng trong khoảng thời gian hiệu lực nhất định; văn bản có thể bị sửa đổi, thay thế hoặc bãi bỏ từng phần, tạo ra các phiên bản hiệu lực khác nhau.
3. **Quan hệ tham chiếu giữa các quy định**: Điều, Khoản, Điểm tham chiếu chéo lẫn nhau; văn bản này dẫn chiếu văn bản kia; các quy định xử phạt thường gắn kèm quy định về điểm giấy phép lái xe hoặc biện pháp khắc phục hậu quả.
4. **Trích dẫn ảo giác**: Mô hình ngôn ngữ có thể tạo thông tin hoặc trích dẫn không tồn tại trong corpus, hoặc ghép nội dung đúng với `provision_id` sai.
5. **Bỏ sót retrieval theo định danh chính xác**: Retrieval theo vector thuần túy có thể bỏ sót số hiệu văn bản, số Điều, số Khoản, nhãn Điểm hoặc cụm từ pháp lý chính xác, dù các token này có tính quyết định.
6. **Câu hỏi đa bằng chứng**: Một câu hỏi có thể yêu cầu nhiều loại bằng chứng (ví dụ vừa mức phạt vừa số điểm trừ); hệ thống không được âm thầm trả lời một nửa dễ của câu hỏi và bỏ sót nửa còn lại.
7. **Tham chiếu chéo và tính đầy đủ bằng chứng**: Bằng chứng cho câu trả lời thường nằm rải rác ở các quy định liên quan; hệ thống phải chủ động mở rộng ngữ cảnh theo quan hệ tham chiếu và kiểm chứng rằng mọi loại bằng chứng cần thiết đều đã được thu thập.

Câu hỏi nghiên cứu trung tâm:

> Làm thế nào để một hệ thống RAG truy xuất đúng đơn vị pháp lý, áp dụng đúng phiên bản văn bản tại thời điểm được hỏi, mở rộng đúng các quy định liên quan, và chỉ trả về các kết luận có trích dẫn kiểm chứng được?

---

## 3. Mục tiêu và nguyên tắc cốt lõi của thiết kế lại

Mục tiêu thiết kế của phiên bản v2:

> Hệ thống RAG pháp luật nhận biết cấu trúc, nhận biết quan hệ tham chiếu, nhận biết thời gian hiệu lực, với retrieval đa tầng, mở rộng bằng chứng theo quan hệ pháp lý và verification cấp claim, hướng tới trích dẫn có thể kiểm chứng.

Các nguyên tắc bắt buộc, có hiệu lực toàn cục:

1. **Loại bỏ hoàn toàn UDEF** khỏi mọi pipeline và phụ thuộc; thay thế bằng Parser Router, Canonical Document IR và bộ phân tích pháp lý do dự án sở hữu.
2. **Giữ nguyên các năng lực đã chốt**: nhận biết cấu trúc pháp lý; định danh ổn định cấp provision; câu hỏi hiện hành/lịch sử/so sánh; khoảng hiệu lực [effective_from, effective_to); PostgreSQL là nguồn chân lý dữ liệu pháp lý; Qdrant là index retrieval có thể dựng lại; trích dẫn theo `provision_id`; verified-or-abstain; evaluation tái lập được.
3. **Ingestion dùng parser trực tiếp** lên tài liệu nguồn, không qua tầng UDEF.
4. **Chất lượng parser là mục tiêu evaluation hạng nhất** (first-class), có benchmark riêng.
5. **Mô hình hóa tham chiếu chéo pháp lý** (cross-reference) ở cấp provision và cấp văn bản.
6. **Retrieval đa tầng** (multi-stage): exact lookup, dense, sparse, RRF fusion, reranking, mở rộng ngữ cảnh pháp lý.
7. **Kiểm tra tính đầy đủ bằng chứng** (evidence completeness) trước khi sinh câu trả lời.
8. **Verification xác định** (deterministic) mạnh hơn, sáu tầng, với bất biến API Returned Invalid Citation Rate = 0.
9. **Langfuse** phục vụ observability, quản lý prompt, trace và experiment; không nằm trên đường tới hạn tính đúng đắn.
10. **RAGFlow chỉ là baseline so sánh bên ngoài**, không bao giờ là nền tảng chính.
11. **Không thu hẹp phạm vi** vì lịch trình hoặc độ khó.
12. **Không bao giờ mô tả kết quả thực nghiệm chưa hoàn thành như đã đạt được.**
13. **Không dùng kiến trúc multi-agent tự trị**; LangGraph là controlled workflow với các nhánh xác định trước.
14. **Không dùng open-web search để sinh câu trả lời pháp lý.**

---

## 4. Đóng góp chính

Thiết kế v2 thay toàn bộ nền tảng UDEF bằng các thành phần sau:

### 4.1. Pipeline phân tích tài liệu với Parser Router và Canonical Document IR

- **Parser Router** chọn parser theo đặc tính tài liệu và quality gate: PDF có text tìm kiếm được (searchable) dùng Docling trước; tài liệu scan hoặc layout lỗi dùng Docling trước, nếu quality gate không đạt thì dùng MinerU; bảng phức tạp so sánh kết quả hai parser khi cần. Không khẳng định parser nào vượt trội tuyệt đối cho mọi trường hợp.
- **Docling** là parser chính; **MinerU** là parser phụ và fallback/challenger.
- **Canonical Document IR** là biểu diễn trung gian do dự án sở hữu, không phụ thuộc parser, gồm `ParsedDocument`, `ParsedPage`, `DocumentElement`. Tầng IR cô lập việc phân tích pháp lý khỏi định dạng đầu ra của Docling/MinerU.

### 4.2. Legal Structure Extractor cho phân cấp pháp luật Việt Nam

- Nhận diện Chương, Mục, Điều, Khoản, Điểm, Phụ lục, bảng pháp lý, điều khoản chuyển tiếp, tiêu đề, đánh số văn bản pháp luật Việt Nam và các biến thể do OCR.
- **Bắt buộc hỗ trợ nhãn Điểm tiếng Việt a) b) c) d) đ) e)**; không dùng giả định `[a-z]` đơn giản.
- **Giữ Điểm ngắn**: một Điểm pháp lý ngắn nhưng hợp lệ vẫn là provision hợp lệ, không loại bỏ vì số token thấp (short-Point retention).

### 4.3. Mô hình quan hệ tham chiếu pháp lý

- `ProvisionReference` với các loại quan hệ cấp provision: `PARENT_OF`, `REFERS_TO`, `SIBLING_OF`, `PENALTY_COMPANION`.
- `DocumentRelation` với các loại quan hệ cấp văn bản: `AMENDS`, `REPEALS`, `SUPERSEDES`, `CORRECTS`, `GUIDES`, `RELATED_TO`.
- Quan hệ được lưu trong bảng PostgreSQL và xử lý bằng application logic; không dùng Neo4j hoặc knowledge graph.

### 4.4. LegalContextEnricher và bổ trợ ngữ cảnh cha (parent-context enrichment)

- `retrieval_text` của một Điểm có thể kế thừa ngữ cảnh cha như câu mở đầu của Khoản, tiêu đề Điều, hoặc ngữ cảnh cấu trúc liên quan.
- `source_text` luôn giữ nguyên nội dung pháp lý gốc, không bao giờ bị biến đổi; trích dẫn vẫn trỏ tới Điểm thực tế.

### 4.5. Mô hình thời gian hiệu lực

- Mỗi provision mang khoảng hiệu lực [effective_from, effective_to) với điều kiện hợp lệ xác định (xem mục 8.6).
- Hỗ trợ câu hỏi hiện hành, câu hỏi tại ngày cụ thể, câu hỏi so sánh, biên sửa đổi, sửa đổi từng phần, quy định bị thay thế, và định tuyến các quy định hiệu lực không chắc chắn sang review.

### 4.6. Retrieval đa tầng

- Ba kênh song song: **exact legal lookup** (xử lý định danh như `168/2024/NĐ-CP`, `Điều 7`, `Khoản 4`, `Điểm a`), **dense semantic**, **sparse BM25**.
- **RRF fusion** cho kết hợp dense + sparse, sau đó **reranking**, rồi **mở rộng ngữ cảnh pháp lý** theo quan hệ (cha, anh em, tham chiếu trực tiếp, quy định kèm xử phạt).

### 4.7. Evidence planning và Evidence Completeness Gate

- Query understanding xây dựng **evidence plan** liệt kê các loại bằng chứng cần thiết (định nghĩa hành vi vi phạm, mức phạt tiền, trừ điểm giấy phép, tước quyền sử dụng giấy phép lái xe (license suspension), ngoại lệ, thủ tục, điều kiện pháp lý).
- Trước khi sinh câu trả lời, hệ thống kiểm tra mọi loại bằng chứng trong plan đã có; nếu thiếu sẽ chạy targeted retrieval hoặc mở rộng theo quan hệ, không sinh câu trả lời nửa vời.

### 4.8. Verification xác định sáu tầng

- L1 Schema, L2 Citation ID, L3 Temporal validity, L4 Numeric grounding, L5 Claim support, L6 Evidence completeness (chi tiết mục 6.3).
- Bất biến API: **Returned Invalid Citation Rate = 0**.

### 4.9. Verified-or-abstain với failure-aware repair

- Không đơn thuần regenerate: mỗi lỗi có hướng sửa riêng (thiếu bằng chứng chạy targeted retrieval, claim không được hỗ trợ sinh lại từ bằng chứng hiện có, schema sai sinh lại structured output, xung đột thời gian truy xuất phiên bản đúng).
- Số lần repair có giới hạn (bounded); hết giới hạn thì ABSTAIN. Không có vòng lặp vô hạn.

### 4.10. Structured generation với schema cấp claim

- Câu trả lời được sinh theo schema với các field: `answer_summary`; `claims` (mỗi claim gồm `claim`, `claim_type`, `provision_ids`, `numbers`); `missing_information`; `should_abstain`.
- Phần trích dẫn hiển thị được dựng từ metadata tin cậy, không phải văn bản tự do do LLM gõ.

### 4.11. Langfuse observability

- Trace toàn bộ pipeline: `legal_query` với các span `analyze_query`, `normalize_query`, `rewrite_query`, `hyde`, `exact_lookup`, `dense_retrieval`, `sparse_retrieval`, `rrf_fusion`, `reranker`, `reference_expansion`, `evidence_check`, `generate`, `citation_verify`, `numeric_verify`, `claim_verify`.
- Hỗ trợ quản lý prompt và phiên bản prompt, experiment, dataset, LLM-as-judge, annotation và feedback.
- Không nằm trên đường tới hạn tính đúng đắn: nếu Langfuse không khả dụng, query vẫn hoạt động.

### 4.12. RAGFlow chỉ làm baseline bên ngoài

- Baseline so sánh: RAGFlow default, RAGFlow + Docling, RAGFlow + MinerU, so với VNLRAG custom legal-aware pipeline, trên cùng corpus và cùng bộ câu hỏi evaluation.
- RAGFlow chạy trong môi trường benchmark riêng, không nằm trong compose production.

- **RAGFlow chỉ là baseline so sánh bên ngoài**, không phải release dependency.
- **Không chạy background ingestion, upload API, review queue hoặc human approval trong MVP**; ingestion manual CLI và các gate tự động.
- **MVP single-user trong localhost/private network**, không auth/admin/reviewer role/API/UI.

### 4.14. Evaluation tái lập được với nhiều bộ thí nghiệm

- Bốn suite: A (parser P1-P3), B (embedding E1-E3), C (retrieval R1-R10), D (generation và verification G1-G7).
- Deterministic metrics là headline, LLM judge là thứ cấp; final test set đóng băng; toàn bộ bối cảnh chạy được ghi lại (chi tiết mục 11).

---

## 5. UDEF đã được loại bỏ

Thiết kế v1 dựa trên UDEF Traffic Law Domain Pack (`traffic_law` RuleSpec) cho việc trích xuất cấu trúc và metadata, với pipeline `PDF -> UDEF -> Docling -> CDM`. Phiên bản v2 **loại bỏ hoàn toàn** phụ thuộc này.

Lý do loại bỏ:

- UDEF định nghĩa schema domain riêng, tạo tầng chuyển đổi và chi phí bảo trì không cần thiết giữa output của parser và mô hình dữ liệu pháp lý của dự án.
- Domain pack không được thiết kế riêng cho phân cấp pháp luật Việt Nam; việc nhận diện nhãn Điểm tiếng Việt (bao gồm đ) và Điểm ngắn) đòi hỏi bộ phân tích do dự án kiểm soát.
- UDEF đưa thêm lớp confidence/validation mà dự án tự đảm nhận tốt hơn qua quality gate và review routing của riêng mình.

Những gì thay thế UDEF:

1. **Parser Router** trực tiếp đọc tài liệu bằng Docling (chính) hoặc MinerU (phụ/fallback).
2. **Canonical Document IR** do dự án sở hữu làm biểu diễn trung gian chuẩn hóa.
3. **Legal Structure Extractor** là parser pháp lý riêng của VNLRAG, chịu trách nhiệm toàn bộ việc nhận diện cấu trúc và chuẩn hóa Điều, Khoản, Điểm.

Loại bỏ mọi phụ thuộc vào: UDEF, UDEF domain pack, `traffic_law` RuleSpec, UDEF CDM, UDEF confidence engine, UDEF projector, UDEF adapter, UDEF commit pin, UDEF review routing, UDEF ingestion tests, quy trình deployment/bảo trì riêng của UDEF. Các tài liệu cũ phải được rà soát để không còn xuất hiện các thuật ngữ này trừ khi mang tính lịch sử có chủ đích.

---

## 6. Kiến trúc chốt

### 6.1. Offline ingestion
```text
Allowlist datafiles.chinhphu.vn
        ↓
14 PDF MVP → deduplicate by document/hash → immutable snapshot manifest
        ↓
Manual CLI sync
        ↓
Parser Router (Docling | MinerU)
        ↓
Canonical Document IR
        ↓
Legal Structure Extractor
        ↓
Legal Context Enricher
        ↓
Legal Reference Resolver
        ↓
Temporal and Amendment Resolver
        ↓
Automatic quality + provenance + temporal gates
        ↓
PostgreSQL (nguồn chân lý dữ liệu pháp lý)
        ↓
Embedding and Sparse Indexing
        ↓
Qdrant (index dẫn xuất, rebuild sau khi benchmark/chọn embedding)
```

Ingestion chỉ chạy thủ công qua CLI, không có upload endpoint, worker queue, review routing hoặc human approval. Mỗi snapshot ghi hash bất biến; tài liệu trùng theo document identity hoặc file hash chỉ giữ một bản. Khi rebuild index, index cũ được giữ nguyên cho tới khi index mới vượt qua các gate; lỗi rebuild không được thay thế index đang phục vụ.

### 6.2. Online query workflow

```text
Câu hỏi người dùng
        ↓
Query Understanding (intent, query_date, comparison dates,
                     vehicle_type, legal entities, normalized query,
                     số văn bản/Điều/Khoản/Điểm, evidence plan)
        ↓
Temporal Resolution
        ↓
Query Expansion (original | normalized | multi-query rewrite | conditional HyDE)
        ↓
Parallel Multi-Recall (exact legal lookup | dense | sparse BM25)
        ↓
RRF Fusion
        ↓
Reranking
        ↓
Legal Context Expansion (parent | sibling | cross-reference | penalty companion)
        ↓
Evidence Completeness Gate (complete → generate | incomplete → targeted retrieval)
        ↓
Context Builder
        ↓
Structured Answer Generator
        ↓
Verification (schema, citation ID, temporal, numeric grounding,
             claim support, evidence completeness)
        ↓
Verified Answer | Abstention
```

Query expansion luôn giữ câu hỏi gốc của người dùng. HyDE chỉ dùng có điều kiện (câu ngắn, khẩu ngữ, ngữ nghĩa yếu hoặc bằng chứng chưa đủ), không bật luôn. Không có vòng rewrite không giới hạn.

Mở rộng ngữ cảnh pháp lý chỉ quanh các seed provision mạnh, mỗi provision mở rộng phải ghi lý do vào context:

```json
{"provision_id": "...", "added_by": "CROSS_REFERENCE", "source_id": "...", "depth": 1}
```

Tránh mở rộng đồ thị không giới hạn.

### 6.3. LangGraph controlled workflow

LangGraph là lớp điều phối workflow có kiểm soát (không phải autonomous multi-agent). Đồ thị đề xuất:

```text
START → analyze_query → resolve_temporal → expand_query → retrieve_parallel
     → fuse → rerank → expand_legal_context → check_evidence → generate
     → verify → finalize | repair | abstain → END
```

Các cạnh có điều kiện:

- `check_evidence`: `complete` -> `generate`; `incomplete` -> `targeted_retrieval` -> `check_evidence`.
- `verify`: `valid` -> `finalize`; `repairable` -> repair path; `invalid/unrecoverable` -> `abstain`.

Sửa lỗi có ý thức (failure-aware repair), không chỉ regenerate:

- thiếu bằng chứng -> targeted retrieval -> dựng lại context -> regenerate;
- claim không được hỗ trợ -> regenerate từ bằng chứng hiện có, hoặc targeted retrieval nếu thiếu bằng chứng;
- schema không hợp lệ -> regenerate structured output;
- xung đột thời gian -> truy xuất phiên bản thời gian đúng.

Sau số lần repair có giới hạn: **ABSTAIN**. Không có vòng lặp vô hạn. Cơ chế đếm bước trong state hoặc interrupt để dừng, kết hợp checkpoint để retry/resume idempotent.

### 6.4. Verification sáu tầng

| Tầng | Bộ kiểm chứng | Nội dung |
|---|---|---|
| L1 | Schema verifier | Kết quả tuân thủ Pydantic schema cấp claim |
| L2 | Citation ID verifier | `provision_id` tồn tại; đã được retrieve hoặc được mở rộng hợp lệ; review_status ACCEPTED; metadata citation có thẩm quyền |
| L3 | Temporal verifier | Provision được trích dẫn có hiệu lực tại ngày được hỏi |
| L4 | Numeric grounding verifier | Mức phạt, số điểm trừ, ngày, tuổi, thời hạn, số lượng khớp giá trị bằng chứng đã chuẩn hóa |
| L5 | Claim support verifier | Quy tắc xác định (deterministic) trước; LLM judge độc lập chỉ dùng cho các trường hợp ngữ nghĩa |
| L6 | Evidence completeness verifier | Mọi loại bằng chứng cần thiết trong evidence plan đã được bao phủ |

Bất biến API: **Returned Invalid Citation Rate = 0**.

### 6.5. Vị trí của HITL

MVP không có HITL, reviewer role hoặc approval workflow. Ingestion chỉ được publish khi các quality, provenance và temporal gates tự động đạt; nếu gate fail thì snapshot/index mới bị từ chối, còn snapshot/index đang phục vụ được giữ nguyên.

### 6.6. Feedback và observability

- End-user feedback chỉ gồm LIKE hoặc DISLIKE, ẩn danh và tối thiểu; không nhận comment, category, raw prompt/answer hoặc PII.
- Feedback chỉ dùng làm tín hiệu quan sát, không tự động sửa corpus, không đưa vào gold set và không phải release gate.
- Observability không được làm thay đổi legal-safety gates hoặc query result.

---

## 7. Tech stack chốt

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.11 |
| API | FastAPI + Pydantic v2 |
| Workflow | LangGraph 1.x (controlled workflow, pin `langgraph>=1.1`) |
| Parser chính | Docling 2.x |
| Parser phụ / fallback | MinerU 3.4.x (Parser Router) |
| Metadata và versioning | PostgreSQL 18 + SQLAlchemy 2 + Alembic |
| Retrieval | Qdrant v1.19 (dense + sparse + payload filter + RRF) |
| Dense embedding | Ứng viên: Gemini Embedding 2 (768 dimensions) benchmark với Jina Embeddings v5 text-nano / text-small |
| Sparse retrieval | Qdrant sparse BM25 |
| Fusion | Qdrant RRF |
| Reranker | Ứng viên: Jina Reranker v3 |
| Generator | Gemini 3.7 Flash | `gemini-3.7-flash` | Structured legal answer theo schema cấp claim |
| Judge độc lập | Gemini 3.5 Flash Lite | `gemini-3.5-flash-lite` | Semantic judge fail-closed và metric thứ cấp |
| Evaluation | Ragas v0.4.x + deterministic custom metrics |
| Object storage | MinIO (S3-compatible) |
| Background jobs | Redis (broker + cache) + Dramatiq 2.x |
| Observability | Langfuse Cloud (mặc định) |
| Frontend | Next.js + TypeScript + shadcn/ui |
| Testing | pytest + Playwright |
| Package management | uv |
| Deployment | Docker Compose |
| CI/CD | GitHub Actions |

Ghi chú về tech stack:

- **Embedding chưa được chốt vĩnh viễn.** Gemini Embedding 2 (768 dimensions) là ứng viên mặc định nhưng phải được benchmark với Jina Embeddings v5 text-nano và text-small trên các câu hỏi pháp luật tiếng Việt (Recall@10, MRR@10, nDCG@10, latency, cost) trước khi chọn embedding production. Quyết định phải dựa trên bằng chứng thực nghiệm.
- **Reranker chưa được khẳng định cải thiện chất lượng.** Jina Reranker v3 là ứng viên chính; late-interaction/ColBERT-style reranking chỉ là ứng viên thí nghiệm. Không tuyên bố reranker cải thiện chất lượng trước khi benchmark.
- Tên model và model ID phải nằm trong cấu hình, không hardcode trong domain logic. Trước khi chạy evaluation cuối, phải pin model snapshot hoặc ghi lại model version thực tế.
- Không dùng full LangChain, Haystack hoặc LlamaIndex trong core implementation. Chỉ giữ `langgraph`, `langchain-core` nếu cần, SDK chính thức của provider và các thư viện hạ tầng trực tiếp.
- Không dùng pgvector trong thiết kế này: vector retrieval nằm trong Qdrant, PostgreSQL giữ metadata và quan hệ pháp lý.
- Trên máy phát triển cá nhân (CPU, RAM 19 GB, GPU không dùng được cho LLM/reranker), ingestion job chạy với `MAX_INGESTION_WORKERS=1`; toàn bộ LLM, embedding và reranker dùng API online.
- Langfuse Cloud là lựa chọn mặc định cho dev và evaluation; self-hosting là tùy chọn (cần ClickHouse, Redis/Valkey, blob storage, PostgreSQL, web và worker service).

---

## 8. Mô hình dữ liệu cốt lõi

### 8.1. Canonical Document IR

Biểu diễn trung gian, parser-neutral, do dự án sở hữu:

```text
ParsedDocument
  └── ParsedPage[]
      └── DocumentElement[]
```

`DocumentElement` gồm: `element_id`, `element_type`, `text`, `page_number`, `bbox`, `reading_order`, `parent_element_id`, `table_html` (khi có), `source_parser`, `parser_version`, `parser_confidence`, `raw_reference`.

### 8.2. LegalDocument và DocumentVersion

`LegalDocument` gồm: `document_id`, `document_number`, `document_title`, `document_type`, `issuer`, `issued_date`, `source_url`, `file_hash`, `status`, `version`, `created_at`, `updated_at`.

`DocumentVersion` ghi nhận mỗi phiên bản nội dung của văn bản, gắn với các quan hệ pháp lý (AMENDS/REPEALS/SUPERSEDES/CORRECTS/GUIDES/RELATED_TO).

### 8.3. LegalProvision

Các field tối thiểu:

```text
provision_id
document_version_id
chapter
section
article
clause
point
heading
source_text
retrieval_text
parent_context
effective_from
effective_to
status
page_number
bbox
source_element_ids
content_hash
version
review_status
```

Quy tắc:

- `source_text` là nội dung pháp lý thuộc trực tiếp provision, giữ nguyên văn bản gốc.
- `retrieval_text` có thể kế thừa ngữ cảnh cha khi phục vụ retrieval; trích dẫn vẫn trỏ tới provision thực tế (Điểm).
- `provision_id` phải ổn định và có thể tái tạo theo quy tắc xác định trước: `{loai-van-ban}-{so}-{nam}__dieu-{n}__khoan-{n}__diem-{chu-cai}` (ví dụ `nd-168-2024__dieu-7__khoan-4__diem-b`). Nhãn Điểm được ánh xạ xác định bằng cách giữ nguyên ký tự tiếng Việt trong ID, bao gồm cả `đ` (ví dụ Điểm `đ)` tương ứng `diem-đ`), tránh va chạm với Điểm `d)` (`diem-d`).
- Khi một provision bị sửa đổi, `provision_id` giữ nguyên để trích dẫn ổn định và câu hỏi lịch sử vẫn hoạt động; nội dung mới được lưu dưới một `version` mới (xem `ProvisionVersion`) với khoảng [effective_from, effective_to) mới.
- `status` mô tả vòng đời pháp lý của provision (ví dụ draft/published/repealed); `review_status` mô tả trạng thái review corpus (ví dụ PENDING/ACCEPTED/REJECTED) và là cổng chặn trong điều kiện hiệu lực (mục 8.6); hai trường này độc lập nhau.

Ví dụ stable ID:

```text
nd-168-2024__dieu-7__khoan-4__diem-b
```

Ví dụ tách source_text / retrieval_text:

- `source_text`: `"p) Dàn hàng ngang từ 03 xe trở lên"`
- `retrieval_text`: `"Khoản 4. Phạt tiền từ ... đến ... đối với một trong các hành vi sau: p) Dàn hàng ngang từ 03 xe trở lên"`
- Citation vẫn trỏ tới Điểm p.

Lưu ý: ví dụ stable ID (`diem-b`) và ví dụ tách source_text/retrieval_text (`Điểm p)`) là hai minh họa độc lập, không phải cùng một Điểm. Ví dụ mang tính minh họa: các con số trong `retrieval_text` là placeholder ("..."), không phải khẳng định về nội dung văn bản thực tế của NĐ 168/2024.

### 8.4. ProvisionReference và DocumentRelation

`ProvisionReference` (cấp provision): `PARENT_OF`, `REFERS_TO`, `SIBLING_OF`, `PENALTY_COMPANION`. Trong đó `PENALTY_COMPANION` gắn quy định xử phạt với quy định đi kèm, ví dụ trừ điểm giấy phép lái xe hoặc tước quyền sử dụng giấy phép lái xe (license suspension).

`DocumentRelation` (cấp văn bản/hiệu lực): `AMENDS`, `REPEALS`, `SUPERSEDES`, `CORRECTS`, `GUIDES`, `RELATED_TO`.

Không dùng Neo4j; quan hệ được lưu trong bảng PostgreSQL và xử lý bằng application logic.

### 8.5. LegalEffectEvent

Ghi lại sự kiện pháp lý ảnh hưởng tới hiệu lực của văn bản/provision (sửa đổi, thay thế, bãi bỏ, có hiệu lực, hết hiệu lực) để phục vụ temporal resolver và câu hỏi so sánh lịch sử.

### 8.6. Điều kiện hiệu lực thời gian

Provision hợp lệ cho ngày `d` khi thỏa mãn đồng thời:

```text
effective_from <= d
AND (effective_to IS NULL OR d < effective_to)
AND review_status = ACCEPTED
```

PostgreSQL là nguồn chân lý dữ liệu pháp lý. Qdrant là index dẫn xuất, luôn có thể dựng lại từ PostgreSQL; nếu dữ liệu hai nơi khác nhau thì PostgreSQL thắng.

### 8.7. Các thực thể còn lại

Hệ thống còn quản lý: `LegalSource`, `ProvisionVersion`, `IngestionRun`, `IngestionArtifact`, `ReviewItem`, `QueryTrace`, `QueryFeedback`, `EvaluationDataset`, `EvaluationRun`, `EvaluationResult`.

---

## 9. Phạm vi chức năng

### 9.1. P0, bắt buộc

1. Ingest PDF qua Parser Router (Docling chính, MinerU phụ/fallback).
2. Canonical Document IR và Legal Structure Extractor (Chương/Mục/Điều/Khoản/Điểm, nhãn Điểm tiếng Việt a) b) c) d) đ) e), short-Point retention).
3. Legal Context Enricher (parent-context enrichment vào `retrieval_text`).
4. Legal Reference Resolver và Temporal/Amendment Resolver (quan hệ provision + quan hệ văn bản).
5. Provenance đến page và bounding box; `source_element_ids` truy vết về Document IR.
## 9. Phạm vi chức năng

### 9.1. MVP bắt buộc

1. Ingest đúng 14 PDF từ allowlist chính xác `datafiles.chinhphu.vn`, khử trùng lặp theo document identity/file hash và lưu snapshot/hash bất biến.
2. Sync thủ công qua CLI; không upload endpoint, background worker, admin/reviewer role, approval UI hoặc approval API.
3. Parser Router, Canonical Document IR, Legal Structure Extractor và provenance tới page/bounding box.
4. Legal Reference Resolver và Temporal/Amendment Resolver.
5. Quality, provenance và temporal gates tự động; fail closed khi thiếu bằng chứng hoặc provenance.
6. PostgreSQL là nguồn chân lý; Qdrant là index dẫn xuất. Index cũ được giữ tới khi rebuild mới vượt qua gates.
7. Embedding local được benchmark nhỏ trên các ứng viên đã cài/cache; chỉ rebuild sau khi chọn ứng viên. Không chốt model hoặc ngưỡng số trong tài liệu khi chưa có bằng chứng.
8. Query-time chỉ exact/dense/sparse retrieval trên corpus đã phục vụ; không tìm web, không dùng tài liệu ngoài corpus.
9. Evidence planning, Evidence Completeness Gate, structured claims, sáu tầng verification và bounded repair/abstention.
10. Hỏi hiện hành, lịch sử, so sánh; query chỉ có năm dùng ngày chuẩn `01/07` nếu không có biến cố hiệu lực trong năm, nếu có thì yêu cầu ngày cụ thể hoặc abstain `MISSING_QUERY_DATE`.
11. Phân loại riêng `CORPUS_NOT_COVERED` cho câu hỏi thuộc miền giao thông nhưng không có căn cứ trong 14 PDF; không gộp với lỗi hệ thống hoặc `OUT_OF_SCOPE`.
12. Vehicle taxonomy mở rộng; khi câu hỏi không chỉ rõ loại xe, chỉ trả các nhóm phương tiện có bằng chứng trực tiếp, không suy diễn nhóm còn lại.
13. Chat UI tối thiểu để hỏi, xem câu trả lời đã verify, citation/passage, ngày áp dụng, disclaimer và LIKE/DISLIKE.
14. Gold gate chạy toàn bộ 200 câu risk-weighted thuộc 17 category trước release; feedback không phải release gate.

### 9.2. Ngoài phạm vi khóa luận

- open web search hoặc crawl ngoài allowlist để sinh câu trả lời pháp lý;
- upload qua API/UI, background ingestion, admin/reviewer role, human approval hoặc review queue;
- comment/category/triage feedback, lưu raw prompt/answer trong feedback hoặc dùng feedback làm release gate;
- corpus ngoài đúng 14 PDF MVP, toàn bộ pháp luật Việt Nam, mobile, voice, multi-agent, Neo4j, fine-tuning, local LLM, microservices, Kubernetes;
- câu trả lời tư vấn pháp lý cá nhân hóa có tính kết luận.
- Có văn bản hiện hành và văn bản lịch sử.
- Tập trung vào giao thông đường bộ.

### 10.2. Nguyên tắc nguồn

Chỉ dùng nguồn chính thống hoặc bản sao được đối chiếu với nguồn chính thống.

Mỗi tài liệu phải có manifest:

```text
document_id
source_url
downloaded_at
file_hash
document_number
document_type
issuer
issued_date
effective_from
effective_to
status
relation_notes
review_status
reviewed_by
reviewed_at
```

Không index tự động tài liệu chưa qua validation hoặc review bắt buộc.

## 10. Corpus

### 10.1. Quy mô và ranh giới MVP

- Corpus MVP gồm đúng **14 PDF**, khử trùng lặp theo document identity và file hash.
- Nguồn được phép duy nhất là allowlist chính xác `datafiles.chinhphu.vn`; không có open web hoặc nguồn ngoài allowlist ở query-time.
- Manifest của từng snapshot ghi `document_id`, `source_url`, `downloaded_at`, `file_hash`, định danh văn bản, ngày ban hành/hiệu lực và quan hệ temporal khi có.
- Snapshot và hash là bất biến. Tài liệu mới chỉ được publish khi tự động đạt quality, provenance và temporal gates; gate fail thì không thay thế snapshot/index hiện hành.
- Query thuộc giao thông nhưng không được 14 PDF hỗ trợ trả `CORPUS_NOT_COVERED`; không suy diễn hoặc dùng web fallback.

### 10.2. Corpus QA

Corpus QA kiểm tra hierarchy, short-Point, nhãn đ), parent context, provenance, bảng, cross-reference, duplicate, effective date và temporal conflict. Các gate là tự động; không có human approval.
|---|---|
| P1 | Docling |
| P2 | MinerU |
| P3 | Parser Router |

Chỉ số: Article P/R/F1, Clause P/R/F1, Point P/R/F1, Short Point Recall, Vietnamese đ) Recall, Parent Context Completeness, Table Preservation, Header/Footer Leakage, Provenance Coverage.

**Suite B - Embedding benchmark:**

| Thí nghiệm | Model |
|---|---|
| E1 | Gemini Embedding 2 (768 dims) |
| E2 | Jina Embeddings v5 text-nano |
| E3 | Jina Embeddings v5 text-small |

Chỉ số: Recall@10, MRR@10, nDCG@10 trên câu hỏi pháp luật tiếng Việt, latency, cost.

**Suite C - Retrieval ablation:**

| Thí nghiệm | Cấu hình |
|---|---|
| R1 | legal chunk + dense |
| R2 | R1 + sparse/RRF |
| R3 | R2 + query normalization |
| R4 | R3 + multi-query rewrite |
| R5 | R4 + conditional HyDE |
| R6 | R5 + reranker |
| R7 | R6 + parent/sibling expansion |
| R8 | R7 + cross-reference expansion |
| R9 | R8 + temporal filtering |
### 11.1. Gold set và release gate

Toàn bộ **200 câu gold đã review**, chia 40 development / 40 validation / 120 final test, phải chạy trước release. Bộ câu hỏi gồm đúng 17 category: CURRENT, HISTORICAL, COMPARISON, EXACT_REFERENCE, PENALTY, LICENSE_POINTS, CONDITION, EXCEPTION, PROCEDURE, CROSS_REFERENCE, MULTI_PROVISION, MULTI_DOCUMENT, COLLOQUIAL_QUERY, AMBIGUOUS, MISSING_INFORMATION, OUT_OF_SCOPE và ADVERSARIAL_CITATION. Phân bổ là risk-weighted; không dùng feedback để thay đổi gate.

Mỗi câu ghi expected/acceptable provisions, required evidence, must-include/must-not-include facts, temporal metadata, category và hash. Các metric/ngưỡng release chỉ được ghi khi đã có kết quả chạy thực tế.
| G2 | Structured output |
| G3 | G2 + citation ID verifier |
| G4 | G3 + temporal verifier |
| G5 | G4 + numeric grounding |
| G6 | G5 + claim support |
| G7 | G6 + evidence completeness |

### 11.3. Headline metrics

**Retrieval:** Recall@5, Recall@10, Recall@20, MRR@10, nDCG@10.

**Evidence:** Evidence Set Recall, All Required Evidence@10, Cross-reference Resolution Recall, Multi-hop Evidence Completeness.

**Temporal:** Temporal Validity Accuracy, Temporal Leakage Rate, Current/Historical Separation Accuracy, Comparison Separation Accuracy.

**Citation:** Citation Precision, Citation Recall, Citation F1, Invalid Citation Rate.

**Grounding:** Numeric Grounding Accuracy, Unsupported Claim Rate, Claim Support Precision, Answer Evidence Completeness.

**Corpus:** Hierarchy F1, Point Coverage, Short Point Recall, Provenance Coverage, Parent Context Coverage.

**Abstention:** Precision, Recall, F1.

**Performance:** P50 latency, P95 latency, token usage, cost, parser time, indexing time.

### 11.4. Phương pháp luận evaluation

- Deterministic metrics là headline; LLM judge chỉ là nguồn thứ cấp (dùng Ragas v0.4.x cho Faithfulness, Response Relevancy, Factual Correctness khi cần).
- Final test set đóng băng, không dùng để tuning.
- Không ghi kết quả metric vào tài liệu trước khi chạy thực nghiệm.
- Mọi lần chạy phải ghi lại: raw outputs được giữ, run bất biến, corpus version/hash, gold-set version/hash, model IDs, prompt versions, config, Git commit; kết quả truy vết được theo từng query; các trường hợp fail vẫn nằm trong error analysis.
- Thí nghiệm được thiết kế có tham khảo các quan sát bên ngoài từ dự án Traffic-RAG (ranh giới chunk phải trùng ranh giới trích dẫn, Điểm ngắn không được lọc bỏ, đ) phải được nhận diện, retrieval cần ngữ cảnh câu mở đầu Khoản, mở rộng Khoản lân cận, giả mạo citation không lọc được bằng textual F1, label gold có thể sai cần review độc lập). Các quan sát này **chỉ là động lực thiết kế thí nghiệm, không phải kết quả của VNLRAG** và không bao giờ được báo cáo như kết quả VNLRAG.

---

## 12. Kế hoạch thời gian

| Giai đoạn | Thời gian | Deliverable |
|---|---|---|
| Chốt thiết kế và corpus | 20/07-26/07 | ADR, manifest, schema, thiết kế Parser Router và Canonical Document IR |
| Parser foundation | 27/07-02/08 | Suite A (P1-P3), chọn hướng parser, Canonical Document IR hoàn chỉnh |
| Legal extraction và data platform | 03/08-09/08 | Legal Structure Extractor, corpus QA, PostgreSQL, Qdrant, MinIO, ingestion queue |
| Relation graph và temporal | 10/08-16/08 | Legal Reference Resolver, Temporal/Amendment Resolver, bảng quan hệ, parent-context enrichment |
| Retrieval và query workflow | 17/08-23/08 | Suite B và C (R1-R10), query expansion, reranker, evidence gate, LangGraph, Langfuse |
| UI và review flow | 24/08-30/08 | Frontend, citation panel, feedback, review tooling |
| Evaluation và stabilization | 31/08-06/09 | Gold set 200 câu, Suite D (G1-G7), RAGFlow baseline, performance |
| Finalization | 07/09-12/09 | Code freeze, report, demo |
| Rehearsal | 13/09 | Offline demo rehearsal |
| Defense | 14/09 | Bảo vệ |

Mốc kiểm soát:

- **Feature freeze**: 06/09/2026.
- **Code freeze**: 10/09/2026.
- **Release candidate**: 12/09/2026.
- Không thêm feature mới trong hai ngày cuối.

Thiết kế không bị thu hẹp vì lịch trình; mọi hạng mục P0 phải hoàn thành trước feature freeze.

---

## 13. Thứ tự cập nhật tài liệu

1. `00-scope-and-decisions.md`
2. `01-phan-tich-kha-thi.md`
3. `02-yeu-cau-he-thong.md`
4. `03-thiet-ke-he-thong.md`
5. `04-tech-stack-llm-research.md`
6. `05-ke-hoach-trien-khai.md`
7. `06-test-evaluation.md`
8. `07-deployment.md`
9. `08-bao-tri.md`
10. `01-mo-ta-he-thong.tex`
11. `MoTa.odt`
12. `09-giai-thich-he-thong.tex`
13. `references.bib`
14. PDF build artifacts

Các file PDF được sinh từ LaTeX hoặc nguồn tài liệu tương ứng, không chỉnh sửa trực tiếp.

---

## 14. Các phương án đã loại bỏ

1. **UDEF-based pipeline** - thay bằng Parser Router + Canonical Document IR + Legal Structure Extractor do dự án sở hữu.
2. **ChromaDB** - thay bằng Qdrant (dense + sparse + filter + RRF trong một hệ thống).
3. **SQLite làm database chính** - thay bằng PostgreSQL (source of truth, JSONB, migration, nhiều writer).
4. **Kiến trúc rank-bm25 pickle riêng** - thay bằng Qdrant sparse BM25, loại bỏ file pickle thủ công.
5. **DuckDuckGo/SerpAPI fallback khi thiếu dữ kiện** - loại bỏ; hệ thống ABSTAIN thay vì tìm trên web.
6. **Query-time web HITL** - loại bỏ; HITL chỉ còn ở khâu review ingestion.
7. **Autonomous multi-agent** - bác bỏ; LangGraph là controlled workflow với nhánh xác định trước.
8. **Neo4j cho đồ thị quan hệ** - bác bỏ; dùng bảng quan hệ trong PostgreSQL và application logic.
9. **RAGFlow làm nền tảng chính** - bác bỏ; chỉ là baseline so sánh bên ngoài, chạy trong môi trường benchmark riêng.
10. **Open-web search cho câu trả lời pháp lý** - bác bỏ; câu trả lời chỉ dựa trên corpus đã kiểm chứng.

---

## 15. Tóm tắt ADR

Các quyết định kiến trúc này sẽ được chi tiết hóa trong `03-thiet-ke-he-thong.md`:

- ADR loại bỏ UDEF và thay thế bằng Parser Router;
- ADR Parser Router (Docling chính, MinerU phụ/fallback);
- ADR Canonical Document IR parser-neutral;
- ADR đồ thị quan hệ bằng bảng PostgreSQL, không dùng Neo4j;
- ADR Qdrant là index dẫn xuất, PostgreSQL là nguồn chân lý;
- ADR Evidence Completeness Gate và evidence planning;
- ADR Langfuse nằm ngoài đường tới hạn tính đúng đắn;
- ADR RAGFlow chỉ là baseline bên ngoài;
- ADR background ingestion (Redis + Dramatiq) và MinIO object storage.

---

## 16. Quy tắc quản lý thay đổi

Một quyết định trong tài liệu này chỉ được thay đổi khi:

1. Có bằng chứng kỹ thuật hoặc thực nghiệm rõ ràng.
2. Thay đổi không phá vỡ deadline.
3. Tài liệu liên quan được cập nhật đồng bộ.
4. Thay đổi được ghi trong ADR hoặc change log.
5. Nếu thay đổi ảnh hưởng experiment matrix, gold set phải được giữ nguyên hoặc tạo version mới, không chỉnh sửa âm thầm.

Các quyết định sau được xem là khóa cứng:

- không có web fallback để sinh câu trả lời pháp lý;
- không gọi hệ thống là autonomous agent;
- UDEF đã bị loại bỏ, không đưa trở lại;
- Parser Router + Canonical Document IR + Legal Structure Extractor thay cho UDEF;
- Qdrant thay cho ChromaDB và BM25 index riêng; Qdrant là index dẫn xuất dựng lại được từ PostgreSQL;
- PostgreSQL quản lý metadata, quan hệ và version (nguồn chân lý);
- citation được dựng từ provision metadata, không do LLM tự gõ;
- không trả câu trả lời có citation chưa verified (Returned Invalid Citation Rate = 0);
- Evidence Completeness Gate bắt buộc trước khi sinh câu trả lời;
- RAGFlow chỉ là baseline bên ngoài;
- kết quả thực nghiệm chỉ được ghi sau khi chạy evaluation.
