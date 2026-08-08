# 01. Phân Tích Tính Khả Thi (Feasibility Analysis)

> **Giai đoạn SDLC**: 1 - Phân tích tính khả thi  
> **Ngày tạo**: 16/06/2026  
> **Ngày baseline v1**: 19/07/2026  
> **Ngày thiết kế lại v2**: 08/08/2026  
> **Hạn hoàn thành**: 12/09/2026  
> **Ngày bảo vệ**: 14/09/2026  
> **Tên đề tài**: Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng  
> **English title**: A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations  
> **Tài liệu quyết định nguồn**: [00-scope-and-decisions.md](00-scope-and-decisions.md)

---

## 1.1. Bối cảnh và vấn đề

### Vấn đề thực tế

Người dùng khi tra cứu pháp luật giao thông đường bộ Việt Nam thường gặp các khó khăn sau:

1. **Văn bản dài và phân tán**  
   Quy định liên quan đến một hành vi có thể nằm trong Luật, Nghị định, Thông tư và các văn bản sửa đổi hoặc thay thế. Người dùng phải đọc nhiều tài liệu và tự đối chiếu Điều, Khoản, Điểm.

2. **Cùng một câu hỏi có thể có đáp án khác nhau theo thời gian**  
   Mức phạt hoặc điều kiện áp dụng tại một thời điểm trong quá khứ có thể khác quy định hiện hành. Một hệ thống chỉ index phiên bản mới nhất không thể trả lời chính xác câu hỏi lịch sử.

3. **Mô hình ngôn ngữ có thể tạo thông tin không có căn cứ**  
   LLM có thể viết sai mức phạt, ghép nội dung từ nhiều văn bản hoặc tạo trích dẫn không tồn tại. Prompt yêu cầu "không bịa" không đủ để bảo đảm độ chính xác.

4. **Chunking thông thường làm mất cấu trúc pháp lý**  
   Cắt theo số token cố định có thể tách phần mở đầu của Khoản khỏi các Điểm bên dưới, tách căn cứ khỏi mức xử phạt hoặc làm mất quan hệ Chương, Mục, Điều, Khoản, Điểm.

5. **Dense retrieval không đủ cho mọi loại truy vấn pháp lý**  
   Vector embedding phù hợp với câu hỏi diễn đạt tự nhiên, nhưng có thể bỏ sót số hiệu văn bản, mã điều khoản, thuật ngữ chuyên biệt hoặc cụm từ cần khớp chính xác.

6. **Dữ liệu pháp luật cần được kiểm soát trước khi đưa vào hệ thống**  
   Một PDF parse thành công chưa đồng nghĩa với dữ liệu đủ tin cậy để index. Hệ thống cần kiểm tra metadata, hierarchy, provenance và quan hệ hiệu lực trước khi cho phép sử dụng trong câu trả lời.

7. **Quan hệ tham chiếu chéo giữa các quy định chưa được mô hình hóa**  
   Điều, Khoản, Điểm tham chiếu chéo lẫn nhau (`REFERS_TO`) và quy định xử phạt thường gắn kèm quy định trừ điểm hoặc tước giấy phép (`PENALTY_COMPANION`). Nếu không mô hình hóa các quan hệ này, hệ thống chỉ trả lời được nửa thông tin có trong một provision đơn lẻ.

8. **Câu hỏi đa bằng chứng cần kế hoạch bằng chứng tường minh**  
   Một câu hỏi có thể yêu cầu vừa mức phạt tiền vừa số điểm trừ giấy phép lái xe. Nếu không có evidence plan và kiểm tra tính đầy đủ, hệ thống có thể âm thầm trả lời một nửa dễ của câu hỏi.

9. **Chất lượng đầu ra parser không đồng đều, cần định tuyến và quality gate**  
   Docling và MinerU có thế mạnh khác nhau tùy loại tài liệu; đầu ra có thể sai layout hoặc OCR trên PDF pháp luật tiếng Việt. Hệ thống cần Parser Router quyết định parser nào chạy trước, và quality gate quyết định khi nào chuyển parser khác.

10. **Citation tồn tại là chưa đủ**  
    Một trích dẫn hợp lệ về mặt định danh vẫn có thể đi kèm số liệu sai (mức phạt, số điểm trừ) hoặc claim không được passage hỗ trợ. Cần numeric grounding và claim support verification, không chỉ kiểm tra ID.

### Khoảng trống cần nghiên cứu

Các chatbot hỏi đáp tài liệu phổ thông thường triển khai luồng:

```text
PDF -> Chunk -> Vector Database -> LLM
```

Luồng này chưa giải quyết đầy đủ:

- cấu trúc pháp lý (Chương, Mục, Điều, Khoản, Điểm với nhãn tiếng Việt d) đ));
- phiên bản và thời gian hiệu lực;
- sửa đổi, thay thế hoặc bãi bỏ từng phần;
- quan hệ tham chiếu chéo giữa các quy định;
- câu hỏi cần nhiều loại bằng chứng phối hợp;
- citation đến đúng Điều, Khoản, Điểm;
- kiểm chứng claim và số liệu bằng passage;
- từ chối trả lời khi thiếu căn cứ;
- đánh giá retrieval, citation và evidence bằng metric xác định.

### Giải pháp đề xuất

Xây dựng **hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực** để hỗ trợ tra cứu pháp luật giao thông Việt Nam với các khả năng:

- xử lý tài liệu bằng **Parser Router**: Docling là parser chính, MinerU là parser phụ và fallback/challenger;
- biểu diễn tài liệu qua **Canonical Document IR** do dự án sở hữu (`ParsedDocument`, `ParsedPage`, `DocumentElement`);
- trích xuất cấu trúc pháp lý bằng **Legal Structure Extractor** riêng của VNLRAG, hỗ trợ phân cấp Chương, Mục, Điều, Khoản, Điểm với nhãn tiếng Việt a) b) c) d) đ) e);
- mô hình hóa quan hệ tham chiếu chéo qua bảng quan hệ trong PostgreSQL, không dùng Neo4j;
- bảo toàn provenance đến trang và bounding box;
- quản lý metadata, phiên bản và quan hệ bằng PostgreSQL làm nguồn chân lý;
- retrieval đa tầng trong Qdrant: exact legal lookup, dense, sparse BM25, RRF fusion, reranking, mở rộng ngữ cảnh pháp lý;
- evidence planning và Evidence Completeness Gate trước khi sinh câu trả lời;
- sinh câu trả lời có cấu trúc theo schema cấp claim với `provision_id`;
- kiểm chứng sáu tầng (schema, citation ID, temporal, numeric grounding, claim support, evidence completeness) trước khi trả kết quả;
- verified-or-abstain với failure-aware repair có giới hạn;
- Langfuse cho observability, quản lý prompt và experiment;
- RAGFlow chỉ dùng làm baseline so sánh bên ngoài.

Hệ thống không sử dụng open web search để tạo câu trả lời pháp lý. Web chỉ có thể được dùng ngoài luồng hỏi đáp để phát hiện văn bản chính thức mới phục vụ quy trình cập nhật corpus.

