# VN Traffic Law RAG (VNLRAG)

Runnable MVP for Vietnamese traffic-law questions. The active product combines a
dual-source legal explorer with grounded chat:

```text
Markdown manifest + local PDFs -> legal documents/provisions -> local Qdrant HYBRID
                                                        -> ChatOpenRouter -> citations
```

## Quick start

Canonical local startup uses `dev.sh`:

```bash
cp .env.example .env
# Fill server and public Supabase/OpenRouter values in .env.
./dev.sh
```

Open `http://127.0.0.1:3000`. Supabase provides registration/login and stores
profiles, chat sessions, messages, feedback, and bookmarks. Browser receives
only public Supabase values; backend requires service-role credentials. Never
commit `.env` or keys.

Docker Compose is optional deployment tooling and currently starts only the
frontend, backend, and Qdrant services:

```bash
docker compose --env-file .env -f deploy/compose/compose.release.yml up --build
```

Supabase/PostgreSQL and OpenRouter remain external dependencies when configured;
worker, Redis, MinIO, and parser services are not part of the active MVP runtime.

## Nạp corpus và lập chỉ mục Qdrant

Chạy các lệnh từ thư mục gốc của repo. Giữ `.env` ở thư mục gốc. Backend tự
đọc file này khi khởi động. Không commit `.env` hoặc API key.

### 1. Crawl tài liệu pháp luật thành Markdown

Crawler tải corpus mặc định và nhóm tài liệu được khuyến nghị vào
`data/corpus/mds/`:

```bash
.venv/bin/python scripts/fill_traffic_corpus.py \
  --dir data/corpus/mds \
  --include-recommended
```

Với các văn bản sửa đổi hiện hành năm 2026, thêm:

```bash
.venv/bin/python scripts/fill_traffic_corpus.py \
  --dir data/corpus/mds \
  --include-recommended \
  --include-current-2026
```

Crawl riêng một tài liệu khi cần sửa hoặc tải lại:

```bash
.venv/bin/python scripts/fill_traffic_corpus.py \
  --dir data/corpus/mds \
  --only nd-44-2024.md
```

Crawler kiểm tra số hiệu văn bản, độ dài tối thiểu và số lượng điều. Dừng xử lý
nếu có file `MISSING`, `INVALID` hoặc `FAILED`.

### 2. Đồng bộ manifest với các file Markdown

`fetch_sources.py` chỉ đọc các file được liệt kê trong
`data/sources/manifest.json`; script không tự quét toàn bộ thư mục. Mỗi file
Markdown trong corpus, trừ `README.md`, phải có một entry trong manifest. Giá trị
`file` phải trùng chính xác tên file.

Kiểm tra coverage:

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
assert actual == listed
PY
```

Hai danh sách `missing` phải rỗng.

### 3. Tạo chunks JSONL chuẩn

Lệnh trên ghi các chunk tương thích với LangChain. Số chunk phải lớn hơn 0.
Sau đó kiểm tra coverage của document:

```bash
cd ..
python - <<'PY'
import json
from pathlib import Path

chunks = Path("data/processed/markdown-chunks.jsonl")
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

### 4. Tạo hoặc thay mới index Qdrant HYBRID

```bash
cd backend
uv run python scripts/index.py \
  --chunks ../data/processed/markdown-chunks.jsonl \
  --force-recreate \
  --collection traffic_law
```

Lệnh này tạo dense embedding qua OpenRouter và sparse vector BM25 bằng
FastEmbed. Với cấu hình local mặc định, Qdrant lưu collection `traffic_law`
trong `data/processed/qdrant/`. `--force-recreate` xoá và tạo lại collection
đã chỉ định. Không chạy đồng thời hai tiến trình index.

### 5. Khởi động và kiểm tra backend/frontend

Chạy từ thư mục gốc:

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

Readiness yêu cầu Supabase và Qdrant hoạt động. Lệnh index thành công chưa đủ
để xác nhận chat đã xác thực, citation và frontend hoạt động.

Authenticated six-question verification is required after rebuilding Qdrant. The current runtime test matrix is documented in the release notes and must report status, citations, and abstention reason for every question.

Khi đã có đủ Markdown và manifest, quy trình local đầy đủ là:

```bash
# Từ thư mục gốc
.venv/bin/python scripts/fill_traffic_corpus.py \
  --dir data/corpus/mds \
  --include-recommended

python scripts/clean_traffic_corpus.py \
  --dir data/corpus/mds \
  --dry-run

python scripts/clean_traffic_corpus.py \
  --dir data/corpus/mds

python - <<'PY'
import json
from pathlib import Path

manifest = json.loads(Path("data/sources/manifest.json").read_text())
listed = {entry["file"] for entry in manifest["documents"]}
actual = {
    path.name for path in Path("data/corpus/mds").glob("*.md")
    if path.name != "README.md"
}
assert listed == actual, (sorted(actual - listed), sorted(listed - actual))
PY

cd backend
uv run python scripts/fetch_sources.py \
  --manifest ../data/sources/manifest.json \
  --local-dir ../data/corpus/mds \
  --output ../data/processed/markdown-chunks.jsonl

cp ../data/processed/markdown-chunks.jsonl ../data/processed/chunks.jsonl

uv run python scripts/index.py \
  --chunks ../data/processed/chunks.jsonl \
  --force-recreate \
  --collection traffic_law

cd ..
./dev.sh
```

## Legal source explorer

