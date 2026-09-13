# 04. Tech stack và chính sách nghiên cứu LLM

> **Audit runtime:** 13/09/2026  
> **Trạng thái release:** UNVERIFIED / NOT RELEASE-READY  
> **Nguồn phạm vi cao nhất:** [00-scope-and-decisions.md](00-scope-and-decisions.md)

Tài liệu này chỉ ghi nhận những gì có bằng chứng trong dependency manifest, cấu hình, mã nguồn hoặc deployment hiện tại. Kiến trúc mục tiêu và nghiên cứu lịch sử được tách nhãn rõ ràng; không dùng chúng để mô tả runtime đã triển khai.

## 1. Inventory runtime hiện tại

| Khu vực | Thành phần và bằng chứng | Trạng thái |
|---|---|---|
| API | FastAPI, Uvicorn, Pydantic v2 trong `backend/pyproject.toml`; các router được đăng ký tại `backend/app/main.py` | **active** |
| Retrieval | Qdrant qua `langchain-qdrant`/`qdrant-client`; collection mặc định `traffic_law`; local path hoặc `QDRANT_URL` theo `backend/app/config.py` và compose | **active** |
| Sparse retrieval | FastEmbed, dùng cho sparse BM25 trong `backend/app/rag/retrieval.py` | **active** |
| Dense embeddings | OpenAI-compatible embeddings qua cấu hình OpenRouter và LangChain OpenAI integration | **active** |
| Generation provider | OpenRouter-compatible endpoint (`OPENROUTER_BASE_URL`, mặc định `https://openrouter.ai/api/v1`) và `langchain-openrouter` | **active** |
| Auth và persistence | Supabase Python client; backend xác thực bearer token và lưu chat/user data qua Supabase REST/Auth | **active** |
| Web UI | Next.js 16, React 19, TypeScript, Supabase SSR/client và React Markdown trong `frontend/package.json` | **active** |
| Deployment topology | Compose release chỉ có `qdrant`, `backend`, `frontend`; Supabase và OpenRouter là dịch vụ bên ngoài | **active** |
| Ingestion | Markdown/JSONL loader (`backend/app/ingestion/markdown.py`) đọc manifest và `data/corpus/mds`; không có bằng chứng parser PDF production | **active, giới hạn** |

### Model defaults (chỉ là facts cấu hình)

Các giá trị mặc định hiện có trong `backend/app/config.py` và `.env.example` là:

- `EMBEDDING_MODEL=text-embedding-3-small` trong backend settings; compose example truyền `openai/text-embedding-3-small` làm default OpenRouter model ID.
- `GENERATION_MODEL=deepseek/deepseek-v4-flash-0731`.
- `EMBEDDING_DIMENSIONS=768` trong `.env.example`.

Đây là giá trị cấu hình, không phải kết luận rằng một model cụ thể đã đạt benchmark hoặc luôn là model đang chạy trong mọi deployment. Deployment thực tế có thể override bằng environment; mọi thay đổi embedding phải được coi là thay đổi index và được kiểm tra tương thích trước khi phục vụ.

## 2. Phân loại thành phần ngoài inventory active

| Thành phần | Nhãn | Cách ghi nhận đúng |
|---|---|---|
| Docling | **target** | Parser trong kiến trúc mục tiêu; chưa có dependency hoặc runtime path active trong backend hiện tại. |
| MinerU | **target** | Parser challenger/fallback trong thiết kế mục tiêu; chưa có dependency hoặc runtime path active. |
| LangGraph | **target** | Controlled workflow orchestration mục tiêu; audit không thấy implementation active. Không gọi hệ thống hiện tại là agent. |
| Langfuse | **candidate** | Có thể nghiên cứu cho tracing/prompt experiments; không có dependency, config hoặc service trong release compose. Không phải release gate. |
| PostgreSQL | **target** | Source of truth quan hệ/pháp lý trong kiến trúc mục tiêu; runtime hiện tại không chứng minh PostgreSQL/SQLAlchemy/Alembic legal store. |
| Redis | **target** | Broker/cache cho thiết kế background jobs mục tiêu; không có dependency hoặc service release. |
| Dramatiq | **target** | Worker orchestration mục tiêu; không có dependency hoặc worker deployment hiện tại. |
| MinIO | **target** | Object storage mục tiêu/ứng viên S3-compatible; không có service hoặc client active trong release. |
| Jina | **candidate** | Embedding/reranker candidate trong nghiên cứu; không có Jina dependency hoặc active model assertion. |
| Gemini | **historical** | Provider/model research record; không phải provider bắt buộc hay model active được chứng minh. |
| Ragas | **candidate** | Evaluation option phụ; không có trong backend dependency set và không thay thế deterministic release evidence. |
| RAGFlow | **baseline** | Baseline so sánh độc lập nếu thực hiện; không nằm trong compose hoặc đường chạy production. |

