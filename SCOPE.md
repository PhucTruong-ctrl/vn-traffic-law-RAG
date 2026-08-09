# SCOPE — Phạm Vi Dự Án VNLRAG v2

Tài liệu này chốt baseline phạm vi của hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam (bản thiết kế lại v2), phục vụ triển khai theo kế hoạch đến hạn hoàn thành 12/09/2026 và bảo vệ 14/09/2026.

## Mục đích

- Văn bản này xác định **baseline phạm vi v2** của VN Traffic Law RAG: phạm vi P0 bắt buộc, phạm vi P1 sau khi P0 ổn định, các hạng mục ngoài phạm vi, công nghệ chốt và các quyết định kiến trúc (ADR).
- Phạm vi được đóng băng tại **mốc M0 — Scope Freeze ngày 19/07/2026**: scope, kiến trúc, tech stack và kế hoạch chốt ở mức scope-baseline freeze; các cập nhật nghiên cứu sau freeze có kiểm soát và phải được ghi vào change log, không làm thay đổi phạm vi đã chốt.
- Nguồn quyết định cao nhất là `docs/00-scope-and-decisions.md` (doc 00); chi tiết kỹ thuật trong `docs/03-thiet-ke-he-thong.md` (doc 03), `docs/04-tech-stack-llm-research.md` (doc 04) và `docs/05-ke-hoach-trien-khai.md` (doc 05).

## Nguyên tắc phạm vi

Các nguyên tắc bắt buộc, có hiệu lực toàn cục (doc 00 §3, rút gọn):

1. Loại bỏ hoàn toàn UDEF khỏi mọi pipeline và phụ thuộc; thay bằng Parser Router, Canonical Document IR và Legal Structure Extractor do dự án sở hữu.
2. Giữ nguyên các năng lực đã chốt: nhận biết cấu trúc pháp lý; định danh ổn định cấp provision; câu hỏi hiện hành/lịch sử/so sánh; khoảng hiệu lực `[effective_from, effective_to)`; PostgreSQL là nguồn chân lý; Qdrant là index dựng lại được; trích dẫn theo `provision_id`; verified-or-abstain; evaluation tái lập được.
3. Ingestion dùng parser trực tiếp trên tài liệu nguồn, không qua tầng UDEF.
4. Chất lượng parser là mục tiêu evaluation hạng nhất, có benchmark riêng (Suite A).
5. Mô hình hóa tham chiếu chéo pháp lý (cross-reference) ở cấp provision và cấp văn bản.
6. Retrieval đa tầng: exact lookup, dense, sparse, RRF fusion, reranking, mở rộng ngữ cảnh pháp lý.
7. Kiểm tra tính đầy đủ bằng chứng (evidence completeness) trước khi sinh câu trả lời.
8. Verification xác định (deterministic) sáu tầng với bất biến Returned Invalid Citation Rate = 0.
9. Langfuse phục vụ observability, không nằm trên đường tới hạn tính đúng đắn.
10. RAGFlow chỉ là baseline so sánh bên ngoài, không bao giờ là nền tảng chính.
11. **Không thu hẹp phạm vi** vì lịch trình hoặc độ khó.
12. Không bao giờ mô tả kết quả thực nghiệm chưa hoàn thành như đã đạt được.
13. Không dùng kiến trúc multi-agent tự trị; LangGraph là controlled workflow với các nhánh xác định trước.
14. Không dùng open-web search để sinh câu trả lời pháp lý.

### Các quy tắc cấm thu hẹp phạm vi (kèm trích dẫn)

> "**Không thu hẹp phạm vi** vì lịch trình hoặc độ khó." — doc 00, nguyên tắc 11 (§3)

> "Thiết kế không bị thu hẹp vì lịch trình; mọi hạng mục P0 phải hoàn thành trước feature freeze." — doc 00, §12

> "Không có hạng mục P0 nào bị loại bỏ hoặc hoãn lại vì lịch trình." — doc 05, §5.1.2

> "Chọn công nghệ khi nó trực tiếp giảm code, giảm rủi ro hoặc tạo giá trị nghiên cứu. Không chọn framework chỉ vì phổ biến hoặc có nhiều tính năng ngoài scope. Không thu hẹp phạm vi vì lịch trình. Không tuyên bố kết quả chưa đạt." — doc 04, §4.1 (canonical spec mục 38)

## Phạm vi P0 (bắt buộc)

23 hạng mục bắt buộc theo doc 00 §9.1 (toàn bộ phải hoàn thành trước feature freeze 06/09/2026):

1. Ingest PDF qua Parser Router (Docling chính, MinerU phụ/fallback).
2. Canonical Document IR và Legal Structure Extractor (Chương/Mục/Điều/Khoản/Điểm, nhãn Điểm tiếng Việt a) b) c) d) đ) e), short-Point retention).
3. Legal Context Enricher (parent-context enrichment vào `retrieval_text`).
4. Legal Reference Resolver và Temporal/Amendment Resolver (quan hệ provision + quan hệ văn bản).
5. Provenance đến page và bounding box; `source_element_ids` truy vết về Document IR.
6. Quality gates và review routing trước khi index.
7. PostgreSQL là nguồn chân lý; Qdrant dense + sparse (BM25) + RRF hybrid retrieval.
8. Temporal filtering theo `[effective_from, effective_to)`.
9. Query Understanding và Query Expansion (normalized, multi-query rewrite, conditional HyDE).
10. Reranking (Jina Reranker v3 là ứng viên).
11. Legal Context Expansion (parent/sibling/cross-reference/penalty companion).
12. Evidence planning và Evidence Completeness Gate.
13. Structured answer theo schema cấp claim với provision IDs.
14. Verification sáu tầng (L1-L6) và bất biến Returned Invalid Citation Rate = 0.
15. Verified-or-abstain với failure-aware repair có giới hạn.
16. Langfuse tracing trên toàn bộ pipeline, không trên đường tới hạn.
17. Background ingestion (Redis + Dramatiq) và MinIO object storage.
18. Hỏi luật hiện hành, hỏi luật tại ngày cụ thể, so sánh hai giai đoạn.
19. Chat UI và citation panel dựng từ metadata.
20. Feedback Useful / Not Useful lưu PostgreSQL và gửi về Langfuse.
21. Gold set (200 câu) và các bộ thí nghiệm A-D.
22. RAGFlow benchmark riêng làm baseline so sánh.
23. Docker Compose chạy local; regression tests trong CI.

## Phạm vi P1 (sau khi P0 ổn định)

Chỉ làm sau khi toàn bộ acceptance criteria P0 đạt (doc 00 §9.2):

- admin upload và review UI hoàn chỉnh (upload API cơ bản có từ P0);
- conversation history;
- follow-up question có giới hạn;
- evaluation dashboard;
- self-hosted Langfuse (tùy chọn, mặc định dùng cloud);
- rà soát feedback thành ứng viên gold set.

## Ngoài phạm vi

Các hạng mục ngoài phạm vi khóa luận (doc 00 §9.3):

- open web search để sinh câu trả lời pháp lý;
- tự động crawl toàn bộ pháp luật Việt Nam;
- lĩnh vực ngoài giao thông đường bộ;
- multi-agent (LangGraph là controlled workflow);
- knowledge graph hoặc Neo4j;
- mobile app;
- voice chatbot;
- microservices;
- Kubernetes;
- fine-tuning LLM;
- local LLM;
- RAGFlow như nền tảng chính (chỉ là external baseline);
- tư vấn pháp lý cá nhân hóa có tính kết luận.

## Công nghệ chốt

Tóm tắt tech stack (chi tiết tại [ARCHITECTURE.md](ARCHITECTURE.md)):

- **Ngôn ngữ / API / workflow**: Python 3.11, FastAPI + Pydantic v2, LangGraph 1.x (controlled workflow, pin `langgraph>=1.1`).
- **Parser**: Docling 2.x (chính) / MinerU 3.4.x (phụ/fallback) qua Parser Router.
- **Lưu trữ**: PostgreSQL 18 + SQLAlchemy 2 + Alembic (metadata và versioning, nguồn chân lý); Qdrant v1.19 (dense + sparse + payload filter + RRF, index dẫn xuất); ObjectStoragePort (S3-compatible, MinIO là ứng viên hiện tại).
- **Background jobs / observability**: Redis + Dramatiq 2.x; Langfuse Cloud (mặc định).
- **Frontend**: Next.js + TypeScript (+ shadcn/ui).
- **LLM**: generator Gemini 3.5 Flash; judge độc lập GPT-5.4 mini (snapshot pin); embedding/reranker là ứng viên chờ benchmark Suite B/C.
- **RAGFlow chỉ là baseline so sánh bên ngoài**, chạy trong môi trường benchmark riêng, không nằm trong compose production.
- Không dùng pgvector; không dùng full LangChain/Haystack/LlamaIndex trong core implementation (chỉ giữ `langgraph`, `langchain-core` nếu cần).

## Quyết định kiến trúc (ADR)

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

## Phương án bị bác bỏ

Các phương án đã xem xét và loại bỏ (doc 00 §14):

1. **UDEF-based pipeline** — thay bằng Parser Router + Canonical Document IR + Legal Structure Extractor do dự án sở hữu.
2. **ChromaDB** — thay bằng Qdrant (dense + sparse + filter + RRF trong một hệ thống).
3. **SQLite làm database chính** — thay bằng PostgreSQL (source of truth, JSONB, migration, nhiều writer).
4. **Kiến trúc rank-bm25 pickle riêng** — thay bằng Qdrant sparse BM25, loại bỏ file pickle thủ công.
5. **DuckDuckGo/SerpAPI fallback khi thiếu dữ kiện** — loại bỏ; hệ thống ABSTAIN thay vì tìm trên web.
6. **Query-time web HITL** — loại bỏ; HITL chỉ còn ở khâu review ingestion.
7. **Autonomous multi-agent** — bác bỏ; LangGraph là controlled workflow với nhánh xác định trước.
8. **Neo4j cho đồ thị quan hệ** — bác bỏ; dùng bảng quan hệ trong PostgreSQL và application logic.
9. **RAGFlow làm nền tảng chính** — bác bỏ; chỉ là baseline so sánh bên ngoài, chạy trong môi trường benchmark riêng.
10. **Open-web search cho câu trả lời pháp lý** — bác bỏ; câu trả lời chỉ dựa trên corpus đã kiểm chứng.

---

> **Nguồn**: `docs/00-scope-and-decisions.md` (chính: §1, §3, §7, §9, §12, §14, §15); bổ sung trích dẫn từ `docs/04-tech-stack-llm-research.md` §4.1 và `docs/05-ke-hoach-trien-khai.md` §5.1.2; tiêu đề ADR lấy từ `docs/03-thiet-ke-he-thong.md` §3.32.
