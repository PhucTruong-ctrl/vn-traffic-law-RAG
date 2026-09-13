# 01. Phân tích tính khả thi

> **Trạng thái audit:** UNVERIFIED / NOT RELEASE-READY  
> **Tài liệu quyết định phạm vi:** [00-scope-and-decisions.md](00-scope-and-decisions.md)  
> **Evidence artifact:** [evaluation/thesis-release-full-40-20260913.md](evaluation/thesis-release-full-40-20260913.md)  
> **Historical diagnostic artifact:** [evaluation/thesis-api-subset-32-20260913.md](evaluation/thesis-api-subset-32-20260913.md)

## 1. Bài toán và giá trị nghiên cứu

Đề tài xây dựng RAG hỗ trợ tra cứu pháp luật giao thông Việt Nam với cấu trúc pháp lý, hiệu lực theo thời điểm và citation có thể kiểm chứng. Bài toán không chỉ là tìm đoạn văn gần nghĩa: hệ thống phải giữ ranh giới Chương/Mục/Điều/Khoản/Điểm, xử lý tham chiếu và sửa đổi, tránh citation không tồn tại, nhận biết thiếu bằng chứng và abstain khi không thể xác minh.

Giá trị nghiên cứu nằm ở việc kết hợp exact lookup, dense/sparse retrieval, temporal filtering, bounded legal-context expansion và evidence-gated generation trên corpus có provenance. Thiết kế lịch sử từng dùng UDEF làm tầng trung gian. UDEF đã bị loại bỏ vì tạo schema domain riêng, thêm một tầng chuyển đổi và chi phí bảo trì giữa parser và mô hình pháp lý của dự án. Hướng thay thế là Parser Router, Canonical Document IR và Legal Structure Extractor do dự án sở hữu. Đây là rationale và kiến trúc mục tiêu, không phải bằng chứng đã triển khai hoàn tất.

## 2. Khả thi của kiến trúc mục tiêu

Kiến trúc mục tiêu về nguyên tắc có thể triển khai theo các ranh giới đã khóa trong tài liệu 00:

```text
Allowlist → immutable snapshot/manifest → manual ingestion CLI
         → Parser Router (Docling | MinerU)
         → Canonical Document IR
         → legal structure / provenance / temporal enrichment
         → quality gates → accepted corpus source of truth
         → dense + sparse derived index (Qdrant)

Question → intent/reference/date/evidence plan
         → temporal + exact/dense/sparse retrieval
         → bounded expansion → completeness gate
         → structured generation → deterministic verification
         → verified answer অথবা abstention
```

Các thành phần như Parser Router, IR, relation/temporal model, reranking, structured claims, bounded repair và verification chỉ được coi là **target architecture**. Không được suy ra rằng chúng đã có runtime implementation chỉ từ thiết kế. Frozen scope yêu cầu corpus release đúng 14 PDF allowlisted sau deduplicate, không open-web fallback, ingestion manual và fail-closed, không upload/admin/reviewer approval trong MVP, Qdrant là index dẫn xuất, và verified-or-abstain.

## 3. Baseline runtime thực tế

Audit hiện tại cho thấy:

- FastAPI đăng ký router RAG, auth, chats và legal. Supabase Auth xác thực bearer token; persistence chat, feedback và bookmark được giới hạn theo user.
- `RAGService` chạy đồng bộ: phân tích câu hỏi, fan-out bounded, hybrid retrieval, RRF-like merge, diversity/structural/temporal filtering, evidence checks và sinh Markdown. Retrieval dùng Qdrant, dense embeddings qua cấu hình OpenAI-compatible/OpenRouter và FastEmbed BM25; có exact metadata filtering, temporal filtering, sibling completion và cross-reference expansion.
- Citation được dựng từ `chunk_id`, `document_id`, Điều/Khoản/Điểm và source metadata. Có deterministic checks trong evidence layer, nhưng chưa có bằng chứng đầy đủ cho stable `provision_id`/accepted review workflow, production reranker, LangGraph, sáu verifier độc lập hoặc failure-aware repair graph.
- Ingestion runtime là Markdown/JSONL loader (`backend/app/ingestion/markdown.py`), đọc `data/sources/manifest.json` và Markdown dưới `data/corpus/mds`. Manifest hiện có 17 entries; điều này không chứng minh release corpus đúng 14 PDF. Chưa có bằng chứng runtime cho Parser Router, Canonical IR, PostgreSQL legal source-of-truth hoặc immutable accepted-publish pipeline.
- Release compose hiện có Qdrant, backend và frontend; Supabase/OpenRouter là dịch vụ bên ngoài. Audit không thấy active runtime path cho PostgreSQL/SQLAlchemy/Alembic legal source-of-truth, Redis/Dramatiq, MinIO, Langfuse, LangGraph hoặc Docling/MinerU Parser Router.
Evidence artifact hiện có diagnostic run 40/40 case qua API, không qua UI; kết quả cho thấy retrieval hit@5 và legal-coordinate accuracy bằng 0, citation validity chưa đạt gate, có timeout/null prediction và semantic review còn kết quả incorrect/partial/unavailable. Đây là bằng chứng chẩn đoán, không phải bằng chứng release-ready. Artifact 32/40 trước đó chỉ là lịch sử chẩn đoán, không phải release result.

