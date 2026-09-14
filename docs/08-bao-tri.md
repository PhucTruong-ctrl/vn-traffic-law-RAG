# 08. Bảo trì

> **Trạng thái release:** `RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME`
> (audit 14/09/2026). Public production hardening and complete semantic review
> remain outside this local MVP release claim.
> Đây là runbook cho những gì đang có trong repository, không phải cam kết rằng
> toàn bộ kiến trúc mục tiêu đã được triển khai.

Tài liệu quyết định phạm vi: [00-scope-and-decisions.md](00-scope-and-decisions.md).
Tham chiếu vận hành: [07-deployment.md](07-deployment.md) và
[06-test-evaluation.md](06-test-evaluation.md).

## 1. Runtime và nguyên tắc bất biến

Runtime hiện tại gồm:

- frontend Next.js/React;
- backend FastAPI/Python;
- Qdrant local hoặc remote theo cấu hình, phục vụ dense OpenRouter-compatible
  embeddings và sparse FastEmbed BM25;
- Supabase REST/Auth bên ngoài Compose, làm boundary cho authentication và
  persistence theo user;
- OpenRouter bên ngoài Compose, dùng cho embedding/generation khi được cấu hình.

Release Compose chỉ có **ba service**: `frontend`, `backend`, `qdrant`, trong
`deploy/compose/compose.release.yml`. Không có PostgreSQL app-owned, Redis,
Dramatiq, MinIO, worker, parser service, reviewer/admin service hay web-search
service trong topology active.

Mọi thao tác bảo trì phải giữ các nguyên tắc sau:

1. Chỉ dùng corpus/index local đã được kiểm soát; query-time **không gọi web**,
   không crawl ngoài allowlist và không fallback sang nguồn ngoài.
2. Không sửa âm thầm artifact bất biến, không ghi đè gold set hoặc kết quả đánh
   giá cũ.
3. Rebuild và publish phải fail closed: candidate lỗi không được thay index đang
   phục vụ.
4. Citation phải được dựng từ metadata/chunk identity đã kiểm tra; evidence
   không đủ hoặc provider lỗi thì abstain/trả lỗi trung thực.
5. Không ghi secret vào log, report, screenshot, hash manifest hoặc repository.
6. `data/sources/manifest.json` hiện có **17 entries** và loader active đọc
   Markdown/JSONL; không gọi đây là corpus release 14-PDF đã được xác minh.
   Artifact candidate 14-PDF riêng biệt cũng không tự động trở thành runtime
   source of truth.

## 2. Corpus, manifest và chunks

Các đầu vào cần giữ và kiểm tra cùng nhau:

- `data/sources/manifest.json`;
- các file corpus dưới `data/corpus/mds`;
- các artifact chunks/processed local nếu pipeline đang sử dụng;
- file hash và metadata source đi kèm;
- frozen evaluation artifacts trong `data/` và `docs/evaluation/`.

Khi thay đổi source:

1. Làm việc trên bản sao/branch và lưu SHA-256 trước khi biến đổi.
2. Kiểm tra host nguồn đúng allowlist đã đóng băng; không thêm nguồn web tùy ý.
3. Đối chiếu manifest với file thực tế: identity, URL/path, kích thước, hash,
   title, trạng thái và metadata thời gian phải nhất quán.
4. Kiểm tra duplicate theo document identity/file hash và kiểm tra chunk identity,
   `content_sha256`, hierarchy Điều/Khoản/Điểm, `effective_from`/
   `effective_to` và source metadata.
5. Không publish nếu manifest, chunks, hash hoặc metadata temporal không khớp.

Các script corpus có trong repository được dùng khi phù hợp với artifact hiện tại:

```bash
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/validate_manifest.py
uv run --project backend python backend/scripts/freeze_candidate_corpus.py
uv run --project backend python backend/scripts/validate_gold_set.py
```

Không tự tạo thêm cờ lệnh hoặc coi một script là bằng chứng release nếu script đó
không tồn tại/không được version hóa. `fetch_sources.py` là đường fetch corpus
được kiểm soát; không dùng nó để mở rộng ngoài allowlist. Các script
`validate_manifest.py`, `freeze_candidate_corpus.py` và `validate_gold_set.py`
chỉ được chạy nếu có trong checkout hiện tại; chúng kiểm tra artifact, không
biến candidate thành corpus đang phục vụ.

