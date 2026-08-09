# ARCHITECTURE — Kiến Trúc Hệ Thống VNLRAG v2

Tài liệu này mô tả kiến trúc tổng quan của hệ thống VN Traffic Law RAG (bản thiết kế lại v2) ở mức đủ để triển khai theo phạm vi đã đóng băng tại M0 — Scope Freeze 19/07/2026 (xem [SCOPE.md](SCOPE.md)). Chi tiết thiết kế nằm ở `docs/03-thiet-ke-he-thong.md` và `docs/04-tech-stack-llm-research.md`.

## Tổng quan

Hệ thống là một RAG pipeline **nhận biết cấu trúc và thời gian hiệu lực** cho pháp luật giao thông Việt Nam: tài liệu nguồn được phân tích cấu trúc pháp lý, lưu trữ trong PostgreSQL (nguồn chân lý), tạo index retrieval dẫn xuất trong Qdrant, và câu hỏi được trả lời theo workflow có kiểm soát với trích dẫn `provision_id` được verify, verified-or-abstain.

Luồng xử lý chính:

- **Offline ingestion**: Nguồn văn bản chính thống → Source Registry và Corpus Manifest → Ingestion Queue (Redis + Dramatiq) → Parser Router (Docling | MinerU) → Canonical Document IR → Legal Structure Extractor → Legal Context Enricher → Legal Reference Resolver → Temporal and Amendment Resolver → Quality Gates → Human Review → PostgreSQL → Embedding and Sparse Indexing → Qdrant (index dẫn xuất).
- **Online query**: Câu hỏi người dùng → Query Understanding (intent, query_date, evidence plan) → Temporal Resolution → Query Expansion (original | normalized | multi-query rewrite | conditional HyDE) → Parallel Multi-Recall (exact legal lookup | dense | sparse BM25) → RRF Fusion → Reranking → Legal Context Expansion (parent | sibling | cross-reference | penalty companion) → Evidence Completeness Gate → Context Builder → Structured Answer Generator → Verification (schema, citation ID, temporal, numeric grounding, claim support, evidence completeness) → Verified Answer | Abstention.
- **LangGraph controlled workflow** điều phối nhánh xác định trước: `START → analyze_query → resolve_temporal → expand_query → retrieve_parallel → fuse → rerank → expand_legal_context → check_evidence → build_context → generate → verify → finalize | repair | abstain → END`, với vòng repair có giới hạn (`MAX_REPAIR_ATTEMPTS`) trước khi ABSTAIN.

## Sơ đồ thành phần

- **FastAPI app** — REST API (chat, search, documents, jobs, reviews, feedback, health, evaluation, corpus-qa), OpenAPI, validation bằng Pydantic v2.
- **Parser Router** — chọn parser theo đặc tính tài liệu và quality gate: PDF searchable → Docling trước; scan/broken layout → Docling trước, MinerU nếu quality gate fail; bảng phức tạp → so sánh đầu ra hai parser (config tại [`docs/parser_router.yaml`](docs/parser_router.yaml)). Docling là parser chính, MinerU là parser phụ/fallback (challenger).
- **Canonical Document IR** — biểu diễn trung gian parser-neutral do dự án sở hữu (`ParsedDocument → ParsedPage[] → DocumentElement[]`), schema version `document-ir-v1` (contract tại [`docs/canonical-document-ir-design.md`](docs/canonical-document-ir-design.md)). Mọi module khác chỉ đọc IR, không đọc định dạng Docling/MinerU.
- **Legal Structure Extractor** — bộ phân tích pháp lý riêng của VNLRAG: nhận diện Chương/Mục/Điều/Khoản/Điểm (kể cả nhãn tiếng Việt a) b) c) d) đ) e) và short-Point retention), chỉ đọc IR.
- **PostgreSQL 18** — nguồn chân lý dữ liệu pháp lý: metadata, phiên bản, quan hệ (`ProvisionReference`, `DocumentRelation`), hiệu lực thời gian `[effective_from, effective_to)`, review routing, audit, query trace và feedback.
- **Qdrant v1.19** — retrieval engine duy nhất: dense + sparse (BM25) + payload filter + RRF fusion trong cùng collection; index dẫn xuất, luôn dựng lại được từ PostgreSQL; nếu dữ liệu lệch nhau, PostgreSQL thắng.
- **Redis + Dramatiq 2.x** — background ingestion: upload trả `202 Accepted` kèm `ingestion_job_id`; các actor ngắn, rời rạc, idempotent (parse → normalize → extract → resolve_refs → resolve_temporal → quality_gate → embed → index); `MAX_INGESTION_WORKERS=1` trên máy cá nhân.
- **ObjectStoragePort (S3-compatible)** — MinIO là ứng viên hiện tại; lưu PDF nguồn, parser output, ảnh trang, artifact ingestion/review/evaluation; PostgreSQL lưu object key và metadata.
- **Langfuse Cloud (mặc định)** — observability, prompt management, trace, experiment; nằm ngoài đường tới hạn tính đúng đắn (nếu không khả dụng, query vẫn hoạt động).
- **LangGraph 1.x** — controlled workflow, KHÔNG phải autonomous agent; LLM không tự chọn tool hay tự lập kế hoạch.
- **RAGFlow v0.26.x** — chỉ là baseline so sánh bên ngoài (RAGFlow default / +Docling / +MinerU so với VNLRAG custom pipeline), chạy trong môi trường benchmark riêng, không nằm trong compose production.

## Bảng công nghệ

Tổng hợp từ `docs/04-tech-stack-llm-research.md` §4.2 (đồng bộ với doc 00 §7):

| Lớp | Công nghệ | Phiên bản | Ghi chú |
|---|---|---|---|
| Ngôn ngữ | Python | 3.11.x | Backend, ingestion, retrieval, workflow, evaluation |
| Package manager | uv | Pin bằng `uv.lock` | Dependency và virtual environment |
| API / web framework | FastAPI | Minor ổn định đã lock | REST API, OpenAPI, validation |
| Workflow | LangGraph | 1.x (pin `langgraph>=1.1`) | Controlled workflow orchestration |
| Parser chính | Docling | 2.x line, pin exact | PDF/DOCX/PPTX/XLSX/HTML parse, OCR, hierarchy, provenance |
| Parser phụ / fallback | MinerU | 3.4.x, pipeline backend CPU | Parser thay thế khi quality gate fail (challenger) |
| IR trung gian | Canonical Document IR | `document-ir-v1` | Biểu diễn parser-neutral do dự án sở hữu |
| Relational database | PostgreSQL | 18.x (18.4) | Source of truth: metadata, relation, version, review, audit |
| ORM | SQLAlchemy | 2.0.x | Persistence và transaction |
| Migration | Alembic | 1.18.x | Database migrations |
| Vector database | Qdrant | v1.19.0 | Dense + sparse + payload filter + RRF fusion, index dẫn xuất |
| Dense embedding | Gemini Embedding 2 (ứng viên E1) | 768 dimensions (cấu hình thử nghiệm) | Chưa chốt vĩnh viễn, chọn sau Suite B |
| Dense embedding | Jina Embeddings v5 text-nano (E2) | 768 dims | Ứng viên |
| Dense embedding | Jina Embeddings v5 text-small (E3) | 1024 dims | Ứng viên |
| Sparse retrieval | Qdrant sparse BM25 | `qdrant/bm25` hoặc encoder tiếng Việt nếu cần | Lexical retrieval trong cùng collection |
| Fusion | Qdrant RRF | Query API prefetch + fusion | k và weights configurable |
| Reranker | Jina Reranker v3 | `jina-reranker-v3` (ứng viên chính) | Rerank sau RRF; chưa khẳng định cải thiện trước benchmark |
| Generator | Gemini 3.5 Flash | `gemini-3.5-flash` | Structured legal answer theo schema cấp claim |
| Judge độc lập | GPT-5.4 mini | `gpt-5.4-mini-2026-03-17` (snapshot pin) | L5 semantic judge + evaluation metric thứ cấp |
| Evaluation | Ragas + deterministic custom metrics | Ragas 0.4.x (0.4.3) | Deterministic là headline, LLM judge là thứ cấp |
| Object storage | ObjectStoragePort (S3-compatible); MinIO là ứng viên hiện tại | MinIO date-tagged community release (AIStor) | PDF nguồn, parser output, artifact review/evaluation |
| Background jobs | Dramatiq | v2.2.0 | Actor ingestion idempotent, Redis broker |
| Cache / broker | Redis | 8.10.0 | Dramatiq broker + cache |
| Observability | Langfuse | Server v4, SDK v4.x | Trace, prompt management, experiments; ngoài đường tới hạn |
| Frontend | Next.js | 16.x App Router | Chat, search, citation panel |
| UI | React + TypeScript + Tailwind + shadcn/ui | Pin lock file | Giao diện |
| Testing | pytest + Playwright | Pin exact | Unit, integration, E2E |
| Container | Docker + Compose Spec | Pin image tags | Local deployment |
| CI/CD | GitHub Actions | Action SHA hoặc major pin | Automated checks |
| Benchmark baseline | RAGFlow | v0.26.x, môi trường benchmark riêng | Baseline so sánh bên ngoài |

Ghi chú ràng buộc tech stack:

- **Không dùng pgvector**: vector retrieval nằm trong Qdrant; PostgreSQL giữ metadata và quan hệ pháp lý.
- **Không dùng full LangChain, Haystack hoặc LlamaIndex** trong core implementation; chỉ giữ `langgraph`, `langchain-core` nếu cần, SDK chính thức của provider và các thư viện hạ tầng trực tiếp.
- Embedding và reranker **chưa được chốt vĩnh viễn**; quyết định phải dựa trên bằng chứng thực nghiệm (Suite B, C), không dựa trên tuyên bố nhà cung cấp.
- Model ID nằm trong cấu hình, không hardcode trong domain logic; trước evaluation cuối phải pin model snapshot hoặc ghi lại model version thực tế.

