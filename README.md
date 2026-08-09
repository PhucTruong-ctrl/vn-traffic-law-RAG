# 🏛️ VN Traffic Law RAG (VNLRAG) — Khóa Luận Tốt Nghiệp 2026

> **Đề tài**: Hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực (structure-aware + temporal) cho pháp luật giao thông Việt Nam, với trích dẫn chính xác (Điều/Khoản/Điểm) và cơ chế **verified-or-abstain** — chỉ trả lời khi mọi bằng chứng đã được kiểm chứng.

## 📅 Timeline

- **Bắt đầu**: 16/06/2026
- **M0 — Scope Freeze**: 19/07/2026
- **Triển khai v2**: 8 tuần (W1–W8)
- **Bảo vệ**: 14/09/2026

## 📚 Tài liệu thiết kế

| # | File | Nội dung |
|---|------|----------|
| 00 | [00-scope-and-decisions.md](docs/00-scope-and-decisions.md) | Phạm vi & quyết định thiết kế — **nguồn quyết định cao nhất** |
| 01 | [01-phan-tich-kha-thi.md](docs/01-phan-tich-kha-thi.md) | Phân tích tính khả thi |
| 02 | [02-yeu-cau-he-thong.md](docs/02-yeu-cau-he-thong.md) | Đặc tả yêu cầu + Use Case |
| 03 | [03-thiet-ke-he-thong.md](docs/03-thiet-ke-he-thong.md) | Thiết kế hệ thống (kiến trúc, ADR §3.32) |
| 04 | [04-tech-stack-llm-research.md](docs/04-tech-stack-llm-research.md) | Tech stack + nghiên cứu LLM |
| 05 | [05-ke-hoach-trien-khai.md](docs/05-ke-hoach-trien-khai.md) | Kế hoạch triển khai + gate M0–M8 |
| 06 | [06-test-evaluation.md](docs/06-test-evaluation.md) | Test plan + evaluation (Ragas + metric xác định) |
| 07 | [07-deployment.md](docs/07-deployment.md) | Triển khai Docker + CI/CD |
| 08 | [08-bao-tri.md](docs/08-bao-tri.md) | Bảo trì + cập nhật corpus |

## 🎯 Scope & Architecture

- [SCOPE.md](SCOPE.md) — baseline phạm vi v2
- [ARCHITECTURE.md](ARCHITECTURE.md) — kiến trúc tổng quan
- [docs/parser_router.yaml](docs/parser_router.yaml) — cấu hình Parser Router
- [docs/canonical-document-ir-design.md](docs/canonical-document-ir-design.md) — contract Canonical Document IR
- [docs/adr/](docs/adr/) — **20 ADR** đã chốt ([ADR-001](docs/adr/ADR-001.md)..[ADR-020](docs/adr/ADR-020.md))

**M0 — Scope Freeze (19/07/2026)**: scope, kiến trúc, tech stack và kế hoạch được chốt ở mức scope-baseline freeze; các cập nhật nghiên cứu sau freeze có kiểm soát và phải ghi vào change log, không làm thay đổi phạm vi đã chốt. Doc 00 là nguồn quyết định cao nhất; danh mục ADR-001..020 được tài liệu hóa tại `docs/adr/`.

**Mục tiêu chính**:

- Trích dẫn chính xác theo đơn vị pháp lý (Điều/Khoản/Điểm, `provision_id` ổn định), dựng citation từ metadata.
- Cơ chế **verified-or-abstain**: verification sáu tầng (L1–L6) với bất biến Returned Invalid Citation Rate = 0; thiếu bằng chứng thì từ chối (abstain) thay vì bịa đặt.
- Không dùng open-web search và không có query-time HITL (ADR-015) — câu trả lời chỉ dựa trên corpus đã kiểm chứng.
- Evaluation bằng **Ragas + deterministic metrics** (Recall@k, MRR, nDCG, Citation P/R/F1, Temporal Validity Accuracy, Numeric Grounding Accuracy, Evidence Set Recall, Abstention P/R/F1) trên gold set 200 câu.
- So sánh các chiến lược retrieval (dense / sparse BM25 / RRF hybrid, reranking) qua bốn suite thí nghiệm A–D, kèm RAGFlow baseline bên ngoài.

## 🛠️ Tech Stack

| Thành phần | Công nghệ |
|------------|-----------|
| Ngôn ngữ / env | Python 3.11 + uv |
| API / validation | FastAPI + Pydantic v2 |
| Workflow | LangGraph 1.x (controlled workflow, **không phải** autonomous agent) |
| Parser | Docling 2.x (chính) / MinerU 3.4.x (phụ/fallback) qua **Parser Router** |
| IR trung gian | Canonical Document IR (`document-ir-v1`) |
| Database | PostgreSQL 18 (nguồn chân lý) + SQLAlchemy 2 + Alembic |
| Vector DB | Qdrant v1.19 (index dẫn xuất, dense + sparse + RRF fusion) |
| Background jobs | Redis + Dramatiq 2.x (background ingestion) |
| Object storage | ObjectStoragePort (S3-compatible); MinIO là ứng viên hiện tại |
| Observability | Langfuse (ngoài đường tới hạn) |
| LLM | Gemini 3.5 Flash (generator) + GPT-5.4 mini (judge độc lập) + Jina Reranker v3 |
| Frontend | Next.js 16 App Router + TypeScript + Tailwind + shadcn/ui |
| Evaluation | Ragas 0.4.x + deterministic metrics |
| Testing | pytest + Playwright |
| Deploy | Docker Compose + GitHub Actions |

> Embedding và reranker chưa được chốt vĩnh viễn cho tới khi có bằng chứng thực nghiệm (ADR-013, ADR-014); Jina Reranker v3 là ứng viên chính.

## 🏃 Quick Start

> Trạng thái W1: tooling + compose skeleton đã sẵn sàng; app code đang được triển khai theo [doc 05](docs/05-ke-hoach-trien-khai.md).

```bash
# 1. Sao chép cấu hình môi trường
cp .env.example .env

# 2. Backend — cài dependency bằng uv
cd backend && uv sync

# 3. Hạ tầng: PostgreSQL, Qdrant, Redis, MinIO (kèm health checks)
docker compose --env-file .env.example up -d
docker compose ps   # chờ cả 4 service đạt healthy

# 4. Chạy backend
uv run uvicorn app.main:app --reload

# 5. Frontend
cd frontend && npm install && npm run dev
```

> **Note**: `MAX_INGESTION_WORKERS=1` được enforce trên máy cá nhân (doc 03 §3.2.5) — không chạy song song nhiều job parse.

## 📊 Tài liệu tham khảo chính

1. **CTU-LinguTechies/VN-Law-Advisor** (91⭐) — github.com/CTU-LinguTechies/VN-Law-Advisor
   - Tham khảo: cấu trúc microservices, schema CSDL, PDF crawler

2. **Viblo - RAG Pháp luật Giao thông** — viblo.asia/p/xay-dung-he-thong-agentic-rag-phap-luat-giao-thong
   - Tham khảo: LangGraph state machine, Hybrid Retrieval, đánh giá RAG

## 📋 Project Management

**Jira**: truongphucwork.atlassian.net — project VNLRAG (8 sprint W1–W8, gate M1→M8)

- Backlog: 8 sprint W1–W8, gate path **M1→M8** (labels `gate-M1`..`gate-M8`)
- 20 ADR đã chốt (ADR-001..ADR-020) tại `docs/adr/`

## 📝 License

MIT License — Open source cho mục đích học thuật.
