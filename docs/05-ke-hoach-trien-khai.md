# 05. Kế Hoạch Triển Khai (7 Tuần)

> **Giai đoạn SDLC**: 4 — Thực hiện, cài đặt
> **Ngày bắt đầu**: 16/06/2026
> **Ngày bảo vệ**: 03/08/2026
> **Tổng**: 7 tuần (49 ngày)

---

## 5.1. Tổng quan (POST-REVIEW A7)

> **Đã thay đổi (A7)**: 
> - **HITL dropped** (Tuần 4 giờ chỉ làm web fallback đơn giản, không có admin UI)
> - **Tuần 7 reserved CHỈ cho báo cáo + slide + bảo vệ** (không code)
> - **Chunker moved lên Tuần 1-2** (parallel với setup, do là phần khó nhất)
> - **Risk R5** (deadline) đã upgrade từ "Trung bình" → "Cao"
> - **Risk R8** (HITL) đã XÓA vì không còn trong scope

| Tuần | Thời gian | Giai đoạn | Deliverable chính | Trạng thái |
|------|-----------|-----------|-------------------|------------|
| 1 | 16-22/06 | Setup + Design + **Chunker** | Repo + 5 VB parsed + chunker working | ⏳ |
| 2 | 23-29/06 | Core RAG | Hybrid retrieval **Recall@10 ≥ 0.4** | ⏳ |
| 3 | 30/6-6/7 | Agentic Core | End-to-end chat + eval pipeline | ⏳ |
| 4 | 7-13/07 | Web Fallback + UI cơ bản | Web search + simple chat UI | ⏳ |
| 5 | 14-20/07 | Frontend + Corpus mở rộng | UI polish + 30 văn bản | ⏳ |
| 6 | 21-27/07 | Evaluation + Optimization | 5 metrics × 3 variants = 15 số | ⏳ |
| 7 | 28/7-3/8 | **BÁO CÁO + SLIDE** (no code) | **BẢO VỆ** | ⏳ |

---

## 5.2. CHI TIẾT TỪNG TUẦN

### 📅 TUẦN 1 (16-22/06): Setup + Design hoàn thiện

**Mục tiêu**: Có repo chuẩn, môi trường chạy được, 5 văn bản đầu tiên parse thành công.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (16/6) | Đọc & finalize design | Review docs/01-03, xác nhận tech stack với GVHD | OK to start coding |
| T3 (17/6) | Init repo | Tạo GitHub repo, folder structure, .gitignore, README | Repo on GitHub |
| T3 (17/6) | Setup backend | Poetry init, pyproject.toml, install deps | `poetry install` thành công |
| T4 (18/6) | Setup frontend | Next.js init, Tailwind config, base layout | `npm run dev` chạy |
| T4 (18/6) | API keys | Lấy Gemini + OpenAI API keys, lưu .env | `.env` có keys |
| T5 (19/6) | Hello World FastAPI | `app/main.py` với 1 endpoint `/health` | API trả 200 |
| T5 (19/6) | Docker Compose | docker-compose.yml cho backend + frontend | `docker compose up` chạy |
| T6 (20/6) | Crawl PDFs | Tải 5 văn bản đầu: NĐ 168/2024, Luật 36/2024, 3 Thông tư | `data/pdfs/*.pdf` |
| T7 (21/6) | Parse + chunk | Test PyMuPDF + custom chunker + VietnameseNormalizer | `data/corpus/*.json` |
| CN (22/6) | Gold set (H4 fix) | Tạo 15 câu manual + freeze file, trước khi code retriever | `data/gold_set.frozen.json` |

**Milestone tuần 1** ✅:
- [x] Repo có structure chuẩn
- [x] Backend FastAPI chạy được (Hello World + health)
- [x] Frontend Next.js chạy được
- [x] Có 5 văn bản PDF + JSON parsed
- [x] Docker Compose hoạt động

**Rủi ro tuần 1**:
- ⚠️ Không cài được Poetry → dùng `pip install` + `venv` thay thế
- ⚠️ Không crawl được PDF → tải thủ công từ thuvienphapluat.vn

---

### 📅 TUẦN 2 (23-29/06): Core RAG Pipeline

