# VN Traffic Law RAG (VNLRAG)

MVP hỏi đáp pháp luật giao thông đường bộ Việt Nam. Hệ thống gồm trình khám phá nguồn luật và chat có trích dẫn. Phạm vi serving hiện tại dùng đúng 17 tài liệu trong `data/sources/manifest.json`; corpus Markdown, đoạn dữ liệus và Qdrant là artifact local, không commit vào Git.

## Chạy nhanh

Tạo `.env`, điền credential Supabase/OpenRouter rồi chạy:

```bash
cp .env.example .env
./dev.sh
```

Docker Compose là cách triển khai tùy chọn:

```bash
docker compose --env-file .env -f deploy/compose/compose.release.yml up --build
```

## Kiến trúc

```mermaid
flowchart LR
  A[Chat + history] --> B[Analyzer<br/>strict JSON]
  B --> C[standalone_query<br/>expanded_queries ≤3]
  C --> D[Multi-query retrieval<br/>Qdrant dense + sparse<br/>top_k=8/query]
  D --> E[RRF fuse<br/>1/(60+rank)]
  E --> F[Enrichment<br/>siblings, sanctions, references]
  F --> G[Relevance filter<br/>graceful fallback]
  G --> H[Generator]
  H --> I[Citation sanitation<br/>metadata matching]
  I --> J[Answer / status]
```

- Analyzer dùng LLM trước với `AnalyzerOutput` strict JSON gồm `category`, `intent`, `vehicle_type`, `standalone_query` và tối đa 3 `expanded_queries`; nếu lỗi hoặc timeout, dùng phương án dự phòng tất định.
- Mỗi truy vấn mở rộng tìm top 8 bằng truy xuất hybrid Qdrant (dense + sparse). RRF dùng trọng số `1/(60+rank)`, giới hạn candidate theo cấu hình và tối đa 3 đoạn dữ liệu cho mỗi Điều/Khoản.

```bash
python - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("data/sources/manifest.json").read_text())
listed = {entry["file"] for entry in manifest["documents"]}
actual = {
    path.name for path in Path("data/corpus/mds").glob("*.md")
    if path.name != "README.md"
}
print("manifest:", len(listed))
print("corpus:", len(actual))
print("missing from manifest:", sorted(actual - listed))
print("missing on disk:", sorted(listed - actual))
assert listed == actual
PY
```

Crawl corpus mặc định:

```bash
.venv/bin/python scripts/fill_traffic_corpus.py \
  --dir data/corpus/mds \
  --include-recommended
```

Muốn lấy thêm văn bản hiện hành năm 2026:

```bash
.venv/bin/python scripts/fill_traffic_corpus.py \
  --dir data/corpus/mds \
  --include-recommended \
  --include-current-2026
```

Nên chạy cleanup trước khi ingest:

```bash
python scripts/clean_traffic_corpus.py \
  --dir data/corpus/mds \
  --dry-run

python scripts/clean_traffic_corpus.py \
  --dir data/corpus/mds
```

Tạo đoạn dữ liệus từ đúng manifest:

```bash
cd backend
uv run python scripts/fetch_sources.py \
  --manifest ../data/sources/manifest.json \
  --local-dir ../data/corpus/mds \
  --output ../data/processed/markdown-chunks.jsonl

cp ../data/processed/markdown-chunks.jsonl ../data/processed/chunks.jsonl
```

```bash
cd ..
python - <<'PY'
import json
from pathlib import Path

chunks = Path("data/processed/chunks.jsonl")
ids = {
    json.loads(line)["metadata"]["document_id"]
    for line in chunks.read_text(encoding="utf-8").splitlines()
    if line.strip()
}
files = {
    path.stem for path in Path("data/corpus/mds").glob("*.md")
    if path.name != "README.md"
}
print("chunk documents:", len(ids))
print("corpus documents:", len(files))
print("corpus without chunks:", sorted(files - ids))
assert files == ids
PY
```

Hoặc chỉ chạy backend:

```bash
cd backend
uv run uvicorn app.main:app --reload
```

Kiểm tra readiness:

```bash
curl -i http://127.0.0.1:8000/api/v1/health/ready
```

```text
GET /api/v1/legal-search?q=...
```

- `VERIFIED`
- `GREETING`
- `OUT_OF_SCOPE`
- `CORPUS_NOT_COVERED`
- `INSUFFICIENT_EVIDENCE`
- `WORKFLOW_UNAVAILABLE`

