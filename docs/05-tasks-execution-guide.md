# Hướng dẫn thực thi 5 task còn thiếu

Tài liệu này là runbook thực thi cho corpus, gold set, runtime, evaluation và release gate. Không đánh dấu `ACCEPTED`, `APPROVED`, `PASS` hoặc `Done` nếu chưa có bằng chứng thật.

## Quy ước chung

- Làm việc từ repository root: `/home/phuctruong/Work/Studies/vnlaw-agentic-rag`.
- Backend chạy bằng `uv`; không tạo virtualenv hoặc dependency manager mới.
- PDF nguồn và secret **không commit**. README của corpus xác nhận chỉ manifest được commit; PDF nằm trong `data/` và bị gitignore.
- Artifact evaluation phải có corpus hash, gold hash, commit SHA và model/config version.
- Credentials đặt trong `.env` cục bộ hoặc secret manager, không gửi vào chat/Jira/PR.
- Khi cần review pháp lý, người review phải đọc nguồn chính thức và ghi điều/khoản/điểm; không suy luận từ tên file.

---

# Task 1 — Review 13 manifest `PENDING`, xác nhận relation và ingest/index

## 1.1. Tìm manifest đang PENDING

Từ repository root:

```bash
find data/manifests -name '*.manifest.json' -print0 \
  | xargs -0 jq -r 'select(.review_status == "PENDING") | input_filename'
```

Kiểm tra README của từng batch:

```bash
sed -n '1,220p' data/manifests/batch-01/README.md
sed -n '1,220p' data/manifests/batch-02/README.md
sed -n '1,220p' data/manifests/batch-03/README.md
sed -n '1,220p' data/manifests/batch-04/README.md
sed -n '1,220p' data/manifests/batch-05/README.md
sed -n '1,220p' data/manifests/batch-06/README.md
```

Nếu số lượng không phải 13, dừng và cập nhật danh sách thực tế trước khi review. Không lấy danh sách từ README thay cho JSON.

## 1.2. Tìm nguồn chính thức

Mỗi manifest phải có URL hoặc `relation_notes` chỉ tới nguồn chính thức. Kiểm tra:

```bash
jq '{document_id, source_url, file_hash, effective_from, effective_to,
     review_status, reviewed_by, reviewed_at, relation_notes}' \
  data/manifests/batch-05/<document>.manifest.json
```

Nguồn ưu tiên là Cổng thông tin điện tử Chính phủ, ví dụ `vanban.chinhphu.vn` hoặc `datafiles.chinhphu.vn`. Nếu nguồn không tải được hoặc không chứng minh được là bản chính thức, không chuyển sang `ACCEPTED`.

Tải PDF vào thư mục local bị gitignore, ví dụ:

```bash
mkdir -p data/<document_id>/source
curl --fail --location '<OFFICIAL_URL>' \
  --output data/<document_id>/source/<document_id>.pdf
sha256sum data/<document_id>/source/<document_id>.pdf
file data/<document_id>/source/<document_id>.pdf
```

Nếu văn bản có nhiều phần, merge bằng `pdfunite`, sau đó hash file merged đầy đủ:

```bash
pdfunite data/<document_id>/source/part-*.pdf \
  data/<document_id>/source/<document_id>.pdf
sha256sum data/<document_id>/source/<document_id>.pdf
```

Không commit PDF. Hash trong manifest phải đúng hash của file canonical cuối cùng.

## 1.3. Xác nhận amendment/replacement/repeal

Đọc toàn bộ điều khoản hiệu lực, sửa đổi và bãi bỏ trong PDF. Tìm nhanh các cụm pháp lý, sau đó đọc vùng ngữ cảnh trong PDF:

```bash
pdftotext -layout data/<document_id>/source/<document_id>.pdf /tmp/<document_id>.txt
rg -n 'sửa đổi|bổ sung|thay thế|bãi bỏ|hết hiệu lực|hiệu lực thi hành' \
  /tmp/<document_id>.txt
```

Không ghi quan hệ chỉ từ kết quả `rg`. Mỗi relation phải có:

- `relation_type`: `AMENDS`, `REPLACES`, `REPEALS`, `IMPLEMENTS` hoặc loại đã quy định trong schema.
- `source_document_id`.
- `target_document_id`.
- Điều/khoản/điểm cụ thể.
- Trang hoặc section của PDF.
- Trích dẫn nguyên văn.
- Ngày hiệu lực và điều khoản chuyển tiếp nếu có.