**Mục tiêu**: Hybrid retrieval hoạt động, có thể query và trả về top-5 chunks chính xác.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (23/6) | Embedding service | `services/embedding.py` load model e5-small | Embedding 384d OK |
| T3 (24/6) | Vector store | `db/vector_store.py` wrap ChromaDB | CRUD chunks |
| T3 (24/6) | Ingest pipeline | `scripts/ingest_corpus.py` đọc JSON → embed → store | 5 VB index xong |
| T4 (25/6) | BM25 indexer | `db/bm25_index.py` dùng rank-bm25 + pyvi | Tokenize tiếng Việt |
| T5 (26/6) | Hybrid retrieval | `services/retrieval.py` implement RRF | `retrieve()` trả top-k |
| T6 (27/6) | Test retrieval | Test 10 câu query thủ công, tính Recall@10 | Báo cáo test |
| T7 (28/6) | API endpoint | `GET /api/search?q=...` | Swagger UI test được |
| CN (29/6) | Regression test | `tests/test_retrieval_regression.py` | CI pass |

**Milestone tuần 2** ✅:
- [x] Hybrid retrieval với RRF
- [x] Test set 10 câu đạt Recall@10 ≥ 0.5
- [x] Có 5 văn bản trong Vector DB
- [x] API `/api/search` chạy được

**Tiêu chí kiểm thử tuần 2**:
```bash
# Test truy vấn
curl "http://localhost:8000/api/search?q=vượt%20đèn%20đỏ"
# Expected: top-1 chunk chứa "đèn đỏ" + "phạt tiền"
```

---

### 📅 TUẦN 3 (30/6-6/7): Agentic Core + LLM Integration

**Mục tiêu**: End-to-end chat với citation, không cần HITL.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (30/6) | LangGraph setup | `agents/graph.py`, `agents/state.py` | State machine |
| T2 (30/6) | Node: rewrite | Implement query rewrite | Working |
| T3 (1/7) | Node: retrieve (Hybrid search) | Dense + BM25 with E5 prefix, pyvi | recall ≥ 0.4 |
| T3 (1/7) | Node: grade | LLM chấm relevance score | Score 0-1 |
| T4 (2/7) | LLM service | `services/llm.py` wrap Gemini + OpenAI | Cả 2 chạy |
| T5 (3/7) | Node: generate | Legal Reasoning Prompt | Answer có citation |
| T5 (3/7) | Citation validator | `services/citation.py` check format | Validate OK |
| T6 (4/7) | Node: validate | Validate citation có trong context | Pass/fail |
| T6 (4/7) | Test E2E | 5 câu test, manual verify | Trả lời đúng |
| T7 (5/7) | API `/api/chat` | POST endpoint, non-streaming | Test trên Swagger |
| CN (6/7) | Buffer | Sửa lỗi, tối ưu prompt | |

**Milestone tuần 3** ✅:
- [x] LangGraph state machine chạy
- [x] Chat trả lời câu đơn giản có citation
- [x] E2E test 5/5 pass
- [x] API `/api/chat` chạy

**Test case tuần 3**:
```python
# Test 1: Câu hỏi đơn giản
query = "Vượt đèn đỏ phạt bao nhiêu?"
expected_citation = "Nghị định 168/2024, Điều 6, Khoản 2"

# Test 2: Câu định nghĩa
query = "GPLX là gì?"
expected_answer = "Giấy phép lái xe là..."

# Test 3: Câu tình huống
query = "Ai có lỗi khi 2 xe va chạm?"
expected_pattern = r"Tỷ lệ % lỗi cuối cùng phải do CSGT"
```

---

### 📅 TUẦN 4 (7-13/7): Web Search + Frontend cơ bản (POST-REVIEW C4)

> **C4 fix (CRITICAL)**: Tuần 4 KHÔNG làm HITL nữa. Focus: web fallback + disclaimer + effectivity + frontend chat cơ bản.

**Mục tiêu**: Web search fallback hoạt động, có disclaimer cho web answer, frontend chat chạy được.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (7/7) | DuckDuckGo service | `services/web_search.py` với retry 3 lần | Web results |
| T2 (7/7) | Node: web_search | Tích hợp vào graph | Trigger khi relevance_score < 0.4 |
| T3 (8/7) | Web fallback disclaimer | "Nguồn: Web (chưa qua kiểm duyệt)" auto-append | Code + test |
| T3 (8/7) | CitationExtractor | Regex parser cho legal citations | Parser working |
| T4 (9/7) | Frontend chat (basic) | `ChatWindow.tsx` + SSE streaming | Chat UI |
| T5 (10/7) | Frontend components | `MessageBubble.tsx`, `CitationBadge.tsx` | Components |
| T5 (10/7) | Effectivity display | Show `(còn hiệu lực)` / `(hết hiệu lực)` | Working |
| T6 (11/7) | Test web fallback | 5 test case: web OK, web fail, no results | Pass |
| T7 (12/7) | UX polish | Loading states, error handling | UI đẹp |
| CN (13/7) | Integration test | E2E test chat full flow | Pass |

