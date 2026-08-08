# 05. Kế Hoạch Triển Khai (Implementation Plan)

> **Giai đoạn SDLC**: 4 - Thực hiện và cài đặt
> **Ngày tạo**: 16/06/2026
> **Ngày baseline v1**: 19/07/2026
> **Ngày thiết kế lại v2**: 08/08/2026
> **Ngày bắt đầu kế hoạch mới**: 20/07/2026
> **Hạn hoàn thành**: 12/09/2026
> **Ngày tập bảo vệ**: 13/09/2026
> **Ngày bảo vệ**: 14/09/2026
> **Tổng thời gian**: 55 ngày triển khai và hoàn thiện
> **Tên đề tài**: Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng
> **English title**: A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations
> **Tài liệu quyết định nguồn**: [00-scope-and-decisions.md](00-scope-and-decisions.md)
> **Tài liệu thiết kế nguồn**: [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md)
> **Tài liệu tech stack nguồn**: [04-tech-stack-llm-research.md](04-tech-stack-llm-research.md)

---

## 5.1. Mục tiêu và phạm vi kế hoạch

Kế hoạch này triển khai kiến trúc VNLRAG v2 đã chốt trong [00-scope-and-decisions.md](00-scope-and-decisions.md), thiết kế chi tiết trong [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md) và tech stack trong [04-tech-stack-llm-research.md](04-tech-stack-llm-research.md). Đây là bản kế hoạch thay thế hoàn toàn kế hoạch v1 dựa trên UDEF; thuật ngữ UDEF chỉ xuất hiện trong tài liệu này ở ghi chú lịch sử (mục 5.1.3 và phần Ghi chú lịch sử cuối tài liệu) và hạng mục dọn dependency/chuyển đổi (5.4 W1); bảng mapping chi tiết nằm tại doc 04 mục 4.20.

### 5.1.1. Mục tiêu cuối cùng trước 12/09/2026

1. Hoàn thành toàn bộ yêu cầu chức năng P0 (FR-01..FR-28, FR-31, FR-32) theo acceptance criteria cấp hệ thống của doc 02 mục 2.10.
2. Có corpus đã review chứa văn bản hiện hành và lịch sử, có manifest và SHA-256, version hóa.
3. Current, historical và comparison query chạy end-to-end qua LangGraph controlled workflow.
4. Bất biến API Returned Invalid Citation Rate = 0.
5. Chạy được bốn suite thí nghiệm A-D trên gold set 200 câu (40 development / 40 validation / 120 final test).
6. Có bảng so sánh RAGFlow baseline (bốn variant) trên cùng corpus và cùng bộ câu hỏi evaluation.
7. Có final evaluation report tái lập được, báo cáo khóa luận, slide và demo local ổn định.
8. Có kế hoạch khôi phục khi lỗi xảy ra (failure-recovery plan) cho từng rủi ro cụ thể, không thu hẹp chức năng vì thời gian.

### 5.1.2. Phạm vi P0 bắt buộc

Mọi FR P0 trong doc 02 mục 2.9 đều nằm trong phạm vi bắt buộc của kế hoạch này:

- **Ingestion**: FR-01 Parser Router (Docling chính, MinerU phụ/fallback), FR-02 Canonical Document IR, FR-03 Legal Structure Extractor (nhãn Điểm a) b) c) d) đ) e), short-Point retention), FR-04 parent-context enrichment, FR-05 Legal Reference Resolver, FR-06 Temporal and Amendment Resolver, FR-07 background ingestion qua hàng đợi, FR-08 object storage MinIO, FR-09 review routing, FR-10 corpus QA.
- **Retrieval và query**: FR-11 Query Understanding và evidence planning, FR-12 Query Expansion, FR-13 exact legal lookup, FR-14 dense + sparse + RRF, FR-15 reranking, FR-16 legal context expansion, FR-17 Evidence Completeness Gate, FR-18 Hỏi đáp quy định hiện hành, FR-19 Hỏi đáp quy định tại thời điểm lịch sử, FR-20 So sánh quy định giữa hai thời điểm, FR-21 provision search.
- **Generation và verification**: FR-22 structured generation, FR-23 verification sáu tầng L1-L6, FR-24 failure-aware repair và abstention, FR-25 disclaimer, FR-26 observability Langfuse, FR-27 feedback, FR-28 evaluation bốn suite A-D.
- **Tích hợp và benchmark**: FR-31 benchmark RAGFlow baseline, FR-32 hiển thị answer và citation từ metadata.

P1 (FR-29 conversation history, FR-30 admin review UI) chỉ được triển khai sau khi toàn bộ acceptance criteria P0 đạt (rủi ro R20). Không có hạng mục P0 nào bị loại bỏ hoặc hoãn lại vì lịch trình.

### 5.1.3. Ghi chú lịch sử ngắn

Thiết kế v1 dựa trên UDEF với pipeline `PDF -> UDEF -> Docling -> CDM` và các milestone M1-M8 gắn với UDEF domain pack. Phiên bản v2 loại bỏ hoàn toàn UDEF (ADR-001, doc 03 mục 3.35); kế hoạch này xây milestone mới quanh Parser Router, Canonical Document IR và Legal Structure Extractor do dự án sở hữu. Các thành phần cũ bị loại: ChromaDB, SQLite làm database chính, rank-bm25 pickle, DuckDuckGo/SerpAPI fallback, query-time HITL. Chi tiết tại doc 00 mục 5 và 14.

---

## 5.2. Nguyên tắc lập kế hoạch

### 5.2.1. Gate gắn với acceptance criteria

Mỗi milestone kết thúc bằng gate, và mỗi gate gắn với tiêu chí kiểm chứng có thể đo được từ doc 02 (tiêu chí kiểm chứng của từng FR và acceptance criteria cấp hệ thống mục 2.10). Một hạng mục chỉ được đánh dấu hoàn thành khi gate tương ứng pass, không phải khi code đã tồn tại trên branch.

### 5.2.2. Thứ tự dependency

Thứ tự bắt buộc của pipeline xác định trình tự tối thiểu của các workstream:

```text
Parser Router và Canonical Document IR
    -> Legal Structure Extractor
    -> Legal Reference Resolver và Temporal/Amendment Resolver
    -> PostgreSQL (nguồn chân lý)
    -> Qdrant (index dẫn xuất)
    -> Retrieval đa tầng
    -> Evidence Completeness Gate
    -> Structured generation và verification L1-L6
    -> Frontend và feedback
    -> Evaluation và RAGFlow baseline
    -> Final report
```

Không triển khai UI phức tạp trước khi retrieval và verifier ổn định (doc 03 mục 3.2.4).

### 5.2.3. Workstream song song

Các luồng độc lập được chạy song song để không chặn nhau:

- Parser benchmark (Suite A) song song với thiết lập data platform (PostgreSQL, Qdrant, MinIO, Redis, Dramatiq);
- Thiết lập Langfuse (project, API key, trace skeleton) song song từ tuần 1, không chờ pipeline chính;
- Gold set được soạn dần từ tuần 2 (nhập liệu và review song song với code);
- Báo cáo khóa luận được viết song song từ tuần 3, không dồn vào tuần cuối.

### 5.2.4. Đường găng (critical path)

Đường găng của đề tài đi qua các thành phần nghiên cứu chính:

```text
Canonical Document IR
    -> Legal Structure Extractor
    -> PostgreSQL
    -> Qdrant
    -> Retrieval
    -> Evidence Completeness
    -> Verification
    -> Evaluation
    -> Final report
```

Chi tiết tại mục 5.13. UI không nằm trên đường găng nghiên cứu nhưng cần cho demo bảo vệ, nên frontend được lập kế hoạch độc lập từ tuần 6.

### 5.2.5. Đo tiến độ bằng gate, không bằng số file

Tiến độ được đo theo trạng thái gate:

```text
not started -> implemented -> tested -> integrated -> evaluated -> released
```

Ví dụ: `Legal Structure Extractor implemented != completed`; hoàn thành nghĩa là có unit test, integration test trên fixture ba loại văn bản và chỉ số corpus QA. Số dòng code hoặc số file commit không phải thước đo tiến độ.

### 5.2.6. Viết tài liệu song song

Mỗi tuần phải cập nhật: ADR hoặc change log, implementation note, test result, limitation, số liệu benchmark (nếu có), screenshot hoặc diagram. Không để toàn bộ báo cáo đến tuần cuối (R18).

### 5.2.7. Không thay đổi kiến trúc âm thầm

Mọi thay đổi ảnh hưởng schema, corpus, retrieval, model, prompt, experiment hoặc deadline phải có ADR hoặc change log (doc 00 mục 16). Không sửa gold set đã đóng băng sau khi xem final test result.

### 5.2.8. Không ghi kết quả trước khi đo

Mọi con số ngưỡng trong kế hoạch này là target hoặc gate, không phải kết quả thực nghiệm đã đạt. Kết quả thực nghiệm chỉ được ghi sau khi chạy evaluation theo doc 00 mục 11 và doc 06.

---

## 5.3. Mốc tổng thể (summary table)

Các mốc dưới đây xây quanh kiến trúc v2. Cột "Thời gian" khớp tuần mà công việc chính của mốc diễn ra; cột "Tuần chính" là tuần tập trung hoàn thành gate. Ngoại lệ duy nhất: M2 có gate accept+index chốt ở W4 (10/08-16/08) vì cần Legal Reference Resolver và Temporal/Amendment Resolver tồn tại từ M3 (W4). LangGraph triển khai theo doc 00 mục 12: skeleton controlled workflow trong W5 (M4), full graph với verifier thật trong W6 (M5); toàn bộ là controlled workflow, không phải autonomous agent.

| Milestone | Thời gian | Tuần chính | Deliverable chính | Gate |
|---|---|---|---|---|
| M0. Scope Freeze | 19/07 | - | Scope, kiến trúc, tech stack và kế hoạch chốt ở mức scope-baseline freeze | Kế hoạch này được duyệt; tài liệu 00-04 đạt baseline scope, không phải bất biến; cập nhật nghiên cứu sau freeze có kiểm soát và được ghi vào change log |
| M1. Parser Foundation + Canonical IR | 20/07-02/08 | W1-W2 | Suite A (P1-P3) first pass parser-only, Canonical Document IR, Parser Router, manifest và fixture | Ba loại văn bản (Luật, Nghị định, Thông tư) parse được qua IR; routing ghi `source_parser`; gate 5.4, 5.5 |
| M2. Legal Extraction + Data Platform | 03/08-16/08 | W3 (gate W4) | Legal Structure Extractor, corpus QA, PostgreSQL, Qdrant, MinIO, ingestion queue | Extractor và data platform pass cuối W3 (gate 5.6); Gate M2 accept+index E2E chốt W4 sau khi resolver tồn tại (gate 5.7) |
| M3. Relation Graph + Temporal | 10/08-16/08 | W4 | Legal Reference Resolver, Temporal/Amendment Resolver, bảng quan hệ, `LegalEffectEvent`, parent-context enrichment | Quan hệ provision/văn bản trong PostgreSQL; khoảng hiệu lực đúng; Gate M2 chốt (gate 5.7) |
| M4. Retrieval + Expansion + Evidence | 17/08-23/08 | W5 | Suite B (E1-E3) và Suite C (R1-R10), query expansion, reranker, legal context expansion, Evidence Completeness Gate, LangGraph skeleton | Retrieval đa tầng chạy; evidence gate chặn câu trả lời nửa vời; LangGraph skeleton chạy (gate 5.8) |
| M5. Verification + Langfuse + Feedback | 24/08-30/08 | W6 | Verification sáu tầng L1-L6, LangGraph full flow (từ skeleton W5), failure-aware repair, Langfuse trace, feedback | Current/historical/comparison E2E; Returned Invalid Citation Rate = 0; gate 5.9 |
| M6. Frontend + Integration | 24/08-30/08 | W6 | Chat UI, search, citation panel, passage viewer, feedback widget, review CLI (P0) | Demo flow hoàn chỉnh; gate 5.9 |
| M7. Evaluation + Stabilization | 31/08-06/09 | W7 | Gold set 200 câu (40/40/120), Suite D (G1-G7), RAGFlow baseline B1-B4 + bảng so sánh, performance | Gold set đóng băng; Suite D report; RAGFlow B1-B4 hoàn tất; feature freeze 06/09; gate 5.10 |
| M8. Finalization | 07/09-12/09 | W8 | Code freeze 10/09, final evaluation, report, slide, release candidate `v1.0.0-rc2` 12/09 (packaging bảng so sánh RAGFlow vào report) | Release candidate reproducible; gate 5.11 |
| M9. Defense | 13/09-14/09 | - | Rehearsal và bảo vệ | Demo local ổn định trên đúng tag `v1.0.0-rc2` |

Mốc kiểm soát cứng theo doc 00 mục 12 và doc 01 mục 1.5:

- **Feature freeze**: 06/09/2026.
- **Code freeze**: 10/09/2026.
- **Release candidate**: 12/09/2026.
- Không thêm tính năng mới trong hai ngày cuối; không deploy hoặc cập nhật code trong ngày bảo vệ.
- Sau M0, các cập nhật nghiên cứu có kiểm soát vẫn được cho phép và phải ghi vào change log (ví dụ doc 04 được refresh nghiên cứu ngày 08/08/2026); chúng không làm thay đổi phạm vi đã chốt.

### 5.3.1. Workstream corpus hoàn chỉnh (W1-W6)

Theo doc 00 mục 10, corpus mục tiêu gồm **20-30 văn bản chính thống**, ít nhất **5 chuỗi sửa đổi/thay thế/bãi bỏ**, có cả văn bản hiện hành và lịch sử; mỗi văn bản có manifest (`document_id`, `source_url`, `downloaded_at`, `file_hash`, `document_number`, `document_type`, `issuer`, `issued_date`, `effective_from`, `effective_to`, `status`, `relation_notes`, `review_status`, `reviewed_by`, `reviewed_at`). Workstream này chạy song song từ W1 đến W6, độc lập với pipeline code, và là tiền đề cho mọi evaluation trên gold set.

| Tuần | Batch mới | Lũy kế mục tiêu | Yêu cầu nội dung |
|---|---|---|---|
| W1 (20/07-26/07) | 3-5 văn bản (Luật, Nghị định, Thông tư) | 3-5 | Có văn bản hiện hành và ít nhất một văn bản lịch sử; manifest + SHA-256 |
| W2 (27/07-02/08) | +3-5 văn bản | 6-10 | Tiếp tục phân bố hiện hành/lịch sử; bắt đầu gom chuỗi quan hệ |
| W3 (03/08-09/08) | +3-5 văn bản | 9-15 | Ít nhất 2 chuỗi sửa đổi/thay thế/bãi bỏ đã ghi nhận |
| W4 (10/08-16/08) | +4-5 văn bản | 13-20 | Ít nhất 3 chuỗi quan hệ; structural QA cho văn bản quan trọng |
| W5 (17/08-23/08) | +4-5 văn bản | 17-25 | Mọi văn bản dev/validation gold set tham chiếu được review |
| W6 (24/08-30/08) | +3-5 văn bản | 20-30 | Hoàn tất review; đủ ít nhất 5 chuỗi quan hệ; mọi văn bản indexed |

Gate "corpus ready" (hai mức, đều đo được):

- **Corpus evaluation-ready (trước Suite B/C ở W5)**: mọi văn bản được dev/validation gold set tham chiếu đều có trong corpus đã review (manifest, SHA-256, `review_status = ACCEPTED`); Suite B/C không bắt đầu khi gate này fail.
- **Corpus complete (cuối W6, trước final evaluation W7)**: 20-30 văn bản đã review và index, ≥5 chuỗi quan hệ, có cả hiện hành và lịch sử, corpus QA 16 chỉ số đã chạy; gate này là điều kiện bắt đầu Suite D và final evaluation.

Nếu tốc độ review không theo kịp target tuần, ưu tiên review theo thứ tự văn bản được gold set tham chiếu trước, giữ mọi văn bản có manifest và hash trước khi index (R10).

---

## 5.4. Tuần 1: 20/07-26/07 - Chốt thiết kế, corpus, schema và hạ tầng foundation

**Milestone**: M0 (hoàn tất 19/07) + khởi động M1.

### Mục tiêu

- Repository chuyển sang baseline v2, dependency được pin.
- Schema manifest và Canonical Document IR được chốt dạng schema.
- Workstream corpus (5.3.1) khởi động: batch 01 gồm 3-5 văn bản chính thống có text layer, cả hiện hành và lịch sử.
- Hạ tầng nền (Docker Compose cho PostgreSQL, Qdrant, Redis, MinIO) khởi động được.
- Langfuse Cloud được cấu hình để trace từ sớm.
- Fixture cho Suite A (Luật, Nghị định, Thông tư) và gold annotation cấu trúc được tạo.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 20/07 | Đồng bộ tài liệu 00-04, tạo branch triển khai, cập nhật change log | Branch và ADR đầu tiên | doc 00 mục 13 |
| 20/07 | Pin Python 3.11, uv lock, dependency backend và frontend; dọn dependency v1 (UDEF, ChromaDB, rank-bm25, pyvi) khỏi plan | `pyproject.toml`, `uv.lock`, `.python-version` | doc 04 mục 4.2 |
| 21/07 | Docker Compose skeleton: PostgreSQL 18, Qdrant v1.19, Redis 8, MinIO, backend, worker | Compose khởi động, health pass | doc 03 mục 3.2.5 |
| 21/07 | Cấu hình env: `MAX_INGESTION_WORKERS=1`, giới hạn bộ nhớ Docker theo service, `.env.example` | Cấu hình vận hành | doc 03 mục 3.2.5 |
| 22/07 | Tạo `corpus-manifest.schema.json`, `legal-document.schema.json`, `legal-provision.schema.json` | JSON Schema pass | FR-01, FR-03; doc 03 mục 3.9 |
| 22/07 | Thiết kế schema Canonical Document IR (`ParsedDocument`, `ParsedPage`, `DocumentElement`) | IR schema | FR-02; doc 03 mục 3.6 |
| 23/07 | Corpus batch 01 (mục tiêu workstream 5.3.1): 3-5 văn bản (Luật, Nghị định, Thông tư; ưu tiên PDF born-digital có text layer), gồm hiện hành và lịch sử; tải và tính SHA-256 | `data/manifests/batch-01/` | doc 00 mục 10; doc 01 mục 1.2.10 |
| 23/07 | Cấu hình Langfuse Cloud: project, API key, trace skeleton, prompt template đầu | Langfuse hoạt động | FR-26; doc 03 mục 3.27 |
| 24/07 | Tạo fixture Suite A: một Luật, một Nghị định, một Thông tư kèm gold annotation cấu trúc (Điều/Khoản/Điểm, nhãn d) đ)) | `tests/fixtures/` + gold annotation | FR-28, UC-11 |
| 24/07 | Thiết kế quy tắc Parser Router và quality gates (nhóm A parser-level, nhóm B structural) dạng config | `parser_router.yaml` draft | FR-01; doc 03 mục 3.7 |
| 25/07 | Viết golden fixture đầu tiên cho Legal Structure Extractor (stable-ID phân biệt `diem-d` và `diem-đ`) | Golden fixture | FR-03; doc 03 mục 3.8.5 |
| 25/07 | Spike Docling trên một Nghị định, kiểm tra layout/OCR tiếng Việt | Parser output thử nghiệm | doc 04 mục 4.3 |
| 26/07 | Review tuần: kiểm tra gate W1, cập nhật change log và weekly status | Weekly status | - |

### Deliverable

```text
templates/corpus-manifest.schema.json
templates/legal-document.schema.json
templates/legal-provision.schema.json
backend/app/ingestion/document_ir.py         (Pydantic IR schema)
backend/app/config.py
data/manifests/batch-01/
tests/fixtures/parser_benchmark/
docker-compose.yml
.env.example
```

### Gate

- [ ] Docker Compose khởi động PostgreSQL, Qdrant, Redis, MinIO; health endpoint pass (NFR-03).
- [ ] Manifest và schema validate bằng JSON Schema.
- [ ] Corpus batch 01 có 3-5 văn bản (Luật, Nghị định, Thông tư), gồm hiện hành và lịch sử, mỗi văn bản có manifest và SHA-256 (doc 00 mục 10; mục 5.3.1).
- [ ] Fixture Suite A có gold annotation cấu trúc.
- [ ] Golden fixture stable-ID phân biệt `diem-d` (Điểm d)) và `diem-đ` (Điểm đ)) (FR-03).
- [ ] Langfuse nhận được trace thử nghiệm; `LANGFUSE_ENABLED=false` tắt được trace không làm fail query (FR-26).
- [ ] Không còn dependency v1 (UDEF, ChromaDB, rank-bm25, pyvi) trong `pyproject.toml`.

### Dependencies

- Phụ thuộc: tài liệu 00-04 đã chốt (M0).
- Chặn: toàn bộ workstream ingestion (W2, W3) vì thiếu IR schema, manifest và hạ tầng nền.

### Failure recovery

- Nếu nguồn chính thức khó tải PDF có text layer: giảm batch đầu xuống 3 văn bản nhưng giữ đủ Luật, Nghị định, Thông tư; PDF scan đi qua OCR backend CPU và phải qua quality gate trước review (doc 01 mục 1.2.10).

---

## 5.5. Tuần 2: 27/07-02/08 - Parser foundation và Canonical Document IR

**Milestone**: M1 (gate W2).

### Mục tiêu

- Cài đặt Canonical Document IR và adapter cho Docling và MinerU.
- Cài đặt Parser Router với quality gates nhóm A và nhóm B.
- Chạy Suite A first pass (P1 Docling, P2 MinerU, P3 Parser Router) trên fixture.
- Ghi nhận kết quả routing và parser version vào IR và `ingestion_runs.parser_routing`.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 27/07 | Adapter Docling -> Canonical Document IR | `adapters/docling_adapter.py` | FR-02; doc 03 mục 3.6 |
| 27/07 | Adapter MinerU -> Canonical Document IR (đọc JSON/Markdown output) | `adapters/mineru_adapter.py` | FR-02 |
| 28/07 | Pin exact version Docling 2.x và MinerU 3.4.x tại install, ghi parser version | Lock dependency | doc 04 mục 4.3 |
| 28/07 | Parser Router: quy tắc routing theo đặc tính tài liệu | `parser_router.py` | FR-01; doc 03 mục 3.7 |
| 29/07 | Quality gates nhóm A (provenance coverage, text extraction rate, table detection, layout coherence) | `quality_gates.py` (parser-level) | FR-01; doc 03 mục 3.7.3 |
| 29/07 | Quality gates nhóm B (point label detection, hierarchy completeness, short-Point retention) | `quality_gates.py` (structural) | FR-01; doc 03 mục 3.7.3 |
| 30/07 | Chạy P1 (Docling) trên fixture, tính chỉ số Suite A | Suite A - P1 raw result | FR-28, UC-11 |
| 30/07 | Chạy P2 (MinerU) trên fixture, xác minh OCR tiếng Việt 3.4.x | Suite A - P2 raw result | FR-28, UC-11 |
| 31/07 | Chạy P3 (Parser Router) trên fixture, kiểm tra fallback Docling -> MinerU | Suite A - P3 raw result | FR-28, UC-11 |
| 31/07 | Triển khai metric Suite A parser-only (first pass): Article/Clause/Point P/R/F1, Short Point Recall, Vietnamese đ) Recall, Table Preservation, Header/Footer Leakage, Provenance Coverage | `evaluation/suites/suite_a.py` | FR-28; doc 03 mục 3.9.13 |
| 01/08 | Ingest batch đầu qua pipeline parse (chưa extract pháp lý), lưu parser output lên MinIO | IR JSON + parser artifacts | FR-07, FR-08 |
| 01/08 | Corpus batch 02 (5.3.1): +3-5 văn bản, tải và manifest | Corpus batch 02 | doc 00 mục 10 |
| 01/08 | Quyết định MinerU local (pipeline CPU) hay remote `*-http-client` sau P2 | Quyết định + ghi chú | doc 01 mục 1.2.7 |
| 02/08 | Review tuần, tổng hợp kết quả Suite A first pass (raw, chưa kết luận) | Suite A first-pass report | - |