## 4. Khả thi phần cứng và vận hành — có điều kiện

Runtime hiện tại có thể chạy theo topology local/private-network với Qdrant, backend và frontend; các dịch vụ xác thực và model API phụ thuộc cấu hình bên ngoài. Tuy nhiên khả năng chạy Parser Router, OCR, snapshot quality gates, corpus rebuild và full evaluation chưa được chứng minh bằng benchmark trong repository. GPU local không phải điều kiện bắt buộc cho online path vì embedding/generation có thể dùng API, nhưng chi phí, quota, độ trễ và khả năng xử lý PDF/OCR vẫn là điều kiện cần đo.

Do đó, kết luận phần cứng/vận hành chỉ là **khả thi có điều kiện** khi có đủ tài nguyên CPU/RAM/disk, credentials hợp lệ, network ổn định, giới hạn concurrency, quy trình backup/rollback và quan sát được latency/error. MVP không bao gồm upload, admin/reviewer UI hay background queue; không được coi các quy trình đó là năng lực đã có.

## 5. Khả thi tài chính — chưa được xác nhận

Chi phí phụ thuộc số lần gọi OpenRouter/embedding, kích thước corpus, rebuild index, evaluation và lưu trữ dịch vụ ngoài. Không có trong tài liệu này một báo giá đã chạy hoặc cam kết free tier có thể dùng cho release. Vì vậy ngân sách chỉ có thể đánh giá sau khi chốt workload, quota, model/configuration và thời gian chạy thực tế. Không khẳng định một model cố định hoặc tổng chi phí cố định là kết quả đã đạt.

Lịch cũ không đủ để chứng minh hoàn thành. Các hạng mục còn cần bằng chứng gồm: đối soát corpus frozen 14 PDF và provenance, triển khai/đánh giá pipeline ingestion mục tiêu, kiểm tra temporal/reference semantics, hoàn thiện evidence-gated verified-or-abstain, chạy đủ release gate 40 case thuộc 8 category, kiểm tra UI/browser, đánh giá citation và semantic correctness, cùng release smoke test. Bộ 40 case chỉ có coverage giới hạn và không có ngưỡng metric cố định; khi các gate này chưa có artifact đạt, không thể kết luận lịch trình khả thi hoặc cam kết ngày release.
Lịch cũ không đủ để chứng minh hoàn thành. Các hạng mục còn cần bằng chứng gồm: đối soát corpus frozen, provenance, kiểm tra temporal/reference semantics, hoàn thiện evidence-gated verified-or-abstain, chạy release gate 40 case thuộc 8 category, kiểm tra UI/browser, đánh giá citation và semantic correctness, cùng release smoke test. Bộ 40 case có coverage giới hạn và không có ngưỡng metric cố định; khi các gate này chưa có artifact đạt, không thể kết luận lịch trình khả thi hoặc cam kết ngày release.

## 7. Blocker và rủi ro chính

1. **Corpus mismatch:** loader hiện dùng 17 Markdown entries, trong khi frozen release contract yêu cầu 14 PDF allowlisted; provenance và publish gate chưa được chứng minh.
2. **Citation/evidence risk:** evidence checks có nhưng citation validity và abstention accuracy trong subset còn thấp; có nguy cơ trả claim thiếu căn cứ hoặc citation sai.
3. **Temporal/reference risk:** filtering hiện có, nhưng semantics sửa đổi/thay thế và relation source-of-truth mục tiêu chưa được chứng minh end-to-end.
4. **Performance risk:** diagnostic run có latency cao; chưa có phân tích đầy đủ qua UI, tải đồng thời hoặc đánh giá coverage rộng hơn bộ 40 case.
5. **Operational dependency risk:** Supabase, OpenRouter-compatible embeddings/generation và Qdrant deployment cần cấu hình, quota và availability ngoài repository.
6. **Scope confusion:** các thành phần PostgreSQL, queue, object storage, observability, parser router và workflow orchestration là target/historical design, không được báo cáo như runtime.
7. **Evaluation gap:** đã có diagnostic run 40 case qua API nhưng chưa chứng minh release gate đầy đủ; semantic review, manual browser verification và các gate corpus/provenance vẫn chưa đạt.

## 8. Kết luận

Đề tài có **giá trị nghiên cứu rõ ràng** và kiến trúc mục tiêu **có thể triển khai về nguyên tắc**, nhưng tính khả thi kỹ thuật, vận hành, tài chính và lịch trình chỉ là kết luận có điều kiện. Runtime hiện tại chứng minh một MVP RAG có auth, persistence, hybrid retrieval, temporal filtering giới hạn và citation assembly; chưa chứng minh toàn bộ frozen release contract hay target architecture.

> **Quyết định hiện tại: UNVERIFIED / NOT RELEASE-READY.**

Chỉ có thể chuyển trạng thái sau khi evidence artifact đầy đủ xác nhận corpus/provenance, retrieval và citation, evidence-gated abstention, temporal/reference behavior, performance, release gate 40 case/8 category và UI/browser release gates. Bộ đánh giá này có coverage giới hạn, không thay thế đánh giá toàn diện. Không dùng thiết kế mục tiêu, kế hoạch chi phí hoặc lịch cũ thay cho bằng chứng runtime.