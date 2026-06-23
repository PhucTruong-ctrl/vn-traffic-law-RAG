# 01. Phân Tích Tính Khả Thi (Feasibility Analysis)

> **Giai đoạn SDLC**: 1 — Phân tích tính khả thi
> **Ngày tạo**: 16/06/2026

---

## 1.1. Bối cảnh và vấn đề

### Vấn đề thực tế

Người dân Việt Nam khi muốn tra cứu mức phạt giao thông hoặc các quy định pháp luật giao thông đường bộ hiện hành (Nghị định 168/2024, Luật Trật tự ATGT 36/2024, Thông tư 47/2024,...) gặp các khó khăn:

1. **Phải đọc PDF dày** — Nghị định 168/2024 có 84 trang, mỗi lần tra cứu mất 10-15 phút
2. **ChatGPT thường hallucinate** — Bịa ra số tiền phạt, điểm trừ, điều khoản không tồn tại
3. **Văn bản cập nhật liên tục** — NĐ 100/2019 đã hết hiệu lực, thay bằng NĐ 168/2024, người dân không nắm
4. **Ngôn ngữ pháp lý phức tạp** — Khó hiểu cho người không chuyên

### Giải pháp đề xuất

Xây dựng **hệ thống RAG** (Retrieval-Augmented Generation có Agent) hỗ trợ tra cứu pháp luật giao thông Việt Nam với:

- **Trích dẫn chính xác** đến từng Điều/Khoản/Điểm
- **Chống hallucination** bằng prompt chặt chẽ
- **Human-in-the-Loop** khi dữ liệu nội bộ không đủ
- **Hybrid Retrieval** (Dense + BM25) tối ưu cho tiếng Việt

---

## 1.2. Phân tích khả thi kỹ thuật (Technical Feasibility)

### 1.2.1. Đánh giá phần cứng mục tiêu

| Linh kiện | Thông số | Đánh giá |
|-----------|----------|----------|
| CPU | Intel Core i5-1035G1 (4C/8T, 1.0GHz base / 3.6GHz boost) |Đủ với single-worker + CPU-only embedding |
| RAM | 19GB DDR4 |
| GPU | NVIDIA MX330 (2GB VRAM, CC 6.1) | ⚠️ Yếu — force `device="cpu"` cho embedding inference; đã drop reranker (V4) |
| Disk | NVMe 473GB (185GB free) |

### 1.2.1b. Môi trường phát triển (Development Environment)

| Công cụ | Phiên bản | Ghi chú |
|---------|-----------|---------|
| **Python** | 3.11.15 (pyenv) | Quản lý qua `pyenv` + virtualenv `vnlaw-env`; không dùng system Python 3.14 |
| **Package manager** | uv 0.11.21 | Thay Poetry (nhanh hơn, drop-in thay pip) |
| **Node.js** | v26.2.0 + npm 11.16 | Exceeds yêu cầu Node 20+ |
| **Docker** | 29.5.2 + Compose 5.1.4 | Ready cho development + deployment |
| **Shell** | fish | pyenv config qua `set -Ux` + `fish_add_path` |

### 1.2.2. Chiến lược xử lý phần cứng yếu

**Quyết định**: **KHÔNG dùng Local LLM**, dùng **API Cloud LLM** thay thế.

| Lựa chọn | Ưu điểm | Nhược điểm | Quyết định |
|----------|---------|-----------|------------|
| Ollama local 3B (Qwen2.5) | Free, offline | Chậm trên CPU, chất lượng kém với legal reasoning | ❌ |
| **Gemini 2.5 Flash API** (Free) | 250 RPD, 1M context, tiếng Việt tốt | Free tier prompts có thể bị review | ✅ **Chính** |
| **OpenAI GPT-4o-mini** | $5 free credit, ~10M input tokens | Cần credit card | ✅ **Phụ (Eval)** |
| Claude API | Chất lượng cao | Tốn phí | ❌ |

Xem chi tiết: [04-tech-stack-llm-research.md](04-tech-stack-llm-research.md)

### 1.2.3. Đánh giá dữ liệu

| Nguồn dữ liệu | Tình trạng | Đánh giá |
|---------------|------------|----------|
| Bộ pháp điển VN | Mở tại phapdien.moj.gov.vn | ✅ Có thể crawl |
| CSDL QPPL | Mở tại thuvienphapluat.vn | ✅ Có thể crawl (tham khảo repo VN-Law-Advisor) |
| Nghị định 168/2024 | PDF công khai | ✅ Ưu tiên nguồn chính |
| Luật 36/2024 | PDF công khai | ✅ |
| 28 văn bản pháp luật GT khác | PDF công khai | ✅ |

**Phạm vi**: 30 văn bản pháp luật giao thông đường bộ (học từ bài Viblo đã thu thập 26 văn bản).

---

## 1.3. Phân tích khả thi vận hành (Operational Feasibility)

### Đối tượng sử dụng

| Đối tượng | Nhu cầu |
|-----------|---------|
| Người dân | Tra cứu mức phạt khi bị CSGT phạt |
| Sinh viên luật | Tham khảo nhanh khi làm bài tập |
| Tài xế công nghệ | Xem quy định mới |
| Phóng viên | Tìm căn cứ pháp lý khi viết bài |

### Tính sẵn sàng