### Deliverable

```text
backend/app/ingestion/adapters/docling_adapter.py
backend/app/ingestion/adapters/mineru_adapter.py
backend/app/ingestion/parser_router.py
backend/app/ingestion/quality_gates.py
backend/app/ingestion/document_ir.py
backend/app/evaluation/suites/suite_a.py
data/evaluation/suite-a-first-pass/
```

### Gate

- [ ] P1, P2 và P3 chạy được trên cùng fixture; raw output lưu bất biến (FR-28).
- [ ] Ma trận fixture routing đúng: searchable PDF -> Docling; scan -> Docling -> quality gate fail -> MinerU; bảng phức tạp -> so sánh đầu ra hai parser (FR-01).
- [ ] Legal Structure Extractor (W3) chỉ đọc IR, không đọc định dạng parser; thêm adapter mới không làm thay đổi extractor (FR-02, NFR-06).
- [ ] Mọi `DocumentElement` có `source_parser`, `parser_version`, `raw_reference` (NFR-09).
- [ ] Header/footer leakage được đo trong Suite A metric.
- [ ] Parent Context Completeness không thuộc first pass W2; chỉ số này được đo và ghi vào Suite A final report sau khi Legal Context Enricher (W3) tồn tại (FR-28; doc 03 mục 3.9.13).
- [ ] Không khẳng định parser nào vượt trội tuyệt đối trước khi có kết quả Suite A hoàn chỉnh (FR-01).

### Dependencies

- Phụ thuộc: IR schema và fixture từ W1.
- Chặn: Legal Structure Extractor (W3), corpus QA (W3), mọi dữ liệu provision phụ thuộc chất lượng parse.

### Gate M1

M1 pass khi:

```text
3 document types (Luật, Nghị định, Thông tư) parse được qua IR
Suite A first-pass raw result tồn tại (P1-P3, parser-only; Parent Context Completeness đo sau W3)
Parser Router quyết định và quality gate kết quả ghi vào parser_routing
```

Nếu M1 fail, không bắt đầu frontend hoặc LangGraph.

### Failure recovery

- Nếu MinerU pipeline backend vượt RAM 19 GB: chuyển sang remote `*-http-client` (dedicated host) hoặc chỉ dùng Docling pipeline cho nhóm tài liệu đang fail, trong khi sửa; kết quả ghi lại trong Suite A (doc 01 mục 1.6).
- Nếu một parser lane không qua quality gates trên một nhóm tài liệu: định tuyến tạm toàn bộ tài liệu nhóm đó qua parser còn hoạt động tốt trong khi sửa parser kia; không trộn kết quả hai parser cho cùng tài liệu (doc 03 mục 3.7.3).

---

## 5.6. Tuần 3: 03/08-09/08 - Legal extraction, corpus QA và data platform

**Milestone**: M2.

### Mục tiêu

- Legal Structure Extractor nhận diện Chương, Mục, Điều, Khoản, Điểm với nhãn tiếng Việt a) b) c) d) đ) e) và short-Point retention.
- Legal Context Enricher bổ sung parent-context vào `retrieval_text`; `source_text` bất biến.
- PostgreSQL schema (toàn bộ entity doc 03 mục 3.10) và Alembic migration.
- Qdrant collection với dense + sparse vector, payload, filter, alias; MinIO buckets.
- Ingestion queue Redis + Dramatiq với chuỗi actor.
- Corpus QA dashboard 16 chỉ số.
- Review routing và review CLI (P0).

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 03/08 | Legal Structure Extractor: state parser Chương/Mục/Điều/Khoản/Điểm, nhãn Điểm tiếng Việt | `structure_extractor.py` | FR-03; doc 03 mục 3.8 |
| 03/08 | Quy tắc tạo `provision_id` deterministic gồm dạng `{loai}-{so}-{nam}__dieu-{n}__khoan-{n}__diem-{chu-cai}` và dạng Appendix/Table/Transitional/Heading | ID rule | FR-03; doc 03 mục 3.8.5 |
| 04/08 | Short-Point retention: không áp dụng ngưỡng loại bỏ Điểm ngắn hợp lệ; xử lý biến thể OCR (d/đ, số La Mã, header/footer) | Normalization | FR-03; doc 03 mục 3.8.4 |
| 04/08 | Legal Context Enricher: bổ sung parent-context vào `retrieval_text`, hash `source_text` không đổi | `context_enricher.py` | FR-04; doc 03 mục 3.8.6 |
| 05/08 | SQLAlchemy models toàn bộ entity + Alembic migration đầu tiên | `persistence/models/`, migration | FR-05, FR-06; doc 03 mục 3.10 |
| 05/08 | Qdrant collection `legal_provisions_v1` + alias `legal_provisions_active`: dense (768 dims khởi điểm), sparse BM25, payload, index | `qdrant_store.py` | FR-14; doc 03 mục 3.11 |
| 06/08 | MinIO buckets (source-pdfs, parser-outputs, page-images, ingestion-artifacts, review-artifacts, evaluation-artifacts) | MinIO layout | FR-08; doc 03 mục 3.12 |
| 06/08 | Redis broker + Dramatiq actors: parse, normalize, extract, resolve_refs, resolve_temporal, quality_gate, embed, index; actor time limit per actor | `actors/` | FR-07; doc 03 mục 3.13 |
| 07/08 | Upload API: `POST /documents` -> 202 + `ingestion_job_id`; job status API | API upload + jobs | FR-07; doc 03 mục 3.28.3 |
| 07/08 | Embedding adapter (Gemini Embedding 2, 768 dims khởi điểm) và sparse encoder adapter | `retrieval/embedding.py`, `retrieval/sparse.py` | FR-14; doc 03 mục 3.11.2 |
| 08/08 | Corpus QA: 16 chỉ số (document/article/clause/point count, Point coverage, short-Point retention, đ) detection, orphan, duplicate, parent-context coverage, provenance coverage, table coverage, unresolved cross-reference, unknown effective date, temporal conflict) | `corpus_qa.py` | FR-10; doc 03 mục 3.10.5 |
| 08/08 | Quality gates + review routing (accepted/needs_review/dropped) và review CLI | `quality_gate_actor`, `scripts/review_item.py` | FR-09; doc 03 mục 3.4.2 |
| 08/08 | Actor idempotency test: kill worker giữa bước, re-run, job tồn tại và không index trùng | Idempotency test | FR-07; doc 03 mục 3.13.3 |
| 08/08 | MinIO put/get round-trip từng bucket; backup độc lập (replication hoặc `mc mirror`/`mc cp`) được xác minh | MinIO backup test | FR-08; doc 03 mục 3.12.3 |
| 09/08 | Đo Parent Context Completeness sau khi enricher hoạt động; cập nhật Suite A | Suite A update | FR-28; doc 03 mục 3.9.13 |
| 09/08 | Chạy pipeline ingestion tới quality gate và review routing trên batch 01; accept+index E2E chưa chốt vì resolver có từ W4 | Corpus batch 01 (review routing) | FR-07, FR-09 |
| 09/08 | Corpus batch 03 (5.3.1): +3-5 văn bản, tải và manifest | Corpus batch 03 | doc 00 mục 10 |
| 09/08 | Review tuần, cập nhật weekly status | Weekly status | - |

### Deliverable

```text
backend/app/ingestion/structure_extractor.py
backend/app/ingestion/context_enricher.py
backend/app/ingestion/quality_gates.py
backend/app/ingestion/actors/*
backend/app/persistence/models/*
backend/app/persistence/repositories/*
alembic/versions/...
backend/app/retrieval/qdrant_store.py
backend/app/retrieval/embedding.py
backend/app/retrieval/sparse.py
backend/app/evaluation/corpus_qa.py
scripts/review_item.py
```

### Gate

- [ ] Fixture Luật, Nghị định, Thông tư nhận diện đúng phân cấp; nhãn `đ)` và `d)` không lẫn (FR-03).
- [ ] Fixture stable-ID phân biệt `nd-168-2024__dieu-7__khoan-4__diem-d` và `...__diem-đ` (FR-03).
- [ ] Điểm ngắn hợp lệ không bị loại bỏ; short-Point retention đo được trong corpus QA (FR-03, FR-10).
- [ ] `source_text` hash không đổi sau enrichment; `retrieval_text` kế thừa parent-context (FR-04).
- [ ] Migration chạy từ database rỗng; document/provision round-trip PostgreSQL (NFR-06).
- [ ] Qdrant point có dense và sparse vector; payload đầy đủ hierarchy, interval, review status, parser version (FR-14).
- [ ] `POST /documents` trả 202 + `ingestion_job_id`; job status theo dõi được; không parse đồng bộ (FR-07).
- [ ] Chỉ `accepted` được index; `needs_review` cần quyết định reviewer; `dropped` không bao giờ được index (FR-09).
- [ ] Corpus QA report có đủ 16 chỉ số (FR-10).
- [ ] Actor time limit cấu hình per actor, không dùng mặc định 10 phút mù cho bước dài (NFR-02).
- [ ] Actor idempotent: kill worker giữa bước, chạy lại actor, job tiếp tục từ state PostgreSQL và không index trùng (FR-07; doc 03 mục 3.13.3).
- [ ] MinIO put/get round-trip cho từng bucket; backup độc lập được xác minh bằng replication hoặc `mc mirror`/`mc cp`; tiering/ILM không được tính là backup (FR-08; doc 03 mục 3.12.3).
- [ ] Parent Context Completeness được đo và ghi vào Suite A final report (FR-28).

### Gate M2 (chốt ở W4)

Gate accept+index E2E của M2 không được kiểm tra trong W3 vì Legal Reference Resolver và Temporal/Amendment Resolver chỉ tồn tại từ W4; provision ACCEPTED phải có interval hiệu lực do resolver xác định. Gate M2 được chốt trong W4 sau khi cả hai resolver hoạt động (xem Gate M2 tại mục 5.7). Các gate khác của M2 (extractor FR-03, enricher FR-04, queue FR-07, MinIO FR-08, review routing FR-09, corpus QA FR-10) vẫn được kiểm tra cuối W3.

### Dependencies

- Phụ thuộc: IR và parser từ W2; fixture và manifest từ W1.
- Chặn: relation graph và temporal (W4), retrieval (W5), verification (W6).

### Failure recovery

- Nếu Legal Structure Extractor lỗi trên một loại văn bản: giảm batch review, không auto-index, chuyển provision nghi vấn sang `needs_review`; tiếp tục fix extractor trong khi các văn bản khác vẫn ingest (R2).
- Nếu RAM không đủ khi chạy ingestion song song: giữ `MAX_INGESTION_WORKERS=1`, lập lịch ingestion riêng (batch), dừng frontend khi cần (R17).

---

## 5.7. Tuần 4: 10/08-16/08 - Relation graph và temporal

**Milestone**: M3.

### Mục tiêu

