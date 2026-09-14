# 00. Scope and decisions

> **Bản audit:** 14/09/2026
> **Trạng thái release:** **RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME**
> **Vai trò:** Nguồn quyết định phạm vi và nguyên tắc kiến trúc cao nhất của VN Traffic Law RAG.
>
> Kết quả này không khẳng định bao phủ toàn bộ pháp luật giao thông hoặc semantic
> correctness đã được human review toàn bộ. Sáu case thiếu corpus được loại khỏi
> denominator và giữ lại như `CORPUS_NOT_COVERED`.
>
> Tài liệu này phân biệt rõ **quyết định/frozen scope**, **kiến trúc mục tiêu**, và **runtime đã kiểm chứng**. Không coi thiết kế mục tiêu là tính năng đã triển khai. Mọi nhận định runtime bên dưới dựa trên code hiện tại và artifact evaluation được dẫn nguồn.

---

## 1. Tên đề tài

### Tiếng Việt

**Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng**

### Tiếng Anh

**A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations**

Không dùng thuật ngữ **Agentic**. Nếu triển khai workflow có điều phối, đó là controlled workflow với các nhánh xác định trước, không phải autonomous multi-agent.

---

## 2. Metadata và trạng thái

| Thuộc tính | Giá trị |
|---|---|
| Ngày tạo | 16/06/2026 |
| Baseline v1 | 19/07/2026 |
| Thiết kế lại v2 | 08/08/2026 |
| Audit runtime gần nhất | 14/09/2026 |
| Hạn release candidate theo kế hoạch cũ | 16/09/2026 |
| Ngày báo cáo/bảo vệ theo kế hoạch cũ | 16/09/2026 |
| Trạng thái | RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME |

### Bằng chứng release hiện có

Release candidate ngày 14/09/2026 chạy qua API authenticated với `top_k=5`,
được rescored bằng evaluator có phân loại corpus gap:

| Metric | Covered result |
|---|---:|
| Total / covered rows | 40 / 34 |
| Corpus-not-covered | `00`, `15`--`19` |
| Covered-case request errors | 0 |
| Citation validity / invalid citation rate | 1.0 / 0% |
| Abstention accuracy | 0.9118 |
| Retrieval hit@5 | 0.3333 |
| Document / article accuracy | 0.5833 / 0.5833 |
| Clause / point accuracy | 0.5385 / 0.25 |
| Latency mean / P95 | 13.13 s / 24.11 s |

Backend gates passed: Ruff, format, mypy and 161 tests. Frontend lint had zero
errors, typecheck, production build and format check passed; two existing React
Hook warnings remain. Committed evidence: [release-candidate-20260914.md](evaluation/release-candidate-20260914.md).

`answer_correctness_manual` is N/A because full human semantic review was not
supplied. Release status therefore applies only to covered corpus and current
MVP runtime, not to complete legal coverage or semantic certification.

---

## 3. Bài toán nghiên cứu

Hệ thống mục tiêu hỗ trợ tra cứu pháp luật giao thông Việt Nam trên corpus đã kiểm chứng, với bảy thách thức:

1. **Cấu trúc pháp lý**: bảo toàn Chương, Mục, Điều, Khoản, Điểm; nhận diện nhãn Điểm tiếng Việt, bao gồm `đ)`; ranh giới provision phải phù hợp ranh giới citation.
2. **Hiệu lực thời gian**: áp dụng đúng phiên bản tại ngày được hỏi; hỗ trợ sửa đổi, thay thế, bãi bỏ và hiệu lực từng phần.
3. **Quan hệ pháp lý**: xử lý tham chiếu chéo giữa provision/văn bản và liên kết quy định xử phạt với điểm giấy phép hoặc biện pháp khắc phục.
4. **Citation hallucination**: không tạo citation không tồn tại hoặc ghép nội dung đúng với định danh sai.
5. **Exact lookup**: không bỏ sót số hiệu văn bản, Điều, Khoản, Điểm hoặc cụm từ pháp lý quyết định.
6. **Câu hỏi đa bằng chứng**: không trả lời một phần khi còn thiếu loại bằng chứng bắt buộc.
7. **Evidence completeness**: mở rộng bằng chứng có giới hạn, có lý do, và kiểm tra đủ trước khi sinh câu trả lời.