- `GET /api/v1/health`, `/api/v1/health/live`, `/api/v1/health/ready`
- `POST /api/v1/chat`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET/POST /api/v1/chats`
- `GET/PATCH/DELETE /api/v1/chats/{session_id}`
- `POST /api/v1/chats/{session_id}/messages`
- `POST /api/v1/chats/{session_id}/messages/{message_id}/feedback`
- `POST /api/v1/chats/{session_id}/bookmarks`
- `GET /api/v1/saved`
- `GET /api/v1/legal-documents`
- `GET /api/v1/legal-documents/{document_id}`
- `GET /api/v1/legal-documents/{document_id}/provisions`
- `GET /api/v1/legal-search`

## Mô hình và cấu hình

```text
GENERATION_MODEL             model sinh câu trả lời
ANALYZER_MODEL               model phân tích (rỗng = dùng GENERATION_MODEL)
ANALYZER_TIMEOUT_SECONDS     ngân sách riêng cho analyzer (mặc định 15s)
GENERATION_MAX_RETRIES       số lần thử lại generation
EMBEDDING_MODEL              model embedding
EMBEDDING_TIMEOUT_SECONDS    ngân sách gọi embedding; quá hạn thì dùng chỉ mục sparse nội bộ (mặc định 8s)
EMBEDDING_MAX_RETRIES        số lần thử lại embedding (mặc định 0)
```

Bảng 1 , bộ phân tích yêu cầu (6 case: 4 legal + 1 follow-up có history + 1 out-of-scope; tiêu chí JSON hợp lệ / category đúng / vehicle đúng / độ trễ):

| model                                       | JSON hợp lệ | category đúng | vehicle đúng | trễ TB |
| ------------------------------------------- | ----------: | ------------: | -----------: | -----: |
| `google/gemini-2.5-flash-lite`              |         6/6 |           6/6 |          6/6 |   1.3s |
| `mistralai/mistral-small-24b-instruct-2501` |         6/6 |           6/6 |          6/6 |   3.6s |
| `qwen/qwen3-30b-a3b-instruct-2507`          |         6/6 |           6/6 |          6/6 |   4.1s |
| `openai/gpt-oss-20b`                        |         5/6 |           5/6 |          5/6 |  11.2s |

Bảng 2 , bộ sinh câu trả lời (5 lần lặp, câu lệnh cho mô hình thật với 15 đoạn dữ liệu tìm kiếm căn cứ):

| model                                       | thành công |   p50 |   max | ký tự |
| ------------------------------------------- | ---------: | ----: | ----: | ----: |
| `google/gemini-2.5-flash-lite`              |        5/5 |  1.2s |  2.2s |   551 |
| `mistralai/mistral-small-24b-instruct-2501` |        5/5 |  4.8s | 11.2s |   524 |
| `openai/gpt-oss-20b`                        |        5/5 |  6.3s |  6.6s |   764 |
| `deepseek/deepseek-v4-flash-0731`           |        5/5 | 24.3s | 56.6s |   279 |

Bảng 3 , số nhà cung cấp mô hình và tỉ lệ hoạt động (OpenRouter endpoints API):

| model                                                                                                                                                                                                                                                                                                                                                                      | số nhà cung cấp mô hình | ghi chú                                                                          |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------: | -------------------------------------------------------------------------------- |
| `google/gemini-2.5-flash-lite`                                                                                                                                                                                                                                                                                                                                             |                       5 | Google AI Studio tỉ lệ hoạt động 99.998%, giá $0.05/$0.20 mỗi 1M token           |
| `openai/gpt-oss-20b`                                                                                                                                                                                                                                                                                                                                                       |                      14 | $0.02/$0.10, nhiều nhà cung cấp mô hình ≥99.9%                                   |
| `qwen/qwen3-30b-a3b-instruct-2507`                                                                                                                                                                                                                                                                                                                                         |                       5 | có nhà cung cấp mô hình ở trạng thái degraded                                    |
| `mistralai/mistral-small-24b-instruct-2501`                                                                                                                                                                                                                                                                                                                                |                       1 | chỉ DeepInfra; E2E độ trễ P90 27.8s, P95 40.0s, tỉ lệ lỗi định dạng đầu ra 2.35% |
| `deepseek/deepseek-v4-flash-0731`                                                                                                                                                                                                                                                                                                                                          |                      27 | ổn định nhưng chậm nhất ở generation                                             |
| Đã chọn `GENERATION_MODEL=google/gemini-2.5-flash-lite` và `ANALYZER_MODEL=google/gemini-2.5-flash-lite`: bộ phân tích yêu cầu 6/6, generation p50 1.2s / max 2.2s trên 5 lần lặp, 5 nhà cung cấp mô hình nên `allow_fallbacks` có tác dụng, giá thuộc nhóm thấp. `mistral-small-24b` từng gây `generation_failed` do chỉ có 1 nhà cung cấp mô hình và bị 429 từ upstream. |

## Ma trận acceptance

Đo trên backend đang chạy `GENERATION_MODEL=ANALYZER_MODEL=google/gemini-2.5-flash-lite`, gọi `POST /api/v1/chat` qua API thật, cây mã đóng băng (không sửa file trong lúc đo).

| nhóm                                  | câu hỏi                                                              | status       | reason_code  |     citations |                           giây |
| ------------------------------------- | -------------------------------------------------------------------- | ------------ | ------------ | ------------: | -----------------------------: |
| A-fresh                               | Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?                     | VERIFIED     | ,            |             6 |                          25.2s |
| A-fresh                               | Ô tô vượt đèn đỏ bị phạt bao nhiêu?                                  | VERIFIED     | ,            |             4 |                          11.3s |
| A-fresh                               | Xe máy được chở tối đa bao nhiêu người?                              | VERIFIED     | ,            |             3 |                           9.5s |
| A-fresh                               | Ban đêm có bắt buộc bật đèn chiếu sáng không?                        | VERIFIED     | ,            |            17 |                          16.7s |
| A-fresh                               | Bấm còi trong khu dân cư có bị phạt không?                           | VERIFIED     | ,            |            16 |                          23.1s |
| A-fresh                               | Quay đầu hoặc lùi xe có bị phạt không?                               | VERIFIED     | ,            |             9 |                          22.4s |
| B-session (6 câu A trong một session) | 6/6 VERIFIED                                                         | VERIFIED     | ,            | 4/4/5/15/14/5 | 12.0/12.1/25.5/14.7/11.2/13.0s |
| C-multi-intent                        | Xe máy vừa vượt đèn đỏ vừa chở 3 người thì bị phạt sao?              | VERIFIED     | ,            |             1 |                          11.1s |
| C-multi-intent                        | Vượt đèn đỏ bị phạt bao nhiêu tiền và trừ mấy điểm giấy phép lái xe? | VERIFIED     | ,            |             1 |                          11.5s |
| C-multi-intent                        | Quy định về mũ bảo hiểm và mức phạt khi không đội là gì?             | VERIFIED     | ,            |            16 |                          17.6s |
| D-cross-ref                           | Điều 6 Nghị định 168/2024 quy định gì?                               | VERIFIED     | ,            |             4 |                           6.1s |
| D-cross-ref                           | Điều 7 Khoản 3 Nghị định 168/2024 quy định gì?                       | VERIFIED     | ,            |             1 |                           7.5s |
| D-cross-ref                           | Điều 5 Nghị định 100/2019 quy định gì?                               | VERIFIED     | ,            |             1 |                           6.1s |
| E-followup                            | Ô tô vượt đèn đỏ bị phạt bao nhiêu?                                  | VERIFIED     | ,            |             4 |                          11.0s |
| E-followup                            | … -> Còn xe máy thì sao?                                             | VERIFIED     | ,            |             1 |                          13.9s |
| E-followup                            | Đi xe máy không đội mũ bảo hiểm bị phạt thế nào?                     | VERIFIED     | ,            |             6 |                          14.2s |
| E-followup                            | … -> Vậy còn ô tô?                                                   | VERIFIED     | ,            |             6 |                          25.2s |
| F                                     | Mức phạt khi đi xe buýt không đúng tuyến là bao nhiêu?               | VERIFIED     | ,            |             3 |                           8.7s |
| F                                     | Thời tiết Hà Nội ngày mai thế nào?                                   | OUT_OF_SCOPE | out_of_scope |             0 |                           2.7s |

### Hạn chế đã đo

- Trạng thái: 22/22 lần gọi ra đúng mã trạng thái (VERIFIED cho câu trong phạm vi, OUT_OF_SCOPE cho câu ngoài phạm vi); không còn `generation_failed` hay `insufficient_evidence` ngoài dự kiến. Đây là đánh giá theo trạng thái, khác với xác nhận chất lượng nội dung từng câu (xem hạn chế follow-up bên dưới).
- Độ trễ sau khi nâng song song truy xuất: 2.7, 25.5s mỗi câu.
- Follow-up `Vậy còn ô tô?` sau câu hỏi mũ bảo hiểm chưa đúng ý người hỏi: câu hỏi này mơ hồ vì không có quy định mũ bảo hiểm cho ô tô. Đo hai cách xử lý đều cho kết quả chung về ô tô (dây an toàn) , bỏ hành vi (`Mức phạt đối với ô tô bao nhiêu?`, 1 citation) và giữ hành vi (`… đối với hành vi không đội mũ bảo hiểm …`, 5 citation) , nên nguyên nhân nằm ở câu hỏi thiếu hành vi, khác với ở resolver. Hướng đúng là hỏi lại hành vi cụ thể thay vì trả quy định ô tô bất kỳ; chưa triển khai.
- `Điều 7 Khoản 3 Nghị định 168/2024` và `Điều 5 Nghị định 100/2019` trước đây trả `reference_not_found`; sau khi sửa parser thứ tự `Điều … Khoản …` cả hai đã VERIFIED.
- Case "xe buýt không đúng tuyến" được kỳ vọng thiếu căn cứ trong ma trận cũ, nhưng corpus có khoản 1 Điều 25 Nghị định 168/2024 nên kết quả VERIFIED là đúng.

## Evaluation 40 cases

Run4 của pipeline v2 (`GENERATION_MODEL=ANALYZER_MODEL=google/gemini-2.5-flash-lite`, `top_k=5`, run `20260915T075654Z`) có 34/40 case được corpus bao phủ; 6 case bị loại vì corpus chưa bao phủ: `thesis-gold-40-00`, `thesis-gold-40-15`..`thesis-gold-40-19`. `multi_intent` có count 0 vì toàn bộ case thuộc danh sách bị loại. `answer_correctness_manual` chưa chấm.

`follow_up` có `document_accuracy=0.0` vì runner gửi từng câu độc lập, không kèm history. `insufficient_evidence` có `abstention_accuracy=0.0` (5/5 vẫn trả lời). Tài liệu chỉ ghi kết quả của lần chạy mới nhất; artifact: `data/evaluation/rebuild-20260915-run4/20260915T075654Z.aggregate.json`.

## Các gap hiện tại

### 1. Parser mất cấu trúc pháp lý

`nd-119-2024.md` có marker OCR/HTML bị tách dòng, ví dụ `1` rồi `.`, hoặc `a` rồi `)`. Parser hiện nhận marker inline như `1. Nội dung` và `a) Nội dung`, nên một số khoản và điểm không đi vào metadata.

Hậu quả đã đo được:

- 8 expected point coordinates bị thiếu trong đoạn dữ liệus.
- Point độ chính xác bằng `0` ở cả ba run.
- Case exact reference Điều 11 Khoản 4 và Điều 13 Khoản 2 Điểm b không tìm thấy evidence.

### 2. Corpus mở rộng làm thay đổi evaluation

Thêm hơn 17 tài liệu vào `data/corpus/mds/` mà không thay đổi thiết kế evaluation sẽ làm tăng candidate documents và có thể làm loãng truy xuất. Các văn bản khác phiên bản, văn bản sửa đổi, tài liệu không cùng lĩnh vực hoặc Markdown có cấu trúc khác có thể:

- đẩy provision đúng ra khỏi top-k;
- tạo citation hợp lệ về mặt format nhưng sai điều khoản;
- thay đổi từ chối trả lời behavior;
- làm metric thấp hơn dù code không đổi;
- khiến run mới không so sánh được với baseline 17 tài liệu.

Vì vậy 17-document snapshot hiện tại là boundary của evaluation này. Không gọi kết quả của corpus mở rộng là kết quả tương đương nếu chưa tạo gold set, manifest, đoạn dữ liệu snapshot, Qdrant collection và metric baseline mới.

### 3. Artifact cũ không đủ để reproduce

Các run trước được tạo từ Qdrant/corpus snapshot khác. Chỉ có Git commit không đủ vì nhiều Markdown và processed artifacts đang local/ignored. Mỗi release run cần lưu tối thiểu:

```text
git commit
manifest SHA256
17 Markdown SHA256
chunks.jsonl SHA256
embedding model
Qdrant collection identity
thesis gold-set version
```

## Chạy evaluation

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --top-k 5 \
  --timeout 300 \
  --output-dir data/evaluation/thesis-run
```

```bash
uv run --project backend python backend/scripts/review_thesis_answers.py \
  data/evaluation/thesis-run/<run-id>.jsonl \
  --output data/evaluation/thesis-run/<run-id>.reviews.jsonl
```

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
cd ../frontend
npm run lint
npm run typecheck
npm run build
npm run format:check
```

## License

MIT License, mã nguồn mở cho mục đích học thuật.
