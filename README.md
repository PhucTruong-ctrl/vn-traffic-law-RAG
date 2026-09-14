# VN Traffic Law RAG (VNLRAG)

MVP hỏi đáp pháp luật giao thông đường bộ Việt Nam. Hệ thống hiện gồm trình khám phá nguồn luật và chat có trích dẫn:

```text
Markdown trong manifest -> LangChain Documents -> Qdrant HYBRID cục bộ
                                                   -> ChatOpenRouter -> citations
```

Phạm vi serving hiện tại dùng đúng 17 tài liệu trong `data/sources/manifest.json`. Corpus Markdown, chunks và Qdrant là các artifact local, không được commit vào Git.

## Chạy nhanh

Tạo `.env`, điền credential Supabase/OpenRouter rồi chạy:

```bash
cp .env.example .env
./dev.sh
```

Mở `http://127.0.0.1:3000`. Supabase cung cấp đăng ký, đăng nhập, session chat, message, feedback và bookmark. Browser chỉ nhận public Supabase values; backend cần service-role credentials. Không commit `.env` hoặc API key.

Docker Compose là cách triển khai tùy chọn:

```bash
docker compose --env-file .env -f deploy/compose/compose.release.yml up --build
```

Supabase và OpenRouter vẫn là dependency bên ngoài. Worker, Redis, MinIO và parser service không thuộc runtime MVP hiện tại.

## Corpus 17 tài liệu

`fetch_sources.py` chỉ đọc file được liệt kê trong `data/sources/manifest.json`; script không tự quét toàn bộ `data/corpus/mds/`. Vì vậy số lượng file trong thư mục phải khớp manifest. Nếu đưa thêm file vào corpus mà không kiểm soát nội dung, tài liệu thừa có thể làm nhiễu retrieval, thay đổi kết quả citation và làm các metric evaluation hiện tại giảm.

Snapshot dùng cho ba run mới:

- Manifest SHA256: `ed648933ffa1f26e42cf5e7245bfbfd88a7866640f77d127a97fd0542d36ce90`.
- `data/processed/chunks.jsonl` SHA256: `6bbd72397afa72b9379caaefebdf4e9a60090a09f47ea450c67d1c3418e78ecc`.
- Chi tiết SHA256 của manifest và 17 Markdown nằm trong `data/evaluation/corpus-snapshot-20260915.sha256`.

Kiểm tra file local:

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

Hai danh sách `missing` phải rỗng.

## Crawl và tạo chunks

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

Crawl dừng nếu file bị đánh dấu `MISSING`, `INVALID` hoặc `FAILED`.

Tạo chunks từ đúng manifest:

```bash
cd backend
uv run python scripts/fetch_sources.py \
  --manifest ../data/sources/manifest.json \
  --local-dir ../data/corpus/mds \
  --output ../data/processed/markdown-chunks.jsonl

cp ../data/processed/markdown-chunks.jsonl ../data/processed/chunks.jsonl
```

Kiểm tra chunks:

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

## Tạo index Qdrant HYBRID

```bash
cd backend
uv run python scripts/index.py \
  --chunks ../data/processed/chunks.jsonl \
  --force-recreate \
  --collection traffic_law
```

Index dùng dense embedding qua OpenRouter và sparse BM25 qua FastEmbed. Qdrant local lưu collection `traffic_law` trong `data/processed/qdrant/`. Không chạy đồng thời hai tiến trình index.

Sau khi đổi manifest, đổi Markdown hoặc đổi parser, phải tạo lại chunks và Qdrant. Không dùng collection cũ để kết luận evaluation cho snapshot mới.

## Khởi động và kiểm tra runtime