Câu hỏi nghiên cứu trung tâm:

> Làm thế nào để RAG truy xuất đúng đơn vị pháp lý, áp dụng đúng phiên bản tại thời điểm được hỏi, mở rộng đúng quy định liên quan, và chỉ trả về kết luận có citation kiểm chứng được?

---

## 4. Frozen scope và nguyên tắc bất biến

Các quyết định sau là phạm vi khóa cứng, không được nới hoặc hạ chuẩn để đáp ứng lịch trình:

1. Corpus release gồm đúng **14 PDF sau deduplicate theo document identity/file hash**, từ allowlist chính xác `datafiles.chinhphu.vn`.
2. Query-time chỉ sử dụng corpus/index đã phục vụ; **không open-web search, crawl ngoài allowlist hoặc web fallback** để sinh câu trả lời pháp lý.
3. Ingestion không có upload endpoint, admin/reviewer role, approval UI/API hoặc human approval trong MVP.
4. Ingestion/rebuild phải fail closed; index đang phục vụ không bị thay thế bởi snapshot/index lỗi.
5. UDEF và mọi tầng phụ thuộc UDEF không quay lại pipeline.
6. Citation được dựng từ metadata/provision identity tin cậy, không để LLM tự gõ định danh tự do.
7. Evidence Completeness Gate chạy trước generator.
8. Verified-or-abstain: không trả claim/citation chưa kiểm chứng; bất biến mục tiêu là `Returned Invalid Citation Rate = 0`.
9. Workflow không phải autonomous multi-agent.
10. PostgreSQL/Qdrant, model, parser hoặc dịch vụ khác chỉ được gọi là quyết định production khi có implementation và bằng chứng tương ứng.
11. Không ghi metric chưa chạy thành kết quả đạt.
12. Gold set final đóng băng; không dùng feedback hoặc final test để tuning.

### Phân biệt single-user và authentication

MVP chỉ giới hạn deployment ở localhost/private network và không có role quản trị/reviewer. Runtime hiện tại **có Supabase Auth, user identity và persistence theo user**; vì vậy “single-user” mô tả boundary triển khai, không có nghĩa API bỏ authentication.

---

## 5. Kiến trúc mục tiêu

Kiến trúc mục tiêu vẫn giữ các năng lực nghiên cứu sau:

- Parser Router với Docling/MinerU;
- Canonical Document IR parser-neutral;
- Legal Structure Extractor;
- parent-context enrichment;
- provision/document relation model;
- temporal/amendment resolver;
- exact + dense + sparse retrieval, fusion, reranking và bounded expansion;
- evidence plan và completeness gate;
- structured claims;
- deterministic verification;
- bounded failure-aware repair và abstention;
- reproducible evaluation.

Đây là target architecture, không phải bằng chứng runtime đã hoàn tất.

### 5.1. Offline ingestion mục tiêu

```text
Allowlist datafiles.chinhphu.vn
        ↓
14 PDF → deduplicate → immutable snapshot manifest
        ↓
Manual CLI
        ↓
Parser Router (Docling | MinerU)
        ↓
Canonical Document IR
        ↓
Legal Structure Extractor
        ↓
Context / Reference / Temporal enrichment
        ↓
Automatic quality + provenance + temporal gates
        ↓
Accepted corpus source of truth
        ↓
Dense + sparse indexing
        ↓
Qdrant derived index
```

Snapshot, file hash, parser output và gate report phải truy vết được. Snapshot/index mới chỉ publish sau khi gate đạt; gate fail giữ nguyên index đang phục vụ.

### 5.2. Online query mục tiêu

```text
Question
  → query understanding / intent / references / date / evidence plan
  → temporal resolution
  → exact + dense + sparse retrieval
  → fusion / reranking
  → bounded legal-context expansion
  → evidence completeness
  → structured generation
  → citation / temporal / numeric / claim verification
  → verified answer hoặc abstention
```

Original query phải được giữ trong query expansion. Rewrite/HyDE nếu có phải có điều kiện và giới hạn. Mở rộng relation graph phải bounded, ghi `added_by`, `source_id`, `depth`.

### 5.3. Controlled workflow mục tiêu

