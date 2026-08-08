# 04. Nghiên Cứu Công Nghệ và LLM (Tech Stack and LLM Research)

> **Giai đoạn SDLC**: 3 - Thiết kế  
> **Ngày tạo**: 16/06/2026  
> **Ngày nghiên cứu lại**: 08/08/2026  
> **Hạn hoàn thành**: 12/09/2026  
> **Ngày bảo vệ**: 14/09/2026  
> **Tên đề tài**: Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng  
> **English title**: A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations  
> **Tài liệu quyết định nguồn**: [00-scope-and-decisions.md](00-scope-and-decisions.md)  
> **Tài liệu thiết kế nguồn**: [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md)

---

Tài liệu này là bản nghiên cứu và quyết định công nghệ của VNLRAG v2. Mọi quyết định phải nhất quán với [00-scope-and-decisions.md](00-scope-and-decisions.md) (mục 7, 11, 14) và thiết kế chi tiết [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md) (ADR-001 đến ADR-020). Tài liệu ghi lại phiên bản, khả năng, tài nguyên, chi phí và lý do chọn/bác bỏ từng công nghệ, kèm trạng thái xác minh và URL chính thức.

Quy ước nhãn quyết định dùng trong toàn tài liệu:

```text
selected      công nghệ được chọn cho kiến trúc v2
challenger    công nghệ thay thế/challenger được đánh giá song song
baseline      công nghệ chỉ dùng để so sánh bên ngoài, không phải nền tảng
rejected      công nghệ đã xem xét và bác bỏ, kèm lý do
```

Mọi giá tiền trong tài liệu là đơn giá tham chiếu tại thời điểm cập nhật (2026-07/08), phải kiểm tra lại với tài liệu nhà cung cấp trước khi dùng để ước tính budget. Không có metric nào trong tài liệu này là kết quả đo được; toàn bộ đều là thông số nhà cung cấp công bố hoặc cấu hình khởi điểm.

---

## 4.1. Nguyên tắc lựa chọn công nghệ

Tech stack v2 phải đáp ứng đồng thời các yêu cầu sau:

1. Chạy được trên máy cá nhân: CPU Intel Core i5-1035G1, RAM 19 GB, NVIDIA MX330 2 GB VRAM, NVMe còn trống khoảng 185 GB.
2. GPU local không dùng được cho LLM, embedding hoặc reranker; toàn bộ LLM/embedding/reranker chạy qua API online.
3. Hỗ trợ legal structure-aware và temporal retrieval (Parser Router, Canonical Document IR, Legal Structure Extractor, khoảng hiệu lực [effective_from, effective_to)).
4. Dense và sparse retrieval trong một hệ lưu trữ (Qdrant) thay vì hai hệ tách rời.
5. Buộc LLM trả structured output để citation có thể kiểm chứng (citation-by-ID, Returned Invalid Citation Rate = 0).
6. Cho phép pin model, config, corpus, gold set và experiment (reproducible evaluation).
7. Chạy local bằng Docker Compose trong buổi bảo vệ, không phụ thuộc VPS.
8. Không phụ thuộc open web search hoặc autonomous agent; câu trả lời pháp lý chỉ dựa trên corpus đã kiểm chứng.
9. Giảm số framework trung gian và glue code (không full LangChain, không Haystack, không LlamaIndex trong core).
10. Mọi quyết định về quality (parser, embedding, reranker) phải dựa trên benchmark (Suite A-D), không dựa trên tuyên bố nhà cung cấp.

Nguyên tắc bổ sung theo canonical spec mục 38:

> Chọn công nghệ khi nó trực tiếp giảm code, giảm rủi ro hoặc tạo giá trị nghiên cứu. Không chọn framework chỉ vì phổ biến hoặc có nhiều tính năng ngoài scope. Không thu hẹp phạm vi vì lịch trình. Không tuyên bố kết quả chưa đạt.

Trạng thái xác minh của từng mục trong tài liệu được ghi bằng một trong các mức:

```text
verified      xác minh từ tài liệu chính thức tại ngày nghiên cứu lại
vendor-stated thông số nhà cung cấp công bố, chưa đo độc lập
to-verify     cần xác minh thêm trong quá trình triển khai (ví dụ OCR tiếng Việt, tokenizer)
config-only   giá trị cấu hình khởi điểm, không phải kết quả đo
```

---

## 4.2. Tóm tắt tech stack chốt

Bảng này đồng bộ với mục 7 của doc 00. Mọi khác biệt phải được ghi ADR và cập nhật đồng bộ.

| Thành phần | Công nghệ | Phiên bản / policy | Vai trò | Nhãn |
|---|---|---|---|---|
| Ngôn ngữ | Python | 3.11.x | Backend, ingestion, retrieval, workflow, evaluation | selected |
| Package manager | uv | Pin bằng `uv.lock` | Dependency và virtual environment | selected |
| API | FastAPI | Minor ổn định đã lock | REST API, OpenAPI, validation | selected |
| Workflow | LangGraph | 1.x stable (pin `langgraph>=1.1`) | Controlled workflow orchestration | selected |
| Parser chính | Docling | 2.x line, pin exact | PDF/DOCX/PPTX/XLSX/HTML parse, OCR, hierarchy, provenance | selected |
| Parser phụ / fallback | MinerU | 3.4.x, pipeline backend CPU | Parser thay thế khi quality gate fail | challenger |
| Parser routing | Parser Router | Quy tắc doc 03 mục 3.7 | Chọn parser theo đặc tính tài liệu và quality gate | selected |
| IR trung gian | Canonical Document IR | `document-ir-v1` | Biểu diễn parser-neutral do dự án sở hữu | selected |
| Relational database | PostgreSQL | 18.x (18.4) | Source of truth dữ liệu pháp lý, metadata, relation, version, review, audit | selected |
| ORM | SQLAlchemy | 2.0.x | Persistence và transaction | selected |
| Migration | Alembic | 1.18.x | Database migrations | selected |
| Vector database | Qdrant | v1.19.0 | Dense + sparse + payload filter + RRF fusion, index dẫn xuất | selected |
| Dense embedding | Ứng viên E1/E2/E3 | Chưa chốt vĩnh viễn, chọn sau Suite B | Semantic retrieval | selected (ứng viên) |
| Sparse retrieval | Qdrant sparse BM25 | `qdrant/bm25` hoặc encoder tiếng Việt nếu cần | Lexical retrieval trong cùng collection | selected |
| Fusion | Qdrant RRF | Query API prefetch + fusion, k và weights configurable | Kết hợp dense + sparse | selected |
| Reranker | Jina Reranker v3 | `jina-reranker-v3` (ứng viên chính) | Rerank sau RRF | selected (ứng viên) |
| Generator | Gemini 3.5 Flash | `gemini-3.5-flash` | Structured legal answer theo schema cấp claim | selected |
| Judge độc lập | GPT-5.4 mini | `gpt-5.4-mini-2026-03-17` (snapshot pin) | L5 semantic judge + evaluation metric thứ cấp | selected |
| Evaluation | Ragas | 0.4.x (0.4.3), pin exact | Faithfulness, relevancy, factual correctness (thứ cấp) | selected (thứ cấp) |
| Background jobs | Dramatiq | v2.2.0 | Actor ingestion idempotent, Redis broker | selected |
| Cache / broker | Redis | 8.10.0 | Dramatiq broker + cache | selected |
| Object storage | MinIO | Date-tagged release (AIStor) | PDF nguồn, parser output, artifact review/evaluation | selected |
| Observability | Langfuse | Server v4, SDK v4.x | Trace, prompt management, experiments; ngoài đường tới hạn | selected |
| Frontend | Next.js | 16.x App Router | Chat, search, citation panel | selected |
| UI | React + TypeScript + Tailwind + shadcn/ui | Pin lock file | Giao diện | selected |
| Testing | pytest + Playwright | Pin exact | Unit, integration, E2E | selected |
| Container | Docker + Compose Spec | Pin image tags | Local deployment | selected |
| CI/CD | GitHub Actions | Action SHA hoặc major pin | Automated checks | selected |
| Benchmark platform | RAGFlow | v0.26.x, môi trường benchmark riêng | Baseline so sánh bên ngoài | baseline |

Lưu ý theo doc 00 mục 7:

- Embedding chưa được chốt vĩnh viễn. Gemini Embedding 2 là ứng viên mặc định với cấu hình thử nghiệm 768 chiều (model default là 3072 chiều, 768/1536/3072 là các mức Matryoshka được khuyến nghị), phải benchmark với Jina Embeddings v5 text-nano và text-small trước khi chọn production.
- Reranker chưa được khẳng định cải thiện chất lượng. Jina Reranker v3 là ứng viên chính; không tuyên bố cải thiện trước benchmark.
- Không dùng pgvector trong thiết kế này: vector retrieval nằm trong Qdrant, PostgreSQL giữ metadata và quan hệ pháp lý.
- Trên máy phát triển cá nhân, ingestion chạy với `MAX_INGESTION_WORKERS=1`; toàn bộ LLM, embedding và reranker dùng API online.
- Langfuse Cloud là lựa chọn mặc định cho dev và evaluation; self-hosting là tùy chọn (cần ClickHouse, Redis/Valkey, blob storage, PostgreSQL, web và worker service).

---

## 4.3. Document parser: Docling và MinerU

### 4.3.1. So sánh tổng quan

| Tiêu chí | Docling | MinerU |
|---|---|---|
| Nhãn | selected (chính) | challenger (phụ / fallback) |
| Phiên bản | 2.x line (PyPI `docling` v2.1.x; GitHub releases v2.118.0, cadence cao) | mineru-3.4.4 stable (4.0.0 alpha đang phát triển); dùng 3.4.x |
| Định dạng đầu vào | PDF, DOCX, PPTX, XLSX, HTML, EPUB, images | PDF, image, DOCX, PPTX, XLSX |
| Định dạng đầu ra | `DoclingDocument` (JSON lossless), Markdown, HTML, DocLang | Markdown, JSON |
| Layout analysis | `docling-layout-heron` (RT-DETR based) mặc định; docling-layout-v2 deprecated | DLA + pipeline backend |
| Bảng | TableFormer | Table to HTML, cross-page table merging |
| OCR tiếng Việt | Tesseract (100+ ngôn ngữ, có `vie`), EasyOCR (80+, hỗ trợ `vi`), RapidOCR (PP-OCR v4/v5/v6) | Pipeline OCR 109 ngôn ngữ, tiếng Việt được hỗ trợ; 3.4.x nâng cấp PP-OCRv6 |
| VLM | granite-docling-258M qua OpenAI-compatible server | Backend `vlm`/`*-engine` (MinerU2.5) cần vLLM |
| Tài nguyên | CPU ~2-4 GB RAM điển hình; khuyến nghị 4 threads, 8-16 GB RAM; GPU 1-4 GB VRAM standard | Pipeline: CPU ok, GPU optional min 4 GB VRAM, RAM 16+ (rec 32+), disk 20+ GB; VLM/hybrid cần GPU min 8 GB VRAM |
| Deployment | Python package, CPU/CUDA/MPS/XPU | Docker Linux/WSL2 only (không macOS); hỗ trợ remote `*-http-client` |
| Trạng thái xác minh | verified (tài liệu chính thức) | verified (tài liệu chính thức); OCR tiếng Việt 3.4.x to-verify |

