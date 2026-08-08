# 08. Bảo Trì (Maintenance)

> **Giai đoạn SDLC**: 7 - Bảo trì
> **Ngày tạo**: 16/06/2026
> **Ngày baseline v1**: 19/07/2026
> **Ngày thiết kế lại v2**: 08/08/2026
> **Hạn hoàn thành**: 12/09/2026
> **Ngày tập bảo vệ**: 13/09/2026
> **Ngày bảo vệ**: 14/09/2026
> **Tài liệu quyết định nguồn**: [00-scope-and-decisions.md](00-scope-and-decisions.md)
> **Tài liệu yêu cầu nguồn**: [02-yeu-cau-he-thong.md](02-yeu-cau-he-thong.md)
> **Tài liệu thiết kế nguồn**: [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md)
> **Tài liệu tech stack nguồn**: [04-tech-stack-llm-research.md](04-tech-stack-llm-research.md)
> **Tài liệu kế hoạch nguồn**: [05-ke-hoach-trien-khai.md](05-ke-hoach-trien-khai.md)
> **Tài liệu kiểm thử nguồn**: [06-test-evaluation.md](06-test-evaluation.md)
> **Tài liệu triển khai nguồn**: [07-deployment.md](07-deployment.md)
> **Tên đề tài**: Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng
> **English title**: A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations

---

Tài liệu này định nghĩa kế hoạch bảo trì (maintenance) của VNLRAG v2. Mọi nội dung phải nhất quán với [00-scope-and-decisions.md](00-scope-and-decisions.md) (mục 3, 7, 16), đặc tả yêu cầu [02-yeu-cau-he-thong.md](02-yeu-cau-he-thong.md) (NFR-05, NFR-06, NFR-09), thiết kế chi tiết [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md) (mục 3.6, 3.7, 3.10, 3.11, 3.12, 3.13, 3.15, 3.27), nghiên cứu công nghệ [04-tech-stack-llm-research.md](04-tech-stack-llm-research.md) (mục 4.3, 4.5, 4.7, 4.8, 4.9, 4.12, 4.13, 4.14, 4.15), kế hoạch triển khai [05-ke-hoach-trien-khai.md](05-ke-hoach-trien-khai.md) (mục 5.15, 5.16), kiểm thử [06-test-evaluation.md](06-test-evaluation.md) (mục 6.4, 6.9, 6.10, 6.13) và triển khai [07-deployment.md](07-deployment.md) (mục 7.4, 7.5, 7.8, 7.9, 7.10, 7.13).

> **Ghi chú lịch sử**: bản v1 của tài liệu này mô tả quy trình bảo trì gắn với pipeline ingestion dựa trên một tầng trích xuất trung gian với commit pin, bộ golden fixture riêng và cơ chế version hóa RuleSpec. Phiên bản v2 loại bỏ hoàn toàn tầng đó và bảo trì trực tiếp các thành phần: Parser Router (Docling chính, MinerU phụ/fallback), Canonical Document IR, Legal Structure Extractor, Legal Reference Resolver, Temporal and Amendment Resolver, PostgreSQL, Qdrant, Redis + Dramatiq, MinIO, Langfuse và gold set. Mapping đầy đủ giữa quy trình bảo trì cũ và mới tại mục 8.16.

---

## 8.1. Mục tiêu bảo trì và nguyên tắc

Kế hoạch bảo trì phải bảo đảm hệ thống tiếp tục:

1. Trả lời từ corpus đã được kiểm chứng (review_status = ACCEPTED).
2. Dùng đúng phiên bản văn bản tại ngày được hỏi theo khoảng [effective_from, effective_to).
3. Không làm mất lịch sử khi có văn bản mới; văn bản bị thay thế vẫn phục vụ câu hỏi lịch sử.
4. Không index dữ liệu chưa review; `needs_review` và `dropped` không bao giờ vào Qdrant.
5. Có thể tái tạo PostgreSQL (nguồn chân lý), Qdrant (index dẫn xuất), object storage (MinIO hiện tại) và evaluation artifacts.
6. Phát hiện retrieval hoặc citation regression qua bộ regression subset cố định.
7. Kiểm soát mọi thay đổi model, prompt, parser, embedding, reranker qua gate và regression.
8. Giữ report, code và dữ liệu đồng bộ; số liệu trong báo cáo phải có raw evidence.
9. Có audit trail cho mọi thay đổi corpus, ghi rõ người thực hiện dưới vai trò nào.
10. Không biến hệ thống thành crawler tự động không kiểm soát; phát hiện văn bản mới không đồng nghĩa với kích hoạt.

Nguyên tắc trung tâm:

> Văn bản mới không được append mù vào corpus. Mọi thay đổi phải đi qua detection, parsing, normalization, relation analysis, temporal resolution, quality gates, review, versioning, indexing, regression và activation. Kết quả thực nghiệm chỉ được ghi sau khi chạy evaluation (doc 00 mục 11.4).

### 8.1.1. Lịch bảo trì

| Tần suất | Hoạt động |
|---|---|
| Mỗi ngày khi phát triển | CI, unit test, review log, backup code (git commit) |
| Hàng tuần | Kiểm tra nguồn văn bản mới, pending review, index consistency, queue depth, disk, backup age |
| Hàng tháng | Chạy regression subset, kiểm tra corpus QA drift, cost review |
| Hàng quý | Review model, prompt, parser, dependency, security, corpus coverage; restore drill nhẹ |
| Khi có văn bản mới | Corpus update lifecycle (mục 8.3) |
| Khi có văn bản sửa đổi/thay thế | Relation review, temporal update, LegalEffectEvent |
| Khi đổi embedding model | Full re-embedding và collection migration (mục 8.5) |
| Khi nâng parser | Parser version migration với golden fixtures (mục 8.4) |
| Khi đổi generator/prompt | Prompt change gate và generation regression (mục 8.7) |
| Trước mỗi release | Full backup, migration, evaluation subset, release manifest |
| Sau incident | Root-cause analysis và preventive action (mục 8.12) |

### 8.1.2. Phạm vi bảo trì

| Thành phần | Nội dung bảo trì |
|---|---|
| Corpus | PDF, manifest, version, status, quan hệ, temporal interval |
| Parser layer | Parser Router, Docling 2.x, MinerU 3.4.x, Canonical Document IR |
| Legal parser | Legal Structure Extractor (phân cấp Việt Nam, nhãn Điểm a) b) c) d) đ) e), short-Point retention) |
| Relation extraction | Legal Reference Resolver (ProvisionReference, DocumentRelation) |
| Temporal | Temporal and Amendment Resolver, LegalEffectEvent |
| PostgreSQL | Schema, Alembic migration, metadata, review, audit, feedback |
| Qdrant | Collection, payload, dense/sparse vector, alias, snapshot |
| Retrieval | Embedding, sparse BM25, RRF, reranker, filter, context expansion |
| Workflow | LangGraph controlled workflow, repair loop |
| Generation | Model, prompt, structured schema |
| Verification | L1-L6 verifier, Returned Invalid Citation Rate = 0 |
| Evaluation | Gold set, metrics, judge, run config, raw results |
| Observability | Langfuse trace, prompt management, feedback |
| Frontend/API | Contract, dependency, UX |
| Deployment | Docker images, backup, restore, release manifest |
| Documentation | README, ADR, report, diagram, changelog |

### 8.1.3. Ngoài phạm vi bảo trì P0

- tự động quyết định quan hệ pháp lý không có review;
- tự động crawl và activate văn bản;
- tự động chuyển model production;
- tự động sửa gold set từ model output;
- tự động đổi embedding model mà không re-index toàn bộ collection;
- cập nhật dependency hàng loạt không qua regression;
- nâng version parser, embedding hoặc reranker không qua golden fixtures/regression;
- tự động đổi generator model trong cùng query (không provider fallback mù, NFR-03).

---

## 8.2. Vai trò bảo trì (roles)

| Vai trò | Trách nhiệm |
|---|---|
| Maintainer | Điều phối release, dependency, backup, restore drill và incident |
| Corpus Reviewer | Kiểm tra nguồn, metadata, hierarchy, relation, provenance và hiệu lực; quyết định accept/reject |
| Developer | Sửa code, Alembic migration, index, tests, regression; quản lý prompt version |
| Evaluation Owner | Quản lý gold set, run config, report; đóng băng và version hóa gold set |
| System Operator | Theo dõi health, resource, queue và provider; chạy restore drill |
| Feedback Triage Owner (mới) | Rà soát feedback định kỳ, phân loại, đề xuất ứng viên gold set sau review độc lập |

Quy tắc chung:

- Trong phạm vi khóa luận, một người có thể kiêm nhiều vai trò, nhưng audit record vẫn phải ghi rõ hành động được thực hiện dưới vai trò nào (NFR-09, UC-08).
- Mọi quyết định review phải có reviewer identity và timestamp.
- Feedback Triage Owner chịu trách nhiệm vòng đời feedback từ thu thập tới triage và đề xuất gold-candidate (mục 8.9.5, doc 06 mục 6.9.3); không tự động thêm feedback vào gold set.

---

## 8.3. Vòng đời cập nhật corpus (corpus update lifecycle)

### 8.3.1. Workflow chuẩn

```text
Discover
-> Download
-> Hash (SHA-256)
-> Parse (Parser Router: Docling | MinerU)
-> Normalize to IR (Canonical Document IR)
-> Extract (Legal Structure Extractor)
-> Reference resolve (Legal Reference Resolver)
-> Temporal resolve (Temporal and Amendment Resolver)
-> Quality gates
-> Review (Human Review)
-> Version (document/provision version mới)
-> Update legal relations (persist relations/events atomically, close affected provision-version intervals, rebind by version, route unresolved scope to review)
-> Index (embed + upsert Qdrant)
-> Regress (retrieval/citation/temporal regression)
-> Activate (alias/version phục vụ query)
-> Backup
-> Audit
```

Bước `Update legal relations` cập nhật toàn bộ quan hệ và hiệu lực pháp lý, không chỉ temporal:

- persist `DocumentRelation` (SUPERSEDES/REPEALS/AMENDS/CORRECTS/GUIDES/RELATED_TO) và `LegalEffectEvent` (SUPERSEDED/REPEALED/PARTIAL_AMENDED/CORRECTED/EXPIRED) một cách nguyên tử (atomic) cùng với việc tạo version mới;
- đóng interval của các provision version bị ảnh hưởng trong `legal_provisions` (`effective_to` của từng provision version, không chỉ `effective_to` cấp văn bản), vì temporal retrieval lọc theo interval cấp provision;
- rebind hoặc đánh dấu `ProvisionReference` theo version nguồn/đích (`source_provision_version_id`, `target_provision_version_id`) khi version nguồn hoặc đích thay đổi;
- route các phạm vi ảnh hưởng chưa xác định được (unresolved scope) sang review trước khi index; không index provision hoặc relation mới khi còn scope chưa review.

Pipeline worker tương ứng (doc 03 mục 3.2.1, 3.13): `parse -> normalize -> legal extract -> reference resolve -> temporal resolve -> quality gates -> review -> embed -> index`. Mỗi bước là một actor Dramatiq ngắn, rời rạc, idempotent; trạng thái job nằm trong PostgreSQL (`ingestion_runs`), Redis chỉ là đường truyền message.

Chỉ kết quả phân loại `accepted` mới đi tiếp tới `PostgreSQL -> embed -> index`. Kết quả `needs_review` phải qua Human Review; `dropped` chỉ được ghi thành audit record và không bao giờ được index (FR-09).

### 8.3.2. Phát hiện không đồng nghĩa kích hoạt

```text
Nguồn báo có văn bản mới
    -> tạo candidate
    -> tải PDF và metadata
    -> tính SHA-256
    -> kiểm tra duplicate theo file_hash
    -> chưa xuất hiện trong retrieval
```

Candidate manifest:

```json
{
  "candidate_id": "cand-2026-001",
  "source_url": "https://...",
  "detected_at": "2026-10-01T09:00:00+07:00",
  "downloaded_at": "2026-10-01T09:05:00+07:00",
  "file_hash": "...",
  "document_number": "...",
  "document_type": "DECREE",
  "suspected_relations": [],
  "status": "DISCOVERED"
}
```

Candidate status:

```text
DISCOVERED
DOWNLOADED
DUPLICATE
EXTRACTION_PENDING
NEEDS_REVIEW
ACCEPTED
REJECTED
ACTIVATED
FAILED
```

Candidate chỉ được activate sau khi hoàn tất quality gates và review. Duplicate theo `file_hash` được liên kết với version hiện có thay vì tạo candidate mới.

### 8.3.3. Storage append-only và retrieval visibility

Lịch sử luôn được giữ, nhưng không phải mọi version đều hợp lệ cho mọi query:

- **Storage append-only**: giữ version và audit lịch sử trong PostgreSQL.
- **Retrieval visibility**: phụ thuộc effective interval và review_status.
- **Active index (Qdrant)**: chứa mọi provision version có `review_status = ACCEPTED`, kể cả các version đã hết hiệu lực (expired historical versions); query-time temporal filter quyết định version nào được phục vụ cho ngày được hỏi.
- **Current retrieval**: temporal filter loại version cũ không còn hiệu lực tại ngày hỏi.
- **Historical retrieval**: vẫn dùng version cũ hợp lệ tại mốc hỏi (FR-19).
- Không dùng append-only retrieval logic: tài liệu mới không được append mù vào corpus mà không đóng interval cũ khi cần.

### 8.3.4. Các loại cập nhật

#### A. Văn bản hoàn toàn mới

Không ảnh hưởng interval cũ nếu không có relation. Tạo document/provision version mới, không đóng gì cả.

#### B. Văn bản thay thế toàn bộ

```text
new SUPERSEDES old
old.effective_to = new.effective_from
```

Chỉ thực hiện sau review. Ngoài document-level relation, phải:

- tạo/ghi `DocumentRelation` SUPERSEDES và `LegalEffectEvent` SUPERSEDED với `affected_provision_versions`;
- đóng `effective_to` của từng provision version của văn bản cũ tại `new.effective_from` (temporal retrieval lọc theo interval cấp provision, không phải cấp văn bản);
- rebind hoặc đánh dấu các `ProvisionReference` trỏ vào văn bản cũ theo version;
- route mọi phạm vi thay thế chưa rõ sang review trước khi index.

Văn bản cũ không bị xóa khỏi corpus và vẫn hợp lệ cho câu hỏi lịch sử (doc 03 mục 3.15.4).

#### C. Văn bản bãi bỏ

```text
new REPEALS old
old.effective_to = repeal_effective_date
```

Ghi `DocumentRelation` REPEALS và `LegalEffectEvent` event_type REPEALED với `affected_provision_versions`; đóng `effective_to` của từng provision version bị bãi bỏ tại `repeal_effective_date`; rebind hoặc đánh dấu `ProvisionReference` liên quan theo version; phạm vi bãi bỏ chưa rõ route sang review trước khi index.

#### D. Văn bản sửa đổi một phần (partial amendment)

Không được đóng toàn bộ document cũ nếu chỉ một số provision bị sửa. Cần:

- xác định provision bị ảnh hưởng (affected scope);
- tạo version mới cho từng provision bị sửa (provision_id giữ nguyên, version tăng);
- đóng interval của provision cũ tại biên sửa đổi;
- giữ nguyên provision không bị sửa;
- ghi `LegalEffectEvent` PARTIAL_AMENDED với `affected_provision_versions` structured;
- ghi `ProvisionProvenance` với role = AMENDMENT_TEXT cho phần nội dung thay đổi từ văn bản sửa đổi (`source_document_version_id`, `source_element_id`, `page_number`, `bbox`); phần nội dung không bị sửa giữ role = BASE_TEXT;
- cập nhật `provision_versions` registry với `superseded_by_version` (doc 03 mục 3.15.3).

#### E. Đính chính (correction)

Tạo version mới hoặc correction record tùy mức ảnh hưởng. Không sửa âm thầm content đã accept (mục 8.13).

#### F. Metadata correction

Nếu sửa metadata không ảnh hưởng nội dung text:

- tạo audit record;
- tăng metadata revision;
- đánh giá có cần re-index payload Qdrant hay không;
- nếu metadata nằm trong payload (ví dụ `document_title`, `vehicle_types`), thực hiện payload update hoặc rebuild collection theo chính sách payload schema (mục 8.5.4).

### 8.3.5. Parser Router trong re-ingestion

Parser Router quyết định parser theo đặc tính tài liệu và quality gate (FR-01, doc 03 mục 3.7):

| Đặc tính tài liệu | Quyết định | Fallback |
|---|---|---|
| PDF searchable, layout chuẩn | Docling trước | Không cần trừ khi quality gate fail |
| PDF scan hoặc layout lỗi | Docling trước (OCR backend CPU) | MinerU nếu quality gate fail |
| Bảng phức tạp | So sánh đầu ra hai parser khi cần | Chọn theo quality gate hoặc gửi review |

Khi bảo trì, một tài liệu đã ingest có thể bị re-route sang parser thay thế (Docling <-> MinerU) nếu:

- quality gate nhóm A (provenance coverage, text extraction rate, table detection, layout coherence) fail trên parser hiện tại;
- quality gate nhóm B (point label detection, hierarchy completeness, short-Point retention) fail sau Legal Structure Extractor;
- parser được nâng version và golden fixtures cho thấy parser mới tốt hơn cho một nhóm tài liệu (kết quả Suite A, không khẳng định trước benchmark).