**Milestone tuần 4** ✅:
- [x] Web search khi relevance_score < 0.4
- [x] Web disclaimer auto-appended
- [x] Citation extraction parser working
- [x] Effectivity display trên UI
- [x] Frontend chat với streaming

> **A7 fix (C4)**: HITL + Admin UI đã chuyển sang **Phase 2 (sau khóa luận)**. Không có task HITL nào trong MVP.

**Test web fallback** (POST-REVIEW C4 — HITL removed):
```
1. Hỏi "Năm 2026 có luật xe điện?" → score < 0.4 → web search
2. DuckDuckGo returns results
3. Generate answer + web disclaimer: "Nguồn: Web (chưa qua kiểm duyệt)"
4. User nhận câu trả lời với nguồn web + citation
```

---

### 📅 TUẦN 5 (14-20/7): Frontend hoàn thiện + Corpus mở rộng

**Mục tiêu**: UI demo flow hoàn chỉnh, 30 văn bản trong corpus.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (14/7) | Crawl thêm 25 VB | Tải 25 văn bản PL giao thông khác | 30 PDFs |
| T3 (15/7) | Parse + ingest lại | Batch parse 25 VB mới | 30 VB indexed |
| T4 (16/7) | Frontend chat | `components/ChatWindow.tsx`, SSE | Streaming UI |
| T4 (16/7) | Citation display | `CitationBadge.tsx`, highlight | UI đẹp |
| T5 (17/7) | Frontend search | `app/search/page.tsx` | Search UI |
| T5 (17/7) | History sidebar | Lưu + xem lại threads | Persistence |
| T6 (18/7) | Mobile responsive | Tailwind breakpoints | Mobile OK |
| T6 (18/7) | Streaming UI | SSE + typing indicator | Real-time |
| T7 (19/7) | UX testing | Test với 5 người dùng thật | Feedback |
| CN (20/7) | Bug fixes | Fix issues từ UX test | Polish |

**Milestone tuần 5** ✅:
- [x] 30 văn bản trong corpus
- [x] Frontend chat hoàn chỉnh với streaming
- [x] Search + history pages
- [x] Mobile responsive

**Danh sách 30 văn bản (mục tiêu)**:

| # | Văn bản | Loại | Trạng thái |
|---|---------|------|------------|
| 1 | Nghị định 168/2024/NĐ-CP | NĐ | HĐ chính |
| 2 | Luật Trật tự ATGT đường bộ 36/2024 | Luật | HĐ chính |
| 3 | Thông tư 47/2024 (quy chuẩn biển báo) | TT | HĐ chính |
| 4-30 | 27 văn bản liên quan khác | Mix | Phụ |

---

### 📅 TUẦN 6 (21-27/7): Evaluation + Optimization

**Mục tiêu**: Có bảng đánh giá đầy đủ với 3+ ablation variants.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (21/7) | Mở rộng gold set (optional) | +10 câu LLM-gen (Week 1 có 15 manual rồi) | Tăng độ phủ gold set |
| T3 (22/7) | Custom RAGAS-lite | 5 metrics với prompt custom (Citation Correctness làm headline) | `evaluation.py` |
| T3 (22/7) | Test 1 lần với Gemini | Smoke test eval pipeline | Báo cáo đầu tiên |
| T4 (23/7) | Ablation V1: Dense only | Run eval, lưu kết quả | Variant 1 |
| T4 (23/7) | Ablation V2: BM25 only | Run eval, lưu kết quả | Variant 2 |
| T5 (24/7) | Ablation V3: Hybrid RRF | Run eval, lưu kết quả | Variant 3 |
| T5 (24/7) | Ablation V3+OpenAI: Hybrid + GPT-4o-mini | Cost-quality trade-off | Variant 3b |
| T6 (25/7) | Statistical analysis | Paired t-test, Cohen's d, 95% CI | Báo cáo thống kê |
| T7 (26/7) | Tổng hợp báo cáo | Tạo bảng so sánh + failure analysis | `eval_report.md` |
| CN (27/7) | Tối ưu | Adjust prompt, threshold dựa trên kết quả | Improvements |

> **POST-REVIEW A2/B5/L2 fixes**: 
> - V4 (reranker) DROPPED vì MX330 không khả thi
> - V5/V6 (LLM compare) MERGED thành "V3+OpenAI" (so sánh cost-quality)
> - Thêm statistical analysis để bảo vệ significance