Phân biệt:

- `AMENDS`: sửa/bổ sung một phần văn bản cũ.
- `REPLACES`: thay thế văn bản hoặc phạm vi quy định cũ.
- `REPEALS`: bãi bỏ điều/khoản/văn bản cũ.
- `IMPLEMENTS`: quy định chi tiết hoặc hướng dẫn thi hành, không thay thế văn bản gốc.
- Văn bản hợp nhất không tự động là `REPLACES` văn bản gốc; phải giữ provenance về văn bản gốc và các amendment.

## 1.4. Cập nhật manifest

Mở đúng JSON, không sửa các manifest khác. Giữ schema hiện có; xem manifest đã `ACCEPTED` để làm mẫu:

```bash
cat data/manifests/batch-01/nd-168-2024.manifest.json
```

Các trường review tối thiểu:

```json
{
  "review_status": "ACCEPTED",
  "reviewed_by": "<reviewer-id>",
  "reviewed_at": "2026-09-05T10:00:00Z",
  "relation_notes": "Điều ... khoản ...; trích dẫn ...",
  "file_hash": "<sha256-of-canonical-pdf>"
}
```

Nếu bằng chứng không đủ:

```json
{
  "review_status": "REJECTED",
  "reviewed_by": "<reviewer-id>",
  "reviewed_at": "2026-09-05T10:00:00Z",
  "relation_notes": "Không xác minh được ..."
}
```

Không dùng `ACCEPTED` để vượt gate khi thiếu PDF hoặc thiếu điều khoản.

Validate từng manifest theo công cụ/schema hiện có:

```bash
cd backend
uv run python -m scripts.validate_manifest \
  ../data/manifests/<batch>/<document>.manifest.json
cd ..
```

Nếu module trên không tồn tại ở checkout hiện tại, dùng test schema hiện có và báo lỗi thiếu công cụ; không tự tạo kết quả PASS.

## 1.5. Ingest PostgreSQL và index Qdrant

Đọc flow trước khi chạy:

```bash
sed -n '1,260p' backend/app/ingestion/index.py
sed -n '1,260p' backend/app/ingestion/extract.py
sed -n '1,260p' backend/app/retrieval/indexing.py
sed -n '1,260p' backend/app/retrieval/qdrant_store.py
sed -n '1,260p' backend/app/persistence/models.py
```

Khởi động service bằng compose sau khi đã đặt biến môi trường:

```bash
docker compose up -d postgres qdrant redis minio

docker compose ps
```

Chạy migration/ingestion theo entrypoint thực tế của branch. Không đoán tên command; tìm trước:

```bash
find backend -maxdepth 4 -type f \( -name '*.py' -o -name '*.sh' \) -print \
  | sort
rg -n 'ingest|index|qdrant|create_collection|provision' \
  backend/app backend/tests docs
```

Sau ingest, kiểm tra:

- PostgreSQL: số document, provision, relation và status.
- Qdrant: collection tồn tại, vector count, payload metadata.
- Mỗi vector có `document_id`, `provision_id`, temporal fields và source hash.
- Relation trong database khớp relation đã review.

Lưu report vào artifact ngoài source hoặc thư mục artifact được quy định, ví dụ:

```text
artifacts/corpus-review-<timestamp>/
├── manifest-review.jsonl
├── postgres-counts.json
├── qdrant-counts.json
├── relation-report.json
├── corpus-hash.json
└── checksums.sha256
```

## 1.6. Tiêu chí hoàn thành

- Đủ 13 manifest được kiểm tra.
- Mỗi manifest có reviewer, timestamp, decision và evidence.
- Mỗi relation có điều/khoản/điểm và trích dẫn.
- Hash PDF khớp manifest.
- PostgreSQL và Qdrant có report thật.
- Có corpus hash cuối cùng.

---

# Task 2 — Hoàn thiện 40/40/120 gold set và freeze `gold-v1`

## 2.1. Tìm model/schema và dữ liệu hiện tại

Đọc contract:

```bash
sed -n '1,240p' backend/app/evaluation/gold_set.py
find backend/tests -iname '*gold*' -o -path '*fixtures/golden*'
rg -n 'GoldRecord|DEVELOPMENT|VALIDATION|FINAL_TEST|APPROVED|gold-v1' \
  backend data docs
```

`GoldRecord` trong `backend/app/evaluation/gold_set.py` là contract chính. Không tự tạo field khác nếu không cập nhật contract và test liên quan.

## 2.2. Tạo cấu trúc dữ liệu

Tạo thư mục dữ liệu gold ở vị trí được code/config hiện tại sử dụng. Nếu chưa có path chính thức, dùng local staging ngoài source trước:

```text
artifacts/gold-v1-draft/
├── development.jsonl
├── validation.jsonl
├── final_test.jsonl
└── review-log.jsonl
```

Không đưa record final test chưa review vào `backend/tests/fixtures`; fixture test không thay thế gold set production.

Mỗi record cần có tối thiểu:

- ID duy nhất.
- Câu hỏi nguyên bản.
- Split.
- Category.
- Ngày truy vấn và loại phương tiện nếu câu hỏi cần.
- `expected_provision_ids`.
- `acceptable_provision_ids`.
- Evidence/citation.
- Facts bắt buộc.
- Facts không được nói.
- Temporal metadata.
- Expected answer hoặc abstention.
- Reviewer, timestamp, decision.

Ví dụ record JSONL:

```json
{
  "id": "gold-final-001",
  "split": "FINAL_TEST",
  "category": "CURRENT",
  "question": "...",
  "as_of_date": "2025-01-01",
  "vehicle_type": "motorcycle",
  "expected_provision_ids": ["doc-001-art-5-clause-2"],
  "acceptable_provision_ids": ["doc-001-art-5-clause-2"],
  "must_include_facts": ["..."],
  "must_not_include_facts": ["..."],
  "expected_answer_type": "answer",
  "temporal_expectation": {
    "current_law": true,
    "effective_from": "2025-01-01",
    "effective_to": null
  },
  "evidence": [
    {
      "document_id": "doc-001",
      "citation": "Điều 5 khoản 2",
      "quote": "..."
    }
  ],
  "reviewed_by": "reviewer-01",
  "reviewed_at": "2026-09-05T10:00:00Z",
  "review_status": "APPROVED"
}
```

Tên field thực tế phải khớp `GoldRecord`; dùng `model_validate` để phát hiện mismatch:

```bash
cd backend
uv run python - <<'PY'
import json
from pathlib import Path
from app.evaluation.gold_set import validate_record

for path in Path("../artifacts/gold-v1-draft").glob("*.jsonl"):
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            validate_record(json.loads(line), verify_hash=False)
print("gold schema validation: PASS")
PY
cd ..
```

## 2.3. Review từng record

Lấy provision và evidence từ corpus đã `ACCEPTED`, không viết expected IDs tùy ý:

```bash
rg -n 'provision_id|article|Điều|Khoản' data backend docs
```

Với từng record:

1. Đọc câu hỏi.
2. Xác định ngày áp dụng.
3. Truy vấn provision tương ứng trong PostgreSQL/Qdrant.
4. Đọc nguồn pháp lý gốc.
5. Xác nhận expected và acceptable provision IDs.
6. Viết facts bắt buộc và facts cấm.
7. Xác nhận hiệu lực, bãi bỏ, sửa đổi và điều khoản chuyển tiếp.
8. Ghi review log.

Không cho cùng một record xuất hiện ở nhiều split. Kiểm tra duplicate:

```bash
jq -r '.id' artifacts/gold-v1-draft/*.jsonl | sort | uniq -d
jq -r '.question' artifacts/gold-v1-draft/*.jsonl | sort | uniq -d
```

Kiểm tra số lượng:

```bash
for f in development validation final_test; do
  printf '%s: ' "$f"
  wc -l < "artifacts/gold-v1-draft/$f.jsonl"
done
```

Phải đạt đúng:

```text
development: 40
validation: 40
final_test: 120
```

## 2.4. Review độc lập và freeze

Reviewer độc lập phải ký review log cho từng record. Record thiếu source, provision, temporal metadata hoặc decision phải giữ `DRAFT`/`REJECTED`, không freeze.

Sau khi đủ 200 record `APPROVED`:

```bash
mkdir -p artifacts/gold-v1
cp artifacts/gold-v1-draft/development.jsonl artifacts/gold-v1/
cp artifacts/gold-v1-draft/validation.jsonl artifacts/gold-v1/
cp artifacts/gold-v1-draft/final_test.jsonl artifacts/gold-v1/
sha256sum artifacts/gold-v1/*.jsonl > artifacts/gold-v1/hash-lines.txt
```

