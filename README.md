# 🏛️ VN-Law RAG — Khóa Luận Tốt Nghiệp 2026

> **Đề tài**: Xây dựng hệ thống RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam dựa trên mô hình ngôn ngữ lớn với pipeline trích dẫn có cấu trúc

## 📅 Timeline

- **Bắt đầu**: 16/06/2026
- **Bảo vệ**: 03/08/2026
- **Tổng thời gian**: 7 tuần (49 ngày)

## 🎯 Mục tiêu

1. Xây dựng hệ thống hỏi đáp tự động về pháp luật giao thông VN
2. Câu trả lời **luôn có trích dẫn chính xác** (Điều/Khoản/Điểm)
3. Cơ chế **Human-in-the-Loop** khi cần tìm kiếm web
4. Đánh giá hệ thống bằng **Custom RAGAS-lite**
5. So sánh các chiến lược retrieval (Dense / BM25 / Hybrid)

## 📚 Tài liệu thiết kế

| # | File | Nội dung | SDLC Phase |
|---|------|----------|------------|
| 01 | [01-phan-tich-kha-thi.md](docs/01-phan-tich-kha-thi.md) | Phân tích tính khả thi | 1 |
| 02 | [02-yeu-cau-he-thong.md](docs/02-yeu-cau-he-thong.md) | Đặc tả yêu cầu + Use Case + Sơ đồ ngữ cảnh | 2 |
| 03 | [03-thiet-ke-he-thong.md](docs/03-thiet-ke-he-thong.md) | Kiến trúc + Class Diagram + Sequence | 3 |
| 04 | [04-tech-stack-llm-research.md](docs/04-tech-stack-llm-research.md) | Tech stack + LLM research (Gemini vs OpenAI) | 3 |
| 05 | [05-ke-hoach-trien-khai.md](docs/05-ke-hoach-trien-khai.md) | Lộ trình 7 tuần | 4 |
| 06 | [06-test-evaluation.md](docs/06-test-evaluation.md) | Test plan + RAGAS-lite + Ablation | 5 |
| 07 | [07-deployment.md](docs/07-deployment.md) | Triển khai Docker + CI/CD | 6 |
| 08 | [08-bao-tri.md](docs/08-bao-tri.md) | Bảo trì + Cập nhật corpus | 7 |
| - | [REFERENCES.md](docs/REFERENCES.md) | Tài liệu tham khảo | - |

## 🛠️ Tech Stack Tóm Tắt

| Thành phần | Công nghệ |
|------------|-----------|
| Backend | Python 3.11 + FastAPI |
| | LangGraph (state machine) |
| RAG | LangChain + Hybrid Retrieval (Dense + BM25 + RRF) |
| Vector DB | ChromaDB (local, không cần Docker) |
| Embedding | `intfloat/multilingual-e5-small` (384d) |
| LLM (chính) | **Gemini 2.5 Flash** (Free tier: 250 RPD) |
| LLM (eval) | **OpenAI GPT-4o-mini** ($5 free credit) |
| Web Search | DuckDuckGo (free, no API key) |
| HITL | LangGraph `interrupt_before` + SQLite checkpointer |
| Frontend | Next.js 14 + TypeScript + Tailwind |
| DB | SQLite (state, history, eval) |
| Deploy | Docker Compose + GitHub Actions |

## 🏃 Quick Start (sau khi code xong)

```bash
git clone <repo>
cd vnlaw-agentic-rag
cp .env.example .env  # thêm API keys + ADMIN_TOKEN

# Backend
cd backend && poetry install
python scripts/crawl_pdfs.py  # Crawl 30 văn bản vào data/pdfs/
python scripts/ingest_corpus.py  # Parse + embed + index
uvicorn app.main:app --reload

# Frontend
cd frontend && npm install
npm run dev
```

> **Note (D8 fix)**: Tuần 1 chỉ ship 5 văn bản, scale lên 30 trong Tuần 5. Quick Start trên dùng để development cuối cùng.

## 📊 Tài liệu tham khảo chính

1. **CTU-LinguTechies/VN-Law-Advisor** (91⭐) — github.com/CTU-LinguTechies/VN-Law-Advisor
   - Tham khảo: Cấu trúc microservices, schema CSDL, PDF crawler

2. **Viblo - RAG Pháp luật Giao thông** — viblo.asia/p/xay-dung-he-thong-agentic-rag-phap-luat-giao-thong
   - Tham khảo: LangGraph state machine, Hybrid Retrieval, HITL, RAGAS-lite

## 📝 License

MIT License — Open source cho mục đích học thuật.