Quy tắc bắt buộc khi re-ingestion:

- nếu parser-level gate fail, Router chuyển MinerU và chạy lại từ đầu pipeline (parse mới);
- nếu structural gate fail, dữ liệu structural hiện tại bị hủy bỏ và Router chạy lại toàn bộ pipeline từ parser thay thế; artifact parser/IR/structural cũ được đánh dấu invalid trong `ingestion_artifacts`;
- không trộn kết quả hai parser cho cùng một tài liệu (doc 03 mục 3.7.3);
- mọi quyết định routing và parser version được ghi vào `ingestion_runs.parser_routing` và `DocumentElement.source_parser`;
- kết quả re-ingestion phải được so sánh regression với parser cũ (Suite A fixtures) trước khi activate.

Idempotency key cấp tài liệu (doc 03 mục 3.13.4):

```text
SHA-256(file bytes) + parser version + legal parser version + IR schema version
```

Nếu cùng file và cùng pipeline version đã thành công, không chạy lại mặc định; chỉ chạy lại khi `force=true` hoặc khi pipeline version thay đổi.

### 8.3.6. Canonical Document IR schema versioning trong corpus update

- Mỗi `ParsedDocument` ghi `ir_schema_version` (ví dụ `document-ir-v1`).
- Khi parsing pipeline thay đổi cấu trúc IR (thêm/bớt field, đổi semantics của `DocumentElement`), `ir_schema_version` phải bump (ví dụ `document-ir-v2`).
- IR schema bump yêu cầu re-normalization: đọc artifact parser đã lưu trong object storage (`parser-outputs`), chuyển sang IR mới bằng adapter hiện hành. Nếu chỉ thay đổi IR schema mà parser version không đổi, có thể re-project mà không cần re-parse.
- Nếu parser version thay đổi, phải re-parse (không tái sử dụng parser output cũ) (mục 8.4.5).
- Idempotency key chứa IR schema version; bump schema làm key đổi, cho phép chạy lại pipeline.

---

## 8.4. Bảo trì parser (parser maintenance)

### 8.4.1. Chính sách pin parser

- Docling 2.x (PyPI `docling` v2.1.x; GitHub releases cadence cao): pin exact version tại install, không dùng range mở (doc 04 mục 4.3.2).
- MinerU 3.4.x (mineru-3.4.4 stable; 4.0.0 alpha đang phát triển, không dùng): pin 3.4.x; chạy pipeline backend CPU, không chạy VLM/hybrid local (GPU >= 8 GB VRAM không khả thi trên máy khóa luận).
- Version parser được ghi vào `DocumentElement.parser_version`, `ParsedDocument.parser_version`, payload Qdrant `parser_version` và `ingestion_runs.parser_routing`.
- Nguồn version chính xác là lock file `backend/uv.lock`, không dùng `latest`.

### 8.4.2. Quy trình nâng version parser (parser version migration)

Không tự động nâng parser theo branch. Quy trình:

1. Tạo branch upgrade.
2. Ghi version cũ và mới (Docling `docling-2.1.x` -> `docling-2.2.x` hoặc MinerU `mineru-3.4.4` -> `mineru-3.4.5`).
3. Chạy parser golden fixtures (mục 8.4.3).
4. So sánh Canonical Document IR output (cấu trúc `ParsedDocument`/`DocumentElement`, `element_type`, reading order, table_html).
5. So sánh LegalProvision output (provision_id, hierarchy, source_text, retrieval_text, page_number, bbox).
6. Kiểm tra provenance coverage (page_number, bbox, `source_element_ids`).
7. Chạy hierarchy metrics (Article/Clause/Point P/R/F1).
8. Re-ingest một subset tài liệu đại diện (Luật, Nghị định, Thông tư; born-digital và scan).
9. Review diff: chỉ khác biệt do parser mới, không phải lỗi cấu hình.
10. Chỉ pin version mới khi mọi bước pass và Suite A không regression so với baseline.

Kết quả nâng parser phải được ghi vào Suite A report (raw result) và changelog. Không xóa kết quả đo bằng parser cũ; nếu cần so sánh, ghi cả hai.

### 8.4.3. Parser golden fixtures

Mỗi loại văn bản (Luật, Nghị định, Thông tư) và mỗi dạng tài liệu (born-digital searchable, scan, bảng phức tạp) giữ bộ golden fixture (doc 06 mục 6.13.4):

```text
source PDF
expected IR summary          # cấu trúc ParsedDocument/DocumentElement kỳ vọng
expected LegalProvision IDs   # danh sách provision_id kỳ vọng (gồm d) và đ) tách biệt)
expected hierarchy            # Chương/Mục/Điều/Khoản/Điểm theo gold annotation
expected provenance           # page_number, bbox, source_element_ids
```

Gold annotation là cấu trúc tham chiếu độc lập do con người review từ PDF nguồn, dùng để tính Article/Clause/Point P/R/F1, Short Point Recall, Vietnamese đ) Recall, Table Preservation, Header/Footer Leakage, Provenance Coverage (doc 06 mục 6.4.1).

Fixture stable-ID bắt buộc phân biệt `diem-d` (Điểm d)) và `diem-đ` (Điểm đ)) để ngăn va chạm ID (FR-03, doc 06 mục 6.2.1.4).

### 8.4.4. Docling/MinerU regression (Suite A)

Mọi nâng cấp parser phải pass Suite A parser metrics với no regression so với baseline đã pin:

```text
Article P/R/F1
Clause P/R/F1
Point P/R/F1
Short Point Recall
Vietnamese đ) Recall
Parent Context Completeness
Table Preservation
Header/Footer Leakage
Provenance Coverage
```

Nguyên tắc:

- Suite A (P1 Docling, P2 MinerU, P3 Parser Router) đo trên cùng fixture và cùng gold annotation.
- Không khẳng định parser nào vượt trội tuyệt đối trước khi có kết quả Suite A (FR-01, ADR-002).
- Ngưỡng cụ thể (delta cho phép) chỉ được khóa sau baseline thực tế, không đặt trước thực nghiệm.
- Parent Context Completeness đo sau khi Legal Context Enricher tồn tại (doc 06 mục 6.4.1).

### 8.4.5. Document IR schema version

- `DocumentElement` fields được version hóa qua `ir_schema_version` trên `ParsedDocument`.
- Quy tắc bump IR schema: bất kỳ thay đổi field, kiểu field hoặc semantics của IR làm thay đổi cách Legal Structure Extractor đọc dữ liệu.
- Re-normalization procedure:
  - nếu chỉ IR schema thay đổi: đọc artifact parser gốc từ object storage bucket `parser-outputs`, chuyển sang IR mới bằng adapter hiện hành, không cần re-parse;
  - nếu parser version thay đổi: re-parse từ PDF nguồn (`source-pdfs`) vì parser output cũ không tương thích;
  - sau khi re-normalize/re-parse, chạy lại quality gates và golden fixtures trước khi viết vào PostgreSQL.

### 8.4.6. Legal parser version (Legal Structure Extractor)

- Legal Structure Extractor là parser pháp lý do dự án sở hữu, chạy trên Canonical Document IR.
- Phiên bản của nó được version hóa riêng: `legal_parser_version` (ví dụ `vnlrag-legal-parser-v1`), ghi trong payload Qdrant và run metadata (doc 06 mục 6.6.4).
- Bump version khi thay đổi: nhận diện phân cấp Việt Nam (Chương/Mục/Điều/Khoản/Điểm/Phụ lục/bảng/điều khoản chuyển tiếp), nhãn Điểm tiếng Việt gồm `d)` và `đ)`, short-Point retention, xử lý biến thể OCR.
- Mọi thay đổi ảnh hưởng nhãn Điểm tiếng Việt (gồm việc giữ Điểm ngắn) bắt buộc chạy golden fixtures (fixture d) đ), short-Point) trước khi promote.
- Legal parser không đọc định dạng parser gốc, chỉ đọc IR (FR-02, NFR-06); nâng cấp Docling/MinerU không yêu cầu sửa extractor.

### 8.4.7. Relation extraction version (Legal Reference Resolver)

