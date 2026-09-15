# 04. Tech stack và chính sách nghiên cứu LLM

# 04. Tech-stack and LLM research

> **Audit runtime:** 14/09/2026
> **Trạng thái release:** RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME
> **Nguồn phạm vi cao nhất:** [00-scope-and-decisions.md](00-scope-and-decisions.md)

Tài liệu này chỉ ghi nhận những gì có bằng chứng trong dependency manifest, cấu hình, mã nguồn hoặc deployment hiện tại. Kiến trúc mục tiêu và nghiên cứu lịch sử được tách nhãn rõ ràng; không dùng chúng để mô tả runtime đã triển khai.

## 1. Inventory runtime hiện tại

| Khu vực                         | Thành phần và bằng chứng                                                                                                                               | Trạng thái           |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------- |
| API                             | FastAPI, Uvicorn, Pydantic v2 trong `backend/pyproject.toml`; các router được đăng ký tại `backend/app/main.py`                                        | **active**           |
| Retrieval                       | Qdrant qua `langchain-qdrant`/`qdrant-client`; collection mặc định `traffic_law`; local path hoặc `QDRANT_URL` theo `backend/app/config.py` và compose | **active**           |
| Sparse truy xuất                | FastEmbed, dùng cho sparse BM25 trong `backend/app/rag/retrieval.py`                                                                                   | **active**           |
| Dense embeddings                | OpenAI-compatible embeddings qua cấu hình OpenRouter và LangChain OpenAI integration                                                                   | **active**           |
| Generation nhà cung cấp mô hình | OpenRouter-compatible endpoint (`OPENROUTER_BASE_URL`, mặc định `https://openrouter.ai/api/v1`) và `langchain-openrouter`                              | **active**           |
| Auth và persistence             | Supabase Python client; backend xác thực bearer token và lưu chat/user data qua Supabase REST/Auth                                                     | **active**           |
| Web UI                          | Next.js 16, React 19, TypeScript, Supabase SSR/client và React Markdown trong `frontend/package.json`                                                  | **active**           |
| Deployment topology             | Compose release chỉ có `qdrant`, `backend`, `frontend`; Supabase và OpenRouter là dịch vụ bên ngoài                                                    | **active**           |
| Ingestion                       | Markdown/JSONL loader (`backend/app/ingestion/markdown.py`) đọc manifest và `data/corpus/mds`; không có bằng chứng parser PDF production               | **active, giới hạn** |

### Model defaults (chỉ là facts cấu hình)

Các giá trị mặc định hiện có trong `backend/app/config.py` và `.env.example` là:

- `EMBEDDING_MODEL=text-embedding-3-small` trong backend settings; compose example truyền `openai/text-embedding-3-small` làm default OpenRouter model ID.
- `GENERATION_MODEL=deepseek/deepseek-v4-flash-0731`.
- `EMBEDDING_DIMENSIONS=768` trong `.env.example`.

Đây là giá trị cấu hình, khác với kết luận rằng một model cụ thể đã đạt benchmark hoặc luôn là model đang chạy trong mọi deployment. Deployment thực tế có thể override bằng environment; mọi thay đổi embedding phải được coi là thay đổi index và được kiểm tra tương thích trước khi phục vụ.

## 2. Phân loại thành phần ngoài inventory active