Không parser nào vượt trội tuyệt đối cho mọi trường hợp. Đây là kết luận thiết kế bắt buộc (doc 00 mục 4.1, ADR-002), và là lý do thiết kế Parser Router với quality gate. Kết quả so sánh chi tiết chỉ được ghi sau Suite A (P1-P3).

### 4.3.2. Docling (selected, parser chính)

Docling được chọn làm parser chính vì:

- Hỗ trợ trực tiếp các định dạng chính thức của corpus (PDF, DOCX, PPTX, XLSX, HTML) và images;
- Output `DoclingDocument` lossless JSON export phù hợp để chuyển sang Canonical Document IR;
- Layout analysis (RT-DETR based), table structure (TableFormer), reading order, formulas, code;
- OCR tiếng Việt qua Tesseract `vie`, EasyOCR `vi` hoặc RapidOCR (PP-OCR v4/v5/v6);
- Chạy CPU tốt (2-4 GB RAM điển hình, khuyến nghị 8-16 GB, 4 threads), phù hợp máy cá nhân 19 GB RAM;
- Không yêu cầu GPU; VLM granite-docling-258M là tùy chọn không bắt buộc.

Chunking:

- `HybridChunker` là default: tokenization-aware, `merge_peers`, `repeat_table_header`;
- `HierarchicalChunker` và `LineBasedTokenChunker` là lựa chọn thay thế;
- Phải khớp tokenizer của chunker với tokenizer của embedding production (canonical spec mục 5 liên quan tới chunk boundaries trùng citation boundaries);
- Docling chunker không được dùng làm legal structure parser chính; cấu trúc pháp lý do Legal Structure Extractor của dự án đảm nhiệm (doc 03 mục 3.8).

Lưu ý thay đổi version:

- Dòng 2.x có cadence release rất cao; phải pin exact version tại thời điểm cài đặt, không dùng range mở;
- Layout model mặc định là `docling-layout-heron`; legacy `docling-layout-v2` đã deprecated;
- Vietnamese không nằm trong Nemotron-OCR (chỉ en/zh/ja/ko/ru), nên không dùng Nemotron-OCR cho corpus tiếng Việt.

Tài nguyên theo tài liệu nhà cung cấp:

```text
CPU mode: 2-4 GB RAM typical
Khuyến nghị maintainer: 4 threads, 8-16 GB RAM
GPU: 1-4 GB VRAM standard
```

Đơn vị vận hành (doc 03 mục 3.2.5): chạy local với 4 luồng, theo dõi RAM, `MAX_INGESTION_WORKERS=1`.

### 4.3.3. MinerU (challenger, parser phụ và fallback)

MinerU được chọn làm parser phụ và fallback/challenger. Không phải parser chính vì:

- Pipeline backend cần 16+ GB RAM (khuyến nghị 32+), vượt budget thoải mái trên máy 19 GB;
- Backend `vlm`/`hybrid` yêu cầu GPU min 8 GB VRAM, không khả thi trên MX330 2 GB VRAM;
- Deployment Docker chỉ hỗ trợ Linux/WSL2, không hỗ trợ macOS;
- Dòng 3.4.x: pipeline OCR nâng cấp lên PP-OCRv6 (~+11% accuracy, ~2x speed theo tài liệu), nhưng một số tùy chọn OCR JP/TC/EN/Latin bị loại và routed sang model `ch`; cần xác minh hành vi OCR tiếng Việt trong 3.4.x (to-verify).

Điểm mạnh sử dụng khi cần fallback:

- OCR 109 ngôn ngữ, tiếng Việt được hỗ trợ;
- Formula to LaTeX, tables to HTML, header/footer removal, reading order, cross-page table merging;
- Backend `pipeline` chạy CPU, "no hallucination" theo tài liệu nhà cung cấp (accuracy mặc định 86.47 OmniDocBench, vendor-stated);
- Hỗ trợ remote `*-http-client` (không cần torch local) nếu cần tách host.

Cách chạy thuần CPU:

```text
mineru -p <input> -o <output> -b pipeline
```

Orchestration có sẵn: mineru-api (FastAPI), mineru-router, mineru-gradio, mineru-openai-server, CLI. Port mặc định trong Docker: 30000 (OpenAI server), 7860 (Gradio), 8000 (API), 8002 (router).

### 4.3.4. Parser Router

Parser Router là thiết kế chọn parser theo đặc tính tài liệu và quality gate (doc 03 mục 3.7, ADR-002):

| Đặc tính tài liệu | Quyết định | Fallback |
|---|---|---|
| PDF searchable (có text layer), layout chuẩn | Docling trước | Không cần trừ khi quality gate fail |
| PDF scan hoặc layout lỗi | Docling trước (OCR backend CPU) | MinerU nếu quality gate fail |
| Bảng phức tạp | So sánh đầu ra hai parser khi cần | Chọn theo quality gate hoặc gửi review |
| DOCX/HTML/EPUB | Docling | Không chủ động hỗ trợ trong P0 |

Quality gate chia hai nhóm (parser-level sau IR normalization, structural sau Legal Structure Extractor); khi nhóm structural fail, dữ liệu cũ bị hủy và chạy lại toàn bộ pipeline từ parser thay thế, không trộn kết quả hai parser (doc 03 mục 3.7.3).

Quyết định routing và kết quả quality gate được ghi vào `ingestion_runs.parser_routing` và `DocumentElement.source_parser` để phục vụ Suite A (P1 Docling, P2 MinerU, P3 Parser Router).

### 4.3.5. Trạng thái xác minh

```text
Docling 2.x khả năng và tài nguyên: verified (docling-project.github.io)
MinerU 3.4.x khả năng và tài nguyên: verified (opendatalab.github.io)
OCR tiếng Việt Docling (Tesseract vie / EasyOCR vi / RapidOCR): verified
OCR tiếng Việt MinerU 3.4.x sau khi nâng PP-OCRv6: to-verify trong Suite A
Accuracy pipeline MinerU (86.47 OmniDocBench): vendor-stated, không phải kết quả VNLRAG
```

### 4.3.6. URL chính thức và trích dẫn

```text
Docling:      https://docling-project.github.io/docling/
Docling repo: https://github.com/docling-project/docling
Chunking:     https://docling-project.github.io/docling/concepts/chunking/
Hybrid chunk: https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/

MinerU:       https://opendatalab.github.io/MinerU/
MinerU repo:  https://github.com/opendatalab/MinerU
MinerU Docker:https://opendatalab.github.io/MinerU/quick_start/docker_deployment/
```

Trích dẫn thư mục:

```text
DS4SD / IBM Research (2026). Docling: Get your documents ready for gen AI (v2.x). GitHub.
  https://github.com/docling-project/docling
OpenDataLab (2026). MinerU: High-accuracy document parsing engine (v3.4.x). GitHub.
  https://github.com/opendatalab/MinerU
```

---

## 4.4. LangGraph: controlled workflow orchestration

### 4.4.1. Vai trò và nhãn

```text
Nhãn: selected
Vai trò: lớp điều phối workflow có kiểm soát, không phải agent harness
Phiên bản: langgraph v1.1.x (v1.1.10, 2026-04-27); pin langgraph>=1.1
```

LangGraph là orchestration runtime, không phải agent framework. LangChain phân biệt rõ LangGraph (orchestration runtime) với agents. Trong VNLRAG v2, LangGraph điều phối đồ thị có nhánh xác định trước; LLM không tự chọn tool hoặc tự tạo kế hoạch. Hệ thống không bao giờ được mô tả là autonomous agent (doc 00 mục 1, ADR-016).

### 4.4.2. Khái niệm dùng trong thiết kế

- `StateGraph`: định nghĩa đồ thị từ state schema;
- `state_schema` / `context_schema` / `input_schema` / `output_schema`: khai báo kiểu state, input, output;
- nodes, edges, conditional edges: routing có điều kiện (`check_evidence`, `verify`);
- `Command`: cập nhật state và chọn node tiếp theo (goto/resume);
- checkpointers: `BaseCheckpointSaver`, `InMemorySaver`, SQLite/Postgres checkpointer, phục vụ retry/resume idempotent;
- interrupts: `interrupt()` + `Command(resume=...)` cho cổng chặn human/verifier nếu cần;
- time travel: `get_state_history`, `update_state` phục vụ debug;
- `DeltaChannel` (beta): cho state append-heavy, không bắt buộc.

Yêu cầu phiên bản (theo tài liệu):

```text
langgraph >= 1.1
langchain-core < 2, >= 1.3.0
pydantic >= 2.7.4
```

### 4.4.3. Đồ thị đề xuất (canonical spec mục 21, doc 03 mục 3.2.3)

```text
START -> analyze_query -> resolve_temporal -> expand_query -> retrieve_parallel
     -> fuse -> rerank -> expand_legal_context -> check_evidence
     check_evidence: complete   -> build_context -> generate -> verify
     check_evidence: incomplete -> targeted_retrieval -> check_evidence
     verify -> finalize | repair | abstain -> END
```

Cạnh điều kiện `check_evidence` theo canonical spec mục 21 và doc 03 mục 3.2.3: nếu evidence plan còn thiếu loại bằng chứng bắt buộc (`INCOMPLETE`), workflow chạy `targeted_retrieval` theo `evidence_gaps` rồi quay lại `check_evidence`; chỉ khi `COMPLETE` mới đi tiếp `build_context -> generate`. Mọi lượt quay lại tính vào `repair_attempts` (bounded).

### 4.4.4. Vòng lặp có giới hạn

- Bounded repair loop dùng step-counter trong state (`repair_attempts`) kết hợp conditional edge để dừng;
- `repair_attempts >= max_repair_attempts` (config, khởi điểm 3) -> ABSTAIN;
- Interrupt là phương án thay thế cho cổng chặn human/verifier, không bắt buộc cho P0;
- Checkpointing = retry/resume idempotent khi cần; mọi node thiết kế idempotent (doc 03 mục 3.5.4).

### 4.4.5. Những gì KHÔNG dùng

```text
create_agent
AgentExecutor
ToolNode loop tự do
checkpointer bắt buộc
multi-agent
```

### 4.4.6. Trạng thái xác minh

```text
Version v1.1.10 (2026-04-27): verified (GitHub langchain-ai/langgraph)
v1.1.0 version="v2" type-safe streaming/invoke API (2026-03): verified
Yêu cầu langchain-core <2,>=1.3.0 và pydantic>=2.7.4: verified
Tích hợp Langfuse CallbackHandler: verified (mục 4.5.5)
```

### 4.4.7. URL chính thức và trích dẫn

