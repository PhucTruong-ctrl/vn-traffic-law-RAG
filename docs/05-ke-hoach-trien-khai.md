# 05. Kế hoạch triển khai hiện tại

> **Trạng thái release:** **UNVERIFIED / NOT RELEASE-READY**. Đây là kế hoạch thực thi có điều kiện bằng chứng; không coi thiết kế mục tiêu, tài liệu cũ hoặc một subset evaluation là phase đã hoàn thành.
>
> **Nguồn quyết định:** [00-scope-and-decisions.md](00-scope-and-decisions.md). Các claim runtime phải đối chiếu code, deployment artifact và evaluation artifact tương ứng.

## 1. Baseline đã quan sát

- Runtime hiện tại gồm FastAPI, Supabase Auth/REST và persistence theo user; frontend là Next.js/React với chat, conversation, legal sources, citation viewer, saved items và LIKE/DISLIKE.
- `RAGService` chạy đồng bộ: phân tích câu hỏi, bounded intent/vehicle fan-out, hybrid Qdrant dense + FastEmbed BM25, exact metadata filtering, temporal filtering, sibling/cross-reference expansion giới hạn, deterministic evidence checks, sinh Markdown và dựng citation từ metadata/chunk identity.
- Ingestion đang là Markdown/JSONL loader (`backend/app/ingestion/markdown.py`) đọc manifest và `data/corpus/mds`. Manifest hiện có **17 entries**; điều này chưa chứng minh corpus release đúng 14 PDF, immutable snapshot hay accepted source of truth.
- Deployment release hiện chỉ có Qdrant, backend và frontend; Supabase/OpenRouter là dịch vụ ngoài. Không có bằng chứng runtime active cho LangGraph, PostgreSQL legal source-of-truth, Redis/Dramatiq, MinIO, Langfuse, Docling/MinerU Parser Router, production reranker hoặc đầy đủ sáu verifier độc lập.
- Bằng chứng gần nhất là [`evaluation/thesis-api-subset-32-20260913.md`](evaluation/thesis-api-subset-32-20260913.md): chạy 32/40 case qua API, 3 lỗi, hit@5 `0.1905`, citation validity `0.6552`, abstention accuracy `0.4483`, P95 `84,036.78 ms`, chưa semantic review. Đây là chẩn đoán, không phải full evaluation.

## 2. Frozen release contract

Không thay đổi để đáp ứng lịch trình:

1. Corpus release đúng **14 PDF**, deduplicate theo document identity/file hash, chỉ từ allowlist `datafiles.chinhphu.vn`; snapshot/hash và provenance phải truy vết được.
2. Gold contract gồm **40 case**, thuộc đúng 8 category: `exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, `out_of_scope`. Đây là bộ đánh giá có coverage giới hạn; không áp đặt ngưỡng metric số cố định. Quyết định release cần artifact đầy đủ, semantic review và safety/citation/operational gates.
3. Ingestion manual/CLI, fail closed; index đang phục vụ không bị thay bởi snapshot/index lỗi. Không upload endpoint, admin/reviewer approval flow hoặc web fallback trong MVP.
4. Qdrant là derived retrieval index; citation phải dựng từ identity/provenance tin cậy, không để model tự gõ định danh.
5. Evidence Completeness Gate chạy trước generation; chỉ trả verified answer hoặc abstain. Không trả citation/claim chưa kiểm chứng.
6. Query phải hỗ trợ current/historical/comparison, exact reference, temporal validity và bounded legal expansion mà không suy diễn khi thiếu ngày hoặc evidence.

## 3. Blockers mở — chưa được coi là hoàn tất

Các mục dưới đây là điều kiện phải có bằng chứng trước release, không phải tuyên bố công việc đã xong:

- **Corpus/provenance:** tạo hoặc xác minh artifact snapshot đúng 14 PDF allowlisted, dedup/hash, metadata bắt buộc, provenance và accepted/rejected gate; chứng minh parser output và source-of-truth.
- **Structure/identity:** chứng minh boundary provision, nhãn `đ)`, deterministic stable identity và citation mapping; không chỉ dựa vào chunk_id hiện tại.
- **Temporal/relations:** kiểm chứng amendment/replacement/partial-effect semantics, reference graph bounded và current/historical/comparison cases.
- **Retrieval/evidence:** phân tích lỗi hit@k, exact lookup, cross-reference, multi-provision và multi-document; chứng minh Evidence Set Recall/All Required Evidence và verified-or-abstain.
- **Generation/citation:** kiểm tra claim support, numeric/temporal correctness, invalid citation rate và abstention; semantic review còn thiếu.
- **Reliability/security:** xử lý và tái hiện 3 API errors, latency P50/P95, deterministic Qdrant identity, auth/session isolation và persisted assistant responses; xác minh bằng runtime evidence.
- **Evaluation/release:** chạy diagnostic 40-case gate trên đúng frozen fixture, lưu immutable run manifest (corpus/index/gold/model/prompt/config/commit/raw outputs/error analysis), semantic review cần thiết và safety/citation gates.
- **Product/deployment:** thực hiện manual browser verification cho các flow hiện có và kiểm chứng deployment artifact; không suy ra từ API subset.

## 4. Work lanes và đầu ra bắt buộc

### Lane A — Corpus và ingestion

Đối chiếu 14 PDF với allowlist, deduplicate, tạo snapshot/hash manifest bất biến, kiểm tra metadata/provenance/temporal fields và fail-closed publish. Đầu ra: snapshot, gate report, loader/parser provenance và Qdrant build manifest.

### Lane B — Retrieval, structure và temporal

Đo parser/structure boundary, stable identity, exact/dense/sparse retrieval, fusion, bounded sibling/cross-reference expansion và temporal filtering. Đầu ra: reproducible experiment matrix, error analysis theo category và bằng chứng không leakage.

### Lane C — Evidence, generation và citation

Thiết kế/kiểm chứng evidence plan, completeness gate, structured claims, deterministic citation/temporal/numeric/claim checks, bounded repair và abstention. Đầu ra: per-case traces và invalid-citation/unsupported-claim/abstention evidence; không dùng model output tự do làm identity.

### Lane D — API, auth, persistence và UI

Kiểm chứng bearer propagation, user-owned session/history, assistant persistence, citation rendering, date/disclaimer và feedback telemetry. Đầu ra: API smoke evidence, manual browser evidence, isolation/error traces; feedback không được dùng tuning hay release gate.

### Lane E — Evaluation và release decision

Giữ frozen data tách khỏi tuning; chạy diagnostic 40-case gate theo đúng 8 category. Đầu ra: immutable run manifest, headline metrics, semantic review, error taxonomy và release recommendation. Chỉ lane này được đề xuất thay đổi trạng thái release, dựa trên artifact.

## 5. Acceptance evidence và release gate

Mỗi lane phải liên kết claim với artifact cụ thể; không ghi “pass” khi chưa có output. Release chỉ được xem xét khi tất cả điều kiện sau đều có bằng chứng:

- 14-PDF snapshot/hash/provenance hợp lệ và accepted publish fail-closed.
- Diagnostic 40-case gate trên đúng frozen fixture, đủ 8 category, với denominator và coverage được công bố rõ.
- Retrieval, evidence, temporal, citation, grounding, abstention và performance metrics theo [06-test-evaluation.md](06-test-evaluation.md), kèm error analysis.
- Invalid citation rate đạt bất biến contract bằng kiểm tra deterministic; semantic correctness đã được review.
- Không còn API error chưa phân loại trên run release; auth/session isolation, persistence và UI flows được smoke/manual kiểm chứng.
- Deployment artifact đúng topology đã kiểm chứng và run manifest tái tạo được.

Thiếu bất kỳ mục nào giữ nguyên **UNVERIFIED / NOT RELEASE-READY**. Không tự đặt ngưỡng mới hoặc biến metric subset thành kết quả full.

## 6. Evaluation procedure

1. Freeze và hash corpus/index, gold set, model/config/prompt và commit.
2. Chạy parser/corpus gates, sau đó retrieval ablation và temporal/reference suites.
3. Chạy evidence/generation/citation suite với traces; phân loại lỗi trước khi sửa.
4. Chạy API/runtime smoke và manual browser verification trên build đã gắn manifest.
5. Chạy diagnostic 40-case gate; báo cáo deterministic metrics, latency/cost và semantic review tách biệt.
6. Chỉ sửa/tuning trên dữ liệu development/validation nếu có trong artifact; rerun affected cases và ghi version. Không áp đặt threshold số cố định.
7. Lưu raw outputs, errors, review và provenance; cập nhật status tại mục 7.

## 7. Status tracking

| Hạng mục | Trạng thái hiện tại | Bằng chứng cần cập nhật |
|---|---|---|
| Runtime API/auth/persistence | Có runtime đã audit; chưa release-gated | API traces, isolation và persistence smoke |
| Retrieval/evidence/citation | Có implementation hiện tại; kết quả chưa đạt/đủ | Ablation, traces, semantic review, citation gate |
| Corpus 14 PDF frozen | **UNVERIFIED**; manifest runtime có 17 Markdown entries | Immutable 14-PDF snapshot/provenance/gate |
| Gold 40 cases / 8 categories | Diagnostic gate; coverage giới hạn, chưa đủ bằng chứng release | Immutable run, semantic review và safety/citation gates |
| UI/deployment | Có topology/runtime evidence một phần | Manual browser và deployment verification |
| Release decision | **UNVERIFIED / NOT RELEASE-READY** | Tất cả acceptance evidence ở mục 5 |

## 8. Deferred target topology (không mô tả là runtime)

Các thành phần sau chỉ được triển khai khi có scope/ADR, code, dependency/deployment evidence và evaluation chứng minh; hiện **deferred**, không phải blocker được giả định đã giải quyết:

- Parser Router với Docling/MinerU, Canonical Document IR và Legal Structure Extractor.
- Legal relation database, versioned provision store/amendment resolver và PostgreSQL làm source of truth.
- Redis/Dramatiq background orchestration, MinIO/object storage và immutable accepted-publish pipeline.
- LangGraph controlled workflow, production reranker, structured claims, sáu lớp verifier và bounded failure-aware repair.
- Langfuse/observability mở rộng.
- Upload, reviewer/admin approval, review queue và các flow tương tự.

Deferred topology không được dùng để claim release capability. Mọi thay đổi phải tuân thủ quy tắc quản lý thay đổi trong [00-scope-and-decisions.md](00-scope-and-decisions.md), đồng bộ với [02-yeu-cau-he-thong.md](02-yeu-cau-he-thong.md), [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md), [06-test-evaluation.md](06-test-evaluation.md) và [07-deployment.md](07-deployment.md).