The `/legal-sources` page lists documents exposed by the legal API and supports
text, document-number, and article filtering. API-backed search is available at
`GET /api/v1/legal-search?q=...` with optional `document_id`, `article`, `clause`,
`point`, and bounded `limit` filters. Document and provision routes, together with
citation metadata, provide deep links to a provision or its Markdown/PDF passage.
Markdown sources are rendered as structured legal text; PDF sources are rendered
in the in-app PDF viewer with page navigation, zoom, and citation-coordinate
highlighting when metadata is available. The explorer is read-only and corpus-only:
it does not perform query-time web retrieval.


## Grounded chat and citations

Set `OPENROUTER_API_KEY` and optionally `OPENROUTER_BASE_URL` in `.env`.
`GENERATION_MODEL` selects the configured ChatOpenRouter model.

Chat requests retrieve legal chunks, apply the exact deterministic evidence-completeness
gate, then send only supported context to the configured model. The public response
statuses are `VERIFIED`, `GREETING`, `OUT_OF_SCOPE`, `CORPUS_NOT_COVERED`,
`INSUFFICIENT_EVIDENCE`, and `WORKFLOW_UNAVAILABLE`; they are not collapsed into one
generic failure. `CORPUS_NOT_COVERED` means a traffic-law question is outside the
serving corpus, not that the service will search the web. Insufficient evidence
abstains rather than inventing facts. Responses expose citations assembled from
document metadata, and selecting one opens the corresponding source passage.
The browser bounds a chat request to 120 seconds by default; set
`NEXT_PUBLIC_CHAT_TIMEOUT_MS` to override that limit.


## API routes

- `GET /api/v1/health`, `/api/v1/health/live`, `/api/v1/health/ready`
- `POST /api/v1/chat`
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `GET /api/v1/auth/me`
- `GET/POST /api/v1/chats`
- `GET/PATCH/DELETE /api/v1/chats/{session_id}`
- `POST /api/v1/chats/{session_id}/messages`
- `POST /api/v1/chats/{session_id}/messages/{message_id}/feedback`
- `POST /api/v1/chats/{session_id}/bookmarks` (saved Q&A snapshot)
- `GET /api/v1/saved` (also `/bookmarks`), bookmark status, and deletion routes
- `GET /api/v1/legal-documents`
- `GET /api/v1/legal-documents/{document_id}`
- `GET /api/v1/legal-documents/{document_id}/provisions`
- `GET /api/v1/legal-search`
## Thesis evaluation (40 cases)

The reproducible thesis set is `data/evaluation/thesis-gold-40.json` (40
cases, eight categories). The runner scores retrieval, expected legal
locations, citation validity, abstention behavior, and latency. Semantic answer
correctness remains a separate human-review field and is never inferred from
automatic metrics.

### Release candidate result — 2026-09-14

The release candidate was exercised against the authenticated local API
(`POST /api/v1/chat`) with `top_k=5`, using the prescribed `dev.sh` runtime.
Backend and frontend checks passed:

- Backend: Ruff check, Ruff format check, mypy, and **161 tests passed**.
- Frontend: lint with 0 errors, typecheck, production build, and Prettier
  format check passed. Two existing React hook warnings remain.
- API smoke: authenticated exact-reference request returned HTTP 200 with
  citations in 8.73 seconds.

The final 40-row artifact was rescored with explicit corpus-gap handling:

- Total rows: **40**.
- Covered rows: **34**.
- Explicitly `CORPUS_NOT_COVERED`: `00`, `15`, `16`, `17`, `18`, `19`.
- Covered-case request errors: **0**.
- Citation validity: **1.0**; invalid citation rate: **0%**.
- Abstention accuracy: **0.9118**.
- Retrieval hit@5: **0.3333**.
- Document/article accuracy: **0.5833** each.
- Clause accuracy: **0.5385**.
- Point accuracy: **0.25**.
- Mean latency: **13.13 s**; P95: **24.11 s**.

Artifacts:

- Committed release report: [`docs/evaluation/release-candidate-20260914.md`](docs/evaluation/release-candidate-20260914.md).
- Raw rows and aggregate are reproducible with the command in that report.

This is **release-ready for the covered corpus and current MVP runtime**. It is
not a claim of complete Vietnamese traffic-law coverage or full semantic
certification: `answer_correctness_manual` remains `N/A` because full human
semantic review was not supplied. The committed release evidence report
contains the current scope, metrics, limitations and reproduction command.

Run against the local chat endpoint:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --output-dir data/evaluation/thesis-run
```

Or score an existing prediction JSONL:

```bash
uv run --project backend python backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --predictions path/to/predictions.jsonl \
  --output-dir data/evaluation/thesis-run
```

Review the generated raw JSONL interactively:

```bash
uv run --project backend python backend/scripts/review_thesis_answers.py \
  data/evaluation/thesis-run/<run-id>.jsonl \
  --output data/evaluation/thesis-run/<run-id>.reviews.jsonl
```

For scripted review, pass `--non-interactive --input review-decisions.jsonl`;
each input row contains `case_id`, `answer_correctness_manual` (`pass` or
`fail`), and optional `notes`. Use `--help` on both scripts for the complete,
authoritative option list. No evaluation scores are claimed here.

## Checks

```bash
uv run --project backend python backend/scripts/smoke.py
```

## P2 paused scope

P2 is paused and is not an active runtime dependency. This MVP does not promise
additional ingestion orchestration, external retrieval, autonomous agents, or
a broader review platform. The supported path is the dual-source explorer,
Markdown manifest, LangChain Documents, local Qdrant HYBRID retrieval,
configured ChatOpenRouter generation with citations, and Supabase application
persistence/authentication.

## License

MIT License — open source for academic use.