```text
START → analyze → temporal → expand → retrieve → fuse → rerank
     → expand_context → check_evidence → generate → verify
     → finalize | bounded_repair | abstain → END
```

Repair phải phân biệt thiếu evidence, claim không được hỗ trợ, schema lỗi và temporal conflict. Hết số lần repair hữu hạn thì abstain; không có loop vô hạn.

---

## 6. Runtime hiện tại đã audit

### 6.1. API, auth và persistence

`backend/app/main.py` đăng ký các router RAG, auth, chats và legal. `backend/app/auth/` xác thực bearer token qua Supabase Auth. `backend/app/chats/` lưu session, user/assistant messages, feedback và bookmark qua Supabase REST; token người dùng được truyền cho các request persistence.

`backend/app/rag/api.py` thực hiện flow:

```text
bearer auth
  → load/create user-owned session
  → load follow-up history
  → persist user message
  → RAGService.answer
  → persist assistant response/citations
  → return conversation/message IDs
```

Frontend thực tế là Next.js/React với chat route, conversation route, legal sources, saved items, citation drawer/viewer và LIKE/DISLIKE UI. Đây là runtime capability, không phải phần “không auth” của legacy scope.

### 6.2. Retrieval và evidence hiện tại

`backend/app/rag/retrieval.py` hiện có:

- Qdrant client local hoặc remote theo config;
- dense `OpenAIEmbeddings` qua OpenAI-compatible/OpenRouter settings;
- FastEmbed sparse BM25;
- hybrid Qdrant retrieval;
- exact metadata filtering cho reference;
- temporal filtering theo `effective_from/effective_to`;
- bounded sibling completion và cross-reference expansion.

`backend/app/rag/service.py` thực hiện bằng Python đồng bộ:

```text
analyze_question
  → bounded intent/vehicle fan-out
  → Retriever.retrieve
  → RRF-like score merge + diversity cap
  → structural/temporal/content filtering
  → assess_evidence
  → generate_answer
  → metadata citation assembly
```

`backend/app/rag/evidence.py` có deterministic checks cho identity, reference, content, intent, score và effective interval. Tuy nhiên audit không tìm thấy implementation active của LangGraph, reranker production, sáu verifier độc lập đầy đủ hoặc failure-aware repair graph như target architecture.

Citation runtime hiện dựng từ `chunk_id`, `document_id`, article/clause/point và source metadata trong `RAGService._citation`; chưa có bằng chứng rằng toàn bộ citation đã chuyển sang stable `provision_id` và `review_status = ACCEPTED` theo mô hình mục tiêu.

### 6.3. Ingestion và corpus hiện tại

`backend/app/ingestion/markdown.py` hiện là Markdown/JSONL loader:

- parse front matter;
- nhận diện Điều/Khoản/Điểm bằng regex;
- giữ nhãn Điểm `a-z/đ` ở mức loader;
- tạo metadata, `chunk_id` và `content_sha256`;
- đọc `data/sources/manifest.json` rồi load các file Markdown dưới `data/corpus/mds`.

Manifest hiện chứa **17 entries**, gồm tài liệu hiện hành và lịch sử. Con số này không tự nó chứng minh corpus release “đúng 14 PDF”, vì active loader đang đọc Markdown và manifest thiếu bằng chứng runtime cho PDF source snapshot, Parser Router, Canonical Document IR, PostgreSQL legal source-of-truth hoặc immutable accepted-publish pipeline.

### 6.4. Dependencies và topology hiện tại

Backend `backend/pyproject.toml` hiện khai báo FastAPI, Pydantic, Qdrant/LangChain integration, FastEmbed, Supabase và ONNX Runtime. Frontend `frontend/package.json` hiện khai báo Next.js 16, React 19, Supabase client/SSR và React Markdown.

Audit không thấy các dependency/runtime path active sau trong backend hiện tại:

- LangGraph;
- PostgreSQL/SQLAlchemy/Alembic cho legal corpus;
- Redis/Dramatiq;
- MinIO;
- Langfuse;
- Docling/MinerU Parser Router.

Vì vậy các thành phần trên chỉ là kiến trúc mục tiêu hoặc quyết định thiết kế lịch sử cho tới khi code và deployment chứng minh ngược lại.

---

## 7. Phạm vi chức năng

### 7.1. P0 release contract