```text
Overview:    https://docs.langchain.com/oss/python/langgraph/overview
Graph API:   https://docs.langchain.com/oss/python/langgraph/graph-api
Checkpoints: https://docs.langchain.com/oss/python/langgraph/checkpointers
Interrupts:  https://docs.langchain.com/oss/python/langgraph/interrupts
Repo:        https://github.com/langchain-ai/langgraph
```

Trích dẫn thư mục:

```text
LangChain, Inc. (2026). LangGraph: Low-level orchestration framework (Version 1.1.x).
  https://github.com/langchain-ai/langgraph
```

---

## 4.5. Langfuse: observability, prompt management và experiments

### 4.5.1. Vai trò và nhãn

```text
Nhãn: selected
Vai trò: tracing, token usage, cost, latency, prompt versioning, experiments,
         datasets, LLM-as-judge, human annotations, feedback
Phiên bản: Server v4.0.0 (2026-07-29); Python SDK v4.x (OTel-based core, >= 4.7.0)
Cloud mặc định: https://cloud.langfuse.com
```

Langfuse không nằm trên đường tới hạn tính đúng đắn. Ingest bất đồng bộ (batched -> S3 -> worker -> ClickHouse); toàn bộ callback non-mutating; nếu Langfuse không khả dụng, query vẫn hoạt động bình thường (doc 00 mục 4.11, ADR-009). Bật/tắt qua `LANGFUSE_ENABLED`.

### 4.5.2. Tính năng sử dụng

- Tracing: traces/spans/sessions/users/metadata, OpenTelemetry-native;
- Token usage, cost, latency trên từng span;
- Prompt management + versioning: label production/dev, protected labels, caching;
- Experiments & datasets: `run_experiment`;
- LLM-as-judge / evals: observation-level trong v4;
- Human annotations và feedback (đồng bộ với `QueryFeedback` gửi về Langfuse);
- Monitors & alerts (v4).

Trace hierarchy theo doc 03 mục 3.27.2: trace `legal_query` với các span `analyze_query`, `normalize_query`, `rewrite_query`, `hyde`, `exact_lookup`, `dense_retrieval`, `sparse_retrieval`, `rrf_fusion`, `reranker`, `reference_expansion`, `evidence_check`, `generate`, `citation_verify`, `numeric_verify`, `claim_verify`.

### 4.5.3. Prompt management

Prompt được quản lý trong Langfuse với version và label production/dev (doc 03 mục 3.27.3):

```text
legal-query-analyzer-v1
legal-query-rewriter-v1
legal-hyde-generator-v1
legal-generator-v1
legal-claim-support-judge-v1
legal-citation-renderer-v1
```

Prompt version được ghi vào evaluation run (NFR-08) và `QueryTrace.config_snapshot`.

### 4.5.4. Self-hosting (tùy chọn, không phải default)

Self-hosting Langfuse v4 không phải một container đơn:

```text
langfuse app container     +  langfuse worker container
PostgreSQL   (min 15, rec 16)
ClickHouse   (REQUIRED; v4 >= 25.12, rec 26.4; không có thay thế)
Redis/Valkey (min 7.0, rec 7.2)
S3 / blob storage (events, multimodal, exports)
```

Cloud là lựa chọn mặc định cho dev và evaluation (doc 00 mục 7). Self-hosting chỉ cân nhắc khi cần kiểm soát dữ liệu và có đủ tài nguyên; chi phí vận hành ClickHouse + PostgreSQL + Redis + web/worker là đáng kể so với quy mô khóa luận.

### 4.5.5. Tích hợp LangGraph

```python
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()
graph.invoke(input, config={"callbacks": [langfuse_handler]})
# hoặc dùng .with_config({"callbacks": [langfuse_handler]}) khi compile
```