## Mô hình dữ liệu tổng quan

- **PostgreSQL là nguồn chân lý** (ADR-006): mọi dữ liệu pháp lý (văn bản, version, provision, quan hệ, hiệu lực, review, audit, query trace, feedback) được xác nhận trong PostgreSQL trước khi phục vụ query. Các thực thể chính: `LegalDocument`, `DocumentVersion`, `LegalProvision` (kèm `provision_id` ổn định, `source_text`/`retrieval_text`, `[effective_from, effective_to)`), `ProvisionReference`, `DocumentRelation`, `LegalEffectEvent`, cùng các thực thể vận hành (`IngestionRun`, `ReviewItem`, `QueryTrace`, ...).
- **Qdrant là index dẫn xuất, dựng lại được từ PostgreSQL** (ADR-005): collection dùng named dense vector + sparse vectors + payload (alias `legal_provisions_active`); thay đổi schema (embedding model, dimension, sparse encoding, chunking) bằng rebuild + alias switch, không rebuild in place. Nếu dữ liệu hai nơi lệch nhau, PostgreSQL thắng.
- **Object keys + metadata nằm trong PostgreSQL** (ADR-012): MinIO lưu nội dung file (PDF nguồn, parser output, ảnh trang, artifact), PostgreSQL lưu object key và metadata truy vết; nội dung file không nằm trong database.

## Liên kết ADR

20 ADR đã chốt, tài liệu hóa tại `docs/adr/` (chi tiết ban đầu ở doc 03 §3.32):

| ADR | Quyết định |
|---|---|
| [ADR-001](docs/adr/ADR-001.md) | Loại bỏ UDEF, thay bằng Parser Router + Canonical Document IR + Legal Structure Extractor |
| [ADR-002](docs/adr/ADR-002.md) | Parser Router (Docling chính, MinerU phụ/fallback) |
| [ADR-003](docs/adr/ADR-003.md) | Canonical Document IR là biểu diễn parser-neutral do dự án sở hữu |
| [ADR-004](docs/adr/ADR-004.md) | Đồ thị quan hệ bằng bảng PostgreSQL, không dùng Neo4j |
| [ADR-005](docs/adr/ADR-005.md) | Qdrant là index dẫn xuất, thay ChromaDB và rank-bm25 pickle |
| [ADR-006](docs/adr/ADR-006.md) | PostgreSQL là nguồn chân lý dữ liệu pháp lý |
| [ADR-007](docs/adr/ADR-007.md) | Evidence Completeness Gate bắt buộc trước generation |
| [ADR-008](docs/adr/ADR-008.md) | Verification sáu tầng với bất biến Returned Invalid Citation Rate = 0 |
| [ADR-009](docs/adr/ADR-009.md) | Langfuse là observability, nằm ngoài đường tới hạn |
| [ADR-010](docs/adr/ADR-010.md) | RAGFlow chỉ là baseline bên ngoài |
| [ADR-011](docs/adr/ADR-011.md) | Background ingestion qua Redis + Dramatiq, không parse đồng bộ |
| [ADR-012](docs/adr/ADR-012.md) | MinIO làm object storage |
| [ADR-013](docs/adr/ADR-013.md) | Embedding model chưa được chốt vĩnh viễn cho tới khi benchmark |
| [ADR-014](docs/adr/ADR-014.md) | Reranker là stage chuẩn, Jina Reranker v3 là ứng viên chính |
| [ADR-015](docs/adr/ADR-015.md) | Không dùng open-web search và không có query-time HITL |
| [ADR-016](docs/adr/ADR-016.md) | LangGraph là controlled workflow, không phải autonomous agent |
| [ADR-017](docs/adr/ADR-017.md) | Citation-by-ID và dựng citation từ metadata |
| [ADR-018](docs/adr/ADR-018.md) | Structured generation theo schema cấp claim |
| [ADR-019](docs/adr/ADR-019.md) | Failure-aware repair có giới hạn thay vì regenerate vô hạn |
| [ADR-020](docs/adr/ADR-020.md) | Chính sách canonical date cho câu hỏi lịch sử |

---

> **Nguồn**: `docs/03-thiet-ke-he-thong.md` (§3.1, §3.2, §3.32) — kiến trúc tổng quan, pipeline, LangGraph workflow, danh mục ADR; `docs/04-tech-stack-llm-research.md` (§4.1, §4.2) — bảng công nghệ và ràng buộc tech stack; `docs/00-scope-and-decisions.md` (§3, §6, §7, §8, §15) — nguyên tắc, pipeline, mô hình dữ liệu cốt lõi.
