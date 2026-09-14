# 09. Giải thích hệ thống

> **Trạng thái release:** **RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME**
> (audit 14/09/2026). Sáu case thiếu corpus được ghi rõ và không tính vào
> denominator; semantic correctness toàn bộ vẫn chưa được human review.
*A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations*

**Sinh viên thực hiện:** Quách Trương Phúc  
**Mã số sinh viên:** [Mã số sinh viên]  
**Người hướng dẫn:** [Tên giảng viên hướng dẫn]  
**Cần Thơ, tháng 9 năm 2026**

## 0. Tóm tắt và phạm vi tài liệu

### Tóm tắt

Khóa luận trình bày một hệ thống Retrieval-Augmented Generation (RAG) hỗ trợ tra cứu pháp luật giao thông Việt Nam. Trọng tâm nghiên cứu là bảo toàn cấu trúc Điều–Khoản–Điểm, lọc theo thời gian hiệu lực, kết hợp truy xuất ngữ nghĩa và từ khóa, và cung cấp citation được dựng từ metadata thay vì để mô hình tự tạo định danh. Tài liệu này phân biệt rõ **kiến trúc mục tiêu** với **runtime đã kiểm chứng**; các thành phần chưa có code hoặc bằng chứng vận hành không được trình bày như đã hoàn thành.

Runtime hiện tại gồm FastAPI/Python, Supabase Auth và Supabase REST cho dữ liệu phiên trò chuyện theo người dùng, Qdrant cho hybrid dense/sparse retrieval, FastEmbed BM25, embeddings qua cấu hình OpenAI-compatible/OpenRouter, bộ nạp Markdown/JSONL, và frontend Next.js/React. Hệ thống có temporal filtering, exact metadata filtering, bounded sibling/cross-reference expansion, deterministic evidence checks và sinh câu trả lời Markdown. Audit hiện tại chưa chứng minh LangGraph, PostgreSQL làm nguồn chân lý pháp lý, Redis/Dramatiq, MinIO, Langfuse, production reranker hay verifier sáu tầng độc lập.
**Từ khóa:** RAG, pháp luật giao thông Việt Nam, temporal retrieval, Qdrant, citation verification. Release report hiện tại là [release-candidate-20260914.md](evaluation/release-candidate-20260914.md).


### Abstract

This thesis explains a Retrieval-Augmented Generation system for Vietnamese traffic-law lookup. It distinguishes the proposed target architecture from the currently audited runtime. The runtime uses FastAPI/Python, Supabase authentication and REST persistence, Qdrant hybrid retrieval, FastEmbed BM25, OpenAI-compatible/OpenRouter embeddings, Markdown/JSONL ingestion, and a Next.js/React client. It supports metadata-based exact filtering, effective-date filtering, bounded context expansion, deterministic evidence checks, and metadata-derived citations. The audit does not establish active LangGraph, PostgreSQL legal source of truth, Redis/Dramatiq, MinIO, Langfuse, a production reranker, or a complete six-layer verifier. The available diagnostic evaluation covers only 32 of 40 cases through the API, with three errors; it is not a final release evaluation.

**Keywords:** RAG, Vietnamese traffic law, temporal retrieval, Qdrant, verifiable citations.

### Danh mục ký hiệu và từ viết tắt

| Ký hiệu | Diễn giải |
|---|---|
| API | Application Programming Interface |
| BM25 | Best Matching 25 |
| LLM | Large Language Model |
| RAG | Retrieval-Augmented Generation |
| RRF | Reciprocal Rank Fusion |

## 1. Phạm vi và trạng thái

### Phạm vi nghiên cứu

Tên đề tài là “Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng”. Bài toán xuất phát từ việc một câu trả lời pháp luật phải đồng thời xác định đúng văn bản, Điều, Khoản, Điểm, phiên bản có hiệu lực và các quy định liên quan. Vector similarity đơn thuần không bảo đảm các điều kiện này.

Phạm vi frozen yêu cầu corpus release 14 PDF sau deduplicate theo document identity/file hash từ allowlist `datafiles.chinhphu.vn`; không open-web fallback ở query time; ingestion fail closed; citation phải dựa trên identity tin cậy; và thiếu bằng chứng phải dẫn đến verified-or-abstain. Đây là yêu cầu mục tiêu, không phải tuyên bố rằng runtime hiện tại đã đáp ứng đầy đủ.

### Trạng thái kiểm chứng

Release hiện tại được quyết định theo [release-candidate-20260914.md](evaluation/release-candidate-20260914.md): covered corpus/MVP runtime đạt release-ready; sáu case thiếu corpus được phân loại riêng và không tính denominator. Candidate/gold mở rộng vẫn là artifact nghiên cứu, không phải runtime claim.

## 2. Bài toán và yêu cầu

### Các thách thức