PDF extraction/Parser Router/Docling/MinerU/Canonical IR **chưa phải đường
runtime được chứng minh**. Loader active là Markdown/JSONL (`backend/app/ingestion/markdown.py`);
không mô tả thao tác parser mục tiêu như thao tác production.

## 3. Rebuild Qdrant từ artifact local

Qdrant là derived index. Không khôi phục bằng cách đọc ngược các point đang
hỏng và không dùng một nguồn chưa được hash. Trước rebuild:

- giữ nguyên collection/index đang phục vụ;
- copy và hash manifest, corpus, chunks và config embedding/sparse;
- ghi collection name, Qdrant endpoint/path, embedding model/dimensions và
  sparse encoder version vào run record không chứa secret;
- xác nhận candidate corpus đã qua các kiểm tra manifest/chunk/temporal cần thiết.

Đường index active hiện có trong repository:

```bash
uv run --project backend python backend/scripts/index.py
```

Chạy từ repository root, sau khi artifacts local đã được kiểm tra. Nếu index
script tạo candidate collection, chỉ switch serving collection/alias theo cơ
chế đã có trong cấu hình; không xóa collection cũ trước khi candidate được
kiểm tra. Nếu rebuild lỗi, giữ index cũ và ghi lỗi; không phục vụ candidate một
phần.

Kiểm tra tối thiểu sau rebuild:

- Qdrant readiness và collection tồn tại;
- payload có `chunk_id`, document/source identity, hierarchy và khoảng hiệu lực;
- dense và sparse vectors có cùng phiên bản cấu hình đã ghi;
- exact reference, temporal filter, sibling/cross-reference expansion bounded;
- câu hỏi thiếu evidence không sinh câu trả lời/citation bịa.

Không tuyên bố production reranker, six-layer verifier, stable `provision_id`
hoặc LangGraph workflow khi runtime chưa có implementation và evidence tương ứng.

## 4. Supabase và OpenRouter

### Supabase REST/Auth

Supabase là dependency ngoài Compose. Kiểm tra bằng cấu hình đã cung cấp, không
in giá trị secret:

- endpoint/project URL có thể truy cập;
- Auth token flow hoạt động;
- bearer token được truyền nguyên vẹn tới request persistence;
- session, user/assistant messages, citations, feedback và bookmarks không vượt
  ownership của user;
- readiness báo dependency lỗi rõ ràng và không giả vờ healthy.

Không gọi đây là PostgreSQL application runtime. Supabase có thể dùng PostgreSQL
bên trong, nhưng contract active là REST/Auth.

### OpenRouter

OpenRouter là provider ngoài Compose cho dense embedding và generator. Kiểm tra
bằng request smoke nhỏ với credentials lấy từ environment/secret store:

- model IDs và dimensions khớp config/run record;
- embedding và generation trả về đúng contract;
- timeout, quota, authentication hoặc provider error được ghi nhận;
- khi provider lỗi, API fail closed hoặc abstain, **không** tự động đổi provider
  hay gọi web.

Không commit `.env`, API key, bearer token, raw prompt/answer chứa PII, hoặc
provider response nhạy cảm.

## 5. Restart và readiness ba service

Từ repository root, dùng đúng release Compose file:

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml up -d

docker compose --project-directory . -f deploy/compose/compose.release.yml ps
```

Sau khi thay code/config/image, restart có kiểm soát:

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml up -d --build
```

Readiness cần quan sát cho cả ba service và dependency ngoài:

- Qdrant healthy/readiness trước retrieval;
- backend live/ready sau khi kết nối Qdrant và các dependency configured;
- frontend phục vụ được và gọi đúng backend URL trong release build;
- Supabase/OpenRouter được kiểm tra riêng khi smoke path cần chúng.

Không dùng `docker compose` để chờ PostgreSQL, Redis, Dramatiq, MinIO hoặc
worker vì các service đó không có trong release Compose. Không coi container
`running` là bằng chứng ứng dụng ready. Khi stop/restart, giữ volume Qdrant và
không xóa index đang phục vụ nếu chưa có backup/hash.

## 6. Evaluation và release blockers