**Milestone tuần 6** ✅:
- [x] Gold set 30 câu frozen
- [x] Custom RAGAS-lite (5 metrics) hoạt động
- [x] 3 variants (V1, V2, V3) + V3+OpenAI
- [x] Báo cáo đánh giá có statistical analysis

**Bảng kết quả mẫu**:

| Variant | Faithfulness | Relevancy | Context Prec | Context Recall | Latency P95 |
|---------|--------------|-----------|--------------|----------------|-------------|
| V1: Dense only | ? | ? | ? | ? | ?s |
| V2: BM25 only | ? | ? | ? | ? | ?s |
| V3: Hybrid RRF | ? | ? | ? | ? | ?s |
| V5: Hybrid + Gemini | ? | ? | ? | ? | ?s |
| V6: Hybrid + GPT-4o | ? | ? | ? | ? | ?s |

---

### 📅 TUẦN 7 (28/7-3/8): Deploy + Báo cáo + Bảo vệ

**Mục tiêu**: Deploy production, hoàn thiện báo cáo, sẵn sàng bảo vệ.

| Ngày | Task | Cụ thể | Output |
|------|------|--------|--------|
| T2 (28/7) | Docker prod | Optimize Dockerfile, multi-stage | Image nhỏ |
| T2 (28/7) | Deploy VPS | Oracle Cloud Free Tier hoặc Vultr | Live URL |
| T3 (29/7) | HTTPS + Domain | Let's Encrypt + free domain | https:// |
| T3 (29/7) | Monitoring | Health check endpoint, logs | Uptime |
| T4 (30/7) | Viết báo cáo | 30-50 trang, format theo GVHD | PDF |
| T5 (31/7) | Làm slide | 20-25 slides, demo flow | PPTX |
| T6 (1/8) | Rehearsal | Tập thuyết trình 30 phút | Practice |
| T7 (2/8) | Buffer | Sửa lỗi phát hiện khi rehearsal | Polish |
| **CN (3/8)** | **BẢO VỆ** | **🎓** | **PASS** |

**Milestone tuần 7** ✅:
- [x] Live demo trên production
- [x] Báo cáo PDF hoàn chỉnh
- [x] Slide thuyết trình
- [x] **Bảo vệ thành công** 🎓

---

## 5.3. Sử dụng AI Agent (Claude Code / OpenCode) — Hướng dẫn chi tiết

> **Mục tiêu**: Tăng tốc code, không phải thay thế tư duy.

### 5.3.1. Khi nào DÙNG AI Agent (✅)

| Tình huống | Ví dụ prompt |
|------------|--------------|
| Setup project structure | "Tạo FastAPI project structure với poetry, có folder app/{api,agents,services,db,parsers,models,utils}" |
| Boilerplate code | "Viết class HybridRetriever với methods: index, search, get_top_k" |
| Test cases | "Tạo 20 unit test cho class DocumentParser" |
| README, docs | "Viết README.md cho dự án này" |
| Bug fix | "Lỗi này là gì và fix như thế nào: [paste error]" |
| Refactor | "Refactor function này để dùng async" |

### 5.3.2. Khi nào KHÔNG NÊN dùng AI Agent (❌)

| Tình huống | Lý do |
|------------|-------|
| Custom chunker cho PLVN | Logic nghiệp vụ đặc thù, phải test với PDF thật |
| Legal Reasoning Prompt | Cần hiểu sâu ngữ cảnh, tinh chỉnh từng quy tắc |
| Citation validation | Logic phức tạp, edge cases nhiều |
| Quyết định kiến trúc | Phải hiểu trade-off |
| Đánh giá kết quả ablation | Phải có tư duy phản biện |

### 5.3.3. Workflow đề xuất với AI Agent

```bash
# 1. Khởi tạo session
cd backend
opencode .   # hoặc claude-code

# 2. Mỗi task lớn, tạo 1 session mới
# Tránh context window quá dài

# 3. Luôn paste context cụ thể
# Ví dụ: file path, line range, expected output
```

**Template prompt hiệu quả**:
```text
Bạn là senior Python developer. Tôi cần implement [FEATURE].

Context:
- Dự án: FastAPI + LangChain + ChromaDB
- File cần tạo: backend/app/services/[file].py
- Pattern: các service khác ở backend/app/services/

Yêu cầu:
- Input: ...
- Output: ...
- Edge cases: ...

Code mẫu (nếu có): ...

Trả về:
1. Code đầy đủ
2. Test cases
3. Giải thích các quyết định thiết kế
```

---

## 5.4. Daily Standup