> **Ghi chú lịch sử**: thiết kế v1 dựa trên UDEF và traffic-law domain pack (pipeline `PDF -> UDEF -> Docling -> CDM`). Phiên bản v2 loại bỏ hoàn toàn UDEF khỏi mọi pipeline và thay thế bằng Parser Router, Canonical Document IR và Legal Structure Extractor do dự án sở hữu. Chi tiết lý do tại mục 1.2.3.

---

## 1.2. Phân tích khả thi kỹ thuật (Technical Feasibility)

### 1.2.1. Đánh giá phần cứng mục tiêu

| Linh kiện | Thông số | Đánh giá |
|---|---|---|
| CPU | Intel Core i5-1035G1, 4 nhân 8 luồng | Đủ để chạy FastAPI, PostgreSQL, Qdrant, Redis, MinIO và pipeline xử lý tuần tự trên tập corpus nhỏ |
| RAM | 19 GB DDR4 | Đủ cho Docker Compose nếu giới hạn concurrency; Docling chạy CPU tiêu thụ khoảng 2-4 GB RAM điển hình (nhà sản xuất khuyến nghị 8-16 GB và 4 luồng) |
| GPU | NVIDIA MX330, 2 GB VRAM | Không phù hợp để chạy LLM, reranker lớn hoặc MinerU VLM/hybrid backend (yêu cầu tối thiểu 8 GB VRAM) tại máy cục bộ |
| Disk | NVMe 473 GB, khoảng 185 GB trống tại thời điểm khảo sát | Đủ lưu PDF gốc, đầu ra parser, PostgreSQL, Qdrant volume, MinIO artifacts và kết quả thí nghiệm; MinerU pipeline cần thêm 20+ GB disk cho runtime và model |

### Đánh giá lại giả định tài nguyên parser

Các con số dưới đây là yêu cầu theo tài liệu nhà cung cấp, chưa phải kết quả đo trên máy này:

- **Docling (CPU)**: hoạt động ổn định với khoảng 2-4 GB RAM; khuyến nghị 8-16 GB RAM và 4 luồng. Chạy được trên máy local.
- **MinerU pipeline backend**: hoạt động trên CPU, khuyến nghị RAM 16+ GB (tối ưu 32+), disk 20+ GB, Python 3.10-3.13. Chạy được trên máy local nhưng cần kiểm soát tài nguyên.
- **MinerU VLM/hybrid backend**: yêu cầu GPU tối thiểu 8 GB VRAM. Máy local chỉ có MX330 2 GB VRAM, nên VLM/hybrid backend **không khả thi cục bộ**; các phương án là chạy qua remote (`*-http-client`), hoãn lại, hoặc ghi nhận trong tài liệu là không khả dụng local.

### Ràng buộc phần cứng

Hệ thống online không cần GPU cục bộ vì:

- LLM generator, dense embedding và reranker chạy qua API;
- Qdrant thực hiện vector search trên CPU;
- sparse retrieval không yêu cầu GPU;
- corpus mục tiêu chỉ gồm 20 đến 30 văn bản.

Do GPU local không chạy được MinerU VLM backend, tuyển chọn corpus ưu tiên **PDF born-digital có sẵn text layer**; tài liệu scan được định tuyến qua backend OCR chạy trên CPU:

- Docling với Tesseract/EasyOCR/RapidOCR (có hỗ trợ tiếng Việt: Tesseract `vie`, EasyOCR `vi`, RapidOCR PP-OCR v4/v5/v6);
- hoặc MinerU pipeline backend (109 ngôn ngữ, hỗ trợ tiếng Việt).

Ingestion cần giới hạn concurrency để tránh đầy RAM:

```text
MAX_INGESTION_WORKERS = 1
```

### 1.2.1b. Môi trường phát triển (Development Environment)

| Công cụ | Phiên bản hoặc phạm vi | Ghi chú |
|---|---|---|
| Python | 3.11.x | Đồng bộ với Docling, MinerU và hệ sinh thái xử lý tài liệu |
| Package manager | uv | Quản lý dependency và lock file |
| Node.js | Phiên bản LTS được Next.js hỗ trợ | Không phụ thuộc Node 26 trong tài liệu thiết kế |
| Docker Engine | Compose Spec hiện hành | Chạy backend, frontend, PostgreSQL, Qdrant, Redis, MinIO; RAGFlow chạy trong môi trường benchmark riêng |
| Redis | 8.x | Broker cho Dramatiq và cache (thành phần dev mới) |
| Dramatiq | 2.x | Worker ingestion phía sau hàng đợi (thành phần dev mới) |
| MinIO | Bản community hiện hành | Object storage S3-compatible (thành phần dev mới); ứng viên hiện tại, lựa chọn implementation chờ ADR |
| Langfuse Cloud | SDK v4.x | Tracing, quản lý prompt, experiment (thành phần dev mới, mặc định dùng cloud) |
| Git | Phiên bản hiện hành | Quản lý source, tag release và experiment config |
| CI/CD | GitHub Actions | Lint, type check, unit test, integration test, regression test và security test |

Phiên bản chính xác phải được pin trong:

- `.python-version`;
- `pyproject.toml`;
- `uv.lock`;
- `package.json` và lock file frontend;
- Docker image tag;
- `evaluation-config.yaml`.

### 1.2.2. Đánh giá các thành phần kỹ thuật

