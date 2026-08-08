# Jira Report — VNLRAG-14 → VNLRAG-120

Nguồn: `https://truongphucwork.atlassian.net/jira/software/projects/VNLRAG/boards/1/backlog`
Tổng số ticket: **107** (VNLRAG-14 → VNLRAG-120, liên tục).
Trạng thái chung: tất cả **To Do**, priority **Medium**, assignee **PhucTruong**.

| Key | Loại | Title | Tóm tắt desc | Labels | Status | Priority | Assignee |
|---|---|---|---|---|---|---|---|
| VNLRAG-14 | Task | Finalize Project Scope and Architecture Decisions | Chốt scope dự án và các quyết định kiến trúc (ADR) trước khi bắt đầu triển khai. | architecture, foundation, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-15 | Task | Initialize Repository Structure and Development Tooling | Thiết lập cấu trúc repo + tooling Python/TS: uv, ruff, mypy, pytest, Next.js, Docker Compose, pre-commit. | foundation, sprint-0, tooling, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-16 | Task | Define Corpus Manifest Schema | Định nghĩa Pydantic model CorpusManifest mô tả corpus: nguồn, version, hash, trạng thái xử lý. | foundation, schema, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-17 | Task | Define Legal Document Schema | Schema tài liệu pháp lý biểu diễn metadata và phân cấp đầy đủ của văn bản luật Việt Nam. | foundation, schema, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-18 | Task | Define Legal Provision Schema | Schema điều khoản pháp lý (điều/khoản/điểm) — đơn vị lõi cho retrieval và verification. | foundation, schema, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-19 | Task | Select the Initial Official Legal Corpus | Chọn và thu thập corpus PDF luật giao thông chính thức, tạo corpus manifest. | corpus, foundation, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-20 | Spike | Validate UDEF Integration with the RAG Backend | Spike xác nhận UDEF (Ummelis Document Exchange Format) tích hợp đúng với backend RAG Python. | ingestion, spike, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-21 | Spike | Extract a Legal PDF into CDM with Provenance | Spike trích xuất text/cấu trúc PDF pháp lý bằng Docling, giữ provenance (nguồn, trang, confidence). | ingestion, spike, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-22 | Spike | Prototype Article, Clause, and Point Extraction | Prototype trích xuất cấu trúc điều/khoản/điểm từ CDM do Docling sinh ra. | ingestion, spike, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-23 | Task | Create the Initial Traffic Law RuleSpec | Định nghĩa RuleSpec — các luật/mẫu trích xuất cho văn bản luật giao thông, drive domain pack UDEF. | ingestion, rulespec, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-24 | Task | Create the First Golden Extraction Fixture | Tạo golden fixture đầu tiên — văn bản được chú thích thủ công làm ground truth đánh giá trích xuất. | foundation, gold-set, sprint-0, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-25 | Story | Extract Legal Document Metadata | Trích xuất metadata có cấu trúc (title, number, authority, dates) từ CDM Docling bằng UDEF patterns. | ingestion, metadata, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-26 | Story | Extract Articles, Clauses, and Points | Trích xuất phân cấp điều khoản (điều/khoản/điểm) từ CDM Docling — đơn vị lõi của retrieval. | extraction, ingestion, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-27 | Task | Implement Legal Metadata Normalization | Chuẩn hóa metadata trích xuất (format, tên gọi, ngày tháng) về dạng canonical. | ingestion, normalization, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-28 | Task | Implement Legal Structure State Parser | Parser nhận diện trạng thái cấu trúc văn bản (lời nói đầu, nội dung, điều khoản chuyển tiếp, phụ lục). | ingestion, parsing, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-29 | Task | Aggregate Provision Source References | Gộp provenance từ CDM Docling vào mô hình điều khoản: PDF nào, trang, dòng, confidence. | ingestion, provenance, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-30 | Task | Implement Legal Hierarchy Validation | Validation phân cấp trích xuất: thiếu điều, trùng số, nesting sai. | ingestion, sprint-1, validation, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-31 | Task | Implement Temporal and Relation Validation | Validate tính thời hạn (hiệu lực, lịch sử sửa đổi) và cross-reference giữa các điều khoản. | ingestion, sprint-1, temporal, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-32 | Task | Project UDEF Output into Legal Domain Models | Projection/mapping từ UDEF CDM sang domain models LegalDocument và LegalProvision. | ingestion, sprint-1, udef, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-33 | Task | Configure Ingestion Confidence and Review Routing | Cấu hình ngưỡng confidence và routing để đánh dấu bản trích xuất thấp cần review thủ công. | ingestion, review, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-34 | Task | Create Law and Circular Golden Fixtures | Tạo golden fixtures cho 2 loại văn bản: Luật và Thông tư. | gold-set, ingestion, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-35 | Task | Run Initial Corpus Ingestion and Manual Review | Chạy toàn bộ pipeline ingestion trên corpus đầu tiên và review chất lượng output. | corpus, ingestion, sprint-1, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-36 | Task | Set Up PostgreSQL and Qdrant Services | Cấu hình dịch vụ PostgreSQL (metadata) và Qdrant (vector) trong Docker Compose, validate kết nối. | data-platform, infrastructure, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-37 | Task | Implement SQLAlchemy Legal Data Models | Mapping ORM SQLAlchemy cho LegalDocument/LegalProvision lưu trên PostgreSQL. | data-platform, postgresql, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-38 | Task | Create Initial Alembic Migration | Thiết lập Alembic và tạo migration đầu tiên từ các SQLAlchemy models. | data-platform, migrations, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-39 | Task | Implement Document and Provision Repositories | Tầng repository cho LegalDocument/LegalProvision với CRUD và search. | data-platform, repository, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-40 | Task | Create the Qdrant Legal Provision Collection | Cấu hình collection Qdrant cho vector điều khoản với dense embeddings và sparse vectors. | data-platform, qdrant, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-41 | Task | Implement Gemini Embedding Provider | Triển khai embedding provider Gemini Embedding 2, vector 768 chiều. | data-platform, embedding, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-42 | Spike | Validate Qdrant Server-Side BM25 | Spike xác nhận BM25 server-side của Qdrant hoạt động tốt với văn bản pháp lý tiếng Việt. | data-platform, spike, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-43 | Task | Implement Sparse Encoding Fallback | Fallback sparse encoding tùy chỉnh nếu BM25 tích hợp của Qdrant không đủ tốt. | data-platform, sparse, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-44 | Task | Implement Idempotent Provision Indexing | Pipeline indexing từ PostgreSQL sang Qdrant đảm bảo idempotent, không trùng lặp khi re-index. | data-platform, indexing, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-45 | Task | Implement PostgreSQL and Qdrant Reconciliation | Quy trình reconciliation khi PostgreSQL và Qdrant lệch dữ liệu do lỗi/indexing một phần. | data-platform, reconciliation, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-46 | Task | Implement Fixed Token Chunking | Chunking cố định theo token window có overlap — baseline V1. | chunking, sprint-2, tokenization, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-47 | Task | Integrate Docling Hybrid Chunking | Tích hợp chunker Docling tôn trọng layout/hierarchy — chiến lược V2/V3. | chunking, docling, sprint-2, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-48 | Story | Implement Legal Provision Chunking | Lưu chunk cùng dạng gốc, repository chunk và orchestration pipeline chunking. | chunking, sprint-2, storage, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-49 | Story | Retrieve Provisions Using Dense Search | Dense search bằng embedding vectors trên collection Qdrant — phương pháp retrieval chính. | dense, retrieval, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-50 | Story | Retrieve Provisions Using Sparse Search | Sparse search bằng BM25 bổ trợ dense search khớp keyword chính xác. | retrieval, sparse, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-51 | Story | Fuse Dense and Sparse Results with RRF | Hybrid search fusion dense+sparse bằng Reciprocal Rank Fusion (RRF). | fusion, retrieval, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-52 | Task | Define the Retrieval Result Contract | Định nghĩa contract chung cho các phương pháp retrieval (dense, sparse, fused). | contract, retrieval, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-53 | Story | Filter Retrieval by Legal Document Reference | Lọc kết quả retrieval theo tham chiếu tài liệu pháp lý cụ thể. | filtering, retrieval, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-54 | Story | Filter Provisions by Effective Date | Temporal filtering — retrieval tôn trọng hiệu lực thời gian của điều khoản. | retrieval, sprint-3, temporal, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-55 | Story | Retrieve Historical Legal Provisions | Truy vấn điều khoản theo hiệu lực tại một thời điểm quá khứ cụ thể. | retrieval, sprint-3, temporal, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-56 | Story | Retrieve Current Legal Provisions | Truy vấn "luật hiện hành" — chỉ trả về điều khoản còn hiệu lực hôm nay. | retrieval, sprint-3, temporal, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-57 | Story | Retrieve Separate Contexts for Legal Comparison | Dual temporal retrieval — trả context riêng biệt để so sánh luật trước/sau sửa đổi. | retrieval, sprint-3, temporal, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-58 | Task | Deduplicate Provision Segments and Add Parent Context | Khử trùng lặp chunk chồng lấp và thêm context của điều khoản cha. | processing, retrieval, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-59 | Task | Create the Development Retrieval Gold Set | Gold set phát triển gồm cặp query–provision để đo chất lượng retrieval. | evaluation, gold-set, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-60 | Task | Implement Retrieval Evaluation Metrics | Khung đánh giá retrieval với các metric chuẩn. | evaluation, metrics, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-61 | Task | Run V1 to V4 Retrieval Baselines | Baseline 4 biến thể: V1 dense-only, V2 sparse-only, V3 hybrid RRF, V4 hybrid + temporal. | baseline, evaluation, sprint-3, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-62 | Story | Analyze Query Intent and Legal Entities | Phân tích intent câu hỏi (hiện hành/lịch sử/so sánh) và thực thể pháp lý (số văn bản, điều khoản). | query-analysis, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-63 | Task | Implement Deterministic Date Parsing | Parse ngày tháng kiểu Việt (tuyệt đối + tương đối) bằng logic deterministic. | parsing, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-64 | Task | Implement Structured Query Analysis Fallback | Fallback LLM-based phân tích query khi deterministic không parse được. | analyzer, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-65 | Story | Route Queries with LangGraph | Workflow state machine LangGraph điều phối analyze → retrieve → generate → verify. | langgraph, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-66 | Task | Build the Legal Retrieval Context | Builder gộp các điều khoản truy vấn được thành context có cấu trúc cho LLM. | context, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-67 | Story | Generate Structured Legal Answers | Sinh câu trả lời pháp lý có cấu trúc kèm citation xác minh được bằng Gemini API. | generation, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-68 | Task | Validate Generated Answers with Pydantic | Pydantic validation cho câu trả lời: lỗi cấu trúc, thiếu field, citation không hợp lệ. | sprint-4, validation, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-69 | Story | Verify Cited Provision Identifiers | Verification deterministic: điều khoản được trích dẫn có thực sự tồn tại trong corpus. | sprint-4, verification, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-70 | Story | Verify Citation Temporal Validity | Kiểm tra citation có hợp lệ về thời gian với khung thời gian của query. | sprint-4, verification, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-71 | Task | Implement Deterministic Claim Support Checks | Kiểm tra nội dung claim có được bằng chứng đã truy xuất hỗ trợ hay không. | sprint-4, verification, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-72 | Story | Retry Invalid Answers Once | Một lần retry với context cải thiện khi answer fail validation/verification. | retry, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-73 | Story | Abstain When Evidence Cannot Be Verified | Abstention — từ chối trả lời khi không verify được citation/claim sau retry. | abstention, sprint-4, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-74 | Task | Record Query and Verification Traces | Ghi trace cho toàn bộ vòng đời query + kết quả verification phục vụ đánh giá. | sprint-4, tracing, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-75 | Task | Run Verified Workflow Integration Tests | Test tích hợp end-to-end cho mọi path: hiện hành, lịch sử, so sánh, abstention. | sprint-4, testing, vnlrag, workflow | To Do | Medium | PhucTruong |
| VNLRAG-76 | Story | Expose the Legal Chat API | FastAPI endpoint cho legal chat workflow verified Q&A. | chat, fastapi, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-77 | Story | Expose the Legal Provision Search API | Search API truy vấn điều khoản trực tiếp không qua workflow Q&A đầy đủ. | fastapi, search, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-78 | Task | Implement Standard API Errors and Trace Identifiers | Hạ tầng lỗi API nhất quán và trace identifiers phục vụ debug. | errors, fastapi, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-79 | Story | Build the Legal Chat Screen | Giao diện chat web bằng Next.js + TypeScript để hỏi câu hỏi pháp lý. | chat, nextjs, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-80 | Story | Add Query Date and Vehicle Controls | Date picker (hiện hành/lịch sử/so sánh) và vehicle selector trên chat screen. | controls, nextjs, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-81 | Story | Display Verifiable Citation Cards | Citation cards hiển thị chi tiết trích dẫn và trạng thái verification. | citations, nextjs, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-82 | Story | Display the Original Legal Source Passage | Viewer hiển thị văn bản pháp lý gốc hỗ trợ từng citation. | nextjs, source, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-83 | Story | Display Abstention Results | Màn hình abstention giải thích vì sao hệ thống không trả lời được. | abstention, nextjs, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-84 | Story | Display Historical Comparison Results | View so sánh side-by-side giữa hai thời kỳ cho phân tích pháp lý lịch sử. | comparison, nextjs, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-85 | Task | Add Query Processing Progress Events | SSE (Server-Sent Events) đẩy tiến trình xử lý real-time vì workflow mất vài giây. | events, fastapi, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-86 | Task | Implement the Corpus Review CLI | CLI tool review tài liệu đã ingest và chất lượng trích xuất. | cli, review, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-87 | Task | Build the Full Docker Compose Stack | Stack Docker Compose hoàn chỉnh chạy local cho dev/test/demo defense. | deployment, docker, sprint-5, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-88 | Task | Add Playwright End-to-End Smoke Tests | Playwright E2E smoke test tự động phát hiện integration regression. | e2e, sprint-5, testing, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-89 | Task | Stabilize End-to-End Demo Scenarios | Ổn định các kịch bản demo end-to-end cho defense. | sprint-5, stabilization, testing, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-90 | Task | Freeze the Candidate Legal Corpus | Đóng băng corpus trước đánh giá để đảm bảo tính tái lập, tạo snapshot version. | corpus, evaluation, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-91 | Task | Define and Validate the Gold Set Schema | Định nghĩa và validate schema gold set trước khi mở rộng. | gold-set, schema, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-92 | Task | Complete the Development Gold Set | Hoàn thiện và validate dev gold set từ Sprint 3. | development, gold-set, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-93 | Task | Complete the Validation Gold Set | Gold set validation riêng để tune retrieval parameters tránh overfit dev set. | gold-set, sprint-6, validation, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-94 | Task | Complete the Final Test Gold Set | Gold set test giữ riêng, chỉ dùng một lần cho kết quả cuối. | gold-set, sprint-6, test, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-95 | Task | Review Expected Legal Provision Identifiers | Review toàn bộ provision identifiers kỳ vọng trên các gold set. | gold-set, review, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-96 | Task | Freeze and Hash the Gold Set | Đóng băng và hash toàn bộ gold set trước đánh giá ngăn data leakage. | freeze, gold-set, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-97 | Task | Run V1 to V3 Chunking Evaluation | So sánh chunking V1 fixed token, V2 Docling hybrid, V3 semantic. | chunking, evaluation, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-98 | Task | Run V4 Hybrid Retrieval Evaluation | Đánh giá hybrid retrieval (dense + sparse với RRF). | evaluation, retrieval, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-99 | Task | Run V5 Temporal Retrieval Evaluation | Đánh giá temporal retrieval (hybrid + temporal filtering). | evaluation, sprint-6, temporal, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-100 | Task | Run V6 Citation Verification Evaluation | Đo accuracy verification, cải thiện từ retry và đúng đắn của abstention. | evaluation, sprint-6, verification, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-101 | Task | Run Secondary Ragas Metrics | Ragas metrics chất lượng câu trả lời, judge GPT-5.4 mini. | evaluation, ragas, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-102 | Task | Measure Latency, Resource Usage, and Cost | Thu thập số liệu latency, tài nguyên, chi phí cho chương đánh giá. | evaluation, performance, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-103 | Task | Produce Evaluation Tables and Charts | Sản xuất bảng và biểu đồ chất lượng publication cho chương đánh giá. | evaluation, reporting, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-104 | Task | Perform Evaluation Error Analysis | Phân tích lỗi hệ thống trên các failure để hiểu failure modes. | analysis, evaluation, sprint-6, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-105 | Task | Fix Release-Blocking Regression Defects | Sửa các defect chặn release phát hiện trong quá trình đánh giá. | fixes, sprint-6, stabilization, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-106 | Task | Freeze the Feature Set | Đóng băng feature set Sprint 7, ngăn scope creep trước release. | freeze, sprint-6, stabilization, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-107 | Task | Select the Final Production Variant | Chọn variant cuối (V1-V6 hoặc hybrid) dựa trên metric đánh giá. | release, selection, sprint-7, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-108 | Task | Finalize the Research Methodology Chapter | Hoàn thiện chương phương pháp nghiên cứu với chi tiết triển khai thực tế. | methodology, sprint-7, thesis, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-109 | Task | Finalize the System Implementation Chapter | Hoàn thiện chương triển khai hệ thống mô tả chính xác mọi thành phần. | implementation, sprint-7, thesis, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-110 | Task | Finalize the Evaluation Chapter | Hoàn thiện chương đánh giá với số liệu, bảng biểu, phân tích thực tế. | evaluation, sprint-7, thesis, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-111 | Task | Finalize Limitations and Future Work | Viết phần hạn chế trung thực và hướng phát triển tương lai. | limitations, sprint-7, thesis, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-112 | Task | Audit Citations and References | Rà soát citation/reference: đầy đủ, đúng định dạng, URL truy cập được. | references, sprint-7, thesis, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-113 | Task | Freeze the Source Code | Đóng băng source code với version tag và final commit. | freeze, release, sprint-7, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-114 | Task | Create the First Release Candidate | Tạo release candidate v1.0.0-rc1 kèm build artifacts, release tarball. | build, release, sprint-7, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-115 | Task | Build the Final Thesis PDF | Dựng PDF luận văn hoàn chỉnh từ các chương, LaTeX, bibliography, TOC. | pdf, sprint-7, thesis, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-116 | Task | Complete the Defense Slide Deck | Tạo slide bảo vệ: tổng quan, kiến trúc, kết quả, demo, Q&A backup. | defense, slides, sprint-7, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-117 | Task | Record the Backup Demo Video | Quay video demo backup phòng khi demo live lỗi trong buổi bảo vệ. | defense, sprint-7, video, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-118 | Task | Run a Clean-Room Deployment Test | Kiểm tra hệ thống deploy sạch từ đầu cho buổi bảo vệ. | release, sprint-7, testing, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-119 | Task | Create the Final Backup Bundle | Sao lưu toàn bộ artifact cho bảo vệ và tham khảo tương lai. | backup, release, sprint-7, vnlrag | To Do | Medium | PhucTruong |
| VNLRAG-120 | Task | Create the Defense Release Candidate | Đóng gói toàn bộ cho bảo vệ: code, thesis PDF, slides, demo video, backup. | defense, release, sprint-7, vnlrag | To Do | Medium | PhucTruong |