Python SDK: package `langfuse`, singleton qua `get_client()`, decorator `@observe()`, `start_as_current_observation`. SDK hiểu interrupt và checkpoint của LangGraph (fixes trong langfuse-python PR #1632, #1602).

### 4.5.6. Trạng thái xác minh

```text
Server v4.0.0 (2026-07-29): verified (langfuse.com/docs, GitHub)
Python SDK v4.x, OTel-based core, >= 4.7.0 cho v4 server: verified
ClickHouse là yêu cầu bắt buộc cho self-host v4: verified
Tích hợp LangGraph CallbackHandler: verified
Graceful degradation khi Langfuse down: verified (thiết kế, mục 3.27.6 doc 03)
```

### 4.5.7. URL chính thức và trích dẫn

```text
Docs:         https://langfuse.com/docs
Self-hosting: https://langfuse.com/self-hosting
LangChain:    https://langfuse.com/integrations/frameworks/langchain
Repo:         https://github.com/langfuse/langfuse
```

Trích dẫn thư mục:

```text
Langfuse (2026). Langfuse: Open-source LLM engineering platform (Version 4.x).
  https://github.com/langfuse/langfuse
```

---

## 4.6. RAGFlow: baseline so sánh bên ngoài

### 4.6.1. Vai trò và nhãn

```text
Nhãn: baseline (chỉ so sánh bên ngoài, KHÔNG bao giờ là nền tảng chính)
Phiên bản: v0.26.4 (2026-07-07); v0.27.0 đang phát triển
Image: infiniflow/ragflow:v0.26.4 (~2 GB, x86 only, không ARM)
```

RAGFlow là baseline so sánh chất lượng pipeline pháp lý riêng (doc 00 mục 4.12, ADR-010). Nó chạy trong môi trường benchmark riêng, không nằm trong compose production. Kết quả baseline không phải kết quả VNLRAG.

### 4.6.2. Kiến trúc liên quan

- Deep document understanding;
- DeepDoc parser: DLA/OCR/TSR, dịch vụ OSS `deepdoc_oss`, chạy CPU qua ONNX;
- Khả năng do RAGFlow cung cấp (không dùng trong VNLRAG): Agent-based RAG / Agentic RAG;
- Khả năng do RAGFlow cung cấp (không dùng trong VNLRAG): GraphRAG / Knowledge Graph, dùng Elasticsearch hoặc Infinity doc engine;
- Hybrid vector + full-text (khả năng của RAGFlow).

Từ changelog chính thức 2025-10-23: "Supports MinerU & Docling as document parsing methods". Có lựa chọn "Document parser" theo từng dataset. Điều này cho phép chạy ba biến thể parser baseline.

### 4.6.3. Bốn baseline so sánh

```text
B1  RAGFlow default
B2  RAGFlow + Docling (dùng Docling làm parsing method)
B3  RAGFlow + MinerU (dùng MinerU làm parsing method)
B4  VNLRAG custom legal-aware pipeline
```

Tiêu chí so sánh trên cùng corpus và cùng bộ câu hỏi evaluation (doc 03 mục 3.2.5, FR-31):

```text
Recall@10
citation correctness
temporal leakage
evidence completeness
```

### 4.6.4. Yêu cầu tài nguyên (vendor-stated)

```text
Docker Compose: Elasticsearch hoặc Infinity, MySQL, MinIO, Redis, deepdoc OSS
min 4 CPU, 16 GB RAM, 50 GB disk
Docker >= 24, Compose >= 2.26.1, Python >= 3.13
Web port 80; API port 9380
```

Ràng buộc vận hành (doc 03 mục 3.2.5): RAGFlow chạy trong môi trường benchmark riêng, không chạy cùng lúc với ingestion/demo trên máy 19 GB RAM.

### 4.6.5. Trạng thái xác minh

```text
v0.26.4 (2026-07-07): verified (github.com/infiniflow/ragflow)
Hỗ trợ MinerU & Docling làm parsing methods (2025-10-23): verified (changelog chính thức)
Yêu cầu tài nguyên min 4 CPU / 16 GB RAM / 50 GB disk: verified (docs)
Không hỗ trợ ARM: verified
```

### 4.6.6. URL chính thức và trích dẫn

```text
Docs: https://ragflow.io/docs/
Repo: https://github.com/infiniflow/ragflow
```

Trích dẫn thư mục:

```text
InfiniFlow (2026). RAGFlow: An open-source RAG engine (Version 0.26.x).
  https://github.com/infiniflow/ragflow
```

---

## 4.7. Qdrant: retrieval engine

### 4.7.1. Vai trò và nhãn

```text
Nhãn: selected
Phiên bản: v1.19.0 (trước đó 1.18.3, 2026-07-17)
Vai trò: retrieval engine duy nhất, index dẫn xuất dựng lại được từ PostgreSQL
```

Qdrant là index dẫn xuất. PostgreSQL là nguồn chân lý; nếu dữ liệu hai nơi lệch nhau, PostgreSQL thắng (doc 00 mục 8.6, ADR-005). Collection được thiết kế theo doc 03 mục 3.11 (named dense vector + sparse vectors + payload + alias `legal_provisions_active`).

### 4.7.2. Khả năng sử dụng

- Dense + sparse vectors trong cùng collection (multiple named vectors);
- Query API với prefetch + fusion: RRF (k và weights configurable), DBSF;
- Multi-stage queries;
- Payload filters: match, range, MatchText full-text, geo;
- Quantization 4-bit TurboQuant;
- Memory tiers: cold/cached/pinned;
- Snapshots (create + upload/restore) và công cụ `qdrant-migration` (Docker);
- Docker single node: ví dụ `qdrant/qdrant:latest` ở mức minh họa chạy thử; deployment phải pin image tag đã test patch cụ thể (ví dụ `qdrant/qdrant:v1.19.0`), không dùng tag floating.

Các mốc phiên bản:

```text
Query API      từ v1.10
Sparse vectors từ v1.7
Named-vector add/remove lúc runtime từ v1.18.0
RRF k/weights  configurable ở phiên bản hiện tại
```

### 4.7.3. Sparse BM25 và tiếng Việt

- Sparse retrieval dùng tokenizer-based model `Qdrant/bm25`;
- BM25 lexical matching phụ thuộc tokenizer: tiếng Việt chủ yếu tách theo khoảng trắng nhưng có token khác biệt;
- Cần verify tokenizer mặc định trong Suite C (R2) hoặc dùng sparse model/encoder tiếng Việt phù hợp;
- Sparse encoder được version hóa: `sparse_encoder_version` trong payload; thay encoder = rebuild collection + alias switch (doc 03 mục 3.11.2);
- Dense vectors language-agnostic, dùng embedding Vietnamese-capable (mục 4.8).

### 4.7.4. Vì sao không dùng ChromaDB (rejected)

| Tiêu chí | ChromaDB | Qdrant |
|---|---|---|
| Dense vector | Có | Có |
| Sparse vector | Cần hệ riêng | Có named sparse vector cùng collection |
| BM25 | Phải tự viết | Tokenizer-based server-side |
| Fusion | Phải tự viết | Query API RRF/DBSF |
| Payload filter | Hạn chế | Mạnh (match, range, MatchText, geo) |
| Multi-stage query | Không phải điểm mạnh | Query API |
| Concurrency | Single worker khi embedded | Client-server |
| Index versioning | Tự quản lý directory | Collection + alias |

ChromaDB bị bác bỏ: sparse cần hệ tách rời, BM25/fusion viết tay, filter hạn chế, single-worker. Thay thế bởi Qdrant (doc 00 mục 14.2, ADR-005).

### 4.7.5. Vì sao không dùng PostgreSQL + pgvector cho mọi thứ (rejected)

- Dense-only hoặc cần thêm full-text design riêng cho sparse;
- Sparse và fusion phải tự viết (hoặc thêm hệ phụ);
- Multi-stage query phức tạp hơn nhiều SQL;
- Thiết kế v2 tách rõ: PostgreSQL = metadata/relation/version (source of truth), Qdrant = specialized retrieval index;
- pgvector không phải yêu cầu trong thiết kế này (doc 00 mục 7). Không giới thiệu pgvector như dependency.

### 4.7.6. Vì sao không dùng Pinecone / managed vector DB (rejected)

- Phụ thuộc Internet để phục vụ query;
- Chi phí hoặc quota cloud;
- Khó demo offline trong buổi bảo vệ;
- Corpus nhỏ (20-30 văn bản) không cần scale cloud;
- Qdrant local đủ.

### 4.7.7. Trạng thái xác minh

```text
v1.19.0 (2026-07-17): verified (qdrant.tech/documentation)
Query API, sparse vectors, named vectors, RRF weights, DBSF: verified
Snapshots + qdrant-migration tool: verified
Tokenizer BM25 tiếng Việt: to-verify trong Suite C
```

### 4.7.8. URL chính thức và trích dẫn

```text
Documentation:  https://qdrant.tech/documentation/
Hybrid queries: https://qdrant.tech/documentation/search/hybrid-queries/
Vectors:        https://qdrant.tech/documentation/manage-data/vectors/
Snapshots:      https://qdrant.tech/documentation/tutorials-operations/create-snapshot/
```

Trích dẫn thư mục:

```text
Qdrant (2026). Qdrant: AI-native vector database & semantic search engine (v1.19).
  https://qdrant.tech/documentation/
```

---

## 4.8. Dense embedding: ba ứng viên, chưa chốt vĩnh viễn

### 4.8.1. Nguyên tắc

Không có quyết định embedding vĩnh viễn trước khi benchmark (doc 00 mục 7, ADR-013). Đây là quyết định thiết kế bắt buộc: chỉ chọn embedding production sau khi có bằng chứng thực nghiệm từ Suite B.

```text
Tiêu chí Suite B: Recall@10, MRR@10, nDCG@10 trên câu hỏi pháp luật tiếng Việt,
                  latency, cost
Nhãn: selected (nhưng là ứng viên cho tới khi benchmark xong)
```

### 4.8.2. Bảng so sánh ứng viên

| Tiêu chí | E1 Gemini Embedding 2 | E2 Jina v5 text-nano | E3 Jina v5 text-small |
|---|---|---|---|
| Model ID | `gemini-embedding-2` | `jina-embeddings-v5-text-nano` | `jina-embeddings-v5-text-small` |
| Ngày GA / release | GA 2026-04-22 | 2026-02-18 | 2026-02-18 |
| Kiến trúc | Multimodal (text/image/video/audio/PDF) | EuroBERT-210m base | Qwen3-0.6B base |
| Kích thước | - | 239M | 677M |
| Dimensions | 128-3072 (Matryoshka), default 3072, rec 768/1536/3072, auto-normalized | 768 | 1024 |
| Context | 8.192 token | 8K | 32K |
| Ngôn ngữ | 100+ (gồm tiếng Việt) | 15 core languages | 119+ |
| License | API Google | CC BY-NC 4.0 | CC BY-NC 4.0 |
| Giá tham chiếu (2026-07/08) | $0.20/1M text (batch $0.10/1M) | ~$0.05/1M, 10M free | ~$0.05/1M, 10M free |
| MRL / quantization | MRL truncation | MRL truncation + binary quantization | MRL truncation + binary quantization |
| Task-specific | Semantic retrieval dùng prefix khi SDK hỗ trợ | Task LoRA: retrieval (`Query:`/`Document:` prefixes), text-matching, clustering, classification | Như E2 |

Lưu ý:

- Jina Embeddings v5 license CC BY-NC 4.0 (non-commercial); phù hợp cho khóa luận học thuật;
- Model ID chuẩn của Jina v5 không có hậu tố "-base-en";
- Dimension của collection Qdrant phụ thuộc embedding production: nếu chọn text-small (1024 dims) phải tạo collection mới và alias switch (doc 03 mục 3.11.1, ADR-013);
- Cấu hình thử nghiệm mặc định 768 chiều (E1 hoặc E2) để giảm storage và latency, nhưng đây là lựa chọn cấu hình, không phải default dimension của model (gemini-embedding-2 default 3072 chiều); quyết định cuối theo kết quả benchmark.

### 4.8.3. Embedding text

Không embed raw point text đơn thuần. Embedding text gồm (doc 03 mục 4.5.6 của phiên bản cũ được giữ logic trong retrieval design):

```text
Tên văn bản
Số hiệu
Điều / Khoản / Điểm
Parent context (retrieval_text)
Provision text
```

Metadata không đưa vào text: file hash, review status, page number, internal version, source URL dài. Metadata cần thiết nằm trong payload Qdrant, không nằm trong embedding text.

### 4.8.4. Local model embedding: rejected cho v2

`multilingual-e5-small` local là mô hình embedding của thiết kế v1 và được phân loại rejected cho v2:

- Không nằm trong danh sách embedding candidate của Suite B (E1 Gemini Embedding 2, E2 Jina v5 text-nano, E3 Jina v5 text-small theo doc 00 mục 11.2 và ADR-013);
- Không phải production dependency;
- GPU local (MX330 2 GB VRAM) không dùng được cho embedding; chạy embedding local trên CPU cho corpus nhỏ không phải phương án được chọn;
- Việc so sánh "cloud embedding có cải thiện so với model local nhẹ hay không" không nằm trong phương pháp luận evaluation của v2; nếu cần một thí nghiệm phụ thì phải ghi tách riêng và không làm phình Suite B.

### 4.8.5. Trạng thái xác minh

```text
gemini-embedding-2 (GA 2026-04-22), dims 128-3072, ctx 8192, 100+ langs: verified (ai.google.dev)
jina-embeddings-v5-text-nano 239M / 768d / 8K ctx: verified (jina.ai)
jina-embeddings-v5-text-small 677M / 1024d / 32K ctx / 119+ langs: verified (jina.ai)
License CC BY-NC 4.0: verified (model card)
Giá $0.20/1M và ~$0.05/1M: vendor-stated, đơn giá tham chiếu (2026-07/08)
Chất lượng retrieval trên corpus pháp luật tiếng Việt: chưa đo, phải benchmark (Suite B)
```

### 4.8.6. URL chính thức và trích dẫn

```text
Gemini Embedding 2: https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2
Gemini pricing:     https://ai.google.dev/gemini-api/docs/pricing
Jina text-small:    https://jina.ai/models/jina-embeddings-v5-text-small/
Jina text-nano:     https://jina.ai/models/jina-embeddings-v5-text-nano/
HF text-small:      https://huggingface.co/jinaai/jina-embeddings-v5-text-small
```

Trích dẫn thư mục:

```text
Google (2026). Gemini Embedding 2. https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2
Jina AI (2026). jina-embeddings-v5-text-small. Jina AI Model Hub.
  https://jina.ai/models/jina-embeddings-v5-text-small/
```

---

## 4.9. Reranker: Jina Reranker v3 (ứng viên chính)

### 4.9.1. Vai trò và nhãn

```text
Nhãn: selected (stage chuẩn của pipeline, ứng viên chính chưa khẳng định cải thiện)
Model: jina-reranker-v3 (0.6B, Qwen3-0.6B base, listwise "last-but-not-late")
```

Reranking là stage chuẩn của pipeline, không phải future work (doc 00 mục 7, ADR-014). Không tuyên bố reranker cải thiện chất lượng trước khi có kết quả benchmark (Suite C, R6).

### 4.9.2. Đặc điểm model

```text
Context: 131.072 token (query + documents gộp, ~64 docs/pass, auto-truncation)
Ngôn ngữ: 100+ (tiếng Việt OK)
API: POST https://api.jina.ai/v1/rerank
Body: {"model": "jina-reranker-v3", "query": "...", "documents": [...], "top_n": N, "return_documents": true}
```

Reranker mới hơn:

```text
jina-reranker-v3.5: drop-in thay thế, BEIR nDCG-10 63.20 (vendor-stated).
  Được theo dõi, không mặc định dùng nếu chưa benchmark trên corpus VNLRAG.
```

Rate limit và giá (vendor-stated, cấu hình theo deployment, không hardcode theo free-tier):

```text
Free: 100 RPM / 100K TPM
Paid: 500 RPM / 2M TPM
Giá: ~$0.05/1M token; 10M token miễn phí cho API key mới
```

### 4.9.3. Caching và chi phí

- Cache kết quả rerank theo `SHA-256(query + sorted provision_ids)`, TTL ngắn (khớp query trace);
- Chỉ rerank sau fusion_limit candidates, không rerank toàn bộ dense+sparse;
- `top_n` giới hạn theo final_top_k + buffer;
- Token usage và cost ghi vào `QueryTrace`.

### 4.9.4. ColBERT / late-interaction

Late-interaction/ColBERT-style reranking chỉ là ứng viên thí nghiệm (experiment candidate), không phải production candidate trong scope khóa luận (doc 03 mục 3.19.2).

### 4.9.5. Trạng thái xác minh

```text
jina-reranker-v3 0.6B / 131K ctx / 100+ langs: verified (jina.ai, Hugging Face)
API POST /v1/rerank: verified
jina-reranker-v3.5 tồn tại (drop-in): verified; 63.20 BEIR nDCG-10 là vendor-stated
Cải thiện chất lượng trên corpus VNLRAG: chưa đo, phải benchmark (Suite C R6)
```

### 4.9.6. URL chính thức và trích dẫn

```text
Jina Reranker: https://jina.ai/reranker/
HF model:      https://huggingface.co/jinaai/jina-reranker-v3
Paper:         https://arxiv.org/html/2509.25085v3
```

Trích dẫn thư mục:

```text
Jina AI (2025). jina-reranker-v3 - Listwise Multilingual Reranker. Hugging Face.
  https://huggingface.co/jinaai/jina-reranker-v3
```

---

## 4.10. Generator: Gemini 3.5 Flash

### 4.10.1. Vai trò và nhãn

```text
Nhãn: selected
Model: gemini-3.5-flash (GA 2026-05-19, thay gemini-3-flash-preview)
```

Generator chính cho structured answer theo schema cấp claim (doc 03 mục 3.23, ADR-018).

### 4.10.2. Khả năng phù hợp

- Input context 1.048.576 token, output tối đa 65.536 token;
- Structured outputs: `response_format` `json_schema`, tương thích Pydantic;
- Thinking được hỗ trợ;
- Tiếng Việt được hỗ trợ;
- Multimodal (dự án chỉ dùng text input đã retrieve, không gửi PDF trực tiếp cho generator);
- Stable alias; SDK chính thức `google-genai` mới (`from google import genai`), không dùng package cũ `google.generativeai`.

### 4.10.3. Pricing tham chiếu (đơn giá tại thời điểm cập nhật 2026-07/08)

| Loại token | USD / 1M token |
|---|---:|
| Input (context <= 200K) | 1,50 |
| Input (long context) | ~2,70 |
| Output (gồm thinking token) | 9,00 |
| Context caching input | 1 USD / 1M token-hour |

Lưu ý: `gemini-3.6-flash` đã GA với hiệu quả token tốt hơn ($1.50/$7.50 theo đơn giá tham chiếu). Theo đặc tả kiến trúc, VNLRAG báo cáo Gemini 3.5 Flash là generator được chọn; sự tồn tại của 3.6 được ghi nhận như thông tin theo dõi, không tự ý đổi model trong cùng query.

### 4.10.4. Vì sao không dùng model quá lớn (rejected)

Nhiệm vụ generator:

- tuân thủ context;
- trả JSON đúng schema;
- diễn đạt tiếng Việt;
- chọn `provision_id` từ whitelist context.

Không yêu cầu model reasoning đắt nhất. Retrieval và verification quyết định correctness nhiều hơn model size. Model lớn hơn chỉ dùng trong experiment phụ nếu có, không phải dependency production.

### 4.10.5. Vì sao không dùng automatic fallback sang OpenAI (rejected)

Automatic provider fallback bị bác bỏ vì:

- một query có thể chạy model khác mà user không biết;
- evaluation không tái lập;
- prompt và schema behavior khác;
- khó so sánh cost và latency;
- có thể che lỗi provider.

Policy (doc 03 mục 3.23.1):

```text
development:        operator có thể đổi provider bằng config
final evaluation:   pin một generator model, fallback = false
defense:            fallback chỉ bật nếu operator chủ động cấu hình; trace ghi model thực tế
```

### 4.10.6. Vì sao không chọn local LLM (rejected)

Phần cứng: MX330 2 GB VRAM, 19 GB RAM, i5-1035G1. Local LLM bị bác bỏ vì:

- model nhỏ giảm legal reasoning;
- inference chậm;
- structured output kém ổn định;
- chiếm RAM cùng Docling, PostgreSQL, Qdrant, MinIO;
- tăng thời gian setup;
- không phải đóng góp chính của khóa luận.

Local model chỉ được cân nhắc trong future work cho các tác vụ phụ (out-of-scope classifier, reranker nhỏ, query normalization, private deployment study), không phải dependency P0 (doc 03 mục 4.13 của thiết kế cũ được giữ logic tương đương).

### 4.10.7. Trạng thái xác minh

```text
gemini-3.5-flash GA 2026-05-19: verified (ai.google.dev, model card DeepMind)
1M ctx in / 65K out: verified
Structured outputs json_schema + Pydantic compatible: verified
Giá $1.50/$9.00: vendor-stated, đơn giá tham chiếu (2026-07/08)
gemini-3.6-flash GA (token efficiency tốt hơn): verified, theo dõi
```

### 4.10.8. URL chính thức và trích dẫn

```text
Model docs:    https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
Model card:    https://deepmind.google/models/model-cards/gemini-3-5-flash/
Pricing:       https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
```

Trích dẫn thư mục:

```text
Google DeepMind (2026). Gemini 3.5 Flash - Model Card.
  https://deepmind.google/models/model-cards/gemini-3-5-flash/
```

---

## 4.11. Independent judge: GPT-5.4 mini

### 4.11.1. Vai trò và nhãn

```text
Nhãn: selected
Model: gpt-5.4-mini (snapshot gpt-5.4-mini-2026-03-17)
Vai trò: (1) online L5 semantic judge với fail-closed behavior;
         (2) judge cho metric thứ cấp trong evaluation
```

Judge không bao giờ là nguồn sự thật cho metric xác định (citation ID, temporal validity, numeric grounding). Quyết định này nhất quán với doc 03 mục 3.24.2 và ADR-008.

### 4.11.2. Quyết định L5 judge (nhất quán với doc 03)

Doc 03 mục 3.24.2 quyết định: L5 semantic judge được phép chạy online trong verifier với fail-closed behavior:

- Judge timeout (config, khởi điểm 10s) hoặc provider error -> claim được đánh giá `L5_JUDGE_UNAVAILABLE`, xử lý qua repair path có giới hạn; nếu không xác minh được, claim bị loại hoặc dẫn tới ABSTAIN;
- Khi judge online bị tắt bằng config: mọi claim mà deterministic không kết luận được sẽ bị đánh giá fail theo fail-closed (`L5_CLAIM_NOT_SUPPORTED`), không đổi hành vi verified-or-abstain;
- Judge chỉ nhận một claim + các provision được cite, không nhìn answer tổng thể hay gold answer;
- Judge không bao giờ quyết định citation ID hay temporal validity (ADR-008);
- Cả hai chế độ online và evaluation dùng cùng model snapshot pin.

### 4.11.3. Khả năng phù hợp

- Context 400.000 token, max output 128.000;
- Structured Outputs: `json_schema` strict, Pydantic qua SDK;
- Reasoning effort: none/low/medium/high/xhigh;
- Snapshot cố định phục vụ reproducibility;
- Giá thấp hơn model lớn;
- Provider độc lập với generator (mục 4.16).

### 4.11.4. Pricing tham chiếu (đơn giá tại thời điểm cập nhật 2026-07/08)

| Loại token | USD / 1M token |
|---|---:|
| Input | 0,75 |
| Cached input | 0,075 |
| Output | 4,50 |

Các model rẻ hơn được ghi nhận để theo dõi chi phí:

```text
gpt-5.4-nano  ($0.20 / $1.25)
gpt-5.6-luna  ($0.20 / $1.20)
```

### 4.11.5. Judge không phải nguồn sự thật

- Pin snapshot;
- temperature thấp;
- structured rubric;
- lưu raw output;
- chạy subset lặp lại để kiểm tra variance;
- không cho judge xem tên variant;
- không dùng judge để tính citation exact match (deterministic).

### 4.11.6. Trạng thái xác minh

```text
gpt-5.4-mini snapshot 2026-03-17, 400K ctx, Structured Outputs: verified (developers.openai.com)
Giá $0.75/$4.50: vendor-stated, đơn giá tham chiếu (2026-07/08)
Fail-closed behavior online judge: verified (thiết kế doc 03 mục 3.24.2, ADR-008)
```

### 4.11.7. URL chính thức và trích dẫn

```text
Model docs:      https://developers.openai.com/api/docs/models/gpt-5.4-mini
Structured out:  https://developers.openai.com/api/docs/guides/structured-outputs
```

Trích dẫn thư mục:

```text
OpenAI (2026). GPT-5.4 mini - Model documentation. OpenAI API.
  https://developers.openai.com/api/docs/models/gpt-5.4-mini
```

---

## 4.12. PostgreSQL: source of truth

### 4.12.1. Vai trò và nhãn

```text
Nhãn: selected
Phiên bản: 18.x current stable (18.4, 2026-05-14); PostgreSQL 19 đang beta
Vai trò: nguồn chân lý dữ liệu pháp lý
```

PostgreSQL quản lý toàn bộ metadata, phiên bản, quan hệ, review, audit, query trace và feedback (doc 00 mục 8, ADR-006). Qdrant và MinIO không phải nguồn dữ liệu nghiệp vụ chính.

### 4.12.2. Tính năng dùng

- JSONB (indexed, jsonpath) cho manifest, payload, trace metadata;
- Migration bằng Alembic (1.18.x) và SQLAlchemy 2.0.x;
- Exclusion constraints cho temporal intervals: `EXCLUDE USING gist (provision_id WITH =, daterange(effective_from, effective_to, '[)') WITH &&) WHERE (review_status = 'ACCEPTED')` (doc 03 mục 3.10.4) để không có hai version ACCEPTED chồng lấn;
- CHECK constraint interval `[effective_from, effective_to)` và review-required;
- Partial unique index cho unresolved references.

### 4.12.3. Vì sao không dùng SQLite làm database chính (rejected)

- Relations và concurrent access;
- Migration;
- JSONB;
- Interval query (temporal);
- Deployment parity với môi trường production Docker.

SQLite có thể dùng cho unit test nhỏ, nhưng integration test bắt buộc chạy PostgreSQL.

### 4.12.4. pgvector

pgvector v0.8.6 hỗ trợ PostgreSQL 18 (HNSW tối đa 2000 dims). Tuy nhiên thiết kế v2 dùng Qdrant cho vector retrieval; PostgreSQL giữ metadata và quan hệ pháp lý. Không giới thiệu pgvector như yêu cầu (doc 00 mục 7).

### 4.12.5. Trạng thái xác minh

```text
PostgreSQL 18.4 (2026-05-14): verified (postgresql.org/docs/18)
JSONB indexed + jsonpath: verified
Exclusion constraint daterange: verified (thiết kế doc 03, triển khai trong migration)
pgvector không phải yêu cầu: verified (quyết định doc 00 mục 7)
```

### 4.12.6. URL chính thức và trích dẫn

```text
PostgreSQL 18: https://www.postgresql.org/docs/18/
```

Trích dẫn thư mục:

```text
PostgreSQL Global Development Group (2026). PostgreSQL 18 Documentation.
  https://www.postgresql.org/docs/18/
```

---

## 4.13. Redis: broker và cache

### 4.13.1. Vai trò và nhãn

```text
Nhãn: selected
Phiên bản: 8.x (8.10.0 GA 2026-07-29; 8.8.0 2026-05-25)
Vai trò: Dramatiq broker + cache
```

Redis dùng làm broker cho Dramatiq và cache (doc 00 mục 7, ADR-011). Không phải broker duy nhất mạnh nhất; với workload khóa luận (moderate ingestion + cache) Redis đủ. Với yêu cầu durable guaranteed delivery ở quy mô lớn, RabbitMQ mạnh hơn; không cần trong scope.

### 4.13.2. Tính năng mới đáng chú ý

Redis 8.8 bổ sung Array type, INCREX rate limiter, XNACK. Không phụ thuộc tính năng nào trong số này cho P0.

### 4.13.3. Trạng thái xác minh

```text
Redis 8.10.0 GA 2026-07-29: verified (github.com/redis/redis/releases)
Dùng làm Dramatiq broker + cache: verified (thiết kế doc 03 mục 3.13.1)
```

### 4.13.4. URL chính thức và trích dẫn

```text
Releases: https://github.com/redis/redis/releases
Downloads: https://redis.io/downloads/
```

Trích dẫn thư mục:

```text
Redis Ltd. (2026). Redis 8.10.0. GitHub. https://github.com/redis/redis/releases
```

---

## 4.14. Dramatiq: background jobs

### 4.14.1. Vai trò và nhãn

```text
Nhãn: selected
Phiên bản: v2.2.0 (2026-06-17)
Vai trò: background ingestion, actor idempotent, Redis broker
```

Dramatiq chạy worker ingestion phía sau; `POST /documents` trả `202 Accepted` kèm `ingestion_job_id`; không parse PDF đồng bộ trong request handler (doc 03 mục 3.13, ADR-011).

### 4.14.2. Broker và middleware

- Broker: RabbitMQ (recommended theo tài liệu) và Redis out of the box; StubBroker cho test;
- Retries với exponential backoff: default `max_retries=20`, `min_backoff` 15s, `max_backoff` 7 ngày;
- Middleware: TimeLimit, AgeLimit, Pipelines, Callbacks, Results;
- Dead-letter queue ~7 ngày.

Cấu hình khởi điểm cho ingestion (doc 03 mục 3.13.4):

```text
max_retries: 5 (transient error; mặc định 20 có thể quá nhiều cho bước đắt)
min_backoff: 15 giây
max_backoff: 1 giờ
retry condition: chỉ transient (429, 5xx, timeout, connection), không retry validation error
```

### 4.14.3. Gotcha cho ingestion dài

- Actor time limit mặc định 10 phút; phải nâng per actor (parse_actor 1200s, extract_actor 600s, v.v. theo doc 03 mục 3.13.5);
- Mô hình hóa ingestion thành pipeline các actor ngắn, rời rạc, idempotent: parse -> normalize -> extract -> resolve_refs -> resolve_temporal -> quality_gate -> embed -> index;
- Actor idempotent: đọc state job từ PostgreSQL, bỏ qua nếu bước đã hoàn thành;
- Dead-letter giữ message fail sau retry.

### 4.14.4. Vì sao không dùng Celery (rejected)

Celery nặng hơn và cấu hình phức tạp hơn so với nhu cầu khóa luận. Dramatiq đủ: Redis broker, retry, time limit, dead-letter, kết hợp `ingestion_runs` trong PostgreSQL làm state job.

### 4.14.5. Trạng thái xác minh

```text
Dramatiq v2.2.0 (2026-06-17): verified (dramatiq.io, github.com/Bogdanp/dramatiq)
Redis + RabbitMQ + StubBroker: verified
Retries/time limit/dead-letter: verified
Actor time limit mặc định 10 phút: verified; nâng per actor: config-only (doc 03)
```

### 4.14.6. URL chính thức và trích dẫn

```text
Docs: https://dramatiq.io/
Repo: https://github.com/Bogdanp/dramatiq
```

Trích dẫn thư mục:

```text
Bogdan, D. (2026). Dramatiq: Background processing for Python (v2.2.0).
  https://dramatiq.io/
```

---

## 4.15. MinIO: object storage S3-compatible

### 4.15.1. Vai trò và nhãn

```text
Nhãn: selected
Phiên bản: date-tagged community release (AIStor branding)
Vai trò: lưu PDF nguồn, parser output, ảnh trang, artifact ingestion/review/evaluation
```

PostgreSQL lưu object key và metadata; nội dung file nằm trong MinIO (doc 03 mục 3.12, ADR-012). Managed S3 không cần thiết cho khóa luận (chạy local).

### 4.15.2. Tính năng dùng

- Buckets, versioning, tagging;
- ILM: expiry/transition;
- Object Locking WORM: GOVERNANCE/COMPLIANCE + legal hold, yêu cầu versioning, bật tại bucket creation (`mc mb --with-lock`);
- GNU AGPLv3, community edition source-only builds với date-tagged releases (ví dụ RELEASE.2025-05-20T20-30-00Z);
- Docs hiện tại branding "MinIO AIStor".

Layout bucket theo doc 03 mục 3.12.1:

```text
source-pdfs, parser-outputs, page-images, ingestion-artifacts, review-artifacts, evaluation-artifacts
```

### 4.15.3. Backup: tiering KHÔNG phải backup

- ILM/transition chỉ chuyển dữ liệu giữa các tầng trong cùng hệ thống, không thay thế nơi lưu trữ độc lập cho mục đích phục hồi;
- Backup bằng server-side replication (async) hoặc `mc mirror`/`mc cp` sang nơi lưu trữ độc lập (doc 03 mục 3.12.3).

### 4.15.4. Trạng thái xác minh

```text
S3-compatible, GNU AGPLv3, AIStor docs: verified (docs.min.io, github.com/minio/minio)
Versioning, ILM, WORM Object Locking: verified
Tiering không phải backup: verified (tài liệu + thiết kế doc 03)
```

### 4.15.5. URL chính thức và trích dẫn

```text
Docs: https://docs.min.io/
Repo: https://github.com/minio/minio
```

Trích dẫn thư mục:

```text
MinIO, Inc. (2026). MinIO AIStor - S3-compatible object storage. https://docs.min.io/
```

---

## 4.16. Gemini API và OpenAI: độc lập nhà cung cấp

### 4.16.1. Vai trò tách biệt

Cả Gemini API và OpenAI đều được dùng nhưng với vai trò khác nhau:

```text
Generator:  Gemini 3.5 Flash (mục 4.10)
Judge:      GPT-5.4 mini (mục 4.11)
Embedding:  Gemini Embedding 2 (ứng viên) hoặc Jina (ứng viên)
Reranker:   Jina Reranker v3 (ứng viên)
```

### 4.16.2. Lý do provider independence

- Generator và judge độc lập nhà cung cấp: giảm rủi ro cả hai chức năng chính cùng lỗi/quota từ một provider;
- GPT-5.4 mini có hai vai trò (nhất quán doc 03 mục 3.24.2 và ADR-008): (1) online L5 semantic claim-support verifier cho các trường hợp ngữ nghĩa mà deterministic rule không kết luận được, với fail-closed behavior (judge timeout/provider error -> claim `L5_JUDGE_UNAVAILABLE` -> repair path có giới hạn hoặc ABSTAIN); (2) judge cho metric thứ cấp trong evaluation (faithfulness, relevancy, factual correctness);
- Judge không bao giờ là nguồn sự thật cho L2-L4 (citation ID, temporal validity, numeric grounding) hay metric deterministic headline; do đó không tạo dependency correctness vào OpenAI cho generation;
- Cho phép thay đổi từng vai trò độc lập nếu giá, chất lượng hoặc policy thay đổi;
- Structured outputs của cả hai provider đều tương thích Pydantic nên adapter chỉ gồm mapping response -> domain model.

### 4.16.3. Nguyên tắc vận hành

- Không có automatic fallback giữa provider trong final evaluation (mục 4.10.5);
- Trace ghi model thực tế cho từng span (Langfuse);
- Provider data disclosure: câu hỏi + context pháp lý (không PII) tới generator/judge/embedding/reranker (doc 03 mục 3.31.6).

---

## 4.17. Ragas: evaluation framework (thứ cấp)

### 4.17.1. Vai trò và nhãn

```text
Nhãn: selected (thứ cấp)
Phiên bản: v0.4.3 (2026-01-13), repo vibrantlabsai/ragas (trước là explodinggradients)
Vai trò: metric ngữ nghĩa phụ; deterministic metrics vẫn là headline
```

Ragas dùng cho Faithfulness, Response Relevancy, Factual Correctness khi cần (doc 00 mục 11.4). Headline result của VNLRAG không phụ thuộc Ragas hay judge.

### 4.17.2. Metric và custom metric

Các metric Ragas:

```text
Faithfulness                 (response vs retrieved context)
Response Relevancy           (answer_relevance)
Context Precision / Recall   (LLM-based; variant non-LLM Levenshtein và ID-based)
Context Entities Recall
Context Utilization
Factual Correctness          (claims-based P/R/F1; mode/atomicity/coverage params)
Semantic Similarity
Answer Accuracy
Non-LLM String Similarity    (Rouge/BLEU)
General: AspectCritic, DiscreteMetric, rubric scoring
```

Custom metric:

```text
DiscreteMetric / AspectCritic
hoặc subclass MetricWithLLM / SingleTurnMetric / MultiTurnMetric với PydanticPrompt
```

Lưu ý API:

```text
LEGACY metrics API deprecated trong v0.4, sẽ bị xóa trong v1.0
Bắt buộc dùng collections-based API theo version đã pin
Ví dụ: from ragas.metrics.collections import Faithfulness (xác nhận theo lock version)
```

Judge pluggable: gpt-5.4-mini, Gemini đều dùng được.

### 4.17.3. Deterministic metrics là headline

Toàn bộ metric deterministic (Recall@k, MRR, nDCG, citation P/R/F1, Invalid Citation Rate, Temporal Validity Accuracy, evidence metrics, corpus metrics, abstention P/R/F1) tự triển khai bằng Python, không cần LLM call (doc 03 mục 3.9.13). Ragas chỉ bổ sung metric ngữ nghĩa thứ cấp.

### 4.17.4. Trạng thái xác minh

```text
Ragas v0.4.3 (2026-01-13): verified (docs.ragas.io, github.com/vibrantlabsai/ragas)
Repo chuyển sang vibrantlabsai/ragas: verified
LEGACY API deprecated v0.4, xóa v1.0: verified
Chi tiết metric cụ thể theo lock version: verified (phải xác nhận tại setup)
```

### 4.17.5. URL chính thức và trích dẫn

```text
Docs: https://docs.ragas.io/en/stable/
Repo: https://github.com/vibrantlabsai/ragas
```

Trích dẫn thư mục:

```text
VibrantLabs (2026). Ragas: Evaluation framework (v0.4.3). https://docs.ragas.io/
```

---

## 4.18. Các lựa chọn khác

### 4.18.1. Next.js (frontend)

```text
Nhãn: selected
Phiên bản: 16.x App Router
```

Next.js 16 thay Next.js 14 vì App Router, React 19.2, TypeScript-first, Turbopack stable, documentation hiện hành, dễ build citation panel và server/client boundaries. Minimum runtime: Node.js 20.9+, TypeScript 5.1+. Dùng Node LTS. Next.js không phải backend chính; FastAPI giữ vai trò application backend, Next.js chỉ render UI và gọi FastAPI (doc 03 mục 3.29).

State management: ưu tiên React state, server/client components, TanStack Query nếu cần cache request, URL search params cho filter. Không mặc định thêm Zustand.

UI streaming: không stream raw answer token; hiển thị progress events và render final response sau verification (FR-32, NFR-10).

### 4.18.2. FastAPI (backend)

```text
Nhãn: selected
```

FastAPI: Pydantic request/response, OpenAPI, dependency injection, async I/O, multipart upload, test bằng HTTPX. Pin exact patch bằng lock file. Router không chứa business logic (SQL, Qdrant query, prompt, citation validation) theo doc 03 mục 3.28. CPU-heavy parsing không chạy trực tiếp trong async event loop (qua Dramatiq worker).

### 4.18.3. uv (package management)

```text
Nhãn: selected
```

uv quản lý dependency và virtual environment, pin bằng `uv.lock`. Mọi version trong `pyproject.toml` là range định hướng; lock file là nguồn version chính xác (doc 03 mục 4.15 của thiết kế cũ, giữ nguyên policy).

### 4.18.4. pytest + Playwright (testing)

```text
Nhãn: selected
```

pytest cho unit/integration, Playwright cho E2E. Integration test bắt buộc chạy PostgreSQL và Qdrant (testcontainers), không dùng SQLite thay thế (doc 03 mục 4.8.4).

### 4.18.5. GitHub Actions (CI/CD)

```text
Nhãn: selected
```

Jobs: backend-quality, backend-unit, backend-integration, retrieval-regression, frontend-quality, frontend-e2e-smoke, docker-build, docs-build. Actions pin bằng commit SHA hoặc trusted major version. CI không chạy full LLM evaluation trên mọi PR (tốn tiền, chậm, provider nondeterminism); full evaluation chạy manual workflow / feature freeze / release candidate.

### 4.18.6. Docker Compose (deployment)

```text
Nhãn: selected
```

Compose production: frontend, backend, worker, PostgreSQL, Qdrant, Redis, MinIO. Provider bên ngoài tùy chọn: Langfuse Cloud, Gemini API, OpenAI API, Jina API. RAGFlow trong môi trường benchmark riêng. Không dùng floating tags (`latest`, `alpine`, `main`) cho production compose; pin image tag đã test.

### 4.18.7. Vì sao không dùng full LangChain (rejected)

Thiết kế chỉ cần:

```text
langgraph
langchain-core (nếu LangGraph yêu cầu, < 2, >= 1.3.0)
google-genai
openai
qdrant-client
```

Không cần chain abstraction, retriever wrapper, agent executor. Provider SDK chính thức hỗ trợ structured output; retrieval viết trực tiếp bằng Qdrant client; prompt và schema do application kiểm soát. Giảm lớp adapter và lỗi version conflict.

### 4.18.8. Vì sao không dùng Haystack hoặc LlamaIndex cho core (rejected)

Haystack và LlamaIndex có integration tốt với Docling và vector database, nhưng thêm framework RAG sẽ tạo:

- document model thứ ba bên cạnh Canonical Document IR và LegalProvision;
- wrapper retrieval thừa;
- config phân tán;
- khó instrument experiment Suite A-D;
- khó kiểm soát citation ID;
- thêm dependency upgrade risk.

Có thể dùng trong future work làm baseline độc lập, không dùng trong implementation chính (doc 03 mục 4.3.2 của thiết kế cũ, giữ nguyên quyết định).

### 4.18.9. Dependency bị loại khỏi core

```text
langchain (full), langchain-google-genai, langchain-openai, langchain-chroma
chromadb, rank-bm25, pyvi (bắt buộc), duckduckgo-search, serpapi
sentence-transformers (production dependency), celery
```

Một số dependency có thể tồn tại gián tiếp qua tooling nhưng backend không import trực tiếp.

---

## 4.19. Tóm tắt quyết định

| Công nghệ | Quyết định | Nhãn | Lý do tóm tắt |
|---|---|---|---|
| Docling 2.x | Parser chính | selected | Layout/table/OCR tiếng Việt, chạy CPU 2-4 GB RAM, output lossless JSON |
| MinerU 3.4.x | Parser phụ / fallback | challenger | OCR 109 ngôn ngữ, pipeline CPU ok nhưng RAM 16+ GB, VLM/hybrid không khả thi local |
| Parser Router | Routing parser + quality gate | selected | Không parser nào vượt trội tuyệt đối; quyết định theo đặc tính tài liệu |
| Canonical Document IR | IR parser-neutral | selected | Cô lập legal parsing khỏi định dạng parser; đổi parser chỉ cần adapter |
| LangGraph 1.1.x | Controlled workflow | selected | Orchestration runtime, vòng lặp có giới hạn, checkpointing; không phải agent |
| Langfuse v4 | Observability + prompt mgmt | selected | Trace, prompt version, experiment; ngoài đường tới hạn; self-host cần ClickHouse |
| RAGFlow v0.26.x | Baseline bên ngoài | baseline | So sánh Recall@10, citation, temporal, evidence; môi trường benchmark riêng |
| Qdrant v1.19 | Retrieval engine | selected | Dense + sparse + RRF trong một hệ; index dẫn xuất dựng lại từ PostgreSQL |
| ChromaDB | - | rejected | Sparse cần hệ riêng, BM25/fusion viết tay, filter hạn chế, single-worker |
| PostgreSQL + pgvector | - | rejected | Dense-only hoặc phải tự viết sparse/fusion; PostgreSQL giữ metadata, Qdrant giữ vector |
| Pinecone / managed | - | rejected | Phụ thuộc Internet, chi phí, khó demo offline, không cần scale |
| Gemini Embedding 2 | Ứng viên E1 (mặc định 3072 chiều; cấu hình thử nghiệm 768 chiều) | selected (ứng viên) | Multimodal, 100+ langs, $0.20/1M; chưa chốt vĩnh viễn trước Suite B |
| Jina v5 text-nano | Ứng viên E2 | selected (ứng viên) | 768d, 8K ctx, CC BY-NC 4.0, ~$0.05/1M |
| Jina v5 text-small | Ứng viên E3 | selected (ứng viên) | 1024d, 32K ctx, 119+ langs; cần collection 1024d nếu được chọn |
| Jina Reranker v3 | Reranker chính | selected (ứng viên) | 131K ctx, 100+ langs; chưa khẳng định cải thiện trước Suite C R6 |
| ColBERT / late-interaction | Reranker thí nghiệm | challenger (experiment) | Chỉ dùng làm experiment candidate, không phải lựa chọn production |
| Gemini 3.5 Flash | Generator | selected | Structured output, tiếng Việt, 1M ctx, SDK ổn định, $1.50/$9.00 |
| GPT-5.4 mini | Judge độc lập | selected | Online L5 semantic verifier fail-closed + metric thứ cấp; không phải nguồn sự thật cho L2-L4 hay metric deterministic |
| PostgreSQL 18 | Source of truth | selected | JSONB, migration, exclusion constraint temporal, relations, audit |
| SQLite | - | rejected | Thiếu relation/concurrency/migration/JSONB/interval query/deployment parity |
| Redis 8.10 | Broker + cache | selected | Dramatiq broker + cache; đủ cho quy mô khóa luận |
| Dramatiq v2.2 | Background jobs | selected | Actor idempotent, retry, time limit, dead-letter; ingestion không đồng bộ |
| Celery | - | rejected | Nặng hơn, cấu hình phức tạp hơn nhu cầu |
| MinIO | Object storage | selected | S3-compatible local; tiering không phải backup |
| Ragas v0.4.3 | Evaluation thứ cấp | selected (thứ cấp) | Metric ngữ nghĩa phụ; deterministic là headline |
| Next.js 16 | Frontend | selected | App Router, React 19.2; không phải backend chính |
| FastAPI | Backend | selected | Pydantic, OpenAPI, async I/O |
| uv | Package management | selected | Lock file, dependency và virtual environment |
| pytest + Playwright | Testing | selected | Unit/integration/E2E |
| GitHub Actions | CI/CD | selected | Automated checks; CI không chạy full LLM evaluation |
| Docker Compose | Deployment | selected | Local-first defense; pin image tags |
| Full LangChain | - | rejected | Chỉ cần langgraph + langchain-core; giảm adapter |
| Haystack / LlamaIndex | - | rejected | Framework RAG thừa cho core; future work baseline nếu cần |

---

## 4.20. So sánh kiến trúc cũ và mới

Bảng này chỉ dùng để ghi nhận lịch sử chuyển đổi từ thiết kế v1 (UDEF-based) sang v2. UDEF và các thành phần cũ không còn áp dụng; tham chiếu tới doc 03 mục 3.35 và doc 00 mục 5, 14.

| Thành phần | Thiết kế cũ (v1) | Thiết kế mới (v2) | Nhãn v2 |
|---|---|---|---|
| Tên hệ thống | Agentic RAG | Structure-aware Temporal RAG | historical/replaced |
| Ingestion | PDF -> UDEF -> Docling -> CDM | PDF -> Parser Router -> Docling/MinerU -> Canonical Document IR | rejected (v1) |
| Extraction framework | UDEF + traffic_law RuleSpec | Legal Structure Extractor do dự án sở hữu | rejected (v1) |
| Dense embedding | multilingual-e5-small local | Ba ứng viên E1/E2/E3 chưa chốt; Suite B chạy trước khi chọn; cấu hình thử nghiệm 768 chiều | rejected (v1) |
| Vector store | ChromaDB | Qdrant | rejected (v1) |
| Sparse retrieval | rank-bm25 pickle + PyVi | Qdrant sparse BM25 | rejected (v1) |
| Fusion | Custom Python RRF | Qdrant Query API RRF (k, weights configurable) | rejected (v1) |
| Metadata DB | SQLite | PostgreSQL | rejected (v1) |
| Workflow | Rewrite-grade web loop | Controlled temporal routing (LangGraph) | rejected (v1) |
| Web search | DuckDuckGo / SerpAPI fallback | Không có trong answer path | rejected (v1) |
| HITL | Query-time, sau đó defer | Ingestion-time review | rejected (v1) |
| Citation | Free text + regex | Provision ID + database rendering | rejected (v1) |
| Generator | Gemini 2.5 Flash | Gemini 3.5 Flash | historical/replaced |
| Judge | GPT-4o-mini | GPT-5.4 mini snapshot | historical/replaced |
| Reranker | Không có stage riêng | Jina Reranker v3 (stage chuẩn) | selected (mới) |
| Background jobs | Không rõ ràng (đồng bộ hoặc ad hoc) | Redis + Dramatiq actor pipeline | selected (mới) |
| Object storage | Không có | MinIO (S3-compatible) | selected (mới) |
| Observability | Không có hoặc log thủ công | Langfuse trace toàn pipeline | selected (mới) |
| Streaming | Token buffer-validate-stream | Progress events + verified final | selected (mới) |
| Frontend | Next.js 14 | Next.js 16 | historical/replaced |
| Evaluation | V1-V6 variants, custom RAGAS-lite | Suites A-D (P1-P3, E1-E3, R1-R10, G1-G7) | historical/replaced |
| Gold set | 100-150 câu | 200 câu (40 dev / 40 validation / 120 final test) | historical/replaced |
| Deploy | Chroma volume + SQLite | PostgreSQL + Qdrant + MinIO + Redis | rejected (v1) |

Quy ước cột "Nhãn v2" áp dụng cho thành phần cột "Thiết kế cũ (v1)": `rejected (v1)` = thành phần cũ bị loại bỏ và thay thế trong v2; `historical/replaced` = phiên bản cũ bị thay thế bằng phiên bản mới tương đương; `selected (mới)` = thành phần mới được bổ sung trong v2 (không tồn tại ở v1). Quy ước này nhất quán với hệ nhãn selected/challenger/baseline/rejected ở mục 4.1.

Ghi chú lịch sử ngắn: thiết kế v1 dựa trên UDEF với pipeline `PDF -> UDEF -> Docling -> CDM`. V2 loại bỏ hoàn toàn UDEF vì tầng chuyển đổi không cần thiết, domain pack không thiết kế cho phân cấp pháp luật Việt Nam, và lớp confidence/validation do quality gate + review routing của dự án đảm nhận tốt hơn (doc 00 mục 5, ADR-001). Thuật ngữ UDEF chỉ xuất hiện trong tài liệu này ở bảng mapping và ghi chú lịch sử.

---

## 4.21. Rủi ro công nghệ

| ID | Rủi ro | Biện pháp |
|---|---|---|
| T1 | Parser version drift: Docling 2.x cadence cao, MinerU 3.4.x thay đổi OCR, output thay đổi giữa các release | Pin exact version tại install; Document IR schema version; golden fixtures regression (Suite A); ghi parser_version vào element/provision |
| T2 | MinerU OCR tiếng Việt sau khi nâng PP-OCRv6 có hành vi khác (một số OCR options routed sang model khác) | Xác minh trong Suite A (P2); nếu fail, dùng Docling OCR hoặc remote `*-http-client`; không trộn kết quả hai parser |
| T3 | Embedding model change sau Suite B: dimension và quality khác | Collection mới + rebuild từ PostgreSQL + alias switch (doc 03 mục 3.11.7); không trộn hai embedding space |
| T4 | Judge drift: GPT-5.4 mini snapshot hoặc policy thay đổi | Pin snapshot `gpt-5.4-mini-2026-03-17`; judge là nguồn thứ cấp; deterministic là headline; lưu raw output |
| T5 | Qdrant version: API hoặc weighted RRF thay đổi | Pin Qdrant image tag; regression retrieval; default unweighted RRF; weighted RRF chỉ khi tune trên validation |
| T6 | RAM pressure: Docling + PostgreSQL + Qdrant + MinIO + backend trên 19 GB | `MAX_INGESTION_WORKERS=1`; giới hạn bộ nhớ Docker theo service; theo dõi `docker stats`; không chạy ingestion song song demo/eval |
| T7 | MinerU pipeline backend RAM 16+ GB vượt budget máy 19 GB | Chỉ dùng pipeline CPU; nếu đo vượt budget, chuyển remote `*-http-client`/dedicated host (ADR-002, doc 03 mục 3.2.5) |
| T8 | API cost vượt dự kiến (generator, judge, embedding, reranker) | Budget target <= 30 USD, reserve max 40 USD; dry-run estimate; token cap; cache rerank; không gọi generator cho retrieval-only evaluation; Batch API nếu phù hợp; ghi token usage |
| T9 | Langfuse availability: cloud down hoặc quota | Không nằm trên đường tới hạn; ingest bất đồng bộ; `LANGFUSE_ENABLED=false` chuyển sang không trace |
| T10 | RAGFlow RAM competition khi benchmark | Chạy trong môi trường benchmark riêng, không cùng lúc ingestion/demo; min 4 CPU, 16 GB RAM, 50 GB disk (doc 03 mục 3.2.5) |
| T11 | Provider structured output vẫn fail | Pydantic validation (L1), repair path regenerate có giới hạn, ABSTAIN sau `MAX_REPAIR_ATTEMPTS` |
| T12 | Ragas API thay đổi (legacy deprecated, v1.0 xóa) | Pin 0.4.x; dùng collections-based API; wrapper nội bộ |
| T13 | Reranker/embedding quality chưa được chứng minh | Benchmark Suite B/C; không tuyên bố cải thiện trước khi có kết quả |
| T14 | Next.js 16 breaking behavior | App Router theo current docs; lock dependency; Node LTS |
| T15 | Redis/Dramatiq job mất sau crash | Actor idempotent + state job trong PostgreSQL; retry transient; dead-letter giám sát; reconcile_index |
| T16 | MinIO dữ liệu hỏng | Backup bằng replication/`mc mirror` sang nơi lưu trữ độc lập; tiering không phải backup; PostgreSQL lưu object key + hash |

---

## 4.22. Nguồn chính thức

Các URL trong phần công nghệ chính (Google, OpenAI, Docling, MinerU, Qdrant, LangGraph, Langfuse, RAGFlow, Jina, PostgreSQL, Dramatiq, Redis, MinIO, Ragas) đã được xác minh trong quá trình nghiên cứu lại (08/08/2026) từ tài liệu chính thức của nhà cung cấp, theo research brief. Các URL FastAPI, SQLAlchemy, Alembic và Next.js chưa được xác minh lại trong đợt nghiên cứu này (không nằm trong research brief) và được giữ làm tham chiếu chung. Không dùng blog làm nguồn chính cho quyết định.

### Google (Gemini)

```text
Gemini 3.5 Flash:          https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash
Gemini 3.5 Flash model card: https://deepmind.google/models/model-cards/gemini-3-5-flash/
Gemini Embedding 2:        https://ai.google.dev/gemini-api/docs/models/gemini-embedding-2
Gemini API pricing:        https://ai.google.dev/gemini-api/docs/pricing
Gemini enterprise pricing: https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
```

### OpenAI

```text
GPT-5.4 mini:              https://developers.openai.com/api/docs/models/gpt-5.4-mini
Structured Outputs:        https://developers.openai.com/api/docs/guides/structured-outputs
```

### Docling (IBM Research)

```text
Documentation:             https://docling-project.github.io/docling/
Repo:                      https://github.com/docling-project/docling
Chunking concepts:         https://docling-project.github.io/docling/concepts/chunking/
Hybrid chunking example:   https://docling-project.github.io/docling/_generated/examples/hybrid_chunking/
```

### MinerU (OpenDataLab / Shanghai AI Lab)

```text
Documentation:             https://opendatalab.github.io/MinerU/
Repo:                      https://github.com/opendatalab/MinerU
Docker deployment:         https://opendatalab.github.io/MinerU/quick_start/docker_deployment/
```

### Qdrant

```text
Documentation:             https://qdrant.tech/documentation/
Hybrid queries:            https://qdrant.tech/documentation/search/hybrid-queries/
Sparse/named vectors:      https://qdrant.tech/documentation/manage-data/vectors/
Snapshots:                 https://qdrant.tech/documentation/tutorials-operations/create-snapshot/
```

### LangGraph (LangChain)

```text
Overview:                  https://docs.langchain.com/oss/python/langgraph/overview
Quickstart:                https://docs.langchain.com/oss/python/langgraph/quickstart
Graph API:                 https://docs.langchain.com/oss/python/langgraph/graph-api
Checkpointers:             https://docs.langchain.com/oss/python/langgraph/checkpointers
Interrupts:                https://docs.langchain.com/oss/python/langgraph/interrupts
Repo:                      https://github.com/langchain-ai/langgraph
```

### Langfuse

```text
Docs:                      https://langfuse.com/docs
Self-hosting:              https://langfuse.com/self-hosting
LangChain integration:     https://langfuse.com/integrations/frameworks/langchain
Repo:                      https://github.com/langfuse/langfuse
```

### RAGFlow (InfiniFlow)

```text
Docs:                      https://ragflow.io/docs/
Repo:                      https://github.com/infiniflow/ragflow
```

### Jina AI

```text
Jina Reranker:             https://jina.ai/reranker/
jina-reranker-v3 (HF):     https://huggingface.co/jinaai/jina-reranker-v3
Reranker paper:            https://arxiv.org/html/2509.25085v3
jina-embeddings-v5-text-small: https://jina.ai/models/jina-embeddings-v5-text-small/
jina-embeddings-v5-text-nano:  https://jina.ai/models/jina-embeddings-v5-text-nano/
text-small (HF):           https://huggingface.co/jinaai/jina-embeddings-v5-text-small
```

### PostgreSQL

```text
PostgreSQL 18:             https://www.postgresql.org/docs/18/
```

### Dramatiq

```text
Docs:                      https://dramatiq.io/
Repo:                      https://github.com/Bogdanp/dramatiq
```

### Redis

```text
Releases:                  https://github.com/redis/redis/releases
Downloads:                 https://redis.io/downloads/
```

### MinIO

```text
Docs:                      https://docs.min.io/
Repo:                      https://github.com/minio/minio
```

### Ragas (VibrantLabs)

```text
Docs:                      https://docs.ragas.io/en/stable/
Repo:                      https://github.com/vibrantlabsai/ragas
```

### Backend và hạ tầng khác

```text
FastAPI release notes:     https://fastapi.tiangolo.com/release-notes/
SQLAlchemy 2.0:            https://docs.sqlalchemy.org/en/20/
Alembic:                   https://alembic.sqlalchemy.org/en/latest/
```

### Frontend

```text
Next.js 16:                https://nextjs.org/blog/next-16
Next.js App Router:        https://nextjs.org/docs/app
```

---

## 4.23. Tổng kết

Tài liệu này chốt tech stack v2 với các nhãn selected/challenger/baseline/rejected cho từng quyết định:

- Parser: Docling selected (chính) + MinerU challenger (phụ/fallback) qua Parser Router; không khẳng định parser nào vượt trội tuyệt đối trước Suite A.
- Workflow: LangGraph selected, controlled workflow, không phải agent harness.
- Observability: Langfuse selected, ngoài đường tới hạn; self-host là tùy chọn (ClickHouse bắt buộc).
- Baseline: RAGFlow chỉ là external baseline, môi trường benchmark riêng.
- Retrieval: Qdrant selected (dense + sparse + RRF); ChromaDB, pgvector-only, Pinecone rejected.
- Embedding: E1/E2/E3 là ứng viên, chưa chốt vĩnh viễn trước Suite B; cấu hình thử nghiệm mặc định 768 chiều (gemini-embedding-2 model default là 3072 chiều).
- Reranker: Jina Reranker v3 là ứng viên chính; ColBERT chỉ experiment; chưa tuyên bố cải thiện.
- Generator: Gemini 3.5 Flash selected; automatic fallback, local LLM, model quá lớn rejected.
- Judge: GPT-5.4 mini selected; online L5 semantic judge với fail-closed behavior (nhất quán doc 03); judge không bao giờ là nguồn sự thật cho metric xác định.
- Hạ tầng: PostgreSQL source of truth, Redis broker/cache, Dramatiq background jobs, MinIO object storage.
- Evaluation: deterministic metrics headline, Ragas thứ cấp.
- Khác: Next.js, FastAPI, uv, pytest/Playwright, GitHub Actions, Docker Compose; full LangChain/Haystack/LlamaIndex rejected cho core.

Mọi giá tiền là đơn giá tham chiếu tại thời điểm cập nhật (2026-07/08); mọi thông số chất lượng chưa đo phải được xác nhận bằng benchmark Suite A-D trước khi đưa vào báo cáo. Kết quả thực nghiệm chỉ được ghi sau khi chạy evaluation theo doc 00 mục 11 và doc 06.