Các nhãn trên không biến thành phần target/candidate/historical/baseline thành dependency. Việc nâng một mục lên active chỉ được phép sau khi có code import/runtime path, dependency declaration, cấu hình cần thiết, deployment wiring và bằng chứng kiểm chứng tương ứng.

## 3. Chính sách nghiên cứu và thay đổi công nghệ

1. **Evidence first.** Mỗi tuyên bố active phải truy được tới file dependency, config, code path hoặc deployment. Không suy ra model, dịch vụ, phiên bản, năng lực hoặc metric từ tài liệu thiết kế.
2. **Tách target khỏi runtime.** `docs/00-scope-and-decisions.md` mô tả parser router, Canonical Document IR, legal relations, temporal resolver, reranker và controlled workflow là kiến trúc mục tiêu; tài liệu này không trình bày chúng như đã hoàn tất.
3. **Provider policy.** Runtime dùng client OpenRouter-compatible đã cấu hình. OpenAI/Gemini không được tuyên bố là provider active riêng biệt chỉ vì tên model hoặc thư viện tương thích xuất hiện. Không tự động fallback provider khi chưa có quyết định và kiểm chứng.
4. **Grounded generation.** Retrieval, evidence checks, metadata-derived citations và fail-closed provider errors là contract hiện tại. Model selection không được thay thế citation/evidence verification.
5. **Reproducible model changes.** Ghi lại model ID, dimensions, endpoint policy và snapshot/index liên quan. Đổi embedding model hoặc dimensions yêu cầu rebuild Qdrant có kiểm soát; không trộn vector space.
6. **Research comparisons.** Docling/MinerU, Jina, Gemini, Ragas and RAGFlow chỉ được so sánh trên corpus/case set được nêu rõ, với config và thời điểm ghi lại. Kết quả chưa chạy phải ghi là chưa có bằng chứng; baseline không phải kết quả runtime.
7. **Scope discipline.** Không thêm PostgreSQL, Redis, Dramatiq, MinIO, LangGraph hoặc Langfuse chỉ để làm tài liệu khớp kiến trúc mục tiêu. Chỉ triển khai khi yêu cầu được mở lại, có owner, migration/deployment plan và acceptance evidence.
8. **Release/evaluation gate.** Đánh giá release dùng 40 case thuộc đúng tám category: `exact_reference`, `natural_language`, `penalty`, `multi_intent`, `cross_reference`, `follow_up`, `insufficient_evidence`, `out_of_scope`. Đây là phạm vi coverage có giới hạn và phải công bố artifact/case đã thực hiện; không áp đặt ngưỡng số cố định. Artifact chẩn đoán hiện có không phải kết quả pass/release.
9. **Release honesty.** Artifact hiện tại là chẩn đoán chưa đầy đủ; không gọi release-ready và không ghi metric chưa đo thành kết quả đạt. Full evaluation, semantic review và manual UI verification vẫn là các điều kiện độc lập theo tài liệu phạm vi.

## 4. Nguồn kiểm tra

- [Backend dependency manifest](../backend/pyproject.toml)
- [Frontend dependency manifest](../frontend/package.json)
- [Backend settings](../backend/app/config.py)
- [OpenRouter generation path](../backend/app/rag/generator.py)
- [Qdrant/FastEmbed retrieval path](../backend/app/rag/retrieval.py)
- [Markdown/JSONL ingestion](../backend/app/ingestion/markdown.py)
- [Environment template](../.env.example)
- [Release compose](../deploy/compose/compose.release.yml)
- [Authoritative scope and runtime audit](00-scope-and-decisions.md)