```bash
./dev.sh
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

Readiness chỉ cho biết Supabase và Qdrant hoạt động. Cần chạy request đã xác thực để kiểm tra status, citation và abstention.

## Legal source explorer

Trang `/legal-sources` liệt kê các văn bản được API cung cấp, hỗ trợ tìm theo nội dung, số hiệu và điều khoản. API:

```text
GET /api/v1/legal-search?q=...
```

Có thể thêm `document_id`, `article`, `clause`, `point` và `limit`. Explorer chỉ đọc corpus local và không tự tìm luật trên web tại thời điểm query.

## Chat có grounding và citation

Chat lấy chunks pháp luật, kiểm tra evidence rồi mới gửi context được phép cho model. Status công khai gồm:

- `VERIFIED`
- `GREETING`
- `OUT_OF_SCOPE`
- `CORPUS_NOT_COVERED`
- `INSUFFICIENT_EVIDENCE`
- `WORKFLOW_UNAVAILABLE`

`CORPUS_NOT_COVERED` nghĩa là câu hỏi nằm ngoài corpus đang phục vụ. `INSUFFICIENT_EVIDENCE` nghĩa là hệ thống không đủ căn cứ để trả lời chắc chắn. Citation lấy từ metadata của chunk và mở được passage tương ứng.

Hiện hệ thống chưa xử lý tốt câu hỏi penalty thiếu loại phương tiện. Ví dụ `Mức phạt khi vượt đèn đỏ là bao nhiêu?` vẫn có thể trả `VERIFIED` với citation không phù hợp. Đây là gap an toàn cần giải quyết trước release.

## API chính

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

## Evaluation 40 cases

Bộ test là `data/evaluation/thesis-gold-40.json`, gồm 40 case thuộc 8 nhóm. Có 34 case nằm trong corpus hiện tại và 6 case được đánh dấu `CORPUS_NOT_COVERED`:

```text
00, 15, 16, 17, 18, 19
```

Evaluator đo retrieval, document/article/clause/point coordinates, citation validity, abstention và latency. `answer_correctness_manual` vẫn cần người đánh giá, không được suy ra từ các metric tự động.

### Ba run sau khi rebuild Qdrant

Cả ba run dùng cùng manifest 17 tài liệu, cùng chunks snapshot, collection Qdrant mới, `top_k=5` và API local đã xác thực.

| Metric | Run 1 | Run 2 | Run 3 |
|---|---:|---:|---:|
| Total rows | 40 | 40 | 40 |
| Covered rows | 34 | 34 | 34 |
| Request errors | 0 | 0 | 0 |
| `CORPUS_NOT_COVERED` | 00, 15–19 | 00, 15–19 | 00, 15–19 |
| Retrieval hit@5 | 0.4167 | 0.4167 | 0.4167 |
| Citation validity | 0.9412 | 0.8824 | 0.9412 |
| Abstention accuracy | 0.8529 | 0.7941 | 0.8529 |
| Document accuracy | 0.5417 | 0.5417 | 0.5417 |
| Article accuracy | 0.5000 | 0.5000 | 0.5000 |
| Clause accuracy | 0.3846 | 0.3846 | 0.3846 |
| Point accuracy | 0.0000 | 0.0000 | 0.0000 |
| Mean latency | 16.82 s | 17.77 s | 19.75 s |
| P95 latency | 40.88 s | 42.10 s | 50.17 s |

Artifacts:

```text
data/evaluation/rebuild-20260915-run1/
data/evaluation/rebuild-20260915-run2/
data/evaluation/rebuild-20260915-run3/
data/evaluation/corpus-snapshot-20260915.sha256
```

Ba run cho thấy tọa độ structural ổn định, nhưng kết quả generation vẫn dao động. Các metric hiện chưa đạt release gate:

- Retrieval hit@5 cần `>= 0.80`, hiện `0.4167`.
- Citation validity cần `>= 0.95`, hiện `0.8824–0.9412`.
- Abstention cần `>= 0.90`, hiện `0.7941–0.8529`.
- Document/article/clause/point lần lượt cần `>= 0.85/0.85/0.80/0.75`, hiện `0.5417/0.5000/0.3846/0.0000`.
- P95 latency hiện `40.88–50.17s`.
- Chưa có manual semantic correctness.

### Sáu câu hỏi smoke đã chạy

Các câu hỏi được gửi qua API local với user đã xác thực, sau khi rebuild Qdrant:

| Câu hỏi | Kết quả observed | Gap |
|---|---|---|
| `Xe máy vượt đèn đỏ bị phạt bao nhiêu?` | `VERIFIED`, citation NĐ 100 Điều 17 | Citation không trỏ đúng quy định vượt đèn đỏ |
| `Ô tô vượt đèn đỏ bị phạt bao nhiêu?` | `VERIFIED`, NĐ 100 Điều 5 Khoản 5 Điểm a | Kết quả phù hợp hơn nhưng cần kiểm tra amount trong answer |
| `Không đội mũ bảo hiểm khi đi xe máy bị phạt thế nào?` | `VERIFIED`, NĐ 100 Điều 6 Khoản 2 Điểm i | Citation đúng hành vi, cần kiểm tra amount |
| `Điện thoại khi lái xe máy bị phạt bao nhiêu?` | `VERIFIED`, NĐ 100 Điều 17 | Citation không phù hợp với hành vi dùng điện thoại |
| `Nồng độ cồn khi lái xe máy bị phạt bao nhiêu?` | `INSUFFICIENT_EVIDENCE`, không citation | Corpus/retrieval chưa trả được căn cứ |
| `Mức phạt khi vượt đèn đỏ là bao nhiêu?` | `VERIFIED`, NĐ 168 Điều 15 | Thiếu loại xe nhưng vẫn trả lời; citation sai ngữ cảnh |

Smoke suite chưa đạt. Hệ thống cần hỏi lại loại phương tiện hoặc abstain khi câu hỏi penalty không nêu rõ xe máy, ô tô hay nhóm xe khác.

## Các gap hiện tại

### 1. Parser mất cấu trúc pháp lý

`nd-119-2024.md` có marker OCR/HTML bị tách dòng, ví dụ `1` rồi `.`, hoặc `a` rồi `)`. Parser hiện nhận marker inline như `1. Nội dung` và `a) Nội dung`, nên một số khoản và điểm không đi vào metadata.

Hậu quả đã đo được:

- 8 expected point coordinates bị thiếu trong chunks.
- Point accuracy bằng `0` ở cả ba run.
- Case exact reference Điều 11 Khoản 4 và Điều 13 Khoản 2 Điểm b không tìm thấy evidence.

### 2. Corpus mở rộng làm thay đổi evaluation

Thêm hơn 17 tài liệu vào `data/corpus/mds/` mà không thay đổi thiết kế evaluation sẽ làm tăng candidate documents và có thể làm loãng retrieval. Các văn bản khác phiên bản, văn bản sửa đổi, tài liệu không cùng lĩnh vực hoặc Markdown có cấu trúc khác có thể:

- đẩy provision đúng ra khỏi top-k;
- tạo citation hợp lệ về mặt format nhưng sai điều khoản;
- thay đổi abstention behavior;
- làm metric thấp hơn dù code không đổi;
- khiến run mới không so sánh được với baseline 17 tài liệu.

Vì vậy 17-document snapshot hiện tại là boundary của evaluation này. Không gọi kết quả của corpus mở rộng là kết quả tương đương nếu chưa tạo gold set, manifest, chunk snapshot, Qdrant collection và metric baseline mới.

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

Không commit credential, raw bearer token, `.env`, hoặc Qdrant binary database.

## Hướng refactor cần có trước khi mở rộng corpus

Không nên thêm document vào manifest trước khi có các seam sau:

1. **Corpus registry và snapshot identity**: manifest phải có version, source hash, effective date và trạng thái văn bản; index phải ghi hash của manifest/chunks/model.
2. **Parser normalization**: chuẩn hóa marker tách dòng trước khi tạo metadata, giữ lại raw text để audit và phát hiện mất Điều/Khoản/Điểm.
3. **Structure coverage gate**: từ chối hoặc cảnh báo document nếu tỷ lệ article/clause/point parse được thấp hơn ngưỡng; không silently index tài liệu lỗi cấu trúc.
4. **Document-level retrieval isolation**: hỗ trợ filter theo document family, vehicle scope, effective date và source status trước khi semantic ranking.
5. **Gold set theo corpus version**: mỗi corpus snapshot mở rộng phải có expected coordinates và evaluation baseline riêng; không trộn kết quả với baseline 17 tài liệu.
6. **Clarification gate cho penalty**: query thiếu vehicle scope phải hỏi lại hoặc abstain, không lấy citation gần nghĩa rồi trả `VERIFIED`.
7. **Raw retrieval metrics**: đo hit@k từ top-k retriever trước generation, tách khỏi citation coordinates của final answer.
8. **Release smoke matrix**: giữ sáu câu hỏi smoke và thêm case cho từng vehicle class, penalty, temporal validity, missing evidence và citation mismatch.

## Chạy evaluation

Chạy API local trước, sau đó:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --top-k 5 \
  --timeout 300 \
  --output-dir data/evaluation/thesis-run
```

Review raw JSONL:

```bash
uv run --project backend python backend/scripts/review_thesis_answers.py \
  data/evaluation/thesis-run/<run-id>.jsonl \
  --output data/evaluation/thesis-run/<run-id>.reviews.jsonl
```

## Kiểm tra

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

## Phạm vi chưa cam kết

MVP hiện không cam kết phủ toàn bộ pháp luật giao thông Việt Nam, không query-time web retrieval, không tự suy luận ngoài evidence và chưa đạt release gate nêu trên. Runtime được hỗ trợ là manifest Markdown 17 tài liệu, LangChain Documents, Qdrant HYBRID cục bộ, ChatOpenRouter, citation metadata và Supabase auth/persistence.

## License

MIT License, mã nguồn mở cho mục đích học thuật.