1. Bảo toàn hierarchy Chương, Mục, Điều, Khoản, Điểm, kể cả nhãn tiếng Việt `đ)`.
2. Chọn đúng khoảng hiệu lực cho current, historical và comparison query.
3. Giữ exact lookup cho số hiệu, Điều, Khoản và cụm từ pháp lý quyết định.
4. Mở rộng tham chiếu chéo có giới hạn, không làm loãng evidence.
5. Không trả lời một phần khi câu hỏi đòi hỏi nhiều loại bằng chứng.
6. Không cho LLM tự bịa citation hoặc số liệu không có grounding.

Câu hỏi trung tâm là: làm thế nào để truy xuất đúng đơn vị pháp lý, áp dụng đúng phiên bản tại thời điểm được hỏi, mở rộng đúng quy định liên quan và chỉ trả về kết luận có citation kiểm chứng được?

### Yêu cầu bất biến

Hệ thống mục tiêu không tìm kiếm web tự do để hoàn thiện câu trả lời, không sử dụng autonomous multi-agent, không coi Qdrant là nguồn chân lý pháp lý, và không ghi metric chưa chạy thành kết quả đạt. Boundary triển khai MVP là localhost/private network; runtime vẫn có authentication và dữ liệu chat theo user.

## 3. Kiến trúc mục tiêu

### Ingestion mục tiêu

```text
Allowlist PDFs -> deduplicate/hash -> parser router (Docling|MinerU)
 -> Canonical Document IR -> legal structure/reference/temporal enrichment
 -> quality/provenance gates -> accepted source of truth -> Qdrant derived index
```

Mục tiêu này cho phép thay parser mà không thay đổi tầng phân tích pháp lý, truy vết file hash và provenance, và chỉ publish snapshot sau khi quality gate đạt. Parser Router, Docling/MinerU, Canonical IR, PostgreSQL legal source of truth và immutable accepted-publish pipeline hiện chưa có bằng chứng runtime tương ứng.

### Query mục tiêu

```text
Question -> intent/date/reference analysis -> temporal resolution
 -> exact+dense+sparse retrieval -> fusion/reranking
 -> bounded legal expansion -> evidence completeness
 -> structured generation -> citation/claim verification
 -> verified answer or abstention
```

Đây là thiết kế đích. LangGraph, production reranker, structured claim contract và failure-aware repair graph không được mô tả như thành phần đã triển khai.

## 4. Runtime đã kiểm chứng

### API, authentication và persistence

`backend/app/main.py` đăng ký các router RAG, auth, chats và legal. `backend/app/auth/` xác thực bearer token qua Supabase Auth. `backend/app/chats/` dùng Supabase REST để lưu session, user/assistant messages, feedback và bookmark; token người dùng được truyền trong các request persistence.

`backend/app/rag/api.py` thực hiện luồng: xác thực bearer, load/create session thuộc user, load follow-up history, persist user message, gọi `RAGService.answer`, persist assistant response/citations và trả conversation/message IDs. Frontend Next.js/React có chat, conversation, legal sources, saved items và citation viewer.

### Retrieval và evidence

`backend/app/rag/retrieval.py` cấu hình Qdrant local hoặc remote, dense embeddings OpenAI-compatible/OpenRouter, FastEmbed sparse BM25, hybrid retrieval, exact metadata filtering theo reference, temporal filtering theo `effective_from/effective_to`, sibling completion và cross-reference expansion có giới hạn.

`backend/app/rag/service.py` phân tích câu hỏi, fan-out intent/vehicle có giới hạn, retrieve, hợp nhất điểm kiểu RRF, giới hạn diversity, lọc structural/temporal/content, assess evidence, generate answer và lắp citation từ metadata. `backend/app/rag/evidence.py` có kiểm tra deterministic cho identity, reference, content, intent, score và effective interval. Citation hiện dựa trên `chunk_id`, `document_id`, article/clause/point và source metadata; audit chưa chứng minh stable `provision_id` cùng review status ACCEPTED cho toàn bộ corpus.

### Ingestion và dữ liệu

`backend/app/ingestion/markdown.py` parse front matter, nhận diện Điều/Khoản/Điểm bằng regex, giữ nhãn `a-z/đ`, tạo metadata, `chunk_id` và `content_sha256`. Loader đọc `data/sources/manifest.json` rồi các Markdown dưới `data/corpus/mds`. Manifest hiện có 17 entries, gồm tài liệu hiện hành và lịch sử; điều này không chứng minh yêu cầu release 14 PDF.

### Topology và dependency

Backend hiện khai báo FastAPI, Pydantic, Qdrant/LangChain integration, FastEmbed, Supabase và ONNX Runtime; frontend dùng Next.js 16, React 19 và Supabase client/SSR. Audit không thấy active path cho LangGraph, PostgreSQL/SQLAlchemy/Alembic legal DB, Redis/Dramatiq, MinIO, Langfuse hoặc Docling/MinerU.

## 5. Ma trận khoảng cách