| Thành phần | Phương án chốt | Đánh giá khả thi |
|---|---|---|
| API | FastAPI + Pydantic v2 | Phù hợp cho API có schema rõ ràng, validation và async I/O; upload tài liệu trả `202 Accepted` kèm `ingestion_job_id` |
| Workflow | LangGraph 1.x controlled workflow (pin `langgraph>=1.1`) | Chỉ điều phối các nhánh xác định trước, không phải autonomous agent; hỗ trợ checkpoint và repair loop có giới hạn |
| Parsing | Parser Router: Docling (chính) + MinerU (phụ/fallback) | Docling chạy được trên CPU local; MinerU dùng pipeline backend trên CPU; vlm/hybrid chỉ qua remote hoặc không khả thi local |
| Document IR | Canonical Document IR (ParsedDocument/ParsedPage/DocumentElement) | Do dự án sở hữu, parser-neutral, cô lập việc phân tích pháp lý khỏi định dạng đầu ra của Docling/MinerU |
| Legal extraction | VNLRAG Legal Structure Extractor | Hỗ trợ phân cấp pháp luật Việt Nam, nhãn Điểm a) b) c) d) đ) e), short-Point retention |
| Relational data | PostgreSQL 18 + SQLAlchemy + Alembic | Nguồn chân lý cho metadata, version, quan hệ và trạng thái review |
| Relations | Bảng quan hệ trong PostgreSQL | `ProvisionReference` (PARENT_OF, REFERS_TO, SIBLING_OF, PENALTY_COMPANION) và `DocumentRelation` (AMENDS, REPEALS, SUPERSEDES, CORRECTS, GUIDES, RELATED_TO); không dùng Neo4j |
| Retrieval | Qdrant v1.19 (dense + sparse + payload filter + RRF) | Lưu dense và sparse trong cùng collection, Query API với prefetch + fusion (RRF), snapshot để dựng lại index; payload collection gồm legal provision ID, provision version, document version, field hierarchy, khoảng hiệu lực, loại phương tiện, review status, parser/content version, relation metadata khi cần |
| Dense embedding | Ứng viên: Gemini Embedding 2 (768 dimensions), benchmark với Jina Embeddings v5 text-nano / text-small | Không phụ thuộc GPU local, chi phí thấp với corpus nhỏ; benchmark phải đo Recall@10, MRR@10, nDCG@10 trên câu hỏi pháp luật tiếng Việt cùng latency và cost; không chốt embedding production vĩnh viễn trước khi benchmark |
| Reranking | Jina Reranker v3 (stage chuẩn của pipeline) | Chạy qua API, không cần GPU local; chỉ khẳng định cải thiện chất lượng sau khi benchmark |
| Generator | Gemini 3.5 Flash | Hỗ trợ structured output (`json_schema`) và context lớn |
| Evaluation judge | GPT-5.4 mini (snapshot đã pin) | Model độc lập, pin snapshot để tăng khả năng tái lập |
| Background jobs | Redis + Dramatiq | Actor idempotent, pipeline ngắn rời rạc; lưu ý giới hạn thời gian mặc định 10 phút mỗi actor |
| Object storage | S3-compatible qua `ObjectStoragePort` (MinIO là ứng viên hiện tại, chờ ADR so sánh) | Lưu PDF nguồn, đầu ra parser, ảnh trang và artifact; PostgreSQL lưu object key |
| Observability | Langfuse Cloud | Trace, prompt management, experiment, feedback; không nằm trên đường tới hạn tính đúng đắn |
| Baseline | RAGFlow (môi trường so sánh bên ngoài) | Chạy riêng trong môi trường benchmark, yêu cầu tối thiểu 4 CPU, 16 GB RAM, 50 GB disk; không nằm trong compose production |
| Frontend | Next.js + TypeScript + shadcn/ui | Đủ để xây chat, citation panel và review UI |
| Evaluation | Ragas 0.4.x + deterministic custom metrics | Tách rõ retrieval, evidence, temporal, citation, grounding và abstention quality |

Embedding production chưa được chốt vĩnh viễn. Benchmark embedding (Suite B) bắt buộc đánh giá Recall@10, MRR@10, nDCG@10 trên câu hỏi pháp luật tiếng Việt cùng latency và cost; quyết định chọn embedding chỉ được thực hiện dựa trên bằng chứng thực nghiệm, trước đó không khẳng định model nào là lựa chọn cuối cùng.

### 1.2.3. Khả thi của Parser Router và Canonical Document IR

Thiết kế v1 dùng UDEF làm tầng trung gian `PDF -> UDEF -> Docling -> CDM`. Phiên bản v2 loại bỏ UDEF vì ba lý do:

- UDEF định nghĩa schema domain riêng, tạo tầng chuyển đổi và chi phí bảo trì không cần thiết giữa đầu ra parser và mô hình dữ liệu pháp lý của dự án;
- UDEF domain pack không được thiết kế cho phân cấp pháp luật Việt Nam (nhãn d) đ), Điểm ngắn);
- lớp confidence/validation của UDEF được thay bằng quality gate và review routing của chính dự án.

Pipeline thay thế:

```text
PDF + Manifest
    -> Parser Router (Docling | MinerU)
    -> Canonical Document IR
    -> Legal Structure Extractor
    -> Legal Context Enricher
    -> Legal Reference Resolver
    -> Temporal and Amendment Resolver
    -> Quality Gates -> Human Review
    -> PostgreSQL -> Qdrant
```

**Parser Router** chọn parser theo đặc tính tài liệu và quality gate:

- PDF có text layer tìm kiếm được (searchable) và layout chuẩn: Docling chạy trước;
- tài liệu scan hoặc layout lỗi: Docling chạy trước; nếu quality gate không đạt (mất cấu trúc, OCR kém, provenance thiếu) thì chạy MinerU pipeline backend;
- bảng phức tạp: so sánh đầu ra hai parser khi cần.

Không khẳng định parser nào vượt trội tuyệt đối; kết quả được quyết định bằng Suite A (parser benchmark) trong evaluation.

**Canonical Document IR** là biểu diễn trung gian do dự án sở hữu: `ParsedDocument` chứa `ParsedPage[]`, mỗi trang chứa `DocumentElement[]` với các field `element_id`, `element_type`, `text`, `page_number`, `bbox`, `reading_order`, `parent_element_id`, `table_html`, `source_parser`, `parser_version`, `parser_confidence`, `raw_reference`. Tầng này cô lập việc phân tích pháp lý khỏi định dạng đầu ra Docling/MinerU; khi nâng cấp hoặc thay parser, chỉ cần thêm một adapter vào IR, không viết lại Legal Structure Extractor.

### 1.2.4. Khả thi của trích xuất cấu trúc pháp lý

Legal Structure Extractor là parser pháp lý riêng của VNLRAG, chạy trên Canonical Document IR, chịu trách nhiệm nhận diện Chương, Mục, Điều, Khoản, Điểm, Phụ lục, bảng pháp lý, điều khoản chuyển tiếp, tiêu đề và đánh số văn bản pháp luật Việt Nam kèm biến thể do OCR.

Các yêu cầu chính:

- **Nhãn Điểm tiếng Việt**: bắt buộc hỗ trợ a) b) c) d) đ) e). Không dùng giả định bảng chữ cái `[a-z]` đơn giản vì bảng chữ cái tiếng Việt có 29 ký tự và bao gồm `đ`.
- **Short-Point retention**: một Điểm pháp lý ngắn nhưng hợp lệ vẫn là provision hợp lệ; không loại bỏ vì số token thấp.
- **source_text vs retrieval_text**: `source_text` giữ nguyên nội dung pháp lý gốc thuộc provision; `retrieval_text` có thể kế thừa ngữ cảnh cha (câu mở đầu của Khoản, tiêu đề Điều) để phục vụ retrieval. Trích dẫn luôn trỏ tới provision thực tế.
- **Provision ID ổn định**: `provision_id` được tạo theo quy tắc xác định `{loai-van-ban}-{so}-{nam}__dieu-{n}__khoan-{n}__diem-{chu-cai}`, ví dụ `nd-168-2024__dieu-7__khoan-4__diem-b`. Nhãn Điểm giữ nguyên ký tự tiếng Việt, ví dụ Điểm `đ)` tương ứng `diem-đ`, tránh va chạm với `diem-d`. Khi provision bị sửa đổi, ID giữ nguyên, nội dung mới lưu dưới version mới.
- **Parent-context enrichment**: `retrieval_text` kế thừa ngữ cảnh cha nhưng không bao giờ biến đổi `source_text`.

Các yêu cầu trên được gom vào mô hình **LegalProvision** (nhất quán với `00-scope-and-decisions.md`): mỗi provision mang `provision_id`, `document_version_id`, `chapter`, `section`, `article`, `clause`, `point`, `heading`, `source_text`, `retrieval_text`, `parent_context`, `effective_from`, `effective_to`, `status`, `page_number`, `bbox`, `source_element_ids`, `content_hash`, `version` và `review_status`; trong đó `source_text` giữ nguyên nội dung pháp lý gốc, còn `retrieval_text` phục vụ retrieval và có thể kế thừa ngữ cảnh cha.