| Thành phần | Nhãn           | Cách ghi nhận đúng                                                                                                                                       |
| ---------- | -------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Docling    | **target**     | Parser trong kiến trúc mục tiêu; chưa có dependency hoặc runtime path active trong backend hiện tại.                                                     |
| MinerU     | **target**     | Parser challenger/phương án dự phòng trong thiết kế mục tiêu; chưa có dependency hoặc runtime path active.                                               |
| LangGraph  | **target**     | Controlled workflow orchestration mục tiêu; audit không thấy implementation active. Không gọi hệ thống hiện tại là agent.                                |
| Langfuse   | **candidate**  | Có thể nghiên cứu cho tracing/câu lệnh cho mô hình experiments; không có dependency, config hoặc service trong release compose. Không phải release gate. |
| PostgreSQL | **target**     | Source of truth quan hệ/pháp lý trong kiến trúc mục tiêu; runtime hiện tại không chứng minh PostgreSQL/SQLAlchemy/Alembic legal store.                   |
| Redis      | **target**     | Broker/cache cho thiết kế background jobs mục tiêu; không có dependency hoặc service release.                                                            |
| Dramatiq   | **target**     | Worker orchestration mục tiêu; không có dependency hoặc worker deployment hiện tại.                                                                      |
| MinIO      | **target**     | Object storage mục tiêu/ứng viên S3-compatible; không có service hoặc client active trong release.                                                       |
| Jina       | **candidate**  | Embedding/bộ xếp hạng lại candidate trong nghiên cứu; không có Jina dependency hoặc active model assertion.                                              |
| Gemini     | **historical** | Provider/model research record; khác với nhà cung cấp mô hình bắt buộc hay model active được chứng minh.                                                 |
| Ragas      | **candidate**  | Evaluation option phụ; không có trong backend dependency set và không thay thế deterministic release evidence.                                           |
| RAGFlow    | **baseline**   | Baseline so sánh độc lập nếu thực hiện; không nằm trong compose hoặc đường chạy production.                                                              |

Các nhãn trên không biến thành phần target/candidate/historical/baseline thành dependency. Việc nâng một mục lên active chỉ được phép sau khi có code import/runtime path, dependency declaration, cấu hình cần thiết, deployment wiring và bằng chứng kiểm chứng tương ứng.

## 3. Chính sách nghiên cứu và thay đổi công nghệ

1. **Evidence first.** Mỗi tuyên bố active phải truy được tới file dependency, config, code path hoặc deployment. Không suy ra model, dịch vụ, phiên bản, năng lực hoặc metric từ tài liệu thiết kế.
2. **Tách target khỏi runtime.** `docs/00-scope-and-decisions.md` mô tả parser router, Canonical Document IR, legal relations, temporal resolver, bộ xếp hạng lại và controlled workflow là kiến trúc mục tiêu; tài liệu này không trình bày chúng như đã hoàn tất.
3. **Provider policy.** Runtime dùng client OpenRouter-compatible đã cấu hình. OpenAI/Gemini không được tuyên bố là nhà cung cấp mô hình active riêng biệt chỉ vì tên model hoặc thư viện tương thích xuất hiện. Không tự động phương án dự phòng nhà cung cấp mô hình khi chưa có quyết định và kiểm chứng.
4. **Grounded generation.** Retrieval và metadata-derived citations vẫn là contract. Generator có thể trả lời một phần; chỉ từ chối toàn bộ khi trả `CANONICAL_REFUSAL`. Lỗi nhà cung cấp mô hình `429/5xx` được retry có giới hạn. Sau generation, làm sạch trích dẫn đối chiếu citation/claim với metadata đã tìm kiếm căn cứ và chỉ loại các citation/claim không khớp, không loại toàn bộ answer. Model selection không thay thế citation/evidence verification.
5. **Chọn mô hình.** Benchmark live trên câu lệnh cho mô hình 15 đoạn dữ liệu và cùng tập case đã đo được ghi nhận như sau:

   **Analyzer** , các chỉ số theo thứ tự `JSON / category / vehicle`; thời gian là thời gian đo:

   | Model                   |                 JSON / category / vehicle | Thời gian |
   | ----------------------- | ----------------------------------------: | --------: |
   | `gemini-2.5-flash-lite` |                           6/6 / 6/6 / 6/6 |     1.3 s |
   | `mistral-small-24b`     |                           6/6 / 6/6 / 6/6 |     3.6 s |
   | `qwen3-30b-a3b-2507`    |                           6/6 / 6/6 / 6/6 |     4.1 s |
   | `gpt-oss-20b`           | 5/6 JSON; category/vehicle không ghi nhận |    11.2 s |

   **Generator** , `success/repeats`, p50 và max:

   | Model                    | Kết quả |    p50 |    Max |
   | ------------------------ | ------: | -----: | -----: |
   | `gemini-2.5-flash-lite`  |     5/5 |  1.2 s |  2.2 s |
   | `mistral-small-24b`      |     5/5 |  4.8 s | 11.2 s |
   | `gpt-oss-20b`            |     5/5 |  6.3 s |  6.6 s |
   | `deepseek-v4-flash-0731` |     5/5 | 24.3 s | 56.6 s |

   **Provider, tỉ lệ hoạt động và giá** , giá theo mỗi 1M token, input/output:

   | Model                    | Provider / tỉ lệ hoạt động                                       | Giá / ghi chú                                                                                       |
   | ------------------------ | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
   | `gemini-2.5-flash-lite`  | 5 nhà cung cấp mô hình; Google AI Studio tỉ lệ hoạt động 99.998% | $0.05 / $0.20                                                                                       |
   | `gpt-oss-20b`            | 14 nhà cung cấp mô hình                                          | $0.02 / $0.10                                                                                       |
   | `qwen3-30b-a3b-2507`     | 5 nhà cung cấp mô hình; có nhà cung cấp mô hình degraded         | Không ghi nhận                                                                                      |
   | `mistral-small-24b`      | 1 nhà cung cấp mô hình duy nhất (DeepInfra)                      | E2E P90 27.8 s, P95 40.0 s; structured-output error 2.35%; từng gây `generation_failed` do HTTP 429 |
   | `deepseek-v4-flash-0731` | 27 nhà cung cấp mô hình                                          | Chậm nhất                                                                                           |

   Chọn `gemini-2.5-flash-lite` cho cả bộ phân tích yêu cầu và bộ sinh câu trả lời: bộ phân tích yêu cầu đạt 6/6, bộ sinh câu trả lời có p50 1.2 s, có ít nhất 5 nhà cung cấp mô hình nên `allow_fallbacks` có tác dụng, và giá thấp. Biến cấu hình liên quan: `GENERATION_MODEL`, `ANALYZER_MODEL`, `ANALYZER_TIMEOUT_SECONDS`, `GENERATION_MAX_RETRIES`, `EMBEDDING_MODEL`.

6. **Reproducible model changes.** Ghi lại model ID, dimensions, endpoint policy và snapshot/index liên quan. Đổi embedding model hoặc dimensions yêu cầu rebuild Qdrant có kiểm soát; không trộn vector space.
7. **Scope discipline.** Không thêm PostgreSQL, Redis, Dramatiq, MinIO, LangGraph hoặc Langfuse chỉ để làm tài liệu khớp kiến trúc mục tiêu. Chỉ triển khai khi yêu cầu được mở lại, có owner, migration/deployment plan và acceptance evidence.
8. **Release/evaluation gate.** Đánh giá release dùng 40 case thuộc đúng tám category: `exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, `out_of_scope`. Đây là phạm vi coverage có giới hạn và phải công bố artifact/case đã thực hiện; không áp đặt ngưỡng số cố định. Artifact chẩn đoán hiện có khác với kết quả pass/release.
9. **Release honesty.** Artifact hiện tại là chẩn đoán chưa đầy đủ; không gọi release-ready và không ghi metric chưa đo thành kết quả đạt. Full evaluation, semantic review và manual UI verification vẫn là các điều kiện độc lập theo tài liệu phạm vi.

## 4. Nguồn kiểm tra

- [Backend dependency manifest](../backend/pyproject.toml)
- [Frontend dependency manifest](../frontend/package.json)
- [Backend settings](../backend/app/config.py)
- [OpenRouter generation path](../backend/app/rag/bộ sinh câu trả lời.py)
- [Qdrant/FastEmbed truy xuất path](../backend/app/rag/truy xuất.py)
- [Markdown/JSONL ingestion](../backend/app/ingestion/markdown.py)
- [Environment template](../.env.example)
- [Release compose](../deploy/compose/compose.release.yml)
- [Authoritative scope and runtime audit](00-scope-and-decisions.md)