Mỗi tối, ghi vào `docs/daily-log.md`:
```markdown
## T2 (16/6/2026)
- ✅ Done: Setup repo, init FastAPI
- 🚧 In progress: Đọc xong design docs
- ❌ Blocked: -
- 📅 Tomorrow: Setup frontend
- 💡 Learn: Hiểu thêm về LangGraph state machine
```

---

## 5.5. Risk Register (POST-REVIEW A7, A8, B9)

| # | Rủi ro | Xác suất | Tác động | Giải pháp |
|---|--------|----------|----------|-----------|
| R1 | LLM hallucinate số tiền phạt | Cao | **Rất cao** | Prompt "Legal Reasoning" chặt, bắt buộc trích dẫn, Citation Correctness metric, validate_citation node |
| R2 | Parse PDF giữ hierarchy lỗi | **Cao** | Cao | **Custom chunker moved lên Tuần 1**, test với 3 loại VB (Luật, NĐ, TT) |
| R3 | Gemini Free rate-limit (250 RPD) | Trung bình | Trung bình | Retry with backoff, fallback OpenAI, **2.5 queries/min** budget |
| R4 | Gold set test ít (30 câu) | Trung bình | Trung bình | LLM-gen + manual verify ≥ 30, **C6 fix: freeze independently, không tune retriever trên gold** |
| **R5** | **Deadline 3/8 — không kịp code + báo cáo** | **Cao** ⬆ | **Cao** ⬆ | **Scope cut MVP FR-01/02/04/07 + reserve Tuần 7 only cho báo cáo** |
| R6 | Hybrid retrieval không cải thiện so với Dense | Thấp | Trung bình | Baseline V1 (Dense only) để so sánh |
| R7 | Corpus không đủ 30 VB | Thấp | Trung bình | Ưu tiên NĐ 168, Luật 36, các TT liên quan trước |
| ~~R8~~ | ~~HITL impact~~ | ~~Thấp~~ | — | **XÓA (A7): HITL đã defer sang Phase 2** |
| **R9** | **Legal liability khi LLM trả lời sai** | Trung bình | **Cao** | **FR-09 disclaimer bắt buộc, FR-10 effectivity display** |
| **R10** | **Auth thiếu → VPS bị abuse (tốn tiền API, RCE-adjacent)** | Trung bình | Cao | **B9 fix: Bearer token cho admin/ingest/eval** |
| **R11** | **E5 prefix quên → Recall giảm silently** | Cao | Trung bình | **B1 fix: prefix trong embedding contract + unit test** |
| R12 | DuckDuckGo bị rate-limit từ datacenter | Trung bình | Trung bình | Retry 3 lần, fallback "không tìm thấy web" |

---

## 5.6. Definition of Done (DoD)

Một task được coi là hoàn thành khi:

- [ ] Code đã được viết và commit
- [ ] Đã test manual (nếu không có unit test)
- [ ] Không có lỗi syntax/lint (`ruff check` pass)
- [ ] Type hints đầy đủ (`mypy` không warning)
- [ ] Đã update README nếu cần
- [ ] Đã ghi daily log

Một giai đoạn hoàn thành khi:
- [ ] Tất cả milestone checklist pass
- [ ] Có thể demo được cho GVHD
- [ ] Regression test pass (nếu có)
- [ ] **Citation Correctness** được đo và đạt ≥ 0.7 (target)
- [ ] **Disclaimer** xuất hiện trong 100% response

---

## 5.7. Tiến độ hiện tại (Real-time) — POST-REVIEW

> **Ghi chú (A7)**: Phase 1 (Design) mới chỉ done paper. Code chưa bắt đầu.

| Task | Trạng thái | % Done |
|------|------------|--------|
| Phase 1: Design (paper) | ✅ Done | 100% |
| Phase 2: Setup + Chunker | ⏳ Pending (Tuần 1) | 0% |
| Phase 3: Core RAG (V1, V2, V3) | ⏳ Pending (Tuần 2) | 0% |
| Phase 4: Agentic + Eval pipeline | ⏳ Pending (Tuần 3) | 0% |
| Phase 5: Web Fallback + UI cơ bản | ⏳ Pending (Tuần 4) | 0% |
| Phase 6: Frontend + Corpus 30 VB | ⏳ Pending (Tuần 5) | 0% |
| Phase 7: Evaluation (5 metrics × 3 variants) | ⏳ Pending (Tuần 6) | 0% |
| Phase 8: Báo cáo + Slide + Bảo vệ | ⏳ Pending (Tuần 7) | 0% |

> **A7 fix**: HITL removed from scope. Báo cáo dành riêng 1 tuần.

**Cập nhật cuối**: 16/06/2026