- Legal Reference Resolver trích `ProvisionReference` (PARENT_OF, REFERS_TO, SIBLING_OF, PENALTY_COMPANION) và `DocumentRelation` (AMENDS, REPEALS, SUPERSEDES, CORRECTS, GUIDES, RELATED_TO).
- Temporal and Amendment Resolver tính khoảng `[effective_from, effective_to)` từ manifest, `LegalEffectEvent` và review.
- Hỗ trợ sửa đổi từng phần, thay thế, bãi bỏ; hiệu lực không chắc chắn định tuyến review.
- Parent-context enrichment tích hợp vào ingestion pipeline hoàn chỉnh.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 10/08 | Legal Reference Resolver: pattern `REFERS_TO`, `SIBLING_OF`, suy luận `PENALTY_COMPANION`, `PARENT_OF` từ cây phân cấp | `reference_resolver.py` | FR-05; doc 03 mục 3.14 |
| 10/08 | Ghi unresolved reference (`UNRESOLVED`, `PENDING_REVIEW`) và định tuyến review | Review items | FR-05; doc 03 mục 3.14.3 |
| 11/08 | Temporal and Amendment Resolver: đọc manifest + `LegalEffectEvent`, tính interval | `temporal_resolver.py` | FR-06; doc 03 mục 3.15 |
| 11/08 | `LegalEffectEvent`: EFFECTIVE, AMENDED, PARTIAL_AMENDED, SUPERSEDED, REPEALED, CORRECTED, EXPIRED | Event model | FR-06; doc 03 mục 3.9.8 |
| 12/08 | Sửa đổi từng phần: tạo row provision mới, version tăng, `provision_versions` registry với `superseded_by_version` | Version logic | FR-06; doc 03 mục 3.15.3 |
| 12/08 | Temporal query: điều kiện hợp lệ tại ngày `d` trong PostgreSQL | Temporal repository | FR-06, FR-19; doc 03 mục 3.15.2 |
| 13/08 | Exclusion constraint: không hai version ACCEPTED chồng lấn | DB constraint | doc 03 mục 3.10.4 |
| 13/08 | Canonical date policy: câu hỏi chỉ có năm; kiểm tra sự kiện đổi hiệu lực trong năm | Date policy module | FR-11, UC-02; doc 03 mục 3.16.4 |
| 14/08 | Integration test: quy tắc hiệu lực `effective_from <= d AND (effective_to IS NULL OR d < effective_to) AND review_status = ACCEPTED` | Temporal tests | FR-06 |
| 14/08 | Relation query cho context expansion: mở rộng theo temporal + review filter | Relation repo | FR-16; doc 03 mục 3.20.2 |
| 15/08 | Bắt đầu xây development set (20-30 câu) từ fixture và corpus | `data/gold-sets/development/` | FR-28 |
| 15/08 | Corpus QA trên văn bản quan trọng (ví dụ Nghị định 168): structural QA có mục tiêu | Structural QA report | FR-10, UC-12 |
| 16/08 | Corpus batch 04 (5.3.1): +4-5 văn bản, tải và manifest | Corpus batch 04 | doc 00 mục 10 |
| 16/08 | Review tuần, cập nhật weekly status | Weekly status | - |

### Deliverable

```text
backend/app/ingestion/reference_resolver.py
backend/app/ingestion/temporal_resolver.py
backend/app/persistence/repositories/relations.py
backend/app/persistence/repositories/temporal.py
backend/app/query/date_policy.py
data/gold-sets/development/          (draft)
alembic/versions/xxx_relations_temporal.py
```

### Gate

- [ ] Quan hệ trích được khớp fixture; precision/recall trích xuất quan hệ báo cáo trong corpus QA (FR-05).
- [ ] Reference không giải quyết được ghi `UNRESOLVED` và định tuyến review, không suy đoán quan hệ (FR-05).
- [ ] Provision hợp lệ cho ngày `d` theo đúng điều kiện hiệu lực (FR-06).
- [ ] Không có hai version ACCEPTED chồng lấn trong cùng provision (doc 03 mục 3.10.4).
- [ ] Sửa đổi từng phần: provision ID giữ nguyên, version tăng, `provision_versions` ghi `superseded_by_version` (FR-06).
- [ ] Hiệu lực không chắc chắn: `effective_from`/`effective_to` NULL, tạo ReviewItem, không index (FR-06; doc 03 mục 3.15.6).
- [ ] Canonical date policy: nếu có sự kiện đổi hiệu lực trong năm -> `MISSING_QUERY_DATE`; nếu không -> canonical date + hiển thị ngày áp dụng (FR-11).
- [ ] `LegalEffectEvent` ghi `affected_provision_versions` structured (FR-06).

### Gate M2 (chốt tại W4)

M2 pass khi một accepted provision chạy end-to-end với resolver thật:

```text
Parser output -> IR -> Legal Structure Extractor
    -> Legal Reference Resolver -> Temporal/Amendment Resolver
    -> PostgreSQL (ACCEPTED, có effective interval từ resolver)
    -> embed -> Qdrant -> search result
```

Gate M2 không được chốt trước khi Legal Reference Resolver và Temporal/Amendment Resolver tồn tại và được test (FR-05, FR-06); điều này bảo đảm không có provision ACCEPTED/indexed nào thiếu interval hiệu lực.

### Dependencies

- Phụ thuộc: LegalProvision và PostgreSQL từ W3.
- Chặn: legal context expansion (W5), temporal retrieval (W5), historical/comparison query (W6).

### Failure recovery

- Nếu không mô hình hóa được một quan hệ sửa đổi phức tạp: ghi nhận unsupported relation, định tuyến review, không suy đoán tự động (R2).
- Nếu temporal conflict thực sự xảy ra: mô hình unresolved/PENDING_REVIEW, tạm loại khỏi query serving cho tới khi reviewer quyết định (doc 03 mục 3.10.4).

---

## 5.8. Tuần 5: 17/08-23/08 - Retrieval đa tầng, query expansion và evidence

**Milestone**: M4.

### Mục tiêu

- Query Understanding (QueryPlan) với evidence plan.
- Query Expansion: normalized query, multi-query rewrite, conditional HyDE (luôn giữ câu hỏi gốc).
- Retrieval pipeline: exact legal lookup + dense + sparse + RRF fusion + temporal filter + dedup + exact-match promotion.
- Suite B (E1-E3 embedding benchmark) trên development set.
- Suite C (R1-R10 retrieval ablation) trên validation set.
- Reranker (Jina Reranker v3) tích hợp; đánh giá qua R6.
- Legal Context Expansion (parent, sibling, cross-reference, penalty companion).
- Evidence Completeness Gate và targeted retrieval.
- LangGraph controlled workflow tối thiểu: ghép node retrieval/evidence đã có vào graph, routing `check_evidence` và bộ đếm `repair_attempts`.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 17/08 | Query Understanding: deterministic parsing (ngày, năm, số hiệu văn bản, Điều/Khoản/Điểm, loại phương tiện) + LLM structured fallback | `query/query_understanding.py` | FR-11; doc 03 mục 3.16 |
| 17/08 | Evidence plan mapping theo loại câu hỏi | `query/evidence_plan.py` | FR-11; doc 03 mục 3.16.5 |
| 18/08 | Query Expansion: normalized (thuật ngữ pháp lý versioned), multi-query rewrite (giới hạn), conditional HyDE | `query/expansion.py`, `query/hyde.py` | FR-12; doc 03 mục 3.17 |
| 18/08 | Exact legal lookup theo payload filter + SQL | `retrieval/exact_lookup.py` | FR-13; doc 03 mục 3.18 |
| 19/08 | Dense + sparse + RRF fusion trong Qdrant Query API; temporal filter | `retrieval/hybrid.py` | FR-14; doc 03 mục 3.18 |
| 19/08 | Dedup theo `provision_id`, exact-match promotion | `retrieval/filters.py` | FR-13; doc 03 mục 3.18.5 |
| 20/08 | Reranker Jina Reranker v3: adapter, cache, `top_n` giới hạn | `retrieval/reranker.py` | FR-15; doc 03 mục 3.19 |
| 20/08 | Legal Context Expansion quanh seed mạnh, ghi `added_by`/`source_id`/`depth`, temporal + review filter | `retrieval/context_expansion.py` | FR-16; doc 03 mục 3.20 |
| 21/08 | Evidence Completeness Gate + targeted retrieval theo `evidence_gaps` | `query/evidence_gate.py` | FR-17; doc 03 mục 3.21 |
| 21/08 | Hoàn thiện development set 40 câu; dựng validation set draft | Gold set dev/validation | FR-28 |
| 21/08 | Corpus batch 05 (5.3.1): +4-5 văn bản, tải và manifest | Corpus batch 05 | doc 00 mục 10 |
| 22/08 | Suite B (E1-E3) trên dev set: Recall@10, MRR@10, nDCG@10, latency, cost | `suite_b.py` + raw result | FR-28; doc 03 mục 3.9.13 |
| 22/08 | Suite C (R1-R10) trên validation set: cấu hình tích lũy | `suite_c.py` + raw result | FR-28; doc 03 mục 3.9.13 |
| 23/08 | LangGraph skeleton: `analyze_query -> resolve_temporal -> expand_query -> retrieve_parallel -> fuse -> rerank -> expand_legal_context -> check_evidence`; conditional edge `INCOMPLETE -> targeted_retrieval -> check_evidence`; `generate`/`verify` dùng stub xác định; counter `repair_attempts` | `workflow/graph.py` (skeleton) | FR-24; doc 03 mục 3.5 |
| 23/08 | Review tuần: kết quả Suite B và C (raw, chưa chốt embedding/reranker) | Weekly status | - |

### Deliverable

```text
backend/app/query/query_understanding.py
backend/app/query/evidence_plan.py
backend/app/query/expansion.py
backend/app/query/hyde.py
backend/app/query/evidence_gate.py
backend/app/retrieval/exact_lookup.py
backend/app/retrieval/hybrid.py
backend/app/retrieval/reranker.py
backend/app/retrieval/context_expansion.py
backend/app/evaluation/suites/suite_b.py
backend/app/evaluation/suites/suite_c.py
backend/app/workflow/graph.py   (skeleton, generate/verify stub)
data/gold-sets/development/   (40 câu)
data/gold-sets/validation/    (draft 40 câu)
data/evaluation/suite-b/, data/evaluation/suite-c/
```

### Gate

- [ ] Query Understanding route đúng intent CURRENT/HISTORICAL/COMPARISON/SOURCE_SEARCH/OUT_OF_SCOPE; evidence plan liệt kê đúng loại bằng chứng (FR-11).
- [ ] Câu hỏi gốc luôn được retain trong tập query; HyDE chỉ bật có điều kiện; rewrite có giới hạn (FR-12).
- [ ] Exact lookup trả đúng provision theo số văn bản, Điều, Khoản, Điểm; candidate exact được bảo toàn sau fusion (FR-13).
- [ ] Dense, sparse và RRF chạy độc lập; mỗi variant R1-R10 tái lập được bằng config (FR-14).
- [ ] Reranker chạy như stage chuẩn; không khẳng định cải thiện trước khi có kết quả R6 (FR-15).
- [ ] Mở rộng ngữ cảnh chỉ quanh seed mạnh; `depth` có giới hạn; mọi provision mở rộng ghi lý do (FR-16).
- [ ] Câu hỏi mức phạt + điểm trừ mà chỉ tìm được mức phạt bị đánh dấu `INCOMPLETE` và được bổ sung trước khi gọi generator (FR-17).
- [ ] Suite B và C chạy bằng config, lưu run metadata và raw output (FR-28, NFR-08).
- [ ] Current query không lấy provision hết hiệu lực; historical query không lấy văn bản tương lai (FR-18, FR-19).
- [ ] LangGraph skeleton chạy: `analyze_query -> ... -> check_evidence`; `INCOMPLETE` routing tới `targeted_retrieval`; mọi đường quay lại tăng `repair_attempts`; stub `generate`/`verify` trả kết quả xác định (FR-24; doc 03 mục 3.5.4).
- [ ] Corpus evaluation-ready: mọi văn bản dev/validation gold set tham chiếu có trong corpus đã review (manifest, SHA-256, `review_status = ACCEPTED`); Suite B/C không chạy khi gate này fail (doc 00 mục 10; mục 5.3.1).