Tính khả thi cao vì đầu vào đã được chuẩn hóa trong Canonical Document IR và có thể kiểm thử bằng fixture theo loại văn bản (Luật, Nghị định, Thông tư) trong Suite A và corpus QA.

### 1.2.5. Khả thi của mô hình quan hệ tham chiếu và thời gian

Quan hệ được lưu trong bảng PostgreSQL và xử lý bằng application logic, không dùng Neo4j:

- **Bốn quan hệ cấp provision** trong `ProvisionReference`: `PARENT_OF`, `REFERS_TO`, `SIBLING_OF`, `PENALTY_COMPANION`;
- **Sáu quan hệ cấp văn bản** trong `DocumentRelation`: `AMENDS`, `REPEALS`, `SUPERSEDES`, `CORRECTS`, `GUIDES`, `RELATED_TO`;
- `LegalEffectEvent` ghi sự kiện pháp lý (có hiệu lực, sửa đổi, thay thế, bãi bỏ) phục vụ Temporal/Amendment Resolver và câu hỏi so sánh.

Temporal/Amendment Resolver dùng manifest, `LegalEffectEvent` và review để xác định khoảng hiệu lực. Các trường hợp không chắc chắn được định tuyến sang review thay vì suy đoán tự động. Quy mô corpus 20-30 văn bản với ít nhất 5 chuỗi sửa đổi là đủ để thực hiện và kiểm thử resolver mà không quá tải thao tác thủ công.

### 1.2.6. Khả thi của temporal retrieval

Temporal retrieval không yêu cầu temporal database chuyên dụng. PostgreSQL và payload filter của Qdrant đủ cho quy mô khóa luận.

Điều kiện hợp lệ tại `query_date`:

```text
effective_from <= query_date
AND
(effective_to IS NULL OR query_date < effective_to)
AND
review_status = ACCEPTED
```

PostgreSQL là nguồn chân lý cho metadata, version và quan hệ. Qdrant là index dẫn xuất, dựng lại được từ PostgreSQL; payload của collection phải chứa: legal provision ID, provision version, document version, các field hierarchy, khoảng hiệu lực, loại phương tiện, review status, parser/content version, relation metadata khi cần. Nếu dữ liệu giữa hai nơi khác nhau, PostgreSQL thắng.

Các trường hợp hỗ trợ:

- không có ngày trong câu hỏi: dùng ngày request;
- có một ngày hoặc một năm: chuyển thành `query_date`;
- câu so sánh: tạo hai temporal contexts độc lập, truy vấn hai phiên bản hiệu lực;
- biên sửa đổi: phân biệt phiên bản trước và sau sửa đổi, kể cả sửa đổi từng phần;
- quy định bị thay thế: trả lời theo phiên bản còn hiệu lực tại ngày hỏi;
- ngày không xác định được: yêu cầu người dùng bổ sung, hoặc **ABSTAIN** nếu không thể xác định ngày áp dụng; chỉ trả lời theo hiện hành khi câu hỏi tường minh là câu hỏi hiện hành, không dùng hiện hành làm giá trị mặc định cho câu hỏi có thể là lịch sử.

### 1.2.7. Khả thi của retrieval đa tầng, evidence completeness và verification

Pipeline online có các tầng sau, mỗi tầng có thể được cài đặt và kiểm thử độc lập:

1. **Query Understanding**: trích intent, `query_date`, ngày so sánh, loại phương tiện, số văn bản, số Điều/Khoản/Điểm, thực thể pháp lý, normalized query và **evidence plan**;
2. **Query Expansion**: luôn giữ câu hỏi gốc; thêm normalized query, multi-query rewrite và conditional HyDE (không bật luôn, không rewrite vô hạn);
3. **Parallel Multi-Recall**: exact legal lookup (định danh như `168/2024/NĐ-CP`, `Điều 7`, `Khoản 4`, `Điểm a`), dense semantic và sparse BM25;
4. **RRF Fusion**: kết hợp dense + sparse trong Qdrant;
5. **Reranking**: Jina Reranker v3 là stage chuẩn, chưa khẳng định cải thiện trước benchmark;
6. **Legal Context Expansion**: mở rộng quanh seed provision mạnh theo parent, sibling, cross-reference, penalty companion; mỗi provision mở rộng ghi `added_by`, `source_id`, `depth`; tránh mở rộng đồ thị không giới hạn;
7. **Evidence Completeness Gate**: kiểm tra mọi loại bằng chứng trong evidence plan; nếu đủ thì chuyển sang Context Builder; nếu thiếu (ví dụ hỏi mức phạt + số điểm trừ mà chỉ tìm được mức phạt) thì chạy targeted retrieval hoặc mở rộng theo quan hệ, quay lại kiểm tra tính đầy đủ, sau đó mới dựng ngữ cảnh;
8. **Context Builder**: dựng ngữ cảnh pháp lý cuối cùng từ bằng chứng đã xác nhận đầy đủ để đưa vào generator;
9. **Structured Answer Generator**: sinh theo schema cấp claim (`answer_summary`, `claims` với `claim`, `claim_type`, `provision_ids`, `numbers`, `missing_information`, `should_abstain`);
10. **Verification sáu tầng**: L1 schema, L2 citation ID (provision tồn tại, đã retrieve hoặc mở rộng hợp lệ, ACCEPTED), L3 temporal validity, L4 numeric grounding (mức phạt, điểm trừ, ngày, tuổi, thời hạn khớp giá trị bằng chứng đã chuẩn hóa), L5 claim support (deterministic trước, LLM judge chỉ cho trường hợp ngữ nghĩa), L6 evidence completeness;
11. **Failure-aware repair**: thiếu bằng chứng chạy targeted retrieval; claim không được hỗ trợ sinh lại hoặc truy xuất thêm; schema sai sinh lại structured output; xung đột thời gian truy xuất phiên bản đúng. Sau số lần repair có giới hạn thì **ABSTAIN**;
12. Bất biến API: **Returned Invalid Citation Rate = 0**.

Mỗi tầng được thiết kế để cài đặt và kiểm thử độc lập; Suite C và D sẽ đánh giá tác động của từng tầng trong evaluation.

### 1.2.8. Khả thi của background ingestion và object storage

Ingestion chạy hoàn toàn qua hàng đợi, không parse PDF đồng bộ trong request handler:

```text
POST /documents -> 202 Accepted + ingestion_job_id
-> Worker Dramatiq: parse -> normalize -> legal extract
   -> reference resolve -> temporal resolve
   -> quality gates -> review -> embed -> index
```