Tạo `artifacts/gold-v1/hash.json`:

```json
{
  "version": "gold-v1",
  "development_sha256": "...",
  "validation_sha256": "...",
  "final_test_sha256": "...",
  "gold_sha256": "...",
  "record_counts": {
    "development": 40,
    "validation": 40,
    "final_test": 120
  },
  "frozen_at": "2026-09-05T10:00:00Z",
  "frozen_by": "reviewer-01"
}
```

Sau freeze, chỉ đọc các file. Muốn sửa phải tạo `gold-v2`, không overwrite `gold-v1`.

## 2.5. Tiêu chí hoàn thành

- Đúng 40/40/120 record.
- Tất cả record `APPROVED`.
- Không duplicate.
- Provision ID tồn tại trong corpus.
- Evidence trỏ tới điều/khoản/điểm thật.
- Temporal metadata khớp corpus.
- Có review log và `hash.json`.
- Gold-v1 không bị sửa sau freeze.

---

# Task 3 — Cấu hình runtime và external credentials

## 3.1. Tìm config hiện có

Đọc các file sau:

```bash
sed -n '1,260p' .env.example
sed -n '1,320p' docker-compose.yml
sed -n '1,260p' backend/app/config.py
sed -n '1,240p' docs/07-deployment.md
rg -n 'POSTGRES|QDRANT|REDIS|MINIO|RAGFLOW|GEMINI|JINA|OPENAI|RAGAS|LANGFUSE' \
  .env.example docker-compose.yml backend docs .github
```

Không tự đổi tên biến môi trường. Dùng đúng tên mà `backend/app/config.py` và compose đọc.

## 3.2. Tạo môi trường local

Copy template nhưng không commit file kết quả:

```bash
cp .env.example .env
chmod 600 .env
$EDITOR .env
```

Cần cấu hình các nhóm:

- PostgreSQL DSN/database/schema.
- Qdrant URL/collection/API key.
- Redis URL/password.
- MinIO endpoint/bucket/access key/secret.
- RAGFlow URL/API key/version.
- Gemini/Jina/OpenAI model và API key nếu dùng.
- Ragas package/evaluator model.
- Langfuse host/public key/secret nếu cần observability.

Kiểm tra `.gitignore` trước khi chạy:

```bash
rg -n '^\.env|\.env\*|artifacts' .gitignore
```

Không chạy lệnh in toàn bộ environment. Khi debug chỉ in tên biến và trạng thái có/không có.

## 3.3. Khởi động và health check

Kiểm tra compose:

```bash
docker compose config --quiet
```

Khởi động service local:

```bash
docker compose up -d postgres qdrant redis minio

docker compose ps
```

Kiểm tra endpoint bằng health check của từng service; dùng URL/command theo `docs/07-deployment.md` và compose, không đoán endpoint RAGFlow. Lưu kết quả dạng không chứa secret:

```text
postgres: available
qdrant: available
redis: available
minio: available
ragflow: available|not-configured
embedding-provider: configured|not-configured
llm-provider: configured|not-configured
langfuse: configured|not-configured
```

## 3.4. Pin version

Ghi version trong run metadata:

```bash
python --version
cd backend && uv run python -c 'import pydantic, sqlalchemy; print(pydantic.__version__, sqlalchemy.__version__)'
cd ..
docker compose images
```

API model/version phải nằm trong config snapshot của evaluation run, không chỉ nằm trong `.env`.

## 3.5. Tiêu chí hoàn thành

- Các service cần thiết đang chạy.
- Health check pass.
- Credentials xác thực được nhưng không lộ secret.
- Model/API/package version đã pin.
- `.env` không nằm trong commit hoặc artifact công khai.

---

# Task 4 — Chạy evaluation thật và lưu raw immutable artifacts

Chỉ chạy sau khi Task 1 có corpus hash và Task 2 có gold hash.

## 4.1. Kiểm tra runner và contract

Đọc runner:

```bash
sed -n '1,300p' backend/app/evaluation/run.py
sed -n '1,260p' backend/app/evaluation/suites/suite_b.py
sed -n '1,260p' backend/app/evaluation/suites/suite_c.py
sed -n '1,260p' backend/app/evaluation/suites/suite_d.py
sed -n '1,260p' backend/app/evaluation/metrics/temporal.py
```