- Legal Reference Resolver trích `ProvisionReference` (PARENT_OF, REFERS_TO, SIBLING_OF, PENALTY_COMPANION) và `DocumentRelation` (AMENDS, REPEALS, SUPERSEDES, CORRECTS, GUIDES, RELATED_TO) (FR-05).
- Phiên bản của nó được version hóa riêng: `relation_extraction_version` (ví dụ `relation-extraction-v1`), ghi trong run metadata (doc 06 mục 6.6.4).
- Thay đổi pattern trích xuất quan hệ (pattern `REFERS_TO`, suy luận `PENALTY_COMPANION`, version binding) bắt buộc chạy relation gold fixtures (doc 06 mục 6.13.5) phủ toàn bộ loại quan hệ.
- Assertion bắt buộc khi nâng version:
  - mọi loại quan hệ được trích đúng theo gold;
  - version binding đúng (`source_provision_version_id`, `target_provision_version_id` không trộn version);
  - unresolved reference ghi `UNRESOLVED`/`PENDING_REVIEW` và định tuyến review, không suy đoán;
  - context expansion không mở rộng qua reference unresolved.
- `unresolved cross-reference count` trong corpus QA được theo dõi sau mỗi nâng version resolver; tăng bất thường cần khảo sát.

---

## 8.5. Bảo trì embedding và reranker (embedding/reranker migration)

### 8.5.1. Embedding migration

Không trộn embedding space. Khi embedding model thay đổi (theo kết quả Suite B hoặc nâng cấp sau này), phải re-embed toàn bộ collection:

```text
chọn accepted provisions (SELECT ... WHERE review_status = 'ACCEPTED')
    -> generate embeddings với model mới
    -> build collection mới legal_provisions_v{n+1}
    -> chạy retrieval regression (dev set)
    -> verify số point khớp PostgreSQL
    -> switch alias legal_provisions_active
    -> giữ collection cũ cho rollback
    -> cập nhật release manifest
```

Quy tắc bắt buộc:

- re-embed toàn bộ collection, không re-embed một phần;
- không bao giờ rebuild in place; luôn dùng collection mới + alias switch (doc 03 mục 3.11.7);
- embedding cache key = `embedding_model_id + embedding_dimensions + embedding_text_hash`; không bao giờ tái sử dụng cache giữa hai model khác nhau (mục 8.5.2);
- corpus version/hash của embedding run được ghi vào run metadata và release manifest;
- queries trong thời gian migration vẫn dùng collection cũ cho tới khi alias switch hoàn tất;
- dimension mới phải khớp cấu hình (ví dụ Gemini Embedding 2 768 dims, Jina text-nano 768 dims, Jina text-small 1024 dims - doc 03 mục 3.11.1);
- approval gate: Recall@k không giảm ngoài delta chấp nhận (delta khóa sau baseline, không đặt trước); historical category không giảm; exact reference query không giảm; vector dimension đúng; cost nằm trong budget.

### 8.5.2. Embedding cache

```text
key = embedding_model_id | embedding_dimensions | embedding_text_hash
```

- Không tái sử dụng cache nếu một trong ba thành phần thay đổi.
- Cache dùng để tránh embedding lại khi rebuild collection cùng model.
- Khi rebuild từ PostgreSQL, cache chỉ hợp lệ nếu embedding text không đổi; nếu embedding text thay đổi (chunking/retrieval_text đổi), phải bỏ cache cũ.

### 8.5.3. Reranker migration

- Jina Reranker v3 (`jina-reranker-v3`) là reranker chính, stage chuẩn của pipeline (FR-15, ADR-014).
- Đường nâng cấp: `jina-reranker-v3.5` là drop-in thay thế được theo dõi (vendor-stated BEIR nDCG-10 63.20); không mặc định dùng nếu chưa benchmark trên corpus VNLRAG (doc 04 mục 4.9.2).
- Quy trình nâng reranker:
  1. ghi model cũ/mới;
  2. chạy retrieval regression trên Suite C (R6) và regression subset;
  3. kiểm tra latency và cost (rate limit cấu hình theo deployment, không hardcode theo free-tier - NFR-04);
  4. review diff top-k;
  5. chỉ promote khi pass.
- Không tuyên bố reranker cải thiện chất lượng trước khi có kết quả benchmark (doc 00 mục 7).

### 8.5.4. Qdrant collection versioning

- Tên collection: `legal_provisions_v1`, `legal_provisions_v2`, ... (v1 -> v2 khi đổi cấu hình).
- Alias hoạt động: `legal_provisions_active`.
- Khi đổi payload schema, vector dimension, sparse encoder hoặc chunking production: tạo collection mới + alias switch, không rebuild in place.
- Nguồn rebuild: PostgreSQL (source of truth) `SELECT * FROM legal_provisions WHERE review_status = 'ACCEPTED'`; truy vấn này lấy mọi row ACCEPTED, kể cả version đã hết hiệu lực, để phục vụ câu hỏi lịch sử; không đọc ngược từ Qdrant, không đọc từ `provision_versions`.
- Sparse encoder được version hóa: `sparse_encoder_version` (ví dụ `qdrant-bm25-v1`) trong payload; thay encoder = rebuild collection + alias switch, không trộn hai không gian sparse.
- Giữ collection cũ một thời gian theo chính sách retention để rollback; snapshot trước alias switch (doc 07 mục 7.9.3).

---

## 8.6. PostgreSQL migrations và data versioning

### 8.6.1. Alembic migration policy

- Mỗi schema change có đúng một Alembic migration (NFR-06).
- Không sửa migration đã release; thêm migration mới.
- Destructive migration (xóa bảng/cột, thay đổi ràng buộc temporal) bắt buộc backup trước khi chạy và dry run.
- Migration có data transform phải idempotent hoặc có checkpoint.
- Readiness phải kiểm tra revision khớp release manifest (doc 07 mục 7.13.2).
- Migration chỉ chạy bởi one-shot service `migrate`; application process không bao giờ tự chạy `alembic upgrade head` (doc 07 mục 7.8.1).
- Ghi `alembic current` và `alembic heads` trước mỗi release; revision được ghi vào release manifest.

### 8.6.2. Data versions

Document version:

```text
unique (document_id, version)
```

Version tăng khi: file nội dung thay đổi; effective interval thay đổi; title/number/type được sửa quan trọng; relation thay đổi ảnh hưởng retrieval; source PDF được thay bằng bản chính thức khác.

Provision version:

```text
unique (provision_id, version)
```

`legal_provisions` LÀ bảng version có thẩm quyền (mỗi row = một provision version đầy đủ nội dung, interval, review_status); `provision_versions` là registry/lineage phụ trợ với FK tới `legal_provisions` (doc 03 mục 3.9.5). Provision version tăng khi:

- content (source_text/retrieval_text) thay đổi;
- hierarchy thay đổi;
- effective interval thay đổi;
- provenance thay đổi đáng kể;
- split/merge do legal amendment.

`ProvisionProvenance` (provision_version_row_id, source_document_version_id, source_element_id, page_number, bbox, role = BASE_TEXT | AMENDMENT_TEXT | CORRECTION_TEXT | EFFECT_SOURCE) gắn với từng provision version: thêm hoặc thay đổi bản ghi provenance (ví dụ nguồn AMENDMENT_TEXT từ văn bản sửa đổi, CORRECTION_TEXT từ đính chính, EFFECT_SOURCE từ văn bản gây sự kiện hiệu lực) được xem là provenance thay đổi đáng kể và bump provision version.

### 8.6.3. Pipeline revisions

Pipeline revision tách khỏi legal version:

```text
extraction_revision
chunking_revision
embedding_revision
index_schema_version
```

Re-run bằng parser mới không nhất thiết tạo legal version mới nếu normalized legal content không đổi. Pipeline revisions được ghi trong run metadata (doc 06 mục 6.6.4) cùng `parser_versions` tách riêng từng thành phần: Docling version, MinerU version, document IR schema version, legal parser version, relation extraction version.

### 8.6.4. Content hashes

```text
document_file_hash          SHA-256 của PDF nguồn
normalized_document_hash    hash của nội dung IR đã chuẩn hóa
provision_content_hash      hash của source_text (không đổi sau enrichment)
embedding_text_hash         hash của embedding text (retrieval_text + metadata)
```

Dùng hash để: phát hiện duplicate; tránh embedding lại; audit thay đổi; kiểm tra release (verify_release). Hash của `source_text` phải bất biến sau parent-context enrichment (FR-04).

### 8.6.5. Temporal interval management

- Khoảng hiệu lực dạng `[effective_from, effective_to)` với upper bound exclusive (doc 03 mục 3.10.4).
- CHECK interval: `effective_to IS NULL OR effective_to > effective_from`.
- CHECK review-required: `review_status <> 'ACCEPTED' OR effective_from IS NOT NULL`.
- Exclusion constraint: không có hai version ACCEPTED chồng lấn trong cùng provision:

```sql
ALTER TABLE legal_provisions
    ADD CONSTRAINT legal_provisions_no_overlap_accepted
    EXCLUDE USING gist (
        provision_id WITH =,
        daterange(effective_from, effective_to, '[)') WITH &&
    )
    WHERE (review_status = 'ACCEPTED');
```

- Xung đột hiệu lực thực sự (hai văn bản cùng tuyên bố hiệu lực cho cùng ngày) phải được mô hình unresolved/PENDING_REVIEW và ghi `LegalEffectEvent` + review item; không giữ hai row ACCEPTED chồng lấn.
- Script kiểm tra temporal integrity:

```bash
uv run python scripts/check_temporal_integrity.py
```

### 8.6.6. Integrity queries (ví dụ)

```sql
-- Accepted provision thiếu provenance
SELECT provision_id, version
FROM legal_provisions
WHERE review_status = 'ACCEPTED'
  AND page_number IS NULL;

-- Duplicate provision version
SELECT provision_id, COUNT(*)
FROM legal_provisions
WHERE review_status = 'ACCEPTED'
GROUP BY provision_id, version
HAVING COUNT(*) > 1;

-- Interval không hợp lệ
SELECT *
FROM legal_provisions
WHERE effective_to IS NOT NULL
  AND effective_to <= effective_from;
```

---

## 8.7. Prompt và Langfuse (prompt versioning + Langfuse trace compatibility)

### 8.7.1. Prompt version

Prompt được version hóa và ghi vào từng query trace và evaluation run:

```text
answer-prompt-v1.0.0
query-analyzer-v1.0.0
claim-judge-v1.0.0
legal-query-analyzer-v1
legal-query-rewriter-v1
legal-hyde-generator-v1
legal-generator-v1
legal-claim-support-judge-v1
legal-citation-renderer-v1
```

Các prompt chính của pipeline (doc 03 mục 3.27.3) được quản lý trong Langfuse với version và label production/dev. Mỗi `QueryTrace.config_snapshot` và mỗi evaluation run lưu `prompt_versions` (NFR-08).

Phân loại thay đổi prompt:

- PATCH: wording, không đổi schema.
- MINOR: thêm rule hoặc example.
- MAJOR: đổi output contract/behavior.

### 8.7.2. Prompt change gate

Quy trình thay đổi prompt:

1. Tạo candidate prompt trong Langfuse (label dev, chưa promote).
2. Pin candidate version.
3. Chạy validation generation set (validation set 40 câu).
4. Chạy generation regression: structured parse rate; unknown provision ID rate; draft invalid citation rate; returned invalid citation rate (bất biến = 0); abstention behavior; faithfulness subset; cost; latency.
5. Chỉ promote sang label production khi pass.
6. Ghi prompt version mới vào run metadata và release manifest.

Không đổi prompt production trực tiếp không qua gate. Prompt MAJOR (đổi schema output) phải kèm kiểm tra tương thích verifier L1-L6.

### 8.7.3. Langfuse prompt management

- Prompt được quản lý trong Langfuse với version và label `production`/`dev`.
- Label production là phiên bản duy nhất được dùng trong query serving và evaluation.
- Thay đổi prompt phải tạo version mới, không ghi đè version đã được dùng trong evaluation run (run immutability).
- Prompt version được ghi vào evaluation run (NFR-08) và `QueryTrace.config_snapshot`.

### 8.7.4. Langfuse trace compatibility

- Trace schema version được theo dõi qua cấu trúc span của trace `legal_query` (doc 03 mục 3.27.2):

```text
legal_query
├── analyze_query
├── normalize_query
├── rewrite_query
├── hyde
├── exact_lookup
├── dense_retrieval
├── sparse_retrieval
├── rrf_fusion
├── reranker
├── reference_expansion
├── evidence_check
├── generate
├── citation_verify
├── numeric_verify
└── claim_verify
```

- Khi nâng Langfuse SDK hoặc thay đổi cấu trúc span, kiểm tra trace vẫn emit đúng và SDK v4.x tương thích server v4 (doc 04 mục 4.5).
- Observability KHÔNG nằm trên đường tới hạn tính đúng đắn: ingest bất đồng bộ, toàn bộ callback non-mutating; nếu Langfuse không khả dụng, query vẫn hoạt động bình thường (FR-26, ADR-009).
- Nếu Langfuse Cloud không khả dụng: bỏ qua span hiện tại, tiếp tục pipeline; bật/tắt qua `LANGFUSE_ENABLED=false`; không có functional impact; trace config được ghi trong run metadata khi chạy final evaluation (doc 06 mục 6.8.6).
- Integration test `test_langfuse_non_critical.py` bắt buộc: Langfuse callback error (timeout, 5xx, malformed) không làm đổi verified answer/abstention và không rollback query (doc 06 mục 6.8.6).

### 8.7.5. Model/prompt changes ghi trong evaluation runs

- Mọi thay đổi model, prompt, parser, embedding, reranker phải được ghi trong evaluation runs: `model_ids`, `prompt_versions`, `parser_versions`, `document_ir_schema_version`, `legal_parser_version`, `relation_extraction_version` (NFR-08, doc 06 mục 6.6.4).
- Không đổi model alias sau khi final run bắt đầu (doc 07 mục 7.3.5).
- Provider deprecation: không chờ tới ngày model bị tắt; tạo migration branch; lưu kết quả model cũ; chạy candidate model; cập nhật report cho release tương lai; không sửa số liệu khóa luận cũ như thể chạy bằng model mới.

---

## 8.8. Queue và object storage (Redis job recovery + object-storage retention)

### 8.8.1. Redis job recovery

Nguyên tắc: Redis là broker/cache, job state nằm trong PostgreSQL (`ingestion_runs`) là source of truth; actor idempotent; retry transient; reconcile giữa job state và index state (doc 07 mục 7.4).

Queue health:

```text
queue depth        LLEN của queue Dramatiq chính
dead-letter count  LLEN dramatiq-dlq
worker liveness    dramatiq --check
MAX_INGESTION_WORKERS = 1 (không chạy song song nhiều job parse)
```

Failed job inspection và manual replay:

1. Message fail sau retry được Dramatiq đưa vào dead-letter queue.
2. Đọc nội dung message, phân loại lỗi (transient vs lỗi cố hữu của dữ liệu).
3. Sau khi sửa nguyên nhân, gửi lại message từ dead-letter hoặc enqueue lại actor bằng `run_id`.
4. Actor idempotent: trước khi chạy, đọc state job từ PostgreSQL; nếu bước đã hoàn thành, bỏ qua. Re-enqueue an toàn, không index trùng.
5. `reconcile_index.py` so sánh trạng thái job (`ingestion_runs`) và trạng thái index thực tế (PostgreSQL `legal_provisions` vs Qdrant point count); đánh dấu index pending và re-run `index_actor` (doc 03 mục 3.13.6).

```bash
uv run python scripts/reconcile_index.py --strict
```

Retry policy (doc 03 mục 3.13.4):

```text
max_retries   5   (chỉ transient: 429, 5xx, timeout, connection)
min_backoff   15 giây
max_backoff   1 giờ
retry condition: không retry validation error
```

### 8.8.2. Worker crash recovery

- Actor thời lượng dài phải có time limit tường minh (không dùng mặc định 10 phút mù; `parse_actor` 1200s, `extract_actor` 600s, v.v. theo doc 03 mục 3.13.5).
- Khi worker crash: job tồn tại trong PostgreSQL, message được retry với backoff, actor chạy lại bỏ qua bước đã hoàn thành (idempotency dựa trên state job).
- Job chuyển terminal `FAILED` khi retry cạn; lỗi và stack được lưu (doc 03 mục 3.4.1).
- `index_actor` chỉ chạy sau PostgreSQL commit; nếu Qdrant fail, job giữ `INDEXING` và được retry bởi background/CLI reconcile, không rollback dữ liệu PostgreSQL.

### 8.8.3. Dead-letter retention policy

- Dead-letter queue giữ message fail khoảng 7 ngày (retention mặc định Dramatiq).
- Khảo sát khi dead-letter count tăng liên tục (worker chết, actor time limit, lỗi dữ liệu).
- Message dead-letter không được âm thầm xóa trước khi inspect và replay hoặc ghi nhận lỗi cố hữu.

### 8.8.4. Object storage artifact retention

Object storage được tiếp cận theo hợp đồng `ObjectStoragePort` với implementation S3-compatible; MinIO là ứng viên hiện tại (ADR đang mở). Mọi quy tắc trong mục này áp dụng cho implementation S3-compatible được chọn, không gắn cứng với một sản phẩm cụ thể:

- chuyển implementation (nếu ADR chọn store S3-compatible khác) là thay đổi cấp cấu hình (S3 endpoint, access key, secret key), không phải schema change; bucket layout và object key không đổi;
- bucket versioning, tagging và metadata vẫn do PostgreSQL (`ingestion_artifacts`) quản lý;
- tiering/ILM không phải backup và quy tắc replication/`mc mirror` áp dụng cho mọi implementation được chọn (mục 8.8.5).

Bucket layout (doc 03 mục 3.12.1):

```text
source-pdfs           PDF nguồn đã validate
parser-outputs        Đầu ra parser gốc (Docling JSON, MinerU JSON/Markdown)
page-images           Ảnh trang cho review và passage viewer
ingestion-artifacts   IR JSON, report quality gate
review-artifacts      Bằng chứng review, screenshot, provenance
evaluation-artifacts  Raw output và artifact evaluation
```

Retention rules:

| Bucket | Chính sách |
|---|---|
| source-pdfs | Giữ tới khi mọi version hiệu lực hoặc version được tham chiếu lịch sử không còn được phục vụ; trước khi xóa phải archive sang backup độc lập và ghi audit (doc 07 mục 7.5.6) |
| parser-outputs | Giữ theo IR schema version (mỗi `parser_version`/`ir_schema_version` một bản); bản của pipeline bị supersede được giữ tới khi IR schema/parser cũ không còn được tham chiếu |
| page-images | Giữ theo tài liệu; phục vụ review và passage viewer |
| ingestion-artifacts | Giữ theo version; artifact bị đánh dấu invalid khi re-ingestion giữ lại vì audit |
| review-artifacts | Giữ cho mục đích audit; không xóa trước khi khóa luận được chấm |
| evaluation-artifacts | Giữ theo run, bất biến; không ghi đè, không chỉnh sửa sau khi run kết thúc (append-only) |

Metadata (file_hash, size, parser version, uploaded_at) nằm trong PostgreSQL (`ingestion_artifacts`), không dùng object tag làm nguồn chính (NFR-09). Bật versioning bucket khi cần giữ lịch sử object.

Quy tắc retention source PDF thống nhất với doc 07 mục 7.5.6: source PDF và corpus artifact được giữ theo version văn bản - giữ ít nhất tới khi mọi version hiệu lực hoặc version lịch sử được tham chiếu không còn được phục vụ. Việc xóa (nếu có) chỉ thực hiện sau khi archive sang nơi lưu trữ backup độc lập, ghi audit, và xác nhận không còn provision/relation nào tham chiếu tới nó. Trước khi việc xóa hoàn tất, backup object storage vẫn bắt buộc theo lịch (mục 8.10.1); PDF gốc là nguồn đối chiếu cuối cùng nên việc xóa không được làm mất nguồn đối chiếu cho các version còn được phục vụ.

### 8.8.5. Tiering/ILM không phải backup

- ILM/transition (tiering) chỉ chuyển dữ liệu giữa các tầng trong cùng hệ thống, không thay thế nơi lưu trữ độc lập cho mục đích phục hồi (doc 03 mục 3.12.3, doc 07 mục 7.5.5); quy tắc này áp dụng cho mọi implementation S3-compatible được chọn.
- Backup object storage bằng server-side replication (async) hoặc `mc mirror`/`mc cp` sang nơi lưu trữ độc lập (khác volume lưu trữ production).
- Restore object storage phải đi kèm kiểm tra hash với metadata trong PostgreSQL.
- Backup verification định kỳ: so sánh số object (`mc du`) giữa nguồn và đích; kiểm tra checksum trước khi restore.

---

## 8.9. Đánh giá và regression (evaluation drift)

### 8.9.1. Corpus QA report/dashboard

Corpus có báo cáo/dashboard chất lượng với 16 chỉ số (FR-10, doc 03 mục 3.10.5):

```text
document count
article count
clause count
point count
Point coverage
short-Point retention
Vietnamese đ) detection rate
orphan Point count
orphan Clause count
duplicate provision count
parent-context coverage
provenance coverage
table coverage
unresolved cross-reference count
unknown effective date count
temporal conflict count
```

Với các văn bản quan trọng (ví dụ Nghị định 168), thực hiện structural QA có mục tiêu riêng (FR-10, UC-12). Theo dõi drift sau mỗi corpus update: đối chiếu báo cáo trước/sau khi thêm hoặc sửa văn bản; nếu orphan/duplicate/temporal conflict tăng bất thường, khảo sát ngay. Các chỉ số là kế hoạch đo lường, không phải kết quả thực nghiệm đã đạt.

### 8.9.2. Retrieval/citation regression

Regression subset khoảng 15-25 query đại diện phủ: exact article reference, semantic paraphrase, current, historical, comparison side, sparse-heavy, dense-heavy, cross-reference, multi-evidence (doc 06 mục 6.10.1).

Gate ban đầu:

```text
Không query critical nào mất toàn bộ expected provision trong top-10.
```

Bất biến citation (contract, không phải mục tiêu trung bình):

```text
Returned Invalid Citation Rate của API output = 0
```

Temporal regression quanh boundary:

```text
effective_to - 1 day
effective_to
effective_from
effective_from - 1 day
```

Sau baseline, khóa threshold cụ thể (mean Recall@10 delta, MRR@10 delta, Temporal Validity Accuracy) trên validation set; không đặt threshold số trước baseline (doc 06 mục 6.10.1). PR ảnh hưởng retrieval phải chạy: retrieval regression subset, temporal regression, citation regression invariant, gold-set integrity (doc 07 mục 7.11.2).

### 8.9.3. Gold set errata

Nếu phát hiện gold sai (label thật sai, không phải do hệ thống):

1. Tạo issue.
2. Ghi evidence (nguồn chính thức).
3. Reviewer độc lập xác nhận.
4. Tạo errata và version mới của gold set; không bao giờ sửa âm thầm file gold đã đóng băng.
5. Không xóa kết quả cũ.
6. Chạy lại và ghi cả kết quả trước và sau errata, ghi rõ gold version từng run (doc 06 mục 6.3.9).

Không cập nhật expected answer theo model output; expected answer chỉ thay khi nguồn chính thức chứng minh gold sai, pháp lý/temporal metadata được correction, hoặc review guideline thay đổi có version.

Gold-set health theo dõi: expected IDs còn tồn tại; query date hợp lệ; document version; category balance; duplicate question; review status; coverage current/historical/comparison (doc 06 mục 6.10.4).

### 8.9.4. Evaluation drift

- Chạy lại scheduled validation subset khi corpus hoặc config thay đổi; không sửa production dựa trên một run duy nhất.
- Run immutability được bảo toàn: mỗi run ghi `run_manifest_hash` (hash config + model IDs + prompt versions + corpus hash + gold set hash); artifact paths ghi một lần; status chuyển RUNNING -> COMPLETED/FAILED một chiều (doc 03 mục 3.9.13).
- Phát hiện drift: model/prompt/parser version trong run metadata khác baseline -> cảnh báo; kết quả cũ và mới đều được giữ, không ghi đè.
- Theo dõi: Recall@10 delta, MRR delta, Temporal Accuracy delta, Citation F1 delta, Abstention F1 delta, latency delta, cost delta. Không chỉ theo dõi một overall score (doc 06 mục 6.6.9).

### 8.9.5. Feedback triage

- End-user feedback: Useful / Not Useful, danh mục báo cáo: `wrong_citation`, `missing_information`, `wrong_effective_date`, `wrong_penalty`, `incomplete_answer`, `other` (FR-27, doc 03 mục 3.26).
- Feedback lưu trong PostgreSQL (`query_feedback` gắn `query_trace_id`) và gửi điểm số về Langfuse (non-blocking).
- Feedback Triage Owner rà soát feedback định kỳ; phân tích pattern (ví dụ `wrong_penalty` tăng -> khảo sát L4/L5 hoặc parser accuracy).
- Feedback sau khi được reviewer độc lập đánh giá có thể trở thành ứng viên bổ sung cho gold set; không tự động thêm (doc 06 mục 6.9.3). Câu hỏi gốc phải có nguồn trong corpus đã review; expected IDs xác định lại theo quy trình tạo gold (doc 06 mục 6.3.8), không dùng ID hệ thống đã trả.
- Feedback không chứa PII; comment phải qua PII detection trước khi persist (NFR-05, doc 06 mục 6.9.1).
- Retention tách riêng ba lớp: (1) query trace theo `QUERY_TRACE_RETENTION_DAYS` (khởi điểm 30 ngày, doc 07 mục 7.3.3); (2) conversation history chỉ khi bật FR-29 (P1) giữ mặc định 30 ngày (NFR-05); (3) feedback record (`query_feedback`) giữ lâu dài cho triage và audit, không gắn với retention của trace.
- Khi trace payload bị xóa theo retention, feedback row vẫn giữ `query_trace_id` để bảo toàn liên kết audit với bản ghi query đã ghi; không xóa feedback chỉ vì trace bị xóa.
- Delete job có test (NFR-05); mọi thao tác xóa có audit.

---

## 8.10. Backup và restore

### 8.10.1. Backup schedule

| Dữ liệu | Tần suất |
|---|---|
| PostgreSQL | Trước release và sau corpus update (pg_dump --format=custom) |
| Qdrant snapshot | Trước alias switch và release; copy sang nơi lưu trữ độc lập |
| Object storage artifacts (MinIO/S3-compatible) | `mc mirror` sang nơi lưu trữ độc lập; source PDF + artifact archive sau ingestion accepted |
| Gold set | Mỗi version/run |
| Evaluation results | Mỗi run (append-only) |
| Git repository | Mỗi commit/push |
| Release bundle | Mỗi release candidate (v1.0.0-rc2) |
| Checksums | SHA256SUMS trong backup bundle |

Backup scope bắt buộc (NFR-03, doc 07 mục 7.10.1):

```text
1. PostgreSQL dump        pg_dump --format=custom
2. Qdrant snapshot        snapshot collection active + copy sang nơi độc lập
3. Object storage artifacts  mc mirror sang nơi lưu trữ độc lập
4. Source PDF + manifest      từ bucket source-pdfs của object storage + data/manifests
5. Gold set               gold set version + hash (data/gold-sets)
6. Evaluation results     data/evaluation
7. Release config         deploy/env/*.env.example, release-manifest.json
8. Git tag                v1.0.0-rc2 (tag trên working tree sạch)
9. Checksums              SHA256SUMS
```

### 8.10.2. Restore drill

Ít nhất mỗi quý hoặc trước mỗi release quan trọng:

1. Tạo môi trường rỗng (clean-room).
2. Restore PostgreSQL (pg_restore --clean --if-exists).
3. Restore hoặc rebuild Qdrant.
4. Verify hash/count (verify_release.py).
5. Chạy sample retrieval (current, historical, comparison, abstention).
6. Ghi thời gian phục hồi (RTO mục tiêu dưới 60 phút cho local restore đã rehearsal).
7. Sửa runbook nếu có lỗi.

### 8.10.3. Qdrant rebuild preferred

- Qdrant KHÔNG phải source of truth. Khi index hỏng:

```text
PostgreSQL
    -> accepted provisions
    -> embedding cache/API
    -> rebuild Qdrant
```

- Rebuild từ PostgreSQL (mỗi row `legal_provisions` là một provision version ACCEPTED) được ưu tiên vì đảm bảo nhất quán; snapshot được giữ để rút ngắn RTO.
- Không phục hồi legal metadata từ Qdrant nếu PostgreSQL còn.
- Rebuild bằng alias switch; không rebuild in place (doc 07 mục 7.9).
- Nếu snapshot lỗi/thiếu, dựng lại hoàn toàn từ PostgreSQL.

### 8.10.4. Backup verification

Backup chỉ hợp lệ khi đồng thời:

- checksum pass (sha256sum -c SHA256SUMS);
- restore được (đã thử restore trên môi trường rỗng);
- manifest đầy đủ (release-manifest.json kèm hash);
- version khớp (migration revision, corpus hash, gold-set hash);
- secret không nằm trong archive (`.env` không được đóng gói).

---

## 8.11. Monitoring và alerting

### 8.11.1. System metrics

| Metric | Cảnh báo định hướng |
|---|---|
| Backend readiness | Fail liên tiếp |
| PostgreSQL connectivity | Fail |
| Qdrant connectivity | Fail |
| Redis connectivity | Fail |
| Object storage (MinIO/S3-compatible) connectivity | Fail |
| Disk usage | Trên 80% |
| RAM usage | Trên 85% kéo dài |
| Error rate | Tăng bất thường |
| Query P95 | Vượt baseline đáng kể |
| Provider 429/5xx | Tăng liên tục |
| Backup age | Quá lịch |
| Migration mismatch | Bất kỳ |

Ngưỡng production phải được điều chỉnh từ baseline thực tế, không đặt trước thực nghiệm. Readiness không gọi provider bên ngoài (doc 07 mục 7.13.2); provider health kiểm tra thủ công trước demo.

### 8.11.2. Corpus quality metrics

```text
accepted document count
accepted provision count
pending review count
dropped count
provenance coverage
bbox coverage
unknown effective date count
unresolved relation count
overlap conflict count
index pending count
orphan Qdrant point count
```

Chi tiết 16 chỉ số corpus QA tại mục 8.9.1.

### 8.11.3. Query quality metrics

```text
verified rate
abstention rate
verification failure rate
blocked invalid citation count
temporal conflict rate
no-evidence rate
per-intent latency
per-intent success
```

Abstention tăng không tự động là lỗi. Phải phân tích nguyên nhân: over-abstention (precision giảm) khác với under-abstention (recall giảm); phân loại theo category (doc 06 mục 6.5.7). Chỉ điều chỉnh sau khi xác định được nguyên nhân cụ thể (threshold evidence, retrieval, parser).

### 8.11.4. Alerting

P0 local không cần hệ thống alert enterprise. Có thể dùng cron/systemd:

```bash
#!/usr/bin/env bash
set -euo pipefail

curl --fail http://localhost:8000/api/v1/health/ready
uv run python scripts/check_temporal_integrity.py
uv run python scripts/reconcile_index.py
```

Staging/production tương lai có thể gửi:

- email;
- Slack;
- Telegram;
- incident system.

Không hardcode bot token trong script; token lấy từ env hoặc secret store (NFR-04).

---

## 8.12. Xử lý sự cố (incidents)

### 8.12.1. Severity

| Severity | Ví dụ |
|---|---|
| SEV-1 | Trả citation sai hoặc sai phiên bản pháp luật |
| SEV-2 | Hệ thống không hoạt động, mất index hoặc migration lỗi |
| SEV-3 | Latency cao, provider lỗi, một chức năng phụ hỏng |
| SEV-4 | UI/cosmetic hoặc documentation |

### 8.12.2. SEV-1 response

1. Disable affected query path hoặc switch maintenance mode.
2. Preserve logs/trace (QueryTrace, Langfuse trace, verification_summary).
3. Xác định corpus/model/config đang dùng.
4. Reproduce.
5. Fix.
6. Run regression (retrieval subset, citation invariant, temporal boundary).
7. Rebuild/restore nếu cần.
8. Document incident (postmortem).
9. Không bao giờ che giấu lỗi bằng disclaimer; trạng thái "chưa verified" không được trả ra ngoài.

SEV-1 không được phép: trả lời kèm citation không đạt L2-L6; sửa âm thầm dữ liệu đã accept; đổi model/prompt trong khi xử lý mà không ghi trace.

### 8.12.3. SEV-2 response

- Restore service từ backup release.
- Protect data (không chạy destructive command trước khi backup).
- Use release backup (postgres dump, qdrant snapshot, object storage mirror).
- Verify readiness (health/ready, verify_release.py).
- Postmortem.

### 8.12.4. Postmortem template

```markdown
# Incident

## Summary
## Impact
## Detection
## Timeline
## Root Cause
## Contributing Factors
## Resolution
## Corrective Actions
## Preventive Tests
## Affected Versions
## Artifacts
```

Mỗi incident SEV-1/SEV-2 bắt buộc có postmortem; corrective actions phải có owner và được kiểm tra trong vòng lịch bảo trì.

---

## 8.13. Hiệu chỉnh dữ liệu (data correction)

### 8.13.1. Không sửa trực tiếp accepted record

Không bao giờ edit trực tiếp row `legal_provisions` đã ACCEPTED. Correction workflow:

```text
open correction
    -> attach evidence (nguồn chính thức)
    -> create new revision/version (provision_id giữ nguyên, version tăng)
    -> review
    -> run regression
    -> activate
    -> preserve old record
```

Bản ghi cũ không bị xóa; nó vẫn phục vụ câu hỏi lịch sử và audit. Correction dạng đính chính nội dung pháp lý ghi `LegalEffectEvent` CORRECTED và `DocumentRelation` CORRECTS khi cần. Bản ghi `ProvisionProvenance` với role = CORRECTION_TEXT được tạo cho nội dung hiệu chỉnh, kèm nguồn hiệu chỉnh (`source_document_version_id`, `source_element_id`, `page_number`, `bbox`).

### 8.13.2. Query trace correction

Không sửa answer history (query_traces bất biến sau khi ghi). Nếu phát hiện answer cũ sai:

- đánh dấu affected trace;
- ghi incident (mục 8.12);
- sửa corpus/pipeline;
- không giả vờ answer cũ chưa từng tồn tại; raw output và verification_summary được giữ nguyên.

### 8.13.3. Temporal corrections

Correction sai ngày hiệu lực (wrong effective date) đi theo cùng quy trình với `LegalEffectEvent`:

1. mở correction kèm evidence (nguồn chính thức hoặc manifest);
2. tạo version mới với interval đúng;
3. đóng interval cũ;
4. review và regression temporal (boundary test);
5. activate;
6. kiểm tra exclusion constraint không có hai version ACCEPTED chồng lấn.