- **Redis** làm broker cho Dramatiq và cache.
- **Dramatiq**: mỗi bước là một actor idempotent ngắn; actor được thiết kế để chạy lại an toàn khi worker fail. Lưu ý giới hạn thời gian mặc định 10 phút mỗi actor, cần nâng lên phù hợp hoặc tách bước dài thành nhiều actor.
- **Object storage (S3-compatible, qua `ObjectStoragePort`)**: lựa chọn object storage đang được mở lại; quyết định implementation chờ ADR so sánh và **MinIO là ứng viên hiện tại**, chưa được khóa trong tài liệu này. Object storage dùng buckets riêng cho PDF nguồn, đầu ra parser, ảnh trang, artifact ingestion/review/evaluation; PostgreSQL lưu object key và metadata; backup bằng replication hoặc `mc mirror`/`mc cp` sang nơi lưu trữ độc lập. Lifecycle tiering/ILM/transition không phải là backup; dữ liệu chuyển tầng vẫn nằm trong cùng hệ thống và cần nơi lưu trữ độc lập riêng cho mục đích phục hồi. Lý do khả thi tài nguyên không đổi: lưu trữ S3-compatible chạy local trong Docker Compose và miễn phí (0 USD).

Tính khả thi cao vì Dramatiq và Redis chạy được trong Docker Compose trên CPU, và queue tách ingestion khỏi online query path.

### 1.2.9. Khả thi của observability

- **Langfuse Cloud** là lựa chọn mặc định cho dev và evaluation, không yêu cầu hạ tầng bổ sung.
- Tự host Langfuse là tùy chọn và phức tạp hơn: cần container app + worker, PostgreSQL, ClickHouse, Redis/Valkey, blob storage (S3), web và worker service. Không chọn tự host trong giai đoạn khóa luận.
- Langfuse **không nằm trên đường tới hạn tính đúng đắn**: trace được ingest bất đồng bộ; nếu Langfuse không khả dụng, query vẫn hoạt động bình thường.
- Trace các span: `analyze_query`, `normalize_query`, `rewrite_query`, `hyde`, `exact_lookup`, `dense_retrieval`, `sparse_retrieval`, `rrf_fusion`, `reranker`, `reference_expansion`, `evidence_check`, `generate`, `citation_verify`, `numeric_verify`, `claim_verify`.

### 1.2.10. Đánh giá dữ liệu

| Nguồn dữ liệu | Vai trò | Đánh giá |
|---|---|---|
| Cơ sở dữ liệu quốc gia về văn bản pháp luật | Nguồn ưu tiên cho văn bản và metadata | Phù hợp để đối chiếu số hiệu, ngày và trạng thái |
| Cổng văn bản Chính phủ | Nguồn chính thức bổ sung | Dùng khi cần kiểm tra văn bản do Chính phủ ban hành |
| PDF hoặc bản điện tử của cơ quan ban hành | Nguồn nội dung | Chỉ ingest khi có manifest và file hash; ưu tiên PDF born-digital có text layer để giảm phụ thuộc OCR |
| Bộ pháp điển điện tử | Nguồn tham khảo cấu trúc chủ đề | Không thay thế lịch sử hiệu lực của văn bản gốc |
| Website tổng hợp pháp luật | Nguồn phát hiện hoặc đối chiếu phụ | Không là nguồn sự thật chính của corpus |

### Phạm vi corpus

Mục tiêu:

- 20 đến 30 văn bản chính thống;
- tập trung vào giao thông đường bộ;
- có ít nhất 5 chuỗi sửa đổi, thay thế hoặc bãi bỏ;
- có cả văn bản hiện hành và lịch sử;
- mỗi văn bản có manifest (document_id, source_url, downloaded_at, file_hash, document_number, document_type, issuer, issued_date, effective_from, effective_to, status, relation_notes, review_status, reviewed_by, reviewed_at);
- ưu tiên tài liệu có text layer tìm kiếm được; tài liệu scan đi qua OCR backend CPU và phải qua quality gate trước khi review.

Số lượng này đủ để thực hiện temporal retrieval và mô hình quan hệ tham chiếu mà vẫn cho phép kiểm tra thủ công trong thời gian khóa luận.

### Corpus QA (báo cáo chất lượng corpus)

Corpus có báo cáo/dashboard chất lượng riêng với các chỉ số (kế hoạch đo lường trong evaluation, chưa phải kết quả đã đạt): document count, article count, clause count, point count, Point coverage, short-Point retention, tỷ lệ phát hiện nhãn đ), orphan Point count, orphan Clause count, duplicate provision count, parent-context coverage, provenance coverage, table coverage, unresolved cross-reference count, unknown effective date count, temporal conflict count.

Với các văn bản quan trọng (ví dụ Nghị định 168), thực hiện structural QA có mục tiêu riêng ngoài các chỉ số chung trên.

---

## 1.3. Phân tích khả thi vận hành (Operational Feasibility)

### Đối tượng sử dụng

| Đối tượng | Nhu cầu |
|---|---|
| Người tham gia giao thông | Tra cứu quy định và mức xử phạt có căn cứ |
| Tài xế công nghệ | Kiểm tra quy định hiện hành theo loại phương tiện |
| Sinh viên hoặc người nghiên cứu | Tìm nhanh Điều, Khoản, Điểm và so sánh phiên bản |
| Phóng viên hoặc người viết nội dung | Tìm căn cứ và mở lại passage nguồn |
| Corpus reviewer | Kiểm tra tài liệu, metadata, hierarchy, quan hệ tham chiếu và hiệu lực trước khi index |
| Người vận hành hạ tầng (MinIO, Redis, Dramatiq) | Quản lý bucket, object key, backup/restore, giám sát worker và hàng đợi |
| Nhà phát triển | Vận hành ingestion, evaluation, deployment và regression tests |

### Luồng vận hành chính

#### Người dùng cuối

```text
Đặt câu hỏi
-> Query Understanding (intent, query_date, evidence plan)
-> Temporal Resolution
-> Query Expansion (original | normalized | rewrite | conditional HyDE)
-> Parallel Multi-Recall (exact lookup | dense | sparse)
-> RRF Fusion -> Reranking
-> Legal Context Expansion
-> Evidence Completeness Gate
-> Context Builder
-> Structured Answer Generation
-> Verification (sáu tầng)
-> Verified Answer | Abstention
```

#### Corpus reviewer

```text
Nạp PDF + manifest
-> Parser Router (Docling | MinerU)
-> Canonical Document IR
-> Legal Structure Extractor
-> Legal Reference Resolver + Temporal Resolver
-> Quality Gates
-> review item nếu cần
-> accept hoặc reject
-> index provision được chấp nhận vào PostgreSQL và Qdrant
```

### Tính sẵn sàng

- Có thể demo đầy đủ trên máy local bằng Docker Compose; deployment sạch từ compose file và release manifest.
- Không phụ thuộc VPS trong buổi bảo vệ.
- Có thể export corpus manifest, database backup, Qdrant snapshot, MinIO backup và evaluation report; quy trình backup/restore được kiểm thử trước buổi bảo vệ.
- Khi API LLM không khả dụng, hệ thống có thể demo retrieval và citation source browsing; không tự động chuyển sang model khác rồi làm thay đổi kết quả không kiểm soát.
- Khi Langfuse không khả dụng, query vẫn hoạt động vì Langfuse không nằm trên đường tới hạn.
- Có thể mở rộng corpus sau khóa luận mà không thay đổi online architecture.

### Giới hạn vận hành