Giữ nguyên các artifact evaluation đã commit; mỗi run mới phải ghi timestamp,
Git commit, corpus/manifest/chunk hashes, model/config versions và phạm vi case.
Không sửa frozen gold set để làm đẹp kết quả, không dùng feedback hoặc final test
để tuning rồi gọi đó là evaluation độc lập.

Artifact release candidate ngày 14/09/2026 được ghi nhận tại
[evaluation/release-candidate-20260914.md](evaluation/release-candidate-20260914.md).
Kết quả gồm 40 rows, trong đó 34 covered rows và 6 rows
`CORPUS_NOT_COVERED` (`00`, `15`--`19`). Covered-case request errors bằng 0,
citation validity bằng 1.0, invalid citation rate bằng 0% và abstention accuracy
bằng 0.9118. Sáu case thiếu corpus không được tính vào denominator.

Trạng thái kỹ thuật là **RELEASE-READY FOR COVERED CORPUS**. Đây không phải
chứng nhận semantic đầy đủ: `answer_correctness_manual` vẫn là N/A vì chưa có
human semantic review toàn bộ. Khi corpus hoặc model thay đổi, phải chạy lại
đầy đủ quy trình và tạo artifact mới; không sửa frozen gold để làm đẹp kết quả.

## 7. Backup, hash và khôi phục local

Backup tối thiểu phải bao gồm:

- `data/sources/manifest.json`;
- corpus Markdown/PDF và processed chunks đang được dùng;
- cấu hình không chứa secret;
- Qdrant snapshot/volume hoặc candidate collection;
- frozen gold/evaluation artifacts;
- Git commit và SHA-256 manifest.

Ví dụ tạo hash cho các file local đã chọn (không đưa secret vào danh sách):

```bash
sha256sum data/sources/manifest.json > SHA256SUMS
sha256sum -c SHA256SUMS
```

Mở rộng danh sách hash phải explicit và review được; không hash `.env`, token,
cache hoặc database local có dữ liệu nhạy cảm. Lưu backup ở nơi độc lập với
working tree và ghi ngày, commit, corpus identity, Qdrant collection/path.

Khôi phục theo thứ tự: xác nhận backup/hash, khôi phục manifest/corpus/chunks,
kiểm tra artifact, rebuild Qdrant bằng `backend/scripts/index.py`, rồi restart
ba service và chạy smoke/evaluation subset. Nếu bất kỳ bước nào fail, dừng
publish và giữ bản đang phục vụ. Qdrant snapshot là phương án khôi phục nhanh;
local corpus/manifest/chunks mới là đầu vào cần thiết để rebuild có thể kiểm tra.

## 8. Giới hạn và thiết kế lịch sử/deferred

Các nội dung sau chỉ là historical/deferred research; **không chạy, không đưa
vào checklist active và không tuyên bố đã triển khai**:

- PostgreSQL app-owned legal source of truth, Alembic migrations và relation DB;
- Redis broker/cache và Dramatiq workers/dead-letter/reconcile commands;
- MinIO hoặc object-storage bucket/retention procedures;
- LangGraph orchestration;
- Langfuse prompts/traces;
- Parser Router, Docling, MinerU, Canonical Document IR, Legal Structure/Reference
  Resolver và các parser golden-fixure procedures;
- production reranker, six independent verifiers, upload/reviewer/admin flow,
  human approval và alias migration dựa trên các hệ thống mục tiêu.

Các giới hạn runtime cần nói rõ:

- active loader là Markdown/JSONL và manifest hiện có 17 entries;
- Qdrant là retrieval index theo artifact/config hiện tại, không chứng minh
  PostgreSQL legal source-of-truth;
- generation là free-form Markdown qua một generator OpenRouter, với
  deterministic evidence/citation checks hiện có;
- không có query-time web retrieval hoặc provider fallback;
- Supabase/OpenRouter availability và manual browser verification còn là release
  dependencies;
- metrics subset hiện tại chưa đủ để chứng minh chất lượng, latency hoặc
  release readiness.

Khi tài liệu khác mô tả topology hoặc quy trình deferred, phải gắn nhãn lịch sử
và đối chiếu lại runtime trước khi thao tác. Không biến mục tiêu nghiên cứu thành
lệnh vận hành mới.