Hiệu lực không chắc chắn được ghi `UNKNOWN`/`PENDING_REVIEW`, tạo ReviewItem, không index cho tới khi reviewer quyết định (doc 03 mục 3.15.6). Không suy đoán ngày hiệu lực từ nội dung PDF khi manifest chính thức không cung cấp.

---

## 8.14. Versioning rules tổng hợp (summary)

### 8.14.1. Data versions

- Document version unique `(document_id, version)`.
- Provision version unique `(provision_id, version)`; bump khi content/hierarchy/interval/provenance (gồm các bản ghi `ProvisionProvenance` mới) thay đổi hoặc split/merge.
- `provision_id` giữ nguyên khi provision bị sửa; trích dẫn ổn định và câu hỏi lịch sử vẫn hoạt động.

### 8.14.2. Pipeline revisions

```text
extraction_revision
chunking_revision
embedding_revision
index_schema_version
```

Tách khỏi legal version; re-run bằng parser mới không nhất thiết tạo legal version mới nếu normalized legal content không đổi.

### 8.14.3. Content hashes

```text
document_file_hash
normalized_document_hash
provision_content_hash
embedding_text_hash
```

### 8.14.4. Release SemVer

```text
MAJOR.MINOR.PATCH
```

- MAJOR: breaking API/schema/retrieval semantics.
- MINOR: feature hoặc corpus capability mới.
- PATCH: bug/security/data correction tương thích.

Chuỗi release của khóa luận: 0.1.0 -> 0.9.0 (feature freeze 06/09) -> 1.0.0-rc1 (code freeze 10/09) -> 1.0.0-rc2 (release candidate chốt 12/09, dùng cho rehearsal 13/09 và bảo vệ 14/09) -> 1.0.0 (tag sau bảo vệ, không kèm thay đổi code) (doc 05 mục 5.15.4).

### 8.14.5. Các version phụ trợ

```text
app version
corpus version
gold-set version
prompt version
index schema version
parser version (Docling/MinerU)
Document IR schema version
legal parser version
relation extraction version
object storage implementation (S3-compatible; MinIO hiện tại)
```

Không dùng một version duy nhất cho mọi artifact; mỗi thành phần có version riêng và được ghi trong run metadata và release manifest.

### 8.14.6. Dependency rules

- Parser (Docling/MinerU), embedding và reranker upgrade bắt buộc golden fixtures hoặc regression trước khi promote.
- Object storage implementation (S3-compatible) swap: thay đổi cấp cấu hình (S3 endpoint/keys), không phải schema change; tiering/ILM không phải backup và replication/`mc mirror` vẫn áp dụng cho mọi implementation được chọn (mục 8.8.5).
- Không auto-upgrade parser/embedding/reranker theo branch.
- Không dùng floating tags (`latest`) cho deployment; pin image tag và digest trước code freeze (doc 07 mục 7.2.1).
- Lock file (`uv.lock`, `package-lock.json`) là nguồn version chính xác.
- Không auto-merge dependency bot cho: Qdrant, PostgreSQL, Docling, MinerU, LangGraph, Google/OpenAI SDK, Ragas, Next.js major (chỉ áp dụng cho các công nghệ đang dùng trong v2).

---

## 8.15. Definition of Maintenance Done

### 8.15.1. Sau mỗi corpus update

- [ ] SHA-256 khớp manifest; không duplicate.
- [ ] Quality gates pass; chỉ accepted được index.
- [ ] Regression subset pass (không query critical mất expected provision trong top-10).
- [ ] Returned Invalid Citation Rate = 0.
- [ ] Temporal integrity checks pass (check_temporal_integrity.py sạch).
- [ ] Corpus QA 16 chỉ số không drift bất thường.
- [ ] Backup được tạo (PostgreSQL dump sau corpus update).
- [ ] Changelog + audit được cập nhật.
- [ ] Release manifest cập nhật (nếu release).

### 8.15.2. Sau khi nâng parser/embedding/reranker

- [ ] Golden fixtures pass (parser) hoặc regression pass (embedding/reranker).
- [ ] Suite A/B/C metrics không regression so với baseline.
- [ ] Reranker: Suite C (R6) + regression subset pass, promotion chỉ khi pass; không cần rebuild collection/alias switch vì reranker chỉ thay đổi ranking tại query time (mục 8.5.3).
- [ ] Embedding/sparse encoder/payload schema/chunking: collection mới + alias switch, rollback collection giữ lại (mục 8.5.4).
- [ ] Model/parser version ghi vào run metadata và release manifest.
- [ ] Corpus version/hash ghi trong embedding run.

### 8.15.3. Trước mỗi release

- [ ] CI pass.
- [ ] Backup + restore test pass.
- [ ] Migration revision ghi trong manifest.
- [ ] Corpus hash và gold-set hash pass.
- [ ] Qdrant snapshot + reconciliation pass.
- [ ] Regression + temporal regression + citation invariant pass.
- [ ] Release manifest + tag (working tree sạch).
- [ ] Documentation đồng bộ.

---

## 8.16. Mapping bảo trì cũ sang mới (historical)

Bảng này chỉ ghi nhận lịch sử chuyển đổi từ bảo trì v1 sang bảo trì v2 (nhất quán với doc 00 mục 5, 14; doc 04 mục 4.20; doc 07 mục 7.18). Các cơ chế cũ không còn áp dụng.

| Nội dung bảo trì cũ (v1) | Nội dung bảo trì mới (v2) |
|---|---|
| UDEF commit pin (nâng cấp qua quy trình pin commit) | Parser version migration: pin exact Docling 2.x / MinerU 3.4.x + quy trình nâng version (mục 8.4.2) |
| UDEF RuleSpec versioning (traffic-law-v1.0.0, PATCH/MINOR/MAJOR) | Legal parser version (Legal Structure Extractor) + relation extraction version (Legal Reference Resolver) + Document IR schema version (mục 8.4.5, 8.4.6, 8.4.7) |
| UDEF golden fixtures (expected CDM, expected LegalDocument, expected LegalProvision IDs, expected hierarchy, expected provenance) | Parser golden fixtures theo loại văn bản và dạng tài liệu (expected IR summary, expected LegalProvision IDs, expected hierarchy, expected provenance) + relation gold fixtures (mục 8.4.3, doc 06 mục 6.13.4, 6.13.5) |
| UDEF plugin/projector/validator/commit version tracking trong ingestion run | pipeline revisions (extraction_revision, chunking_revision, embedding_revision, index_schema_version) + parser versions tách riêng trong run metadata (mục 8.6.3, doc 06 mục 6.6.4) |
| UDEF review routing | Parser Router + quality gates (nhóm A parser-level, nhóm B structural) + review routing theo FR-09 (mục 8.3.5, doc 03 mục 3.7) |
| UDEF ingestion tests | Suite A parser benchmark (P1 Docling, P2 MinerU, P3 Parser Router) + parser QA gold fixtures (doc 06 mục 6.4.1) |

Thay thế bổ sung khác trong phạm vi bảo trì: ChromaDB/SQLite-as-primary/rank-bm25 pickle (thiết kế v1) được thay bằng Qdrant + PostgreSQL (ADR-005, doc 07 mục 7.18); DuckDuckGo/SerpAPI fallback và query-time HITL không còn tồn tại trong bảo trì v2 (ADR-015). Các thành phần này không xuất hiện trong bất kỳ quy trình bảo trì đang vận hành.

---

## Kết luận

Bảo trì hệ thống pháp luật không phải chỉ là thêm PDF mới. Mỗi thay đổi có thể làm thay đổi câu trả lời hiện hành, câu trả lời lịch sử, citation và kết quả evaluation.

Lifecycle chốt:

```text
Discover
-> Download
-> Hash
-> Parse (Parser Router)
-> Normalize to IR
-> Extract
-> Reference resolve
-> Temporal resolve
-> Quality gates
-> Review
-> Version
-> Update legal relations
-> Index
-> Regress
-> Activate
-> Backup
-> Audit
```

PostgreSQL giữ lịch sử nghiệp vụ. Qdrant được rebuild hoặc cập nhật theo version với alias switch. Parser thay đổi phải qua golden fixtures và Suite A regression. Embedding model thay đổi phải re-embed toàn bộ collection. Prompt/model thay đổi phải qua prompt change gate và regression. Gold set và evaluation result không bị ghi đè.

Mục tiêu bảo trì quan trọng nhất là giữ ba invariant:

1. Chỉ corpus accepted được dùng.
2. Chỉ provision hợp lệ tại ngày hỏi được cite.
3. Chỉ answer đã verify mới được trả (Returned Invalid Citation Rate = 0).