- Hệ thống hỗ trợ tra cứu, không thay thế tư vấn của luật sư hoặc kết luận của cơ quan có thẩm quyền.
- Corpus không bao phủ toàn bộ pháp luật Việt Nam.
- Chỉ provision có `review_status = ACCEPTED` mới được sử dụng để trả lời.
- Không trả lời bằng nguồn web chưa được ingest.
- Ingestion chạy qua hàng đợi với `MAX_INGESTION_WORKERS = 1`; không parse đồng bộ trong request handler.
- Không xử lý dữ liệu cá nhân nhạy cảm trong scope khóa luận.

---

## 1.4. Phân tích khả thi tài chính (Financial Feasibility)

### Đơn giá tham chiếu tại thời điểm cập nhật

| Dịch vụ | Đơn giá tham chiếu |
|---|---|
| Gemini 3.5 Flash | Paid tier: khoảng 1,50 USD / 1 triệu input token và 9,00 USD / 1 triệu output token |
| Gemini Embedding 2 | Paid tier: khoảng 0,20 USD / 1 triệu text token |
| GPT-5.4 mini | Khoảng 0,75 USD / 1 triệu input token và 4,50 USD / 1 triệu output token |
| Jina API (embedding v5 + reranker v3) | Khoảng 0,05 USD / 1 triệu token; tài khoản API mới có 10 triệu token miễn phí |
| PostgreSQL local | 0 USD |
| Qdrant local | 0 USD |
| Redis local | 0 USD |
| MinIO local | 0 USD (object storage S3-compatible, mã nguồn mở) |
| Langfuse Cloud | Có free/dev tier; paid tier tính theo usage |
| RAGFlow baseline | 0 USD phần mềm (chạy Docker local, dùng chung hạ tầng máy cá nhân) |
| Domain và VPS | Không bắt buộc cho bảo vệ |

Free tier có thể giảm chi phí, nhưng không được xem là điều kiện bắt buộc vì quota và quyền truy cập có thể thay đổi.

### Ước tính theo hoạt động

Kịch bản ngân sách khả thi với tổng dưới 30 USD, kèm giới hạn token và số lần chạy cho từng suite:

| Hoạt động | Giả định và giới hạn chạy | Chi phí dự kiến |
|---|---|---|
| Embed corpus và re-index | Corpus 20-30 văn bản, tối đa 20 lần re-index | Dưới 1 USD |
| Benchmark embedding (Suite B) và reranker (R6) | Dev set 40 câu, mỗi variant chạy 1 lần; ưu tiên Jina 10M token miễn phí; đánh giá Recall@10, MRR@10, nDCG@10, latency, cost | 1-2 USD |
| Phát triển và kiểm thử thủ công | Giới hạn số lần gọi generator, context ngắn | 2-4 USD |
| Ablation retrieval (Suite C) | Validation set 40 câu, mỗi cấu hình R1-R10 chạy 1 lần, không gọi judge | 2-5 USD |
| Ablation generation và verification (Suite D) | Validation set 40 câu, mỗi variant G1-G7 chạy 1 lần | 3-6 USD |
| Final evaluation | Final test set 120 câu, chạy 1 lần với cấu hình đã pin | 4-6 USD |
| Independent judge | Chỉ dùng cho metric phụ, giới hạn số lần gọi | 3-5 USD |
| Observability (Langfuse Cloud) | Free/dev tier với quota theo gói; nếu gần hết quota thì giảm độ chi tiết trace | 0 USD (free tier) |

Tổng kịch bản: khoảng 15-29 USD, nằm dưới mục tiêu 30 USD.

Chi phí benchmark embedding và reranker tăng nhẹ so với v1 do thêm Jina API, nhưng Jina cung cấp 10 triệu token miễn phí cho tài khoản mới và đơn giá 0,05 USD / 1 triệu token nên tác động lên ngân sách thấp. RAGFlow baseline không phát sinh chi phí API mà chiếm tài nguyên cục bộ khi chạy benchmark (tối thiểu 4 CPU, 16 GB RAM, 50 GB disk).

### Ngân sách đề xuất

- **Ngân sách mục tiêu**: không quá 30 USD cho toàn bộ các suite và final evaluation.
- **Ngân sách dự phòng tối đa**: 40 USD, tách biệt với mục tiêu; chỉ dùng khi pipeline lỗi phải chạy lại hoặc cấu hình bắt buộc thay đổi, không phải ngân sách chạy thường.
- Mỗi suite có giới hạn token và số lần chạy như bảng trên; vượt giới hạn thì dừng, xem lại cấu hình trước khi chạy tiếp.
- Langfuse Cloud dự kiến 0 USD trong free/dev tier; nếu quota không đủ, ưu tiên giảm độ chi tiết trace hoặc chỉ trace các span chọn lọc; chi phí phát sinh bất khả kháng được trích từ dự phòng 40 USD và ghi lại trong báo cáo.
- Ghi token usage và estimated cost theo từng evaluation run.
- Dùng deterministic metric trước để tránh gọi judge không cần thiết.
- Không dùng web grounding hoặc external search trong query pipeline.

**Đánh giá**: khả thi đối với khóa luận cá nhân, với điều kiện tuân thủ giới hạn token theo suite và pin cấu hình trước final evaluation.

---

## 1.5. Phân tích khả thi lịch trình (Schedule Feasibility)

### Tổng thời gian còn lại

- Bắt đầu giai đoạn triển khai theo thiết kế mới: 20/07/2026.
- Hạn hoàn thành: 12/09/2026.
- Tổng thời gian triển khai và hoàn thiện: 55 ngày.
- Ngày tập bảo vệ: 13/09/2026.
- Ngày bảo vệ: 14/09/2026.

| Tuần | Thời gian | Giai đoạn | Deliverable chính |
|---|---|---|---|
| 1 | 20/07-26/07 | Chốt thiết kế và corpus | ADR, manifest, schema, thiết kế Parser Router và Canonical Document IR |
| 2 | 27/07-02/08 | Parser foundation | Suite A (P1-P3), chọn hướng parser, Canonical Document IR hoàn chỉnh |
| 3 | 03/08-09/08 | Legal extraction và data platform | Legal Structure Extractor, corpus QA, PostgreSQL, Qdrant, MinIO, ingestion queue |
| 4 | 10/08-16/08 | Relation graph và temporal | Legal Reference Resolver, Temporal/Amendment Resolver, bảng quan hệ, parent-context enrichment |
| 5 | 17/08-23/08 | Retrieval và query workflow | Suite B và C (R1-R10), query expansion, reranker, evidence gate, LangGraph, Langfuse |
| 6 | 24/08-30/08 | UI và review flow | Frontend, citation panel, feedback, review CLI (P0); review UI (P1) chỉ khi P0 ổn định |
| 7 | 31/08-06/09 | Evaluation và stabilization | Gold set 200 câu (40 development / 40 validation / 120 final test), Suite D (G1-G7), RAGFlow baseline, performance |
| 8 | 07/09-12/09 | Finalization | Code freeze, report, demo |
| Rehearsal | 13/09 | Tập bảo vệ | Offline demo rehearsal và backup verification |
| Defense | 14/09 | Bảo vệ | Release candidate đã khóa |

### Mốc kiểm soát