1. Corpus đúng 14 PDF allowlisted, deduplicate và snapshot/hash bất biến.
2. Ingestion manual CLI, fail closed, không upload/admin/reviewer approval.
3. Parser/IR/legal structure giữ đúng boundary provision và provenance.
4. Reference, temporal và amendment semantics có thể kiểm chứng.
5. Qdrant là derived retrieval index; nguồn corpus phải có authoritative boundary rõ ràng.
6. Exact/dense/sparse retrieval và bounded legal expansion.
7. Evidence plan, completeness gate, structured claims và verified-or-abstain.
8. Hỗ trợ current, historical và comparison query; thiếu ngày không được suy diễn nguy hiểm.
9. Phân biệt `CORPUS_NOT_COVERED`, `OUT_OF_SCOPE`, `INSUFFICIENT_EVIDENCE` và lỗi workflow.
10. Vehicle taxonomy không suy diễn nhóm phương tiện không có evidence trực tiếp.
11. UI hiển thị câu trả lời, citation/passage, ngày áp dụng, disclaimer và LIKE/DISLIKE.
12. Chạy release gate 40 case thuộc đúng 8 category trước khi xem xét release; gate không quy định một ngưỡng metric cố định và phải báo cáo rõ giới hạn coverage.

### 7.2. Ngoài phạm vi

- open-web search/crawl hoặc web fallback cho câu trả lời pháp lý;
- upload qua API/UI, admin/reviewer workflow, human approval hoặc review queue;
- feedback comment/category/triage, raw prompt/answer hoặc PII;
- dùng feedback để sửa corpus, gold set hoặc release gate;
- corpus ngoài 14 PDF frozen scope;
- mobile, voice, autonomous multi-agent, Neo4j, fine-tuning, local LLM, microservices, Kubernetes;
- kết luận tư vấn pháp lý cá nhân hóa.

---

## 8. Corpus và provenance contract

Nguồn hợp lệ duy nhất là allowlist `datafiles.chinhphu.vn` và bản sao được đối chiếu với nguồn chính thống. Mỗi snapshot/document manifest phải có tối thiểu:

```text
document_id
document_number
document_title/document_name
document_type
issuer
source_url
downloaded_at
file_hash
issued_date
effective_from
effective_to
status
relation_notes
review_status
reviewed_by
reviewed_at
```

Không index record thiếu identity, provenance hoặc temporal metadata bắt buộc. Citation phải truy nguyên về source element/page/bounding box khi nguồn parse hỗ trợ các trường này.

### Stable identity mục tiêu

Provision identity phải deterministic, tái tạo được và phân biệt `d)` với `đ)`; ví dụ:

```text
nd-168-2024__dieu-7__khoan-4__diem-b
```

Không coi ví dụ này là nội dung pháp lý thực tế. `source_text` giữ nguyên văn bản; `retrieval_text` có thể bổ sung parent context nhưng citation phải trỏ provision thực tế.

### Temporal contract mục tiêu

```text
effective_from <= d
AND (effective_to IS NULL OR d < effective_to)
AND review_status = ACCEPTED
```

Runtime hiện có interval filtering, nhưng chưa chứng minh đầy đủ versioned provision store và amendment resolver theo contract này.

---

## 9. Tech policy

| Khu vực | Chính sách |
|---|---|
| API | FastAPI + Pydantic v2 |
| Retrieval | Qdrant hybrid dense/sparse |
| Auth/persistence hiện tại | Supabase REST/Auth |
| Frontend hiện tại | Next.js + TypeScript + React |
| Embedding | Chỉ chốt sau benchmark và ghi version thực tế |
| Reranker | Không tuyên bố cải thiện trước benchmark |
| Workflow mục tiêu | Controlled workflow; không autonomous agent |
| Parser mục tiêu | Parser Router, Docling/MinerU nếu được triển khai và kiểm chứng |
| Evaluation | Deterministic metrics là headline; LLM judge thứ cấp |
| Deployment | Local/private network theo artifact deployment được kiểm chứng |

Không hardcode model ID trong domain logic. Model production phải có config/version và run manifest. Không gọi tên thư viện mục tiêu là runtime dependency khi dependency manifest không chứa nó.

---

## 10. Evaluation và release gate

### Gold set