- ✅ Có thể demo thật bằng web app
- ✅ Có thể deploy lên VPS miễn phí (Oracle Free Tier / Vercel)
- ✅ Có thể mở rộng corpus từ 30 → 100+ văn bản sau bảo vệ

---

## 1.4. Phân tích khả thi tài chính (Financial Feasibility)

| Khoản mục | Chi phí ước tính |
|----------|----------------|
| Cloud LLM (Gemini Free tier) | **$0** |
| OpenAI API (eval, $5 credit + ~$5 nạp thêm) | **~$5-10** |
| VPS Oracle Free Tier | **$0** (4 CPU, 24GB RAM miễn phí vĩnh viễn) |
| Domain (nếu muốn) | ~$10/năm |
| Tổng | **< $20** cho cả project |

---

## 1.5. Phân tích khả thi lịch trình (Schedule Feasibility)

**Tổng thời gian**: 7 tuần (16/6 → 3/8/2026)

| Tuần | Giai đoạn | Công việc chính | Deliverable |
|------|-----------|-----------------|-------------|
| 1 (16-22/6) | Setup | Design + setup môi trường + crawl 5 VB đầu | Repo + 5 văn bản |
| 2 (23-29/6) | Core RAG | Embedding + BM25 + Hybrid retrieval | Retrieval Recall ≥ 0.4 |
| 3 (30/6-6/7) | Core Agent | LangGraph (rewrite+retrieve+grade+generate+validate) + LLM integration | End-to-end chat |
| 4 (7-13/7) | Web fallback + Frontend | Web search + disclaimer + chat UI | Web fallback hoàn chỉnh |
| 5 (14-20/7) | Frontend + Corpus | Chat UI + crawl thêm 25 VB | UI demo + 30 VB |
| 6 (21-27/7) | Evaluation | Gold set + RAGAS-lite + Ablation | Bảng đánh giá |
| 7 (28/7-3/8) | Deploy + Báo cáo | Docker + Deploy + Viết báo cáo + Slide | **BẢO VỆ** |

**Đánh giá**: ✅ Khả thi với điều kiện:

- Dùng AI Agent (Claude Code / OpenCode) tăng tốc code boilerplate
- Tập trung vào chất lượng, không làm tính năng thừa
- Dùng Gemini Free tier + Ollama chỉ khi cần test local

---

## 1.6. Phân tích rủi ro (Risk Analysis)

| # | Rủi ro | Xác suất | Tác động | Giải pháp |
|---|--------|----------|----------|-----------|
| R1 | LLM hallucinate số tiền phạt | Cao | **Rất cao** | Prompt "Legal Reasoning" chặt, bắt buộc trích dẫn, có validation layer |
| R2 | Parse PDF giữ hierarchy lỗi (đã có UDEF mitigate) | Cao | Cao | Custom chunker theo Điều/Khoản/Điểm, test với 3 loại VB (Luật, NĐ, TT) |
| R3 | Gemini Free rate-limit | Trung bình | Trung bình | Implement retry with backoff, fallback OpenAI |
| R4 | Gold set test ít (25-50 câu) | Trung bình | Trung bình | Sinh câu hỏi từ LLM + manual verify, ≥ 30 câu |
| R5 | Không kịp deadline 3/8 | Trung bình | Cao | MVP tuần 3, mở rộng dần, dùng Claude Code |
| R6 | Hybrid retrieval không cải thiện | Thấp | Trung bình | Có baseline V1 (Dense only) để so sánh |
| R7 | Corpus không đủ 30 VB | Thấp | Trung bình | Ưu tiên NĐ 168, Luật 36, các TT liên quan trước |
| ~~R8~~ | ~~HITL~~ | — | — | **ĐÃ XÓA (A7): HITL defer sang Phase 2** |

---

## 1.7. Kết luận khả thi

> **Hệ thống KHẢ THI** về mặt kỹ thuật, vận hành, tài chính và lịch trình.
>
> **Điều kiện tiên quyết**:
>
> 1. Sử dụng **Gemini 2.5 Flash** làm LLM chính (Free tier, 250 RPD)
> 2. Sử dụng **OpenAI GPT-4o-mini** cho evaluation (~$5-10)
> 3. Tập trung vào **citation chính xác** làm điểm nhấn
> 4. Áp dụng **Hybrid Retrieval** với RRF
> 5. Có **HITL** cho web fallback (optional, có thể làm sau)
>
> **Chi phí ước tính**: < $20 cho toàn bộ project.
>
> **Quyết định**: ✅ **TIẾP TỤC** sang giai đoạn Phân tích yêu cầu.

---

## 1.8. Câu hỏi mở (Open Questions)

1. ✅ Tech stack: Python/FastAPI (GVHD yêu cầu)
2. ✅ Corpus: Pháp luật giao thông, 30 văn bản
3. ✅ LLM: Gemini Free + OpenAI $5 credit
4. ❓ Có cần thiết kế multi-tenant (nhiều user) hay single-user?
   - **Mặc định**: Single-user (đơn giản), có thể mở rộng
5. ❓ Có cần auth/login không?
   - **Mặc định**: Không (giảm độ phức tạp), admin dùng env password
6. ❓ UI tiếng Việt hay tiếng Anh?
   - **Mặc định**: Tiếng Việt (đối tượng chính)