- **Feature freeze**: 06/09/2026.
- **Code freeze**: 10/09/2026.
- **Release candidate**: 12/09/2026.
- Không thêm tính năng mới trong hai ngày cuối.
- PDF báo cáo được build từ LaTeX, không chỉnh trực tiếp.

### Đánh giá khối lượng

Scope lớn hơn bản v1 nhưng vẫn khả thi vì:

- parser chính Docling chạy được trên CPU local;
- corpus giới hạn 20 đến 30 văn bản;
- online architecture là monolith;
- Qdrant thay thế hai hệ retrieval rời;
- không có web fallback;
- không có multi-agent;
- không fine-tune model;
- P1 chỉ bắt đầu khi P0 đã ổn định.

Các bề mặt cài đặt mới so với v1:

- **Parser benchmark trước** (Suite A) quyết định hướng routing và chất lượng đầu vào cho toàn bộ pipeline;
- **MinerU là parser lane bổ sung** (rủi ro mới về tài nguyên và chất lượng OCR tiếng Việt);
- **background ingestion** (Redis, Dramatiq, object storage S3-compatible qua `ObjectStoragePort`);
- **evidence completeness và numeric grounding** là logic mới ngoài citation verification.

Điểm có rủi ro lịch trình cao nhất:

1. parser benchmark và quality gate định tuyến;
2. legal hierarchy extraction, gồm nhãn Điểm d) và đ);
3. relation và temporal resolution;
4. evidence completeness;
5. gold set 200 câu (40 development / 40 validation / 120 final test);
6. review workload;
7. viết báo cáo song song với code.

---

## 1.6. Phân tích rủi ro (Risk Analysis)

| ID | Rủi ro | Xác suất | Tác động | Biện pháp giảm thiểu |
|---|---|---:|---:|---|
| R1 | Gán sai ngày hoặc trạng thái hiệu lực | Trung bình | Rất cao | Manifest bắt buộc, đối chiếu nguồn chính thức, temporal unit test, reviewer approval |
| R2 | Không mô hình hóa đúng sửa đổi một phần | Cao | Rất cao | Giới hạn corpus, relation schema rõ ràng, ghi nhận unsupported relation, không suy đoán tự động |
| R3 | MinerU VLM/hybrid backend không khả thi local (GPU 8 GB VRAM không có) | Cao | Trung bình | Chỉ dùng pipeline backend CPU; vlm/hybrid qua remote `*-http-client` hoặc ghi nhận không khả thi local; ưu tiên corpus PDF có text layer |
| R4 | Docling/MinerU gây lỗi OCR/layout trên PDF pháp luật tiếng Việt, nhận sai nhãn Điểm (d) và đ)) | Cao | Cao | Suite A parser benchmark, fixture theo loại văn bản, quality gates, corpus QA, structural QA cho văn bản quan trọng (ví dụ Nghị định 168) |
| R5 | Parser Router định tuyến sai tài liệu sang parser không phù hợp | Trung bình | Cao | Quy tắc routing theo đặc tính tài liệu, quality gates phát hiện lỗi và kích hoạt fallback parser, ghi `source_parser` vào Document IR |
| R6 | Trích xuất cross-reference sai hoặc reference không giải quyết được | Trung bình | Cao | Relation schema rõ ràng, ghi unresolved reference, định tuyến sang review, không suy đoán quan hệ |
| R7 | LLM tạo claim không được passage hỗ trợ | Cao | Rất cao | Structured output, provision ID whitelist, verifier L2/L4/L5, failure-aware repair có giới hạn, sau đó abstain |
| R8 | Retrieval không lấy được provision đúng | Trung bình | Cao | Exact lookup + dense + sparse + RRF, ablation Suite C, regression set, Recall@k và MRR |
| R9 | Evidence Completeness Gate over-abstain (bác bỏ đáp án hợp lệ) hoặc under-abstain | Trung bình | Cao | Evidence plan chuẩn hóa, threshold xác định từ baseline và validation set, không đặt ngưỡng trước thực nghiệm |
| R10 | Corpus không được review đủ trước deadline | Trung bình | Cao | Ưu tiên corpus cốt lõi, chia batch review qua queue, cache PDF và manifest kèm file hash, đối chiếu từ nhiều nguồn chính thức |
| R11 | Gold set bị tạo sau khi xem kết quả, gây leakage | Trung bình | Cao | Freeze gold set version, hash file, tách development/validation/final test, review độc lập |
| R12 | LLM judge thiên lệch hoặc không ổn định | Trung bình | Trung bình | Deterministic metric làm headline, pin GPT-5.4 mini snapshot, lưu raw judge output |
| R13 | Model API, quota hoặc giá thay đổi | Trung bình | Trung bình | Provider interface, pin model ID, budget cap, không hardcode quota trong logic |
| R14 | Langfuse không khả dụng | Thấp | Thấp | Langfuse không nằm trên đường tới hạn; trace fail không chặn query; bật/tắt qua config |
| R15 | Hạ tầng RAGFlow baseline (tối thiểu 16 GB RAM) cạnh tranh tài nguyên local | Cao | Trung bình | Bắt buộc chạy đủ mọi variant baseline trong môi trường benchmark riêng; chạy tuần tự từng variant, dừng service không cần thiết khi benchmark; nếu RAM local không đủ, chạy tuần tự trên máy phù hợp khác thay vì lược bớt variant |
| R16 | Lỗi hàng đợi MinIO/Redis/Dramatiq | Trung bình | Trung bình | Actor idempotent, retry middleware, dead-letter queue, giám sát worker, backup MinIO; lựa chọn object storage implementation là ADR-gated và nằm sau `ObjectStoragePort`, đổi implementation không làm thay đổi contract |
| R17 | PostgreSQL, Qdrant và parser dùng quá nhiều RAM khi chạy cùng | Cao | Trung bình | `MAX_INGESTION_WORKERS = 1`, dừng frontend khi benchmark cần thiết, giám sát Docker, cấu hình giới hạn bộ nhớ |
| R18 | Không kịp hoàn thiện báo cáo | Trung bình | Rất cao | Viết từng chương song song, feature freeze 06/09, code freeze 10/09 |
| R19 | Demo phụ thuộc Internet | Trung bình | Cao | Chuẩn bị retrieval-only demo, cache corpus, health check API, video backup |
| R20 | Scope P1 lấn sang P0 | Cao | Cao | P1 bị khóa cho đến khi toàn bộ acceptance criteria P0 đạt |

### Kế hoạch khôi phục khi lỗi xảy ra (failure-recovery plan)

Không thu hẹp chức năng cốt lõi vì thời gian. Mọi hạng mục P0 phải hoàn thành trước feature freeze 06/09. Chỉ cho phép kế hoạch khôi phục tường minh khi một lỗi cụ thể xảy ra:

- Nếu một parser lane không qua quality gates trên nhóm tài liệu nhất định, định tuyến tạm toàn bộ tài liệu nhóm đó qua parser còn hoạt động tốt trong khi sửa parser kia; kết quả được ghi lại trong Suite A và corpus QA.
- Nếu MinerU VLM/hybrid backend không khả thi local, dùng pipeline backend CPU hoặc remote `*-http-client`; không giữ giả định VLM local.
- Nếu Evidence Completeness Gate over-abstain, điều chỉnh threshold dựa trên validation set, không loại bỏ gate và không hạ chuẩn verified-or-abstain.
- Nếu retrieval chưa đạt, tiếp tục ablation Suite C để xác định tầng bổ sung hiệu quả thay vì bỏ tầng mặc định.
- Mọi thay đổi phải giữ nguyên bất biến Returned Invalid Citation Rate = 0 và không thay đổi gold set đã đóng băng.

---

## 1.7. Kết luận khả thi

> **Hệ thống khả thi về kỹ thuật, vận hành, tài chính và lịch trình**, nhưng chỉ khi giữ đúng ranh giới đã chốt trong `00-scope-and-decisions.md`.

### Điều kiện tiên quyết

1. Parser Router (Docling chính, MinerU phụ/fallback) phải hoạt động với quality gate trước khi mở rộng corpus.
2. Canonical Document IR hoàn chỉnh trước khi viết Legal Structure Extractor.
3. Legal Structure Extractor phải hỗ trợ phân cấp pháp luật Việt Nam gồm nhãn Điểm d) đ) và short-Point retention.
4. PostgreSQL là nguồn chân lý cho metadata, version và quan hệ; Qdrant là index dẫn xuất dựng lại được.
5. LangGraph chỉ điều phối controlled workflow, không phải autonomous agent.
6. Không dùng open web search để sinh câu trả lời.
7. Citation được dựng từ `provision_id` và metadata đã xác minh, không do LLM gõ tự do.
8. Verification là bất biến: Returned Invalid Citation Rate = 0, verified-or-abstain sau số lần repair có giới hạn.
9. Gold set phải được version hóa và đóng băng trước final evaluation.
10. Langfuse không nằm trên đường tới hạn; query vẫn hoạt động khi Langfuse không khả dụng.
11. RAGFlow chỉ là baseline so sánh bên ngoài, chạy trong môi trường benchmark riêng.
12. P1 không được ảnh hưởng feature freeze và code freeze.

### Kết quả đánh giá

| Khía cạnh | Kết luận |
|---|---|
| Kỹ thuật | Khả thi với kiến trúc monolith, API model, parser chạy CPU và corpus giới hạn |
| Dữ liệu | Khả thi nếu ưu tiên nguồn chính thức, manifest, review thủ công và tuyển chọn PDF có text layer |
| Vận hành | Khả thi với Docker Compose local, background ingestion qua hàng đợi và MinIO |
| Tài chính | Khả thi trong ngân sách mục tiêu 30 USD, dự phòng 40 USD |
| Lịch trình | Khả thi nhưng có rủi ro cao ở parser, legal hierarchy, relation/temporal và evaluation |
| Học thuật | Có đóng góp rõ ở parser routing, legal structure extraction, quan hệ tham chiếu, evidence completeness và verification sáu tầng |

**Quyết định**: **TIẾP TỤC** sang giai đoạn Phân tích và Đặc tả Yêu cầu.

---

## 1.8. Câu hỏi mở (Open Questions)

Các quyết định kiến trúc cốt lõi đã được chốt. Các mục còn lại là quyết định vận hành hoặc thực nghiệm, không làm thay đổi phạm vi nghiên cứu:

1. **Ai thực hiện review corpus cuối cùng?**  
   Mặc định: tác giả review và ghi đầy đủ nguồn, thời điểm, file hash. Nếu có giảng viên hoặc người am hiểu pháp luật hỗ trợ, ghi lại vai trò review trong báo cáo.

2. **Có deploy lên VPS hay không?**  
   Mặc định: local Docker Compose là môi trường bảo vệ chính. VPS chỉ là bản staging bổ sung.

3. **Admin review dùng CLI hay giao diện?**  
   Mặc định: CLI là P0. Review UI là P1.

4. **Reranker có cải thiện kết quả không?**  
   Jina Reranker v3 vẫn là stage chuẩn của pipeline, không phải tùy chọn bỏ qua vì lịch trình; Suite C (R6) đo tác động tăng thêm của reranker trên gold set, nhưng không khẳng định mức cải thiện trước khi chạy thực nghiệm.

5. **Multi-turn có được triển khai không?**  
   Chỉ triển khai sau khi current, historical, comparison và abstention flow đạt acceptance criteria.

6. **Ngưỡng Evidence Completeness Gate là bao nhiêu?**  
   Không đặt con số thành ngưỡng trước thực nghiệm. Threshold ban đầu được xác định từ baseline, sau đó tinh chỉnh trên validation set và khóa trong evaluation config.

7. **MinerU chạy local hay remote?**  
   Quyết định sau Suite A (P2): local dùng pipeline backend CPU; vlm/hybrid không khả thi local nên chỉ qua remote `*-http-client` nếu cần.

8. **RAGFlow baseline chạy variant nào?**  
   Bắt buộc chạy đủ các variant baseline: RAGFlow default, RAGFlow + Docling, RAGFlow + MinerU, so với VNLRAG custom legal-aware pipeline, trên cùng corpus và cùng bộ câu hỏi evaluation. Không lược bớt variant vì RAM. Nếu tài nguyên local không đủ (RAGFlow cần tối thiểu 4 CPU, 16 GB RAM, 50 GB disk), dùng đường khôi phục cụ thể: chạy tuần tự từng variant trong môi trường benchmark riêng, hoặc chạy tuần tự trên máy phù hợp khác, hoặc chia theo batch; mọi variant phải chạy và kết quả được ghi lại đầy đủ.

---

## Nguồn kỹ thuật tham chiếu

1. Docling documentation (IBM):  
   https://docling-project.github.io/docling/

2. MinerU documentation (OpenDataLab):  
   https://opendatalab.github.io/MinerU/

3. Qdrant, Hybrid and Multi-Stage Queries:  
   https://qdrant.tech/documentation/search/hybrid-queries/

4. LangGraph documentation (LangChain):  
   https://docs.langchain.com/oss/python/langgraph/overview

5. Langfuse documentation:  
   https://langfuse.com/docs

6. Jina Embeddings v5 text-small (model hub):  
   https://jina.ai/models/jina-embeddings-v5-text-small/

7. Jina Reranker v3:  
   https://jina.ai/reranker/

8. Google AI for Developers, Gemini 3.5 Flash model documentation:  
   https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash

9. Google AI for Developers, Gemini API pricing:  
   https://ai.google.dev/gemini-api/docs/pricing

10. OpenAI API, GPT-5.4 mini model documentation:  
    https://developers.openai.com/api/docs/models/gpt-5.4-mini

11. Dramatiq documentation:  
    https://dramatiq.io/

12. MinIO documentation:  
    https://docs.min.io/

13. RAGFlow documentation (InfiniFlow):  
    https://ragflow.io/docs/

14. PostgreSQL 18 documentation:  
    https://www.postgresql.org/docs/18/

15. Ragas documentation (VibrantLabs):  
    https://docs.ragas.io/en/stable/

16. Cơ sở dữ liệu quốc gia về văn bản pháp luật:  
    https://vbpl.vn/pages/portal.aspx