### Dependencies

- Phụ thuộc: PostgreSQL, Qdrant (W3); relation graph (W4).
- Chặn: generation và verification (W6); Suite D phụ thuộc pipeline retrieval hoàn chỉnh.

### Failure recovery

- Nếu retrieval chưa đạt trên một variant: tiếp tục ablation Suite C để xác định tầng bổ sung hiệu quả thay vì bỏ tầng mặc định (doc 01 mục 1.6).
- Nếu Evidence Completeness Gate over-abstain: điều chỉnh threshold dựa trên validation set, không loại bỏ gate và không hạ chuẩn verified-or-abstain (R9).
- Nếu embedding API gặp lỗi/quota: retry 429/5xx có giới hạn, budget cap, không đổi model âm thầm (R13).

---

## 5.9. Tuần 6: 24/08-30/08 - Verification, Langfuse, frontend và integration

**Milestone**: M5 + M6.

### Mục tiêu

- Structured generation theo schema cấp claim (Gemini 3.5 Flash, `json_schema`).
- Verification sáu tầng L1-L6 với bất biến Returned Invalid Citation Rate = 0.
- LangGraph full flow (từ skeleton W5): hoàn thiện node `verify`/`repair`/`abstain` với verifier thật và failure-aware repair có giới hạn.
- Langfuse trace toàn pipeline, prompt management, feedback gửi về Langfuse.
- Frontend: chat, search, citation panel, passage viewer, feedback widget, abstention panel, date selector.
- Review CLI (P0) hoàn chỉnh; API contract đầy đủ.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 24/08 | Structured generation: `StructuredAnswer`, `Claim`, generator adapter Gemini 3.5 Flash | `generation/gemini.py`, `generation/schemas.py` | FR-22; doc 03 mục 3.23 |
| 24/08 | L1 schema verifier (kèm `L1_SUMMARY_UNSUPPORTED`) | `verification/l1_schema.py` | FR-23; doc 03 mục 3.24 |
| 25/08 | L2 citation ID verifier (DB + context whitelist + `review_status`) | `verification/l2_citation.py` | FR-23; doc 03 mục 3.24 |
| 25/08 | L3 temporal verifier (interval check theo `query_date`) | `verification/l3_temporal.py` | FR-23 |
| 26/08 | L4 numeric grounding verifier (chuẩn hóa số tiền, điểm, ngày) | `verification/l4_numeric.py` | FR-23 |
| 26/08 | L5 claim support verifier: deterministic trước, LLM judge độc lập (GPT-5.4 mini snapshot) chỉ cho semantic, fail-closed | `verification/l5_claim.py` | FR-23; doc 03 mục 3.24.2 |
| 27/08 | L6 evidence completeness verifier (claims bao phủ evidence plan) | `verification/l6_evidence.py` | FR-23 |
| 27/08 | LangGraph hoàn thiện trên skeleton W5: gắn generator và verifier L1-L6 thật; conditional edges `verify` (valid -> finalize, repairable -> repair, invalid/unrecoverable -> abstain); bounded repair loop | `workflow/graph.py`, `workflow/state.py`, `workflow/nodes/*` | FR-24; doc 03 mục 3.5 |
| 28/08 | Failure-aware repair bốn đường + `MAX_REPAIR_ATTEMPTS` config | Repair module | FR-24; doc 03 mục 3.25 |
| 28/08 | Langfuse trace model: spans `legal_query`, `analyze_query`, ..., `claim_verify`; prompt management | `observability/tracing.py` | FR-26; doc 03 mục 3.27 |
| 29/08 | API contract: chat, search, documents, jobs, reviews, feedback, health, evaluations, corpus-qa; disclaimer field | `api/*` | FR-21, FR-25, FR-32; doc 03 mục 3.28 |
| 29/08 | Feedback: `POST /feedback`, lưu PostgreSQL gắn `trace_id`, gửi điểm số về Langfuse | Feedback API | FR-27; doc 03 mục 3.26 |
| 30/08 | Frontend: chat, search, citation card, passage viewer, applied date badge, abstention panel, feedback widget | `frontend/app/chat/`, `/search/`, components | FR-32; doc 03 mục 3.29 |
| 30/08 | Corpus batch 06 (5.3.1): +3-5 văn bản, hoàn tất review toàn bộ; gate corpus complete | Corpus 20-30 văn bản đã review | doc 00 mục 10 |
| 30/08 | Docker Compose full stack; Playwright smoke; integration bug fixing | Stable demo | NFR-03 |
| 30/08 | Review tuần, cập nhật weekly status | Weekly status | - |

### Deliverable

```text
backend/app/generation/
backend/app/verification/l1_schema.py ... l6_evidence.py
backend/app/workflow/graph.py, state.py, nodes/*
backend/app/observability/tracing.py
backend/app/api/chat.py, search.py, documents.py, jobs.py, reviews.py, feedback.py
frontend/app/chat/, frontend/app/search/
frontend/components/CitationCard.tsx, SourceDrawer.tsx, AbstentionPanel.tsx, FeedbackWidget.tsx
scripts/review_item.py
```

### Gate

- [ ] Current, historical và comparison query chạy end-to-end qua LangGraph (FR-18, FR-19, FR-20).
- [ ] Generator output validate bằng Pydantic; schema fail đi qua repair, không regex/sửa JSON (FR-22).
- [ ] Unknown provision ID không được trả; temporal invalid citation không được trả (Returned Invalid Citation Rate = 0) (FR-23).
- [ ] Claim số liệu sai bị chặn bởi L4; claim không được hỗ trợ bị chặn bởi L5 (FR-23).
- [ ] Mọi nhánh repair tính vào `MAX_REPAIR_ATTEMPTS`; hết giới hạn -> ABSTAIN; không vòng lặp vô hạn (FR-24).
- [ ] OUT_OF_SCOPE và insufficient-evidence query trả abstention kèm lý do chuẩn (FR-24).
- [ ] Disclaimer có trong mọi response (FR-25).
- [ ] Langfuse trace ghi lại được; `LANGFUSE_ENABLED=false` không làm fail query (FR-26).
- [ ] Feedback round-trip create/read; feedback gắn đúng `trace_id`; danh mục báo cáo đầy đủ (FR-27).
- [ ] Citation UI dựng từ database metadata; applied date hiển thị; không stream draft chưa verify (FR-32).
- [ ] Search endpoint `/api/v1/search` chạy độc lập (không gọi LLM generator), trả top-k kèm `provision_id`, hierarchy (article/clause/point), khoảng hiệu lực, page và provenance; integration test pass (FR-21; doc 03 mục 3.28.2).
- [ ] Corpus complete: 20-30 văn bản đã review và index, ≥5 chuỗi quan hệ, hiện hành + lịch sử; gate này chốt trước final evaluation W7 (doc 00 mục 10; mục 5.3.1).
- [ ] Full stack start từ Docker volume sạch; E2E smoke pass (NFR-03).

### Gate M5 và M6

M5 pass khi năm scenario E2E chạy: current verified, historical verified, comparison verified, out-of-scope abstained, invalid citation blocked.

M6 pass khi demo flow hoàn chỉnh: chat current/historical/comparison, citation card mở được passage, feedback gửi được, abstention không hiển thị như system error, review CLI accept/reject hoạt động.

### Dependencies

- Phụ thuộc: retrieval + evidence gate (W5); PostgreSQL, Qdrant (W3); relation/temporal (W4).
- Chặn: evaluation (W7), demo bảo vệ.

### Failure recovery

- Nếu judge online (L5) không khả dụng: claim không kết luận được bằng deterministic bị xử lý fail-closed, không bao giờ giữ với trạng thái "chưa kiểm chứng" (doc 03 mục 3.24.2).
- Nếu provider structured output fail liên tục: repair có giới hạn, sau đó ABSTAIN; không âm thầm đổi model (NFR-03).
- Nếu Langfuse down: trace bỏ qua, query vẫn hoạt động (FR-26).

---

## 5.10. Tuần 7: 31/08-06/09 - Gold set, evaluation và stabilization

**Milestone**: M7.

### Mục tiêu

- Hoàn thiện và đóng băng gold set 200 câu (40 development / 40 validation / 120 final test).
- Chạy Suite D (G1-G7) trên validation set.
- Thiết lập RAGFlow baseline (B1-B4) trong môi trường benchmark riêng; bảng so sánh bốn variant hoàn tất trước feature freeze 06/09.
- Đo performance (latency, cost) và chạy regression.
- Feature freeze 06/09.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 31/08 | Hoàn thiện final test set 120 câu; review expected/acceptable provision IDs | Gold set final draft | FR-28; doc 03 mục 3.9.13 |
| 01/09 | Review độc lập label gold (expected_provision_ids, required_evidence, must_include/must_not_include_facts) | Gold review | NFR-08; doc 03 mục 3.9.13 |
| 01/09 | Hash và đóng băng gold set; ghi `gold_version`, `gold_set_hash` | Frozen gold set | FR-28 |
| 02/09 | Suite D (G1-G7) trên validation set: generation + verification ablation | `suite_d.py` + raw result | FR-28; doc 03 mục 3.9.13 |
| 02/09 | RAGFlow baseline setup (môi trường benchmark riêng, min 4 CPU/16 GB RAM/50 GB disk) | RAGFlow env | FR-31; doc 03 mục 3.2.5 |
| 03/09 | Chạy B1 (RAGFlow default) và B2 (RAGFlow + Docling) trên cùng corpus và eval queries | Baseline raw result | FR-31; doc 04 mục 4.6 |
| 03/09 | Performance: P50/P95 latency, token usage, cost; ghi vào run metadata | Benchmark report | NFR-02, NFR-08 |
| 04/09 | Ragas metrics (thứ cấp) trên selected variants | Semantic report | doc 04 mục 4.17 |
| 04/09 | Regression và defect fixing; reconcile PostgreSQL vs Qdrant | Stable build | NFR-06, doc 03 mục 3.13.6 |
| 05/09 | Chạy B3 (RAGFlow + MinerU) và B4 (VNLRAG custom pipeline) tuần tự sau B1/B2; dựng bảng so sánh bốn variant B1-B4 | Baseline raw result + comparison table | FR-31 |
| 05/09 | Thống kê và charts từ JSON/CSV evaluation | Tables/charts | NFR-08 |
| 06/09 | Feature freeze: khóa feature branch, chỉ sửa defect | Feature freeze | doc 00 mục 12 |
| 06/09 | Review tuần, cập nhật weekly status | Weekly status | - |

### Deliverable

```text
data/gold-sets/gold-v1/                 (40 dev / 40 validation / 120 final test, đã hash)
data/gold-sets/gold-v1/hash.json
backend/app/evaluation/suites/suite_d.py
data/evaluation/suite-d/
data/evaluation/ragflow-baseline/       (B1-B4 raw + comparison.csv)
data/evaluation/performance/
docs/weekly/2026-09-06.md
```

### Gate

- [ ] Gold set 200 câu đã review, đủ 17 danh mục, chia 40/40/120; có `expected_provision_ids`, `acceptable_provision_ids`, `required_evidence`, `temporal_metadata`, `review_status`, `gold_version`, `hash` (FR-28).
- [ ] Final test set đóng băng trước final run; không dùng để tuning (NFR-08).
- [ ] Suite D (G1-G7) chạy bằng config; raw per-query output được lưu; run bất biến (FR-28).
- [ ] B1-B4 RAGFlow chạy tuần tự trong môi trường benchmark riêng, không cùng lúc ingestion/demo; bảng so sánh bốn variant hoàn tất trước feature freeze 06/09 (FR-31).
- [ ] Metric deterministic được tính; judge model được pin; token usage và cost được lưu (NFR-08).
- [ ] Mỗi run B1-B4 lưu: corpus hash dùng chung, query-set hash đã đóng băng, adapter/evaluator version, run config và raw per-query output; `comparison.csv` chỉ sinh sau khi cả bốn variant có raw output (FR-31, NFR-08).
- [ ] Không chỉnh gold set sau khi xem final test result (NFR-08).
- [ ] Feature freeze ngày 06/09; không thêm tính năng mới sau mốc này (doc 00 mục 12).

### Gate M7

M7 pass khi có:

```text
corpus hash
gold-set hash (gold-v1)
Suite D result (G1-G7)
RAGFlow B1-B4 raw result + comparison table
metrics JSON/CSV
latency report
cost report
error analysis
feature freeze confirmed
```

### Dependencies

- Phụ thuộc: pipeline W5-W6; gold set dựng dần từ W4.
- Chặn: finalization (W8), report.

### Failure recovery

- Nếu gold set chưa đủ chất lượng: tăng review, tách batch review qua queue, không hạ số lượng (R10).
- Nếu RAGFlow baseline cạnh tranh RAM local: bắt buộc chạy đủ mọi variant, chạy tuần tự từng variant, dừng service không cần thiết; nếu RAM không đủ, chạy tuần tự trên máy phù hợp khác, không lược bớt variant (R15).

---

## 5.11. Tuần 8: 07/09-12/09 - Finalization, code freeze và release candidate

**Milestone**: M8.

### Mục tiêu

- Chọn production config sau kết quả Suite B/C/D.
- Chạy final evaluation trên final test set 120 câu với cấu hình đã pin.
- Packaging bảng so sánh RAGFlow baseline (B1-B4, đã chạy ở W7) vào report.
- Code freeze 10/09; release candidate `v1.0.0-rc2` 12/09 (tag bất biến dùng cho rehearsal và bảo vệ).
- Báo cáo và slide hoàn thiện; clean-room installation test.

### Công việc

| Ngày | Công việc | Output | FR / doc 03 |
|---|---|---|---|
| 07/09 | Chốt production config (embedding, reranker, threshold evidence, prompt version) từ kết quả Suite B/C/D | Final config | ADR-013; doc 03 mục 3.11.6 |
| 07/09 | Final evaluation: final test set 120 câu, cấu hình pin, chạy 1 lần | Final eval report | FR-28; doc 01 mục 1.4 |
| 08/09 | Packaging bảng so sánh RAGFlow (B1-B4 từ W7) vào report; đối chiếu số liệu raw | Report section | FR-31 |
| 08/09 | Viết chương phương pháp và implementation | Report draft | - |
| 09/09 | Viết chương evaluation (tables/charts từ eval JSON) và discussion/limitation | Report draft | - |
| 09/09 | Kiểm tra citation tài liệu tham khảo; kiểm tra metric report khớp code | Reference audit | - |
| 10/09 | Code freeze: chỉ sửa crash, data corruption, invalid citation leak, deployment fail, report build fail, demo blocker | Release branch | doc 00 mục 12 |
| 10/09 | Tag release candidate `v1.0.0-rc1` từ working tree sạch đã commit | Git tag | mục 5.16 |
| 11/09 | Build LaTeX/PDF từ nguồn; hoàn thiện slide; ghi video backup | Thesis PDF, slide, video | - |
| 12/09 | Clean-room installation test: clone sạch -> compose -> demo | Installation report | NFR-03 |
| 12/09 | Tag `v1.0.0-rc2` từ working tree sạch; rehearsal 13/09 và bảo vệ 14/09 dùng đúng tag này; tag `v1.0.0` chỉ tạo sau bảo vệ; backup corpus, database, Qdrant snapshot, MinIO | Release candidate `v1.0.0-rc2` | mục 5.15.4, 5.16.3 |

### Deliverable

```text
evaluation-config-final.yaml
data/evaluation/final/          (final test result, raw + aggregate)
data/evaluation/ragflow-baseline/B4/ + comparison.csv   (chạy W7, packaging W8)
docs/thesis/*.tex, *.pdf
docs/slides/defense.pptx (hoặc tương đương)
docs/demo/backup-video.mp4
docs/release/manifest-1.0.0-rc2.json
```

### Gate

- [ ] Clean clone chạy theo README; Docker Compose health pass (NFR-03).
- [ ] Demo current/historical/comparison pass; abstention pass (doc 02 mục 2.10).
- [ ] Returned Invalid Citation Rate = 0 trên final evaluation (FR-23).
- [ ] Cả bốn variant RAGFlow baseline chạy trên cùng corpus và eval queries; so sánh Recall@10, citation correctness, temporal leakage, evidence completeness (FR-31).
- [ ] Corpus backup, database backup, Qdrant snapshot, MinIO backup và video backup tồn tại (NFR-03).
- [ ] Report không có metric giả; slide dùng số liệu khớp report; mọi số liệu có raw evidence (doc 00 mục 11).
- [ ] Release tag được tạo; release candidate reproducible từ working tree sạch.
- [ ] Rehearsal và bảo vệ dùng đúng tag `v1.0.0-rc2`; không deploy hoặc đổi code sau tag; tag `v1.0.0` chỉ được tạo sau bảo vệ, không kèm thay đổi code (5.15.4).

### Gate M8

M8 pass khi có release candidate `v1.0.0-rc2` với: git tag, dependency lock, docker image digest, database migration version, corpus hash, gold-set hash, model config, final evaluation report.

### Dependencies

- Phụ thuộc: toàn bộ pipeline (W2-W6), gold set và Suite D (W7).
- Chặn: rehearsal và bảo vệ.

### Failure recovery

- Nếu báo cáo chậm: viết chương song song từ W3; tuần 8 chỉ hoàn thiện, không viết từ đầu (R18).
- Nếu provider down lúc chốt release: dùng config đã pin, không đổi model; demo retrieval-only + video backup (R19).

---

## 5.12. Ma trận phụ thuộc (dependency matrix)

| Deliverable | Phụ thuộc | Chặn |
|---|---|---|
| Canonical Document IR | Adapter Docling/MinerU, manifest schema (W1) | Legal Structure Extractor, corpus QA |
| Parser Router | Docling + MinerU adapter, quality gates (W2) | Suite A (P3), mọi pipeline ingest |
| Suite A (P1-P3) | IR, fixture gold annotation (W1-W2); Parent Context Completeness cần Legal Context Enricher (W3) | Quyết định routing parser; Suite A final report (9 chỉ số) |
| Legal Structure Extractor | Canonical Document IR (W2) | LegalProvision, parent-context, corpus QA |
| Legal Context Enricher | Legal Structure Extractor (W3) | `retrieval_text`; Suite A metric Parent Context Completeness |
| Legal Reference Resolver | LegalProvision, manifest (W3) | Relation graph, context expansion |
| Temporal/Amendment Resolver | LegalProvision, `LegalEffectEvent`, manifest (W3) | Temporal retrieval, historical/comparison |
| PostgreSQL schema | LegalProvision + relation + temporal output (W3-W4) | Qdrant build, temporal query |
| Qdrant collection | PostgreSQL ACCEPTED provisions, embedding (W3) | Retrieval pipeline |
| Ingestion queue (Redis + Dramatiq) | PostgreSQL, MinIO, actors (W3) | End-to-end ingest, review flow |
| Query Understanding + evidence plan | QueryPlan schema (W5) | Query expansion, evidence gate |
| Query Expansion | QueryUnderstanding (W5) | Retrieval variants R3-R5 |
| Retrieval (exact + dense + sparse + RRF) | Qdrant, PostgreSQL (W5) | Rerank, context expansion, evidence gate |
| Reranker | Fusion output, Jina API (W5) | Suite C R6 |
| Legal Context Expansion | Relation graph (W4), retrieval (W5) | Evidence gate, multi-evidence answers |
| Evidence Completeness Gate | Evidence plan, context (W5) | Generation |
| LangGraph skeleton (W5) | Retrieval + Evidence Completeness Gate (W5) | Gắn generator/verifier vào graph (W6) |
| Structured generation | Context package, schema (W6) | Verification |
| Verification L1-L6 | Draft answer, DB, evidence plan (W6) | Finalize/abstain, UI answer |
| Langfuse trace | Workflow (W5-W6) | Observability (không chặn correctness) |
| Frontend | API contract (W6) | Demo bảo vệ |
| Feedback | API, PostgreSQL, Langfuse (W6) | - |
| Gold set | Corpus, review workload (W4-W7) | Suite B/C/D, final report |
| Suite D (G1-G7) | Pipeline W5-W6, validation set (W7) | Chọn config production |
| RAGFlow baseline B1-B4 | Corpus hoàn chỉnh, eval queries (W7) | Bảng so sánh baseline (trước feature freeze 06/09) |
| Final evaluation | Gold set frozen, config pin (W8) | Final report |
| Docker Compose full stack | Tất cả services (W3-W6) | Demo bảo vệ |
| Final report + slide | Final evaluation + baseline (W8) | Bảo vệ |

---

## 5.13. Đường găng (critical path)

Đường găng của đề tài là chuỗi các thành phần nghiên cứu quyết định kết quả evaluation:

```text
Canonical Document IR
    -> Legal Structure Extractor
    -> PostgreSQL (nguồn chân lý)
    -> Qdrant (index dẫn xuất)
    -> Retrieval đa tầng
    -> Evidence Completeness Gate
    -> Verification L1-L6
    -> Evaluation (Suite A-D)
    -> Final report
```

Các mắt xích có rủi ro lịch trình cao nhất trên đường găng (doc 01 mục 1.5):

1. Parser benchmark và quality gate định tuyến (W2);
2. Legal hierarchy extraction, gồm nhãn Điểm d) và đ) (W3);
3. Relation và temporal resolution (W4);
4. Evidence completeness (W5);
5. Gold set 200 câu và review workload (W4-W7);
6. Viết báo cáo song song với code.

**Vị trí của UI**: frontend không nằm trên đường găng nghiên cứu vì nó không ảnh hưởng tới correctness, retrieval hay verification của pipeline. Tuy nhiên UI là yêu cầu cho demo bảo vệ (NFR-03, FR-32), nên nó được lập kế hoạch độc lập từ tuần 6 và không được phép chiếm thời gian của các gate trên đường găng. Nếu một hạng mục trên đường găng chậm, ưu tiên xử lý nó trước thay vì chuyển công sức sang UI (R20).

---

## 5.14. Rủi ro và kế hoạch ứng phó (risk register)

Bảng dưới đây giữ nguyên ID, xác suất, tác động và biện pháp giảm thiểu từ doc 01 mục 1.6. Không có "scope reduction ladder"; mọi tình huống được xử lý bằng failure-recovery plan cụ thể.

| ID | Rủi ro | Xác suất | Tác động | Biện pháp giảm thiểu |
|---|---|---:|---:|---|
| R1 | Gán sai ngày hoặc trạng thái hiệu lực | Trung bình | Rất cao | Manifest bắt buộc, đối chiếu nguồn chính thức, temporal unit test, reviewer approval |
| R2 | Không mô hình hóa đúng sửa đổi một phần | Cao | Rất cao | Giới hạn corpus, relation schema rõ ràng, ghi nhận unsupported relation, không suy đoán tự động |
| R3 | MinerU VLM/hybrid backend không khả thi local (GPU 8 GB VRAM không có) | Cao | Trung bình | Chỉ dùng pipeline backend CPU; vlm/hybrid qua remote `*-http-client` hoặc ghi nhận không khả thi local; ưu tiên corpus PDF có text layer |
| R4 | Docling/MinerU gây lỗi OCR/layout trên PDF pháp luật tiếng Việt, nhận sai nhãn Điểm (d) và đ)) | Cao | Cao | Suite A parser benchmark, fixture theo loại văn bản, quality gates, corpus QA, structural QA cho văn bản quan trọng (ví dụ Nghị định 168) |
| R5 | Parser Router định tuyến sai tài liệu sang parser không phù hợp | Trung bình | Cao | Quy tắc routing theo đặc tính tài liệu, quality gates phát hiện lỗi và kích hoạt fallback parser, ghi `source_parser` vào Document IR |
| R6 | Trích xuất cross-reference sai hoặc reference không giải quyết được | Trung bình | Cao | Relation schema rõ ràng, ghi unresolved reference, định tuyến sang review, không suy đoán quan hệ |
| R7 | LLM tạo claim không được passage hỗ trợ | Cao | Rất cao | Structured output, provision ID whitelist, verifier L2/L4/L5, failure-aware repair có giới hạn, sau đó abstain |
| R8 | Retrieval không lấy được provision đúng | Trung bình | Cao | Exact lookup + dense + sparse + RRF, ablation Suite C, regression set, Recall@k và MRR |
| R9 | Evidence Completeness Gate over-abstain (bác bỏ đáp án hợp lệ) hoặc under-abstain | Trung bình | Cao | Evidence plan chuẩn hóa, threshold xác định từ baseline và validation set, không đặt ngưỡng trước thực nghiệm |
| R10 | Corpus không được review đủ trước deadline | Trung bình | Cao | Ưu tiên corpus cốt lõi, chia batch review qua queue, cache PDF và manifest kèm file hash, đối chiếu từ nhiều nguồn chính thức |
| R11 | Gold set bị tạo sau khi xem kết quả, gây leakage | Trung bình | Cao | Freeze gold set version, hash file, tách development/validation/final test, review độc lập |
| R12 | LLM judge thiên lệch hoặc không ổn định | Trung bình | Trung bình | Deterministic metric làm headline, pin GPT-5.4 mini snapshot, lưu raw judge output |
| R13 | Model API, quota hoặc giá thay đổi | Trung bình | Trung bình | Provider interface, pin model ID, budget cap, không hardcode quota trong logic |
| R14 | Langfuse không khả dụng | Thấp | Thấp | Langfuse không nằm trên đường tới hạn; trace fail không chặn query; bật/tắt qua config |
| R15 | Hạ tầng RAGFlow baseline (tối thiểu 16 GB RAM) cạnh tranh tài nguyên local | Cao | Trung bình | Bắt buộc chạy đủ mọi variant baseline trong môi trường benchmark riêng; chạy tuần tự từng variant, dừng service không cần thiết khi benchmark; nếu RAM local không đủ, chạy tuần tự trên máy phù hợp khác thay vì lược bớt variant |
| R16 | Lỗi hàng đợi MinIO/Redis/Dramatiq | Trung bình | Trung bình | Actor idempotent, retry middleware, dead-letter queue, giám sát worker, backup MinIO |
| R17 | PostgreSQL, Qdrant và parser dùng quá nhiều RAM khi chạy cùng | Cao | Trung bình | `MAX_INGESTION_WORKERS = 1`, dừng frontend khi benchmark cần thiết, giám sát Docker, cấu hình giới hạn bộ nhớ |
| R18 | Không kịp hoàn thiện báo cáo | Trung bình | Rất cao | Viết từng chương song song, feature freeze 06/09, code freeze 10/09 |
| R19 | Demo phụ thuộc Internet | Trung bình | Cao | Chuẩn bị retrieval-only demo, cache corpus, health check API, video backup |
| R20 | Scope P1 lấn sang P0 | Cao | Cao | P1 bị khóa cho đến khi toàn bộ acceptance criteria P0 đạt |

### 5.14.1. Failure-recovery plan (không thu hẹp phạm vi)

Không thu hẹp chức năng cốt lõi vì thời gian. Mọi hạng mục P0 phải hoàn thành trước feature freeze 06/09. Chỉ cho phép các phương án khôi phục tường minh khi một lỗi cụ thể xảy ra (doc 01 mục 1.6):

- Nếu một parser lane không qua quality gates trên nhóm tài liệu nhất định: định tuyến tạm toàn bộ tài liệu nhóm đó qua parser còn hoạt động tốt trong khi sửa parser kia; kết quả được ghi lại trong Suite A và corpus QA.
- Nếu MinerU VLM/hybrid backend không khả thi local: dùng pipeline backend CPU hoặc remote `*-http-client`; không giữ giả định VLM local.
- Nếu Evidence Completeness Gate over-abstain: điều chỉnh threshold dựa trên validation set, không loại bỏ gate và không hạ chuẩn verified-or-abstain.
- Nếu retrieval chưa đạt: tiếp tục ablation Suite C để xác định tầng bổ sung hiệu quả thay vì bỏ tầng mặc định.
- Nếu RAM local không đủ cho RAGFlow: chạy tuần tự từng variant trong môi trường benchmark riêng hoặc trên máy phù hợp khác; mọi variant bắt buộc chạy và kết quả được ghi lại đầy đủ.
- Mọi thay đổi phải giữ nguyên bất biến Returned Invalid Citation Rate = 0 và không thay đổi gold set đã đóng băng.

### 5.14.2. Ma trận khôi phục R1-R20

Mỗi rủi ro có: trigger, trạng thái an toàn tức thời, hành động khôi phục (owner), cách xác minh và ràng buộc giữ phạm vi. Không có phương án thu hẹp chức năng P0.

| ID | Trigger | Trạng thái an toàn tức thời | Hành động khôi phục / owner | Verification | Ràng buộc giữ phạm vi |
|---|---|---|---|---|---|
| R1 | Sai ngày/trạng thái hiệu lực phát hiện trong temporal test hoặc review | Provision nghi vấn không đưa vào query serving; chuyển `needs_review` | Reviewer đối chiếu nguồn chính thức và manifest; sửa interval; chạy temporal unit test (owner: reviewer/developer) | Temporal unit test pass; corpus QA temporal conflict count = 0 | Không suy đoán ngày hiệu lực; không bỏ temporal filtering |
| R2 | Không mô hình hóa được sửa đổi một phần | Ghi unsupported relation + ReviewItem; không suy đoán | Reviewer xác định phạm vi sửa đổi từ nguồn chính thức; ghi `LegalEffectEvent` PARTIAL_AMENDED (owner: reviewer) | Relation coverage trong corpus QA; không có hai version ACCEPTED chồng lấn | Giữ mô hình version-bound; không xóa quan hệ |
| R3 | MinerU VLM/hybrid không khả thi local | Chỉ dùng pipeline backend CPU | Dùng pipeline CPU hoặc remote `*-http-client`; ưu tiên corpus có text layer (owner: developer) | Suite A (P2) raw result ghi backend đã dùng | Giữ MinerU là parser fallback/challenger |
| R4 | OCR/layout lỗi, nhãn Điểm d) đ) sai | Kết quả structural nghi vấn không index | Chạy lại qua parser khác, fixture + quality gates + structural QA; không trộn kết quả hai parser (owner: developer) | Article/Clause/Point P/R/F1 trong Suite A; corpus QA đ) detection | Giữ quality gate; không index structural một phần |
| R5 | Parser Router định tuyến sai | Routing ghi lại, tài liệu ở `needs_review` | Sửa quy tắc routing theo đặc tính tài liệu; chạy ma trận fixture FR-01 (owner: developer) | Ma trận fixture routing pass | Giữ Parser Router + quality gate fallback |
| R6 | Cross-reference sai hoặc unresolved | Reference ghi `UNRESOLVED`, định tuyến review | Reviewer resolve thủ công hoặc re-extract với pattern đã sửa (owner: reviewer) | precision/recall trích xuất quan hệ trong corpus QA | Không suy đoán quan hệ |
| R7 | Claim không được passage hỗ trợ | Draft bị chặn, không ra UI | Verifier L2/L4/L5 + repair có giới hạn; sau đó ABSTAIN (owner: developer) | Returned Invalid Citation Rate = 0; Unsupported Claim Rate trong Suite D | Giữ verified-or-abstain |
| R8 | Retrieval không lấy đúng provision | Không trả answer; ghi lỗi retrieval | Ablation Suite C tìm tầng bổ sung; điều chỉnh config retrieval (owner: developer) | Recall@k, MRR@10 trên dev/validation set | Không bỏ kênh exact/dense/sparse mặc định |
| R9 | Evidence Gate over/under-abstain | Không đổi hành vi khi chưa đo | Điều chỉnh threshold từ baseline + validation set; khóa trong config (owner: developer) | Đo lại trên validation set trước khi chốt | Không loại bỏ gate; không hạ chuẩn verified-or-abstain |
| R10 | Corpus không review kịp | Chỉ index văn bản đã review | Ưu tiên review theo thứ tự gold set tham chiếu; chia batch qua queue (owner: reviewer) | Gate corpus evaluation-ready/complete (5.3.1) | Không index văn bản chưa review |
| R11 | Gold set leakage | Không xem final result khi tạo gold | Freeze + hash; review độc lập; tách dev/validation/final (owner: reviewer/developer) | gold_set_hash; split kiểm chứng | Không sửa gold set sau freeze |
| R12 | Judge thiên lệch/không ổn định | Judge chỉ là nguồn thứ cấp; deterministic là headline | Pin snapshot `gpt-5.4-mini-2026-03-17`; lưu raw judge output; đối chiếu trên subset (owner: developer) | So sánh judge result trên subset có gold | Judge không quyết định citation ID/temporal |
| R13 | API quota/giá thay đổi | Không đổi model âm thầm | Provider interface; retry 429/5xx có giới hạn; budget cap 30 USD/40 USD dự phòng; cấu hình lại (owner: developer) | Cost report mỗi run; không vượt cap | Giữ model config đã pin cho final evaluation |
| R14 | Langfuse không khả dụng | Trace bỏ qua, query vẫn chạy | `LANGFUSE_ENABLED=false`; ingest bất đồng bộ (owner: developer) | Query E2E pass khi Langfuse tắt | Langfuse không chặn correctness |
| R15 | RAGFlow cạnh tranh RAM local | Không chạy cùng ingestion/demo | Chạy tuần tự từng variant, dừng service không cần thiết; nếu không đủ, chạy trên máy khác (owner: developer) | B1-B4 raw + comparison.csv trước feature freeze | Không lược bớt variant |
| R16 | Lỗi queue/MinIO/Redis/Dramatiq | Job giữ state trong PostgreSQL; dead-letter queue giữ message | Actor idempotent + retry transient; reconcile script; restore MinIO từ backup độc lập (owner: developer) | Job phục hồi không index trùng; MinIO round-trip + backup test | Không mất job; không parse đồng bộ |
| R17 | RAM không đủ khi chạy nhiều service | Giới hạn Docker theo service | `MAX_INGESTION_WORKERS=1`; dừng frontend khi benchmark; lập lịch ingestion batch (owner: developer) | `docker stats` theo dõi; demo vẫn chạy | Không hạ RAM budget của RAGFlow baseline |
| R18 | Báo cáo chậm | Draft chương có từ W3 | Viết song song từ W3; feature/code freeze giữ nguyên (owner: tác giả) | Draft các chương trước 31/08 | Không viết báo cáo thay thế cho code |
| R19 | Demo phụ thuộc Internet | Chuẩn bị retrieval-only demo + cache | Health check API; retrieval-only demo; video backup (owner: developer) | Rehearsal chạy đủ kịch bản không LLM | Không đổi model chỉ vì demo |
| R20 | Scope P1 lấn sang P0 | Không merge P1 trước gate P0 | P1 bị khóa tới khi acceptance criteria P0 đạt; gate cứng trong weekly review (owner: tác giả) | Checklist P0 pass trước khi chạm P1 | Giữ phạm vi P0 |

---

## 5.15. Kiểm soát tiến độ (progress tracking)

### 5.15.1. Gate state

Mỗi hạng mục công việc được theo dõi theo gate:

```text
not started -> implemented -> tested -> integrated -> evaluated -> released
```

Ví dụ:

```text
Legal Structure Extractor implemented != completed
Legal Structure Extractor completed = unit test + fixture 3 loại văn bản + corpus QA metric
```

### 5.15.2. Weekly review

Mỗi tuần kết thúc bằng review với mẫu báo cáo:

```markdown
## Weekly Status
### Completed
- ... (kèm FR và doc 03 section)
### Evidence
- Commit:
- Test:
- Screenshot:
- Metric:
### In Progress
- ...
### Blockers
- ...
### Risks
- ...
### Next Week
- ...
### Scope Change
- None / ADR link
```

### 5.15.3. Definition of done theo milestone

- **Milestone hoàn thành**: deliverable tồn tại, gate pass (tie acceptance criteria doc 02 mục 2.10), rủi ro mới được ghi, weekly report được cập nhật, không còn blocker chưa có owner.
- **Feature hoàn thành**: acceptance criteria của FR tương ứng pass, unit test, integration test, failure scenario test, observability cơ bản, không phá regression, có demo hoặc artifact chứng minh.
- **PR gate**: mục tiêu rõ ràng, không vượt scope, unit/integration test, migration nếu đổi database, config docs nếu thêm env var, ADR nếu đổi architecture, Ruff và type check pass, không sửa frozen gold set trái quy trình. PR ảnh hưởng retrieval phải ghi before/after metrics, corpus version, gold-set version, config.

### 5.15.4. Versioning scheme

```text
0.1.0   Parser foundation spike (Parser Router + Canonical IR + Suite A first pass)
0.2.0   Legal extraction và data platform (extractor, PostgreSQL, Qdrant, MinIO, ingestion queue)
0.3.0   Relation graph và temporal (Reference Resolver, Temporal/Amendment Resolver)
0.4.0   Retrieval và evidence (Suite B/C, query expansion, reranker, evidence gate)
0.5.0   Verified query workflow (LangGraph, verification L1-L6, abstention)
0.6.0   Frontend integration + feedback
0.9.0   Feature freeze (06/09)
1.0.0-rc1  Code freeze (10/09)
1.0.0-rc2  Release candidate chốt (12/09); rehearsal (13/09) và bảo vệ (14/09) dùng đúng tag này
1.0.0   Tag sau bảo vệ (14/09, không kèm thay đổi code)
```

Chuỗi version khớp mốc kiểm soát của doc 00 mục 12 và doc 01 mục 1.5.

---

## 5.16. Versioning và branch strategy

### 5.16.1. Branch strategy

```text
main
develop
feat/parser-foundation
feat/legal-extraction
feat/data-platform
feat/relation-temporal
feat/retrieval-evidence
feat/verified-workflow
feat/frontend-chat
test/evaluation-suites
docs/thesis-overhaul
release/1.0.0
```

Khi làm một mình, có thể bỏ `develop` và merge feature branch trực tiếp vào `main` qua PR; release branch vẫn hữu ích trong tuần cuối.

### 5.16.2. Conventional commits

```text
feat(ingestion): add legal structure extractor
feat(retrieval): add rrf fusion and temporal filters
fix(verification): reject citations outside query date
test(evaluation): add historical gold cases
docs(thesis): update system design
chore(deps): pin docling 2.1.x and mineru 3.4.x
```

### 5.16.3. Tag policy

- Version bump theo từng milestone (mục 5.15.4).
- Release candidate chỉ được tag trên working tree sạch (không có file uncommitted), có dependency lock, docker image digest, migration version, corpus hash, gold-set hash.
- Rehearsal (13/09) và bảo vệ (14/09) dùng đúng tag `v1.0.0-rc2`; tag `v1.0.0` được tạo sau bảo vệ và không kèm thay đổi code.
- Không build release từ working tree chưa commit; mọi artifact release phải xuất phát từ git tag đã xác minh.

### 5.16.4. Release candidate requirements

```text
git tag
dependency lock (uv.lock, package-lock.json)
docker image digest
database migration version
corpus hash
gold-set hash
model config (model IDs, prompt versions)
evaluation report (final)
```

---

## 5.17. Tiêu chí thành công (success criteria)

Khóa luận được xem là hoàn thành về mặt kỹ thuật khi đạt đồng thời các tiêu chí sau, được suy ra từ acceptance criteria doc 02 mục 2.10 và doc 01 mục 1.7:

1. Có một release reproducible (clean clone -> compose -> demo theo README).
2. Corpus được version hóa, có manifest và SHA-256, chứa văn bản hiện hành và lịch sử.
3. Current query trả đúng source với citation hợp lệ tại ngày áp dụng.
4. Historical query sử dụng đúng `[effective_from, effective_to)` tại mốc được hỏi; áp dụng canonical date policy và hiển thị ngày đã áp dụng.
5. Comparison query tách hai temporal contexts, không trộn citation giữa hai giai đoạn.
6. Invalid citation bị chặn: Returned Invalid Citation Rate = 0.
7. Insufficient evidence dẫn đến abstention kèm lý do chuẩn, không trả lời nửa vời.
8. Parser được đánh giá hạng nhất: Suite A final report (P1-P3) có đủ 9 chỉ số gồm Article/Clause/Point P/R/F1, Short Point Recall, Vietnamese đ) Recall và Parent Context Completeness (đo sau khi enricher tồn tại).
9. Hybrid retrieval (exact + dense + sparse + RRF + rerank + context expansion) chạy và được đo trong Suite C.
10. Bốn suite A-D có report kèm raw evidence, run metadata đầy đủ, run bất biến.
11. Gold set 200 câu (40/40/120) được version hóa và đóng băng.
12. Benchmark RAGFlow hoàn tất với bốn variant trên cùng corpus và eval queries; so sánh Recall@10, citation correctness, temporal leakage, evidence completeness.
13. Demo local chạy ổn định trong ngày rehearsal trên đúng tag `v1.0.0-rc2`.
14. Báo cáo mô tả đúng hệ thống thực tế; không có claim kết quả chưa được đo; số liệu slide khớp số liệu report.

---

## 5.18. RAGFlow baseline kế hoạch

### 5.18.1. Vị trí và thời điểm

- RAGFlow chạy trong môi trường benchmark riêng, **không nằm trong compose production** (ADR-010, FR-31).
- Image: `infiniflow/ragflow:v0.26.4`; yêu cầu tối thiểu theo nhà cung cấp: 4 CPU, 16 GB RAM, 50 GB disk; Docker >= 24, Compose >= 2.26.1, Python >= 3.13; web port 80, API port 9380 (doc 04 mục 4.6).
- Thời điểm: setup tuần 7 (31/08), chạy đủ B1-B4 và dựng bảng so sánh trước feature freeze 06/09; chỉ packaging vào report diễn ra tuần 8.
- Vì máy cá nhân có 19 GB RAM, RAGFlow không chạy cùng lúc với ingestion/demo/eval nặng. Chạy tuần tự từng variant: dừng service không cần thiết, giữ `MAX_INGESTION_WORKERS=1`, theo dõi `docker stats`.

### 5.18.2. Bốn variant

```text
B1  RAGFlow default
B2  RAGFlow + Docling (dùng Docling làm parsing method)
B3  RAGFlow + MinerU (dùng MinerU làm parsing method)
B4  VNLRAG custom legal-aware pipeline
```

Cả bốn variant chạy trên **cùng corpus** và **cùng bộ câu hỏi evaluation** (FR-31). Không lược bớt variant vì RAM; nếu tài nguyên local không đủ, chạy tuần tự trên máy phù hợp khác hoặc chia theo batch, mọi variant bắt buộc chạy và kết quả được ghi lại đầy đủ (R15).

### 5.18.3. Chỉ số so sánh

```text
Recall@10
citation correctness
temporal leakage
evidence completeness
```

Kết quả baseline là dữ liệu so sánh bên ngoài, không phải kết quả thực nghiệm của VNLRAG; không bao giờ báo cáo baseline như kết quả VNLRAG (FR-31, doc 00 mục 11).

### 5.18.4. Gate tái lập B1-B4

Trước khi sinh `comparison.csv`, mỗi run B1-B4 phải lưu đầy đủ:

```text
corpus hash (dùng chung cho cả bốn variant)
query-set hash (bộ câu hỏi evaluation đã đóng băng)
adapter/evaluator version
run config (variant, parser method, model/config)
raw per-query output cho từng chỉ số so sánh:
  Recall@10
  citation correctness
  temporal leakage
  evidence completeness
```

Chỉ khi cả bốn variant có raw output hợp lệ mới được sinh bảng so sánh; không điền placeholder hoặc giá trị ước lượng vào bảng (FR-31, NFR-08).

---

## 5.19. Báo cáo và slide

### 5.19.1. Viết song song

Báo cáo được viết song song từ tuần 3, không dồn vào tuần cuối (R18). Mỗi tuần cập nhật: ADR, implementation note, test result, limitation, screenshot/diagram, số liệu benchmark (nếu có).

### 5.19.2. Chương báo cáo khớp kiến trúc

```text
1. Giới thiệu và bài toán (doc 00 mục 2, 3)
2. Tổng quan công trình liên quan (retrieval, temporal law, citation verification)
3. Thiết kế hệ thống (doc 03): ingestion, retrieval đa tầng, evidence completeness, verification
4. Cài đặt (doc 03 + doc 04): Parser Router, Canonical IR, PostgreSQL, Qdrant, LangGraph, Langfuse
5. Đánh giá (doc 00 mục 11): Suite A-D, gold set, RAGFlow baseline
6. Thảo luận và limitation
7. Kết luận
```

### 5.19.3. Số liệu sinh từ eval JSON

Mọi bảng số liệu trong report và slide được sinh từ JSON/CSV của evaluation run, không sao chép thủ công. Mỗi con số phải có: run_id, corpus hash, gold-set hash, model IDs, prompt versions, git commit. Metric chưa chạy không được điền.

### 5.19.4. Limitation trung thực

Báo cáo phải ghi rõ: phạm vi corpus 20-30 văn bản giao thông đường bộ; hệ thống không thay thế tư vấn pháp lý; quality phụ thuộc chất lượng parser và gold set; threshold evidence được xác định từ validation set; kết quả RAGFlow là baseline ngoài, không phải thành tích VNLRAG; mọi trường hợp fail nằm trong error analysis, không bị lọc.

### 5.19.5. Slide

Slide dùng số liệu khớp report, cấu trúc theo đề cương bảo vệ: problem, research gap, architecture v2 (không mô tả là autonomous agent), temporal retrieval, evidence completeness, verification, Suite A-D, limitation trung thực. Chuẩn bị câu trả lời cho các nhóm câu hỏi: pháp lý, hallucination, data source, cost, evaluation methodology.

---

## Ghi chú lịch sử

Kế hoạch v1 (UDEF-based, milestone M1-M8 gắn với UDEF domain pack, ChromaDB, rank-bm25 pickle, DuckDuckGo/SerpAPI fallback, query-time HITL) đã bị thay thế hoàn toàn. Các thuật ngữ đó chỉ xuất hiện trong tài liệu này ở mục 5.1.3, bảng so sánh doc 04 mục 4.20 và ADR doc 03 mục 3.32 với vai trò lịch sử hoặc lý do loại bỏ; không phải thành phần đang triển khai. Kế hoạch hiện hành xây quanh Parser Router, Canonical Document IR, Legal Structure Extractor, mô hình quan hệ và thời gian hiệu lực trong PostgreSQL, retrieval đa tầng trong Qdrant, evidence completeness, verification sáu tầng và RAGFlow baseline bên ngoài.