Release gate dùng **40 case**, thuộc đúng 8 category:

`exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, `out_of_scope`.

Đây là bộ đánh giá giới hạn coverage, không phải bằng chứng bao phủ toàn bộ không gian câu hỏi pháp lý. Mỗi case cần expected/acceptable provisions, required evidence, must-include/must-not-include facts, temporal metadata, category và hash. Không áp đặt một ngưỡng metric cố định trong tài liệu này; quyết định release phải dựa trên artifact đầy đủ, semantic review, safety/citation checks và các gate vận hành liên quan.

### Suites

- **Suite A — parser**: P1 Docling, P2 MinerU, P3 Parser Router; hierarchy/provenance/table/short-Point/`đ)` metrics.
- **Suite B — embedding**: benchmark các ứng viên thực sự đã cài/cache; Recall@10, MRR@10, nDCG@10, latency, cost.
- **Suite C — retrieval ablation**: dense, sparse/RRF, normalization, rewrite, conditional HyDE, rerank, parent/sibling, cross-reference, temporal filtering.
- **Suite D — generation/verification**: structured output, citation, temporal, numeric, claim support và evidence completeness.

### Headline metrics

- Retrieval: Recall@5/10/20, MRR@10, nDCG@10.
- Evidence: Evidence Set Recall, All Required Evidence@10, cross-reference resolution, multi-hop completeness.
- Temporal: validity accuracy, leakage rate, current/historical/comparison separation.
- Citation: precision, recall, F1, invalid citation rate.
- Grounding: numeric accuracy, unsupported claim rate, claim support, evidence completeness.
- Corpus: hierarchy F1, Point coverage, short-Point recall, provenance/parent-context coverage.
- Abstention: precision, recall, F1.
- Performance: P50/P95 latency, token usage, cost, parser/indexing time.

### Release decision

Release candidate status applies to covered corpus and current MVP runtime.
Không release nếu thiếu artifact release candidate, phân loại corpus coverage,
safety/citation gate hoặc bằng chứng vận hành cần thiết. Bộ 40 case chỉ đại diện
coverage giới hạn; không được diễn giải là chứng minh toàn diện cho corpus,
retrieval, temporal/reference behavior hay public production readiness.
Mỗi evaluation run phải lưu corpus/index version/hash, gold-set version/hash, model ID/version, prompt/config, Git commit, raw outputs, error analysis và run manifest bất biến. Không ghi metric vào tài liệu trước khi thực nghiệm.

---

## 11. Các phương án đã loại bỏ

1. UDEF-based pipeline.
2. ChromaDB.
3. SQLite làm legal database chính.
4. Rank-BM25 pickle riêng.
5. DuckDuckGo/SerpAPI hoặc open-web fallback.
6. Query-time web HITL.
7. Autonomous multi-agent.
8. Neo4j cho relation graph.
9. RAGFlow làm production platform.
10. Corpus mở rộng ngoài frozen allowlist/scope.

Các lựa chọn trên có thể xuất hiện trong tài liệu lịch sử hoặc benchmark, nhưng không được mô tả là runtime release architecture.

---

## 12. Quy tắc quản lý thay đổi

Thay đổi scope/architecture contract chỉ hợp lệ khi:

1. Có bằng chứng kỹ thuật hoặc thực nghiệm rõ ràng.
2. Không âm thầm hạ release gate hoặc cắt frozen scope.
3. Tài liệu liên quan được cập nhật đồng bộ.
4. Thay đổi được ghi trong ADR/change log thích hợp.
5. Gold set và experiment matrix được giữ nguyên hoặc version hóa rõ ràng.
6. Runtime claims được kiểm tra lại từ code/deployment/evaluation artifact.

Các quyết định không được thay đổi âm thầm:

- không web fallback cho câu trả lời pháp lý;
- không autonomous agent;
- UDEF bị loại bỏ;
- citation không verified không được trả;
- Evidence Completeness Gate là điều kiện trước generation;
- feedback không phải release gate;
- kết quả chưa chạy không được báo cáo là đạt.

Tài liệu chi tiết phải tham chiếu và không được mâu thuẫn với `02-yeu-cau-he-thong.md`, `03-thiet-ke-he-thong.md`, `06-test-evaluation.md`, `07-deployment.md` và các ADR liên quan.