Tìm command entrypoint thực tế:

```bash
rg -n 'run_suite|Suite B|Suite C|Suite D|evaluation|EvaluationRunWriter' \
  backend scripts docs .github
```

Nếu chưa có runner provider thật, không dùng deterministic test/injected evaluator để tuyên bố evaluation thật. Khi thiếu runner, phải tạo adapter tối thiểu dùng cùng `EvaluationRunManifest` và `EvaluationRunWriter`, không tạo số liệu giả.

## 4.2. Tạo run metadata

Mỗi run cần:

```json
{
  "run_id": "run-2026-09-05T100000Z-suite-b",
  "git_commit": "<commit-sha>",
  "corpus_version": "corpus-v1",
  "corpus_hash": "<corpus-sha256>",
  "gold_set_version": "gold-v1",
  "gold_set_hash": "<gold-sha256>",
  "suite": "B",
  "variant": "production",
  "config_snapshot": {},
  "model_ids": {},
  "prompt_versions": {},
  "parser_versions": {}
}
```

Contract này nằm ở `EvaluationRunManifest` trong `backend/app/evaluation/run.py`. Writer lưu descriptor, raw results append-only và finish marker vào bucket `evaluation-artifacts`.

## 4.3. Chạy Suite B/C/D

Chạy từng suite riêng, không overwrite run cũ:

```bash
cd backend
uv run pytest --no-cov -q tests/test_suite_b.py tests/test_suite_c.py tests/test_suite_d.py
cd ..
```

Các test trên chỉ xác nhận contract code; chúng **không phải** evaluation production. Evaluation thật phải gọi provider và gold set thật bằng runner hiện hành.

Lưu per-record:

- Question ID.
- Prompt/config version.
- Retrieved provisions/chunks.
- Raw model output.
- Expected/acceptable provisions.
- Citation validity.
- Temporal correctness.
- Abstention/error.
- Latency/tokens/cost.

Suite D phải đủ 40 validation records; code hiện tại có `VALIDATION_SET_SIZE = 40` trong `backend/app/evaluation/suites/suite_d.py`.

## 4.4. Chạy RAGFlow B1–B4

Trước tiên tìm profile/import script:

```bash
rg -n 'RAGFlow|ragflow|B1|B2|B3|B4' . docs backend docker-compose.yml
```

Kiểm tra health, import cùng corpus hash, chạy record thật và lưu:

- RAGFlow version/image.
- Dataset/knowledge-base ID.
- Chunking/embedding/reranker config.
- Raw retrieval result.
- Raw answer.
- Citation/provenance.
- Per-record metrics.

Không coi `docker compose ps` là bằng chứng B1–B4 đã chạy.

## 4.5. Chạy Secondary/Ragas

Tìm version và evaluator config:

```bash
rg -n 'ragas|Ragas|secondary|evaluator' pyproject.toml uv.lock backend docs .github
```

Lưu package version, evaluator model, rubric, input/output và per-record score. Nếu chưa có credentials, ghi `BLOCKED` thay vì dùng mock output.

## 4.6. Chạy performance/load

Tìm load runner hiện có:

```bash
rg -n 'performance|latency|P50|P95|load|token|cost' backend docs .github
```

Nếu có runner, chạy với corpus/gold/config cố định. Nếu chưa có, chỉ viết runner sau khi thống nhất endpoint và workload; không lấy thời gian unit test làm latency production.

Bắt buộc lưu:

- P50/P95/P99 latency.
- Throughput.
- Error rate.
- Retrieval/generation latency.
- Input/output tokens.
- Cost/query.
- Concurrency và warm/cold state.

## 4.7. Cấu trúc artifact

Dùng một thư mục mới cho mỗi lần chạy:

```text
artifacts/evaluation/<run-id>/
├── metadata.json
├── corpus-hash.json
├── gold-hash.json
├── suite-b/raw.jsonl
├── suite-b/per-record.jsonl
├── suite-b/summary.json
├── suite-c/
├── suite-d/
├── ragflow/
├── secondary-ragas/
├── performance/
└── checksums.sha256
```

Tạo checksum:

```bash
find artifacts/evaluation/<run-id> -type f -not -name checksums.sha256 \
  -print0 | sort -z | xargs -0 sha256sum \
  > artifacts/evaluation/<run-id>/checksums.sha256
```