| Năng lực | Target | Runtime đã audit |
|---|---|---|
| Corpus/source | 14 PDF, snapshot bất biến, source of truth | Markdown/JSONL; manifest 17 entries; chưa chứng minh 14 PDF |
| Parser/IR | Parser Router, Docling/MinerU, Canonical IR | Markdown loader regex |
| Legal relations | provision/reference/amendment DB | bounded cross-reference từ metadata; chưa có legal relation DB |
| Retrieval | exact+dense+sparse, fusion, reranking | Qdrant hybrid, exact filter, BM25, fusion; chưa có production reranker |
| Workflow | controlled graph, repair, six-layer verifier | Python synchronous flow, deterministic evidence checks |
| Persistence | PostgreSQL legal DB, worker, object store | Supabase REST/Auth; không có Redis/Dramatiq/MinIO |
| Observability | Langfuse ngoài critical path | chưa có bằng chứng active Langfuse |

Khoảng cách này là kết quả audit, không phải danh sách tính năng được ngầm xem là hoàn thành. Các mục target chỉ trở thành implemented khi có code, deployment và bằng chứng tương ứng.

## 6. Đánh giá và bằng chứng

### Artifact hiện tại

Artifact release candidate là
[`release-candidate-20260914.md`](evaluation/release-candidate-20260914.md).
Nó ghi nhận 40 rows, 34 covered rows, sáu `CORPUS_NOT_COVERED`, zero
covered-case errors, citation validity 1.0, invalid citation rate 0% và
abstention accuracy 0.9118. Semantic correctness toàn bộ là N/A.

### Cách đánh giá

Gold set giữ nguyên; case thiếu corpus không tính denominator. Runner tách
retrieval, legal coordinates, citation validity, abstention và latency khỏi
human semantic review. Không dùng feedback hoặc dữ liệu ngoài corpus để làm
đẹp release result.

## 7. Triển khai

### Runtime release hiện tại

`deploy/compose/compose.release.yml` chỉ mô tả ba service qdrant/backend/frontend; Supabase và OpenRouter là dịch vụ bên ngoài. Vì vậy topology này không phải compose bảy service của thiết kế lịch sử. Cấu hình bí mật phải đi qua environment/secret management; không đưa credential vào repo.

MVP được giới hạn localhost/private network và cần xác minh health, authentication, session isolation, persistence assistant response, citation viewer và failure behavior trước khi sử dụng. Khởi động backend/frontend chỉ chứng minh khả năng chạy process, không tự chứng minh correctness pháp lý.

### Luồng demo có thể kiểm tra

Có thể kiểm tra câu hỏi hiện hành, historical, comparison, câu ngoài corpus và câu đa bằng chứng qua API/UI khi môi trường ngoài đã cấu hình. Mỗi demo phải ghi rõ input, thời điểm hỏi, evidence trả về, citation và tình trạng abstain. Không dùng demo thành công đơn lẻ để thay thế full evaluation.

## 8. Hạn chế

Corpus runtime là covered serving corpus và không đại diện toàn bộ pháp luật.
Missing-corpus cases được fail closed. Generator, temporal metadata và bounded
expansion vẫn phụ thuộc chất lượng manifest/payload; semantic review chuyên gia,
load test và public hardening nằm ngoài MVP release claim.

## 9. Kết luận và hướng phát triển

### Kết luận

Runtime cung cấp authentication theo user, lưu chat qua Supabase, hybrid
retrieval trên Qdrant, temporal/exact filtering, bounded expansion,
deterministic evidence checks và citation từ metadata. Release candidate đạt
release-ready cho covered corpus/MVP runtime; evidence chi tiết nằm trong
`docs/evaluation/release-candidate-20260914.md`.

### Hướng phát triển có điều kiện

Ưu tiên tiếp theo là hoàn tất corpus contract và provenance, chuẩn hóa provision identity, tăng độ tin cậy retrieval/citation/abstention, chạy full frozen evaluation, review semantic bởi người có chuyên môn và xác minh E2E/UI. Chỉ sau khi các bằng chứng đó đạt yêu cầu mới nên cân nhắc các thành phần target như canonical IR, legal relation source of truth, reranking hoặc workflow repair. Mọi thành phần mới phải đi kèm code, deployment và artifact đo lường; không cập nhật trạng thái dựa trên thiết kế mục tiêu.

## 10. Tài liệu tham chiếu

Các quyết định phạm vi và trạng thái được ghi tại `docs/00-scope-and-decisions.md`. Runtime được đối chiếu từ `backend/app/main.py`, `backend/app/rag/api.py`, `backend/app/rag/retrieval.py`, `backend/app/rag/service.py`, `backend/app/rag/evidence.py`, `backend/app/ingestion/markdown.py`, `data/sources/manifest.json`, `deploy/compose/compose.release.yml` và artifact đánh giá nêu trong Chương 6.