Không overwrite run đã finish. Sửa config hoặc rerun phải tạo `run-id` mới.

## 4.8. Tiêu chí hoàn thành

- Suite B/C/D có raw và summary.
- RAGFlow B1–B4 có output trên record thật.
- Secondary/Ragas có per-record và aggregate result.
- Performance có P50/P95, token và cost.
- Mọi artifact có corpus hash, gold hash, commit SHA, model/config version.
- Checksums pass và artifact không bị sửa sau finish.

---

# Task 5 — Oracle, CI, merge PR #25 và chuyển Jira Done

## 5.1. Kiểm tra PR hiện tại

```bash
git status --short
git branch --show-current
git log -1 --oneline
```

PR: `https://github.com/PhucTruong-ctrl/vn-traffic-law-RAG/pull/25`.

Đảm bảo PR chứa đúng code/evidence cần review và không chứa:

- `.env`.
- API key/secret.
- PDF upload hoặc database local.
- Raw artifact chứa dữ liệu nhạy cảm.
- Số liệu chưa có run provenance.

## 5.2. Chạy local gate

Backend:

```bash
cd backend
uv run --offline ruff check .
uv run --offline ruff format --check .
uv run --offline mypy app
uv run --offline pytest --no-cov -m 'not integration' -q
cd ..
```

Frontend nếu có thay đổi frontend:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
cd ..
```

Compose/security:

```bash
docker compose config --quiet
uv run --directory backend pytest --no-cov -q tests/test_security.py tests/test_suite_d.py
```

Các lệnh trên kiểm tra code. Chúng không thay thế evidence corpus/gold/evaluation thật.

## 5.3. Oracle review

Gửi oracle toàn bộ diff từ base của PR và các artifact liên quan. Oracle phải trả một verdict rõ ràng:

```text
READY
```

`READY-WITH-FIXES` hoặc `NOT-READY` chưa được merge. Sửa hết finding, chạy lại focused checks và yêu cầu verdict theo quy trình repo.

Oracle review phải kiểm tra:

- Acceptance criteria từng ticket.
- Corpus/gold provenance.
- Temporal/citation invariant.
- Không fake/placeholder evidence.
- Security và secrets.
- Tính tái lập evaluation.
- Artifact hash và commit linkage.

## 5.4. GitHub CI

Chờ toàn bộ required checks của PR #25 ở trạng thái green. Không merge khi:

- Có check đỏ.
- Có required check pending.
- Check bị skip do cấu hình sai.
- Oracle chưa `READY`.

Lưu link PR, check names, CI run ID và merge commit SHA.

## 5.5. Merge và Jira

Chỉ sau khi oracle `READY` và CI green mới merge PR #25 theo policy của repository. Sau merge:

1. Ghi merge commit SHA.
2. Kiểm tra branch main chứa commit.
3. Link PR/CI/artifact vào Jira.
4. Chỉ transition các ticket có acceptance evidence thật từ `In Review` sang `Done`.
5. Không chuyển ticket bị thiếu external run, corpus review hoặc gold freeze.

Nếu cần lấy transition ID của Jira, fetch transition hiện tại trước; không hardcode ID khi không chắc chắn. Jira `Done` là trạng thái sau merge, không phải sau khi push branch.

## 5.6. Tiêu chí hoàn thành

- Oracle verdict `READY`.
- Required GitHub CI green.
- PR #25 merged vào `main`.
- Có merge commit SHA.
- Jira ticket đủ evidence được chuyển `Done`.
- Ticket còn thiếu external evidence vẫn giữ đúng trạng thái, không đánh dấu hoàn tất giả.

---

# Bảng tiến độ cần cập nhật

Tạo một bản ghi tiến độ trong artifact hoặc Jira comment, không ghi secret:

| Task | Trạng thái | Evidence | Người phụ trách | Blocker |
|---|---|---|---|---|
| 1. Corpus review/index | `TODO` | link manifest/reports/hash |  |  |
| 2. Gold-v1 freeze | `TODO` | link 40/40/120/hash |  |  |
| 3. Runtime credentials | `TODO` | health/version report |  |  |
| 4. Real evaluation | `TODO` | run IDs/artifacts |  |  |
| 5. Release gate | `TODO` | oracle/CI/merge/Jira |  |  |

Trạng thái hợp lệ: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`. Chỉ dùng `DONE` khi tiêu chí của phần đó đã có bằng chứng tương ứng.
