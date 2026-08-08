# 07. Triển Khai (Deployment)

> **Giai đoạn SDLC**: 6 - Triển khai
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
> **Tên đề tài**: Xây dựng hệ thống RAG nhận biết cấu trúc và thời gian hiệu lực để hỗ trợ tra cứu pháp luật giao thông Việt Nam với trích dẫn có thể kiểm chứng
> **English title**: A Structure-Aware and Temporal RAG System for Vietnamese Traffic Law Question Answering with Verifiable Citations

---

Tài liệu này định nghĩa phương án triển khai (deployment) của VNLRAG v2 bằng Docker Compose local-first. Mọi nội dung phải nhất quán với [00-scope-and-decisions.md](00-scope-and-decisions.md) (mục 7, 12, 16), thiết kế chi tiết [03-thiet-ke-he-thong.md](03-thiet-ke-he-thong.md) (mục 3.2.5, 3.11, 3.12, 3.13, 3.27, 3.28, 3.31), nghiên cứu công nghệ [04-tech-stack-llm-research.md](04-tech-stack-llm-research.md) (mục 4.18.6, 4.20, 4.21), kế hoạch triển khai [05-ke-hoach-trien-khai.md](05-ke-hoach-trien-khai.md) (mục 5.15.4, 5.16, 5.18) và kiểm thử [06-test-evaluation.md](06-test-evaluation.md) (mục 6.10, 6.12).

Mục tiêu triển khai (suy ra từ NFR-03, NFR-04, NFR-06 và doc 03 mục 3.2.5):

1. Toàn bộ hạ tầng dữ liệu (backend, worker, PostgreSQL, Qdrant, Redis, MinIO) chạy bằng Docker Compose trên máy bảo vệ, không phụ thuộc VPS.
2. Dữ liệu pháp lý bền vững qua restart: PostgreSQL là nguồn chân lý; Qdrant là index dẫn xuất dựng lại được từ PostgreSQL.
3. Database schema quản lý bằng Alembic; release lưu migration revision.
4. Ingestion chạy nền qua Redis + Dramatiq; không parse PDF đồng bộ trong request handler (FR-07, ADR-011).
5. Object storage qua MinIO; PostgreSQL lưu object key và metadata (FR-08, ADR-012).
6. Backup và restore tái lập được: PostgreSQL dump, Qdrant snapshot, MinIO artifact, gold set, evaluation report, release config và git tag.
7. External provider failure không làm mất dữ liệu và không bao giờ trả câu trả lời chưa verified.
8. Release candidate tái tạo được từ git tag, lock file, image digest và data hash.
9. Clean-room deployment có quy trình tài liệu hóa và kiểm chứng được.
10. Không còn dependency triển khai của ChromaDB, SQLite-as-primary, BM25 pickle, DuckDuckGo, SerpAPI hoặc UDEF (xem mục 7.18).

> **Ghi chú lịch sử**: bản v1 của tài liệu này dựa trên pipeline UDEF (`PDF -> UDEF -> Docling -> CDM`) với bốn service Compose (frontend, backend, postgres, qdrant), Qdrant pin 1.17.0 và mounted directory làm object storage. Phiên bản v2 loại bỏ hoàn toàn UDEF, thay bằng Parser Router + Canonical Document IR + Legal Structure Extractor (ADR-001), mở rộng Compose lên bảy service (thêm worker, redis, minio), pin Qdrant v1.19.0, PostgreSQL 18 và Redis 8, và dùng MinIO làm object storage (FR-08). UDEF chỉ xuất hiện trong tài liệu này ở ghi chú lịch sử và bảng mapping mục 7.18; không còn là thành phần được triển khai.

---

## 7.1. Kiến trúc triển khai (deployment architecture)

### 7.1.1. Service Compose

Compose production gồm bảy service (canonical spec mục 35, doc 03 mục 3.2.5, doc 04 mục 4.18.6):

```text
frontend    Next.js + TypeScript, port 3000
backend     FastAPI (uvicorn, 1 worker), port 8000
worker      Dramatiq worker ingestion (cùng image backend)
postgres    PostgreSQL 18.x, nguồn chân lý dữ liệu pháp lý
qdrant      Qdrant v1.19.0, retrieval engine dẫn xuất
redis       Redis 8.x, Dramatiq broker + cache
minio       MinIO (S3-compatible candidate), object storage
```

### 7.1.2. Ranh giới network

Mọi service nằm trong một Docker network nội bộ (bridge) tên `vnlaw-network`. Chỉ hai port public local trong release:

```text
127.0.0.1:3000    frontend
127.0.0.1:8000    backend
```

Các service nội bộ (postgres, qdrant, redis, minio) không expose port ra host trong release. MinIO console port (9001) chỉ bind trong dev override. Lý do: giảm bề mặt tấn công, tránh xung đột port với phần mềm khác trên máy bảo vệ, và buộc mọi truy cập đi qua backend.

### 7.1.3. Thành phần bên ngoài

| Thành phần | Vị trí | Ghi chú |
|---|---|---|
| Langfuse Cloud | Bên ngoài, KHÔNG nằm trong compose | Observability, prompt management, experiment; ngoài đường tới hạn (ADR-009) |
| Gemini API | Bên ngoài | Generator (gemini-3.5-flash) và embedding ứng viên (gemini-embedding-2) |
| OpenAI API | Bên ngoài | Judge GPT-5.4 mini snapshot cho L5 và metric thứ cấp |
| Jina API | Bên ngoài | Embedding ứng viên E2/E3 và reranker jina-reranker-v3 |
| RAGFlow | Môi trường benchmark RIÊNG | KHÔNG nằm trong compose production (ADR-010, FR-31) |

RAGFlow chạy trong môi trường benchmark riêng (doc 04 mục 4.6, doc 05 mục 5.18): image `infiniflow/ragflow:v0.26.4`, yêu cầu tối thiểu theo nhà cung cấp 4 CPU, 16 GB RAM, 50 GB disk, web port 80, API port 9380. RAGFlow không bao giờ được đưa vào compose production và không chạy cùng lúc với ingestion/demo/eval nặng trên cùng máy.

### 7.1.4. Parser service tùy chọn

Mặc định Docling chạy trong worker (CPU). MinerU pipeline backend CPU cũng chạy trong worker khi được Parser Router chọn (ADR-002). Nếu đo được RAM thực tế vượt budget của máy 19 GB, MinerU chuyển sang remote `*-http-client` (dedicated host) hoặc host tách biệt; trong trường hợp này có thể thêm một service parser riêng trong compose (không bắt buộc trong release cơ bản). Quyết định và số liệu đo phải được ghi vào tài liệu vận hành (doc 03 mục 3.2.5).

### 7.1.5. Yêu cầu triển khai bắt buộc

Compose release phải hỗ trợ đầy đủ:

```text
persistent volumes       postgres, qdrant, redis, minio
health checks            mọi service có healthcheck
migrations               Alembic upgrade head qua one-shot migrate service
background jobs          Redis + Dramatiq worker
parser artifacts         MinIO buckets cho parser output và IR
Qdrant rebuild           rebuild từ PostgreSQL + alias switch
object storage backup   replication hoặc mc mirror sang nơi độc lập
release manifest         release-manifest.json kèm hash và digest
clean-room deployment    quy trình từ máy trống tới demo
```

### 7.1.6. Sơ đồ topology

```mermaid
graph LR
    B["Browser"]
    FE["frontend (Next.js) :3000"]
    API["backend (FastAPI) :8000"]
    WK["worker (Dramatiq)"]
    PG["postgres :5432"]
    QD["qdrant :6333"]
    RD["redis :6379"]
    MO["minio :9000"]
    LF["Langfuse Cloud"]
    GEN["Gemini API"]
    JN["Jina API"]
    OA["OpenAI API (judge)"]
    RAGF["RAGFlow (benchmark riêng)"]

    B --> FE
    FE --> API
    API --> PG
    API --> QD
    API --> RD
    API --> MO
    WK --> RD
    WK --> PG
    WK --> QD
    WK --> MO
    API --> GEN
    API --> JN
    WK --> GEN
    API --> OA
    API -. "trace async" .-> LF
    RAGF -. "chỉ benchmark, cùng corpus + eval queries" .-> DEV
    DEV["Developer"]
```

---

## 7.2. Docker Compose chi tiết (per-service)

### 7.2.1. Quy tắc pin image

- Không dùng floating tags trong release compose: `latest`, `alpine`, `main` đều cấm (doc 04 mục 4.18.6).
- Pin exact patch đã chạy integration test thực tế: Qdrant `v1.19.0`, PostgreSQL `18.x`, Redis `8.x`.
- Trước code freeze (10/09/2026), mọi image bên thứ ba trong release compose phải được thay bằng digest (`@sha256:...`) của chính tag đã chạy integration test. Digest được ghi vào release manifest.
- Base image cho build (python, node) phải pin tag cụ thể có digest, không dùng `latest`.

Bảng pin khởi điểm (được thay bằng digest trước code freeze):

| Image | Tag khởi điểm |
|---|---|
| `postgres` | `postgres:18.4` |
| `qdrant/qdrant` | `qdrant/qdrant:v1.19.0` |
| `redis` | `redis:8.10.0` |
| `minio/minio` | date-tagged release, ví dụ `RELEASE.2025-05-20T20-30-00Z` (chọn tag đã test) |
| `python` (backend build) | `python:3.11-slim` + digest |
| `node` (frontend build) | Node 20 LTS + digest |

Compose release tại mục 7.2.2 là **template pre-freeze**: tag còn mutable, chỉ dùng để chạy integration/test và phát triển. Final release compose phải digest-pin toàn bộ image bên thứ ba và build image; image reference chỉ được lấy từ release manifest (mục 7.12). Không rebuild hoặc re-tag từ tag mutable sau code freeze (10/09/2026).

### 7.2.2. Compose release (`deploy/compose/compose.release.yml`)

> **Quy ước chạy lệnh (áp dụng toàn tài liệu)**: mọi lệnh `docker compose` phải chạy từ repo root và kèm `--project-directory . -f deploy/compose/compose.release.yml` (bản development thêm `-f deploy/compose/compose.dev.yml`). Các path trong compose file (`context: ./backend`, `context: ./frontend`, `env_file: .env`, volume `./backend:/app`, `./frontend:/app`) là repo-root-relative; `--project-directory .` làm chúng được resolve đúng từ repo root. Compose này là template pre-freeze (tag mutable); final release compose digest-pin theo mục 7.2.1 và 7.12.

```yaml
name: vnlaw-rag

services:
  postgres:
    image: postgres:18.4
    container_name: vnlaw-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-vnlaw}
      POSTGRES_USER: ${POSTGRES_USER:-vnlaw}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - vnlaw-network
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-vnlaw} -d ${POSTGRES_DB:-vnlaw}"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s

  qdrant:
    image: qdrant/qdrant:v1.19.0
    container_name: vnlaw-qdrant
    restart: unless-stopped
    volumes:
      - qdrant_data:/qdrant/storage
      - qdrant_snapshots:/qdrant/snapshots
    networks:
      - vnlaw-network
    healthcheck:
      test: ["CMD-SHELL", "bash -c 'exec 3<>/dev/tcp/127.0.0.1/6333'"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s

  redis:
    image: redis:8.10.0
    container_name: vnlaw-redis
    restart: unless-stopped
    command: ["redis-server", "--appendonly", "yes"]
    volumes:
      - redis_data:/data
    networks:
      - vnlaw-network
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 10s

  # MinIO: implementation hiện tại của ObjectStoragePort (contract S3-compatible).
  # Giữ làm mặc định trong compose; implementation production chốt sau object-storage ADR.
  minio:
    image: minio/minio:RELEASE.2025-05-20T20-30-00Z
    container_name: vnlaw-minio
    restart: unless-stopped
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}
    volumes:
      - minio_data:/data
    networks:
      - vnlaw-network
    healthcheck:
      test: ["CMD-SHELL", "curl -f http://127.0.0.1:9000/minio/health/live || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s

  migrate:
    build:
      context: ./backend
      dockerfile: Dockerfile
      args:
        APP_VERSION: ${APP_VERSION:-dev}
    image: vnlaw-backend:${APP_VERSION:-dev}
    container_name: vnlaw-migrate
    restart: "no"
    command: ["sh", "-c", "alembic upgrade head && python -m app.cli.ensure_qdrant_collection && python -m app.cli.ensure_buckets"]
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-vnlaw}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-vnlaw}
      QDRANT_URL: http://qdrant:6333
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      APP_ENV: ${APP_ENV:-release}
    networks:
      - vnlaw-network
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
      args:
        APP_VERSION: ${APP_VERSION:-dev}
    image: vnlaw-backend:${APP_VERSION:-dev}
    container_name: vnlaw-backend
    restart: unless-stopped
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-vnlaw}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-vnlaw}
      QDRANT_URL: http://qdrant:6333
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      APP_ENV: ${APP_ENV:-release}
    ports:
      - "127.0.0.1:${BACKEND_PORT:-8000}:8000"
    networks:
      - vnlaw-network
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test:
        [
          "CMD",
          "python",
          "-c",
          "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live')"
        ]
      interval: 15s
      timeout: 5s
      retries: 10
      start_period: 30s

  worker:
    build:
      context: ./backend
      dockerfile: Dockerfile
      args:
        APP_VERSION: ${APP_VERSION:-dev}
    image: vnlaw-backend:${APP_VERSION:-dev}
    container_name: vnlaw-worker
    restart: unless-stopped
    command: ["dramatiq", "--processes", "1", "--threads", "1", "app.ingestion.actors"]
    env_file:
      - .env
    environment:
      DATABASE_URL: postgresql+psycopg://${POSTGRES_USER:-vnlaw}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-vnlaw}
      QDRANT_URL: http://qdrant:6333
      REDIS_URL: redis://redis:6379/0
      MINIO_ENDPOINT: minio:9000
      APP_ENV: ${APP_ENV:-release}
    networks:
      - vnlaw-network
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_healthy
      redis:
        condition: service_healthy
      minio:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test: ["CMD", "dramatiq", "--check", "app.ingestion.actors"]
      interval: 15s
      timeout: 10s
      retries: 5
      start_period: 30s

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
        APP_VERSION: ${APP_VERSION:-dev}
    image: vnlaw-frontend:${APP_VERSION:-dev}
    container_name: vnlaw-frontend
    restart: unless-stopped
    environment:
      NODE_ENV: production
      NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL:-http://localhost:8000}
    ports:
      - "127.0.0.1:${FRONTEND_PORT:-3000}:3000"
    networks:
      - vnlaw-network
    depends_on:
      backend:
        condition: service_healthy
      migrate:
        condition: service_completed_successfully
    healthcheck:
      test:
        [
          "CMD",
          "node",
          "-e",
          "fetch('http://127.0.0.1:3000').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
        ]
      interval: 15s
      timeout: 5s
      retries: 10
      start_period: 30s

networks:
  vnlaw-network:
    driver: bridge

volumes:
  postgres_data:
  qdrant_data:
  qdrant_snapshots:
  redis_data:
  minio_data:
```

Ghi chú:

- `worker` và `backend` dùng cùng image `vnlaw-backend` (cùng Dockerfile, cùng env); khác nhau ở command (`backend` chạy uvicorn, `worker` chạy dramatiq) và healthcheck (worker dùng `dramatiq --check`).
- `migrate` là one-shot service: chạy `alembic upgrade head` rồi `ensure_qdrant_collection` rồi `ensure_buckets`, `restart: "no"`. Backend, worker và frontend khai `depends_on: migrate: condition: service_completed_successfully`, nên Compose chỉ khởi động app sau khi migrate hoàn tất thành công. Không service nào khác tự chạy migration.
- `MAX_INGESTION_WORKERS=1` được enforce ở hai tầng: (1) worker command khóa `--processes 1 --threads 1`; (2) application config đọc `MAX_INGESTION_WORKERS` để chỉ chạy một ingestion actor tại một thời điểm (doc 03 mục 3.2.5).
- `DATABASE_URL` dùng driver `psycopg` (postgresql+psycopg) theo doc 03.
- `minio` là implementation hiện tại của `ObjectStoragePort` (contract S3-compatible). Service này giữ trong compose làm mặc định cho tới khi object-storage ADR chốt implementation; cấu hình qua `S3_ENDPOINT`/`MINIO_ENDPOINT` và access/secret key (mục 7.5).
- `restart: unless-stopped` phù hợp máy bảo vệ; với clean-room và rehearsal cũng dùng policy này.
- Backend và frontend healthcheck gọi endpoint `live` / root trang chủ để Compose `depends_on` chờ đúng.
- Worker healthcheck dùng `dramatiq --check app.ingestion.actors`: kiểm tra module actors import được và broker Redis reachable. Hành vi khi fail: container bị đánh dấu unhealthy; `restart: unless-stopped` không tự restart container đang chạy nhưng unhealthy, nên vận hành phải theo dõi (`dramatiq --check`, queue depth, dead-letter) và dùng `reconcile_index.py` làm đường phục hồi (mục 7.4.4).

### 7.2.3. Compose development override (`deploy/compose/compose.dev.yml`)

Override chỉ dùng cho development; không dùng cho rehearsal/defense:

```yaml
services:
  postgres:
    ports:
      - "5432:5432"

  qdrant:
    ports:
      - "6333:6333"
      - "6334:6334"

  redis:
    ports:
      - "6379:6379"

  minio:
    ports:
      - "9000:9000"
      - "9001:9001"

  backend:
    build:
      target: development
    command:
      [
        "uv",
        "run",
        "uvicorn",
        "app.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        "8000",
        "--reload"
      ]
    volumes:
      - ./backend:/app
      - backend_uv_cache:/root/.cache/uv
    environment:
      APP_ENV: development
    ports:
      - "8000:8000"

  worker:
    build:
      target: development
    volumes:
      - ./backend:/app
    environment:
      APP_ENV: development

  frontend:
    build:
      target: development
    command: ["npm", "run", "dev"]
    volumes:
      - ./frontend:/app
      - frontend_node_modules:/app/node_modules
    ports:
      - "3000:3000"

volumes:
  backend_uv_cache:
  frontend_node_modules:
```

Chạy development:

```bash
docker compose \
  --project-directory . \
  -f deploy/compose/compose.release.yml \
  -f deploy/compose/compose.dev.yml \
  up --build
```

Lưu ý về resource limits: không bật `mem_limit` trong release compose mặc định vì giới hạn quá thấp có thể gây false failure. Nếu bật, chỉ bật sau khi đo `docker stats` thực tế và ghi số liệu vào tài liệu vận hành. Giá trị tham khảo ban đầu nằm ở mục 7.15.4.

---

## 7.3. Cấu hình môi trường (env/config management)

### 7.3.1. Nguyên tắc

- `.env` không bao giờ commit; permission `600` (chmod 600).
- Template env được commit dưới `deploy/env/*.env.example`, tách theo môi trường: `development.env.example`, `evaluation.env.example`, `release.env.example`.
- File `.env` thật được tạo từ template và điền secret, không chứa secret trong git.
- Secret phải khác example; `ADMIN_TOKEN`, `MINIO_ROOT_PASSWORD`, `POSTGRES_PASSWORD` và API key đều bắt buộc đổi.
- Final evaluation dùng file env riêng, read-only (không cho phép sửa trong lúc run).
- Model ID không hardcode trong domain logic; mọi model nằm trong config (doc 00 mục 7, NFR-08).

### 7.3.2. Cấu trúc deployment repository

```text
vnlaw-rag/
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── alembic/
│   ├── app/
│   └── scripts/            # ingest_document, rebuild_index, run_evaluation,
│                           # reconcile_index, verify_release, backup, restore
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── package-lock.json
│   └── next.config.ts
├── deploy/
│   ├── compose/
│   │   ├── compose.release.yml
│   │   └── compose.dev.yml
│   ├── env/
│   │   ├── development.env.example
│   │   ├── evaluation.env.example
│   │   └── release.env.example
│   ├── prompts/
│   │   └── fallback/
│   │       ├── query-analyzer.yaml
│   │       ├── query-rewriter.yaml
│   │       ├── hyde.yaml
│   │       ├── generator.yaml
│   │       └── claim-verifier.yaml
│   └── scripts/
│       ├── bootstrap.sh
│       ├── migrate.sh
│       ├── backup.sh
│       ├── restore.sh
│       ├── rebuild-index.sh
│       ├── verify-release.sh
│       └── defense-start.sh
├── data/                   # manifests, pdfs, gold-sets, evaluation (mounted trong dev)
├── backups/                # release backup bundle
├── docker-compose.yml
└── .env.example
```

### 7.3.3. `.env.example` chính

```dotenv
# Application
APP_ENV=release
APP_VERSION=v1.0.0-rc2
LOG_LEVEL=INFO
TIMEZONE=Asia/Ho_Chi_Minh

# Ports
FRONTEND_PORT=3000
BACKEND_PORT=8000
NEXT_PUBLIC_API_URL=http://localhost:8000

# PostgreSQL
POSTGRES_DB=vnlaw
POSTGRES_USER=vnlaw
POSTGRES_PASSWORD=change-me
DATABASE_URL=postgresql+psycopg://vnlaw:change-me@postgres:5432/vnlaw

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_ALIAS=legal_provisions_active
QDRANT_COLLECTION_PREFIX=legal_provisions

# Redis
REDIS_URL=redis://redis:6379/0

# Object storage (ObjectStoragePort, contract S3-compatible).
# MinIO là implementation hiện tại; implementation production chốt sau object-storage ADR.
# App đọc bộ S3_* (generic); bộ MINIO_* là alias tương thích với service MinIO hiện tại.
S3_ENDPOINT=minio:9000
S3_ACCESS_KEY=change-me
S3_SECRET_KEY=change-me
S3_BUCKETS=source-pdfs,parser-outputs,page-images,ingestion-artifacts,review-artifacts,evaluation-artifacts
S3_USE_SSL=false
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=change-me
MINIO_SECRET_KEY=change-me
MINIO_BUCKETS=source-pdfs,parser-outputs,page-images,ingestion-artifacts,review-artifacts,evaluation-artifacts
MINIO_USE_SSL=false

# Langfuse (Cloud mặc định)
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_HOST=https://cloud.langfuse.com

# Prompt fallback cục bộ (Langfuse ngoài đường tới hạn; xem mục 7.3.6)
PROMPT_SOURCE=LANGFUSE                 # LANGFUSE | CACHE | RELEASE_FALLBACK
FALLBACK_PROMPTS_DIR=/app/prompts/fallback
FALLBACK_PROMPT_VERSION_QUERY_ANALYZER=
FALLBACK_PROMPT_VERSION_QUERY_REWRITER=
FALLBACK_PROMPT_VERSION_HYDE=
FALLBACK_PROMPT_VERSION_GENERATOR=
FALLBACK_PROMPT_VERSION_CLAIM_VERIFIER=

# Generator
GENERATION_PROVIDER=gemini
GENERATION_MODEL=gemini-3.5-flash
GEMINI_API_KEY=
GENERATION_FALLBACK_ENABLED=false

# Embedding (chọn sau Suite B; khởi điểm ứng viên E1)
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-2
EMBEDDING_DIMENSIONS=768

# Reranker (ứng viên chính)
RERANKER_PROVIDER=jina
RERANKER_MODEL=jina-reranker-v3
JINA_API_KEY=

# Judge (L5 semantic + metric thứ cấp)
EVALUATION_JUDGE_PROVIDER=openai
EVALUATION_JUDGE_MODEL=gpt-5.4-mini-2026-03-17
OPENAI_API_KEY=

# Security
ADMIN_TOKEN=change-me
MAX_UPLOAD_SIZE_MB=50
PUBLIC_RATE_LIMIT_PER_MINUTE=10
ADMIN_RATE_LIMIT_PER_MINUTE=5

# Ingestion
MAX_INGESTION_WORKERS=1
INGESTION_TIMEOUT_SECONDS=1800

# Dramatiq actor time limits (giây; xem doc 03 mục 3.13.5)
ACTOR_TIME_LIMIT_PARSE=1200
ACTOR_TIME_LIMIT_NORMALIZE=300
ACTOR_TIME_LIMIT_EXTRACT=600
ACTOR_TIME_LIMIT_RESOLVE_REFS=300
ACTOR_TIME_LIMIT_RESOLVE_TEMPORAL=300
ACTOR_TIME_LIMIT_QUALITY_GATE=300
ACTOR_TIME_LIMIT_EMBED=600
ACTOR_TIME_LIMIT_INDEX=300

# Query
RETRIEVAL_TOP_K=8
DENSE_PREFETCH=30
SPARSE_PREFETCH=30
FUSION_LIMIT=20
GENERATION_MAX_CONTEXT_TOKENS=12000
GENERATION_MAX_OUTPUT_TOKENS=1500
MAX_REPAIR_ATTEMPTS=3

# Retention
QUERY_TRACE_RETENTION_DAYS=30

# Budget (USD cap)
DEVELOPMENT_BUDGET_USD=10
EVALUATION_BUDGET_USD=25
PROJECT_BUDGET_USD=40
```

### 7.3.4. Tách env theo môi trường

- `development.env.example`: `APP_ENV=development`, `LOG_LEVEL=DEBUG`, provider có thể dùng mock, budget `DEVELOPMENT_BUDGET_USD`.
- `evaluation.env.example`: `APP_ENV=evaluation`, `LANGFUSE_ENABLED` bật cho trace nhưng có thể tắt trong final run (doc 06 mục 6.8.6), `GENERATION_FALLBACK_ENABLED=false`, `EVALUATION_BUDGET_USD`, read-only.
- `release.env.example`: `APP_ENV=release`, mọi model pin snapshot, dùng cho rehearsal và defense.

### 7.3.5. Quy tắc model và final evaluation

- Không thay model alias sau khi final run bắt đầu (NFR-08; xem mục 7.12).
- Final evaluation dùng file env read-only: config không bị sửa giữa các batch.
- Model ID được ghi trong evaluation run metadata (`generator_model_id`, `embedding_model_id`, `reranker_model_id`, `judge_model_id`) (NFR-08, doc 06 mục 6.6.4).
- `GENERATION_FALLBACK_ENABLED=false` trong final evaluation; không tự động chuyển provider (doc 04 mục 4.10.5, doc 03 mục 3.32 ADR).

### 7.3.6. Prompt fallback cho release (Langfuse ngoài đường tới hạn)

Langfuse nằm ngoài đường tới hạn tính đúng đắn (ADR-009); để contract này deploy được, release phải có prompt fallback cục bộ:

- Thư mục `deploy/prompts/fallback/` chứa prompt bản đóng băng cho các prompt chính: `query-analyzer.yaml`, `query-rewriter.yaml`, `hyde.yaml`, `generator.yaml`, `claim-verifier.yaml`. Thư mục này được build vào image runtime (backend/worker) và có sẵn tại `FALLBACK_PROMPTS_DIR` (ví dụ `/app/prompts/fallback`).
- Mỗi file YAML ghi trường `version` và `hash`; version được pin trong env `FALLBACK_PROMPT_VERSION_*` và trong release manifest (mục 7.12.2).
- Thứ tự nạp prompt: `LANGFUSE` -> `CACHE` (cache nội bộ sau lần nạp thành công) -> `RELEASE_FALLBACK` (file cục bộ). Biến `PROMPT_SOURCE` ghi nguồn prompt đang dùng: `LANGFUSE | CACHE | RELEASE_FALLBACK`.
- Mọi trace và evaluation run metadata ghi `prompt_source` (`LANGFUSE | CACHE | RELEASE_FALLBACK`), `prompt_version`, `prompt_hash` (NFR-08).
- Khi Langfuse không khả dụng, runtime chuyển sang `CACHE`/`RELEASE_FALLBACK` mà không fail query; log và trace ghi rõ `prompt_source`.

---

## 7.4. Hàng đợi và worker (queue health + worker recovery)

### 7.4.1. Broker và mô hình job

- Redis 8.x làm broker Dramatiq và cache (doc 03 mục 3.13.1).
- Dramatiq 2.x chạy worker ingestion; `MAX_INGESTION_WORKERS=1`.
- Job state nằm trong PostgreSQL (`ingestion_runs`) là source of truth; Redis chỉ là đường truyền message (doc 03 mục 3.13.1).
- Actor không trả payload lớn; toàn bộ kết quả trung gian nằm trong PostgreSQL/MinIO; actor nhận `run_id` và tự enqueue bước kế tiếp (explicit chaining) để idempotent resume an toàn.

Danh sách actor và state job tương ứng (doc 03 mục 3.13.2):

```text
parse_actor             PARSING
normalize_actor         NORMALIZING
extract_actor           EXTRACTING
resolve_refs_actor      RESOLVING_REFS
resolve_temporal_actor  RESOLVING_TEMPORAL
quality_gate_actor      QUALITY_CHECK
embed_actor             EMBEDDING (chỉ sau review accept)
index_actor             INDEXING
```

Thứ tự pipeline: `parse_actor -> normalize_actor -> extract_actor -> resolve_refs_actor -> resolve_temporal_actor -> quality_gate_actor`. Sau quality gate: tất cả accepted -> `embed_actor -> index_actor`; có needs_review -> `PENDING_REVIEW` (không embed/index); dropped fatal -> dừng (doc 03 mục 3.13.3, FR-09).

### 7.4.2. Upload flow

```text
POST /api/v1/documents (multipart: file, manifest_json, force; yêu cầu Bearer token)
    -> validate MIME, magic bytes, size, filename, SHA-256
    -> duplicate check theo file_hash
    -> tạo IngestionRun (QUEUED)
    -> lưu PDF nguồn lên MinIO
    -> enqueue parse_actor
    -> 202 Accepted + ingestion_job_id
```

Request handler không chạy parser, extractor hay embed (FR-07, ADR-011, doc 03 mục 3.13.7). Job status truy vấn qua `GET /api/v1/jobs/{job_id}`.

### 7.4.3. Queue health

Queue health được kiểm tra ở hai tầng:

1. **Redis connectivity**: healthcheck container (redis-cli ping) và một mục trong readiness backend (kết nối `REDIS_URL`).
2. **Queue metrics** (admin-only, theo dõi bằng script hoặc endpoint admin):
   - độ sâu queue (`LLEN` của queue Dramatiq chính);
   - số message trong dead-letter queue (`dramatiq-dlq`);
   - worker liveness: Dramatiq CLI `dramatiq --check`;
   - `MAX_INGESTION_WORKERS=1` đảm bảo không chạy song song nhiều job parse.

Threshold khởi điểm (config, không phải kết quả đo): queue depth tăng kéo dài không giảm là dấu hiệu worker chết hoặc actor đang bị time limit; dead-letter count tăng liên tục cần khảo sát ngay. Các con số cụ thể được ghi nhận sau khi đo vận hành.

### 7.4.4. Worker recovery

Nguyên tắc: actor idempotent, retry transient, state job trong PostgreSQL, reconcile giữa job state và index state.

```text
retry policy (doc 03 mục 3.13.4):
  max_retries   5   (chỉ transient: 429, 5xx, timeout, connection)
  min_backoff   15 giây
  max_backoff   1 giờ
  idempotency   actor đọc state job từ PostgreSQL; nếu bước đã hoàn thành, bỏ qua
  idempotency key cấp tài liệu:
    SHA-256(file bytes) + parser version + legal parser version + IR schema version
```

Per-actor time limit (doc 03 mục 3.13.5): Dramatiq mặc định 10 phút, KHÔNG dùng mặc định cho bước dài; cấu hình riêng theo thời lượng bước:

```yaml
ingestion:
  actor_time_limits_seconds:
    parse_actor: 1200
    normalize_actor: 300
    extract_actor: 600
    resolve_refs_actor: 300
    resolve_temporal_actor: 300
    quality_gate_actor: 300
    embed_actor: 600
    index_actor: 300
```

Cấu hình thực tế phải khớp với broker timeout; nếu vượt, tách bước dài thành nhiều actor thay vì kéo dài vô hạn.

Phục hồi khi worker fail:

1. Message fail sau retry được Dramatiq đưa vào dead-letter queue (~7 ngày retention mặc định).
2. Dead-letter inspection: đọc nội dung message, phân loại lỗi (transient lỗi cấu hình, hay lỗi cố hữu của dữ liệu).
3. Manual replay: sau khi sửa nguyên nhân, gửi lại message từ dead-letter hoặc enqueue lại actor bằng `run_id`.
4. Reconciliation: script `reconcile_index.py` so sánh trạng thái job (`ingestion_runs`) và trạng thái index thực tế (PostgreSQL `legal_provisions` vs Qdrant point count); đánh dấu index pending và re-run `index_actor` (doc 03 mục 3.13.6).
5. Job state chuyển terminal `FAILED` khi retry cạn; lỗi và stack được lưu (doc 03 mục 3.4.1).

### 7.4.5. Vận hành queue

```bash
# Worker health (Dramatiq CLI)
docker compose --project-directory . -f deploy/compose/compose.release.yml exec worker dramatiq --check

# Queue depth
docker compose --project-directory . -f deploy/compose/compose.release.yml exec redis redis-cli LLEN <queue-name>

# Dead-letter count
docker compose --project-directory . -f deploy/compose/compose.release.yml exec redis redis-cli LLEN dramatiq-dlq

# Job status
curl http://localhost:8000/api/v1/jobs/<job_id>
```

---

## 7.5. Object storage (MinIO - S3-compatible candidate)

### 7.5.0. ObjectStoragePort (contract S3-compatible)

Object storage được truy cập qua port `ObjectStoragePort` (contract S3-compatible): put/get/delete object, head bucket, list buckets. MinIO là implementation hiện tại (service trong compose, mục 7.2.2) và là ứng viên mặc định; implementation production được chốt sau object-storage ADR. Kết nối qua biến S3-compatible: `S3_ENDPOINT` (hoặc `MINIO_ENDPOINT`), access key, secret key, bucket list, `S3_USE_SSL` (hoặc `MINIO_USE_SSL`). Khi đổi implementation chỉ cần thay service compose và endpoint env, không thay đổi domain logic (NFR-06). Bucket layout, backup, retention và health check trong mục này áp dụng cho mọi implementation S3-compatible của contract.

### 7.5.1. Buckets

MinIO lưu object theo bucket riêng cho từng loại artifact (doc 03 mục 3.12.1). Tên bucket không chứa `/`; dấu gạch nối (hyphen) phân tách các từ trong tên bucket:

| Bucket | Nội dung | Ví dụ object key (trong bucket) |
|---|---|---|
| `source-pdfs` | PDF nguồn đã validate | `documents/nd-168-2024/source/<sha256>.pdf` |
| `parser-outputs` | Đầu ra parser gốc (Docling JSON, MinerU JSON/Markdown) | `documents/nd-168-2024/docling-2.1.0/parsed.json` |
| `page-images` | Ảnh trang cho review và passage viewer | `documents/nd-168-2024/page-012.png` |
| `ingestion-artifacts` | IR JSON, report quality gate | `documents/nd-168-2024/ir-document-ir-v1.json` |
| `review-artifacts` | Bằng chứng review, screenshot, provenance | `review-{id}/evidence.json` |
| `evaluation-artifacts` | Raw output và artifact evaluation | `run-{run_id}/question-{qid}.jsonl` |

### 7.5.2. Quy ước object key

```text
{bucket} = loại artifact (không có slash)
{key}    = {document_id}/{parser}/{version}/{file}
```

- Filename nội bộ do hệ thống sinh, không dùng path từ người dùng (chặn path traversal).
- Metadata (file_hash, size, parser version, uploaded_at) nằm trong PostgreSQL (`ingestion_artifacts`); không dùng MinIO tag làm nguồn chính.
- Ví dụ ghép bucket + key: `s3://source-pdfs/documents/nd-168-2024/source/<sha256>.pdf`.

### 7.5.3. Khởi tạo bucket

Bucket được tạo trong bootstrap bằng client MinIO (mc) hoặc backend CLI, chạy một lần:

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend python -m app.cli.ensure_buckets
```

`MINIO_BUCKETS` trong env liệt kê danh sách bucket; `ensure_buckets` tạo bucket còn thiếu và in ra trạng thái. Bật versioning cho bucket khi cần giữ lịch sử object (doc 03 mục 3.12.3).

### 7.5.4. Health check

MinIO healthcheck container (mục 7.2.2) gọi `/minio/health/live`; backend readiness kiểm tra kết nối S3 (head bucket `source-pdfs` hoặc ListBuckets). Nếu MinIO không khả dụng, upload document trả lỗi structured; query path không phụ thuộc MinIO trừ passage viewer đọc ảnh trang.

### 7.5.5. Backup: tiering không phải backup

- ILM/transition (tiering) chỉ chuyển dữ liệu giữa các tầng trong cùng hệ thống, không thay thế nơi lưu trữ độc lập cho mục đích phục hồi.
- Backup MinIO bằng server-side replication (async) hoặc `mc mirror`/`mc cp` sang nơi lưu trữ độc lập (nơi khác với volume `minio_data`), ví dụ một ổ ngoài hoặc thư mục trên máy thứ hai.
- PostgreSQL lưu object key và hash; restore MinIO phải đi kèm kiểm tra hash với metadata trong PostgreSQL.

```bash
# Ví dụ mc mirror từng bucket sang thư mục backup độc lập
for b in source-pdfs parser-outputs page-images \
         ingestion-artifacts review-artifacts evaluation-artifacts; do
  mc mirror --overwrite --remove "local/$b" "/backups/minio/$(date +%Y%m%d)/$b"
done

# Kiểm chứng số lượng object sau mirror (so sánh cùng cặp nguồn/đích)
mc du local/source-pdfs
mc du /backups/minio/$(date +%Y%m%d)/source-pdfs
```

### 7.5.6. Retention policy

- Source PDF và corpus artifact giữ theo version văn bản (không xóa khi còn version hiệu lực hoặc lịch sử được tham chiếu).
- Review/evaluation artifact giữ theo chính sách ghi rõ trong tài liệu vận hành; mặc định giữ ít nhất tới khi khóa luận được chấm.
- MinIO console (port 9001) chỉ bind trong dev override; trong release không expose console ra host.

---

## 7.6. Parser runtime

### 7.6.1. Docling trong worker (CPU)

- Docling (parser chính) chạy bên trong worker, CPU, không yêu cầu GPU.
- Tài nguyên theo nhà cung cấp: CPU ~2-4 GB RAM điển hình, khuyến nghị 4 threads và 8-16 GB RAM (doc 04 mục 4.3).
- Docling không được cài làm binary riêng trong compose; nó là dependency Python của backend image (pin exact version theo `uv.lock`).
- Chunking: `HybridChunker` mặc định; tokenizer của chunker phải khớp tokenizer của embedding production (doc 04 mục 4.3.2). Docling chunker không dùng làm legal structure parser chính.

### 7.6.2. MinerU pipeline backend CPU

- MinerU (parser phụ/fallback) chạy pipeline backend CPU trong worker; VLM/hybrid KHÔNG chạy local (cần GPU >= 8 GB VRAM, máy có GPU 2 GB VRAM không khả thi).
- Ràng buộc RAM: pipeline backend khuyến nghị 16+ GB RAM (tối ưu 32+). Trên máy 19 GB RAM, MinerU chỉ dùng pipeline CPU, `MAX_INGESTION_WORKERS=1`, và không chạy ingestion song song với demo/eval nặng (doc 03 mục 3.2.5, ADR-002).
- Nếu đo được RAM thực tế vượt budget: MinerU chuyển sang remote `*-http-client` (dedicated host) hoặc host tách biệt; kết quả đo và quyết định ghi vào tài liệu vận hành.
- Optional: khi cần dedicated runtime, có thể thêm service parser riêng trong compose (không bắt buộc trong release cơ bản).

### 7.6.3. Vận hành ingestion

```text
MAX_INGESTION_WORKERS = 1
Không chạy ingestion đồng thời với demo hoặc evaluation nặng
Ingestion được lập lịch thành batch riêng khi cần
```

Lập lịch ingestion batch: dừng demo (hoặc chọn thời điểm không demo), enqueue các document, chờ job terminal, kiểm tra corpus QA trước khi quay lại demo.

### 7.6.4. Parser version và Document IR schema

- Parser version pin exact tại install (Docling 2.x line pin exact; MinerU 3.4.x). Ghi `source_parser` và `parser_version` vào từng `DocumentElement` và payload Qdrant (NFR-09).
- Document IR schema version: `document-ir-v1` (doc 04 mục 4.2). Khi đổi parser version, chỉ cần adapter mới sang Canonical Document IR; không viết lại Legal Structure Extractor (NFR-06).
- Idempotency key cấp tài liệu chứa parser version và IR schema version; cùng file + cùng pipeline version không chạy lại mặc định (doc 03 mục 3.13.4).

---

## 7.7. Provider health (external dependencies)

### 7.7.1. Danh sách provider bên ngoài

| Provider | Mục đích | Model pin | Ghi chú |
|---|---|---|---|
| Langfuse Cloud | Tracing, prompt, experiment | Server v4 / SDK v4.x | Ngoài đường tới hạn; `LANGFUSE_ENABLED=false` không fail query |
| Gemini API | Generator | `gemini-3.5-flash` | Có thể cần embedding `gemini-embedding-2` (ứng viên) |
| OpenAI API | Judge (hai vai) | `gpt-5.4-mini-2026-03-17` | Online L5 semantic judge (fail-closed, doc 03 ADR-008) + metric thứ cấp trong evaluation |
| Jina API | Embedding E2/E3, reranker | `jina-embeddings-v5-text-nano`, `jina-embeddings-v5-text-small`, `jina-reranker-v3` | Embedding quyết định sau Suite B |

### 7.7.2. Endpoint provider health (admin-only)

```http
GET /api/v1/admin/health/providers
Authorization: Bearer <token>
```

Response khởi điểm (doc 03 mục 3.28.7):

```json
{
  "generator": {"configured": true, "checked": "not_checked"},
  "embedding": {"configured": true, "checked": "not_checked"},
  "reranker": {"configured": true, "checked": "not_checked"},
  "langfuse": {"configured": true, "enabled": true}
}
```

Provider check KHÔNG nằm trong public readiness (`/api/v1/health/ready`) vì:

- gọi provider tốn quota;
- làm health check phụ thuộc Internet, có thể false failure khi mạng phòng thi có vấn đề;
- chỉ cần kiểm tra thủ công trước demo.

Public readiness chỉ kiểm tra local infra (PostgreSQL, Qdrant, Redis, MinIO, migration, config, corpus).

### 7.7.3. Không tự động failover

- Không có automatic provider failover (doc 04 mục 4.10.5). Final evaluation pin một generator duy nhất; đổi provider âm thầm làm thay đổi kết quả ngoài kiểm soát (NFR-03, doc 02).
- Mọi degradation phải được cấu hình tường minh, được trace, và được hiển thị trong evaluation report.

### 7.7.4. Xử lý provider failure

- **Generator unavailable**: public query trả structured error kèm `trace_id`; UI đề xuất chuyển sang search source. Không trả draft chưa verified (NFR-01).

```json
{
  "error": {
    "code": "GENERATION_PROVIDER_UNAVAILABLE",
    "message": "Không thể tạo câu trả lời tại thời điểm này. Chức năng tìm kiếm nguồn vẫn khả dụng."
  },
  "trace_id": "..."
}
```

- **Embedding unavailable**: query embedding không cache được thì dense retrieval unavailable; có thể dùng sparse-only nếu config cho phép; response trace ghi retrieval mode thực tế; final evaluation không cho automatic mode degradation.
- **Online L5 judge unavailable** (vai trò online trong verifier L5, doc 03 mục 3.24.2, ADR-008): claim kết luận được bằng deterministic rule vẫn chạy bình thường; claim ngữ nghĩa không kết luận được bằng deterministic bị xử lý fail-closed (coi như unsupported): workflow chuyển sang repair có giới hạn (`MAX_REPAIR_ATTEMPTS`) hoặc ABSTAIN; không bao giờ trả claim chưa verified.
- **Evaluation judge unavailable** (vai trò metric thứ cấp trong evaluation): deterministic metrics vẫn được tính và lưu; metric phụ thuộc judge bị đánh dấu `ABSENT_<lý do>` trong `metric_availability`; run tuân theo terminal-status policy `RUNNING -> COMPLETED/FAILED` một chiều, KHÔNG có trạng thái PARTIAL (doc 06 mục 6.8.5).
- **Langfuse unavailable**: bỏ qua span hiện tại, pipeline tiếp tục, query trả kết quả bình thường (doc 03 mục 3.27.6); prompt được nạp từ fallback cục bộ với `prompt_source = CACHE` hoặc `RELEASE_FALLBACK` (mục 7.3.6).

---

## 7.8. Migration và khởi tạo (migrations + bootstrap)

### 7.8.1. Migration policy (Alembic)

- Một PR đổi schema phải kèm Alembic migration (NFR-06).
- Không sửa migration đã release; thêm migration mới.
- Destructive migration (xóa bảng/cột, thay đổi ràng buộc temporal) phải có backup trước khi chạy.
- Release candidate lưu revision:

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend alembic current
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend alembic heads
```

- Database revision được ghi vào release manifest.
- Migration chỉ chạy một lần bởi one-shot service `migrate` (mục 7.2.2); backend, worker và frontend không bao giờ tự chạy `alembic upgrade head` và chờ `migrate` hoàn thành qua `depends_on: service_completed_successfully`. Không có auto-migration từ application process.

### 7.8.2. Startup sequence

```text
postgres + qdrant + redis + minio healthy
    ↓
migrate (one-shot, service_completed_successfully):
    alembic upgrade head
    ensure_qdrant_collection (tạo legal_provisions_v1 + payload indexes + alias)
    ensure_buckets
    ↓
backend start   (depends_on migrate completed)
    ↓
worker start    (depends_on migrate completed)
    ↓
frontend start  (depends_on backend healthy + migrate completed)
```

`ensure_qdrant_collection` tạo nếu chưa tồn tại:

```text
legal_provisions_v1
    dense: 768 cosine (dimension theo embedding production sau Suite B)
    sparse: bm25
    payload indexes:
      document_id
      document_number
      document_type
      article
      clause
      point
      vehicle_types
      effective_from
      effective_to
      review_status
      content_hash
    alias: legal_provisions_active -> legal_provisions_v1
```

Nếu embedding production là Jina v5 text-small (1024 dims), tạo collection 1024 dims và alias switch theo quy trình rebuild (mục 7.9, ADR-013).

### 7.8.3. Bootstrap script

```bash
#!/usr/bin/env bash
set -euo pipefail

COMPOSE="docker compose --project-directory . -f deploy/compose/compose.release.yml"

echo "[1/3] Starting full stack (infra + one-shot migrate + app)"
$COMPOSE up -d

echo "[2/3] Waiting for readiness"
$COMPOSE wait backend frontend
curl --fail http://localhost:8000/api/v1/health/ready

echo "[3/3] Status"
$COMPOSE ps
```

`migrate` chạy tự động một lần khi `up -d` (đã khai trong compose, mục 7.2.2); toàn bộ lệnh trong script chạy từ repo root. Nếu chỉ muốn chạy migrate thủ công (không kéo app lên), dùng `docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm migrate`.

### 7.8.4. Migration command

Trong vận hành bình thường, migration chạy qua one-shot service `migrate` (mục 7.2.2, 7.8.2). Lệnh thủ công dưới đây chỉ dùng để kiểm tra hoặc chạy lại khi cần:

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend alembic upgrade head
```

### 7.8.5. Migration test từ DB rỗng

- CI integration job chạy `alembic upgrade head` trên PostgreSQL mới (mục 7.11).
- Release checklist yêu cầu migration pass từ database rỗng (Gate F, mục 7.12.3).

---

## 7.9. Qdrant rebuild

### 7.9.1. Nguyên tắc

Qdrant là index dẫn xuất; PostgreSQL là source of truth. Khi dữ liệu lệch, PostgreSQL thắng (doc 03 mục 3.11). Mọi thay đổi schema (embedding model, vector dimension, sparse encoding, payload schema, chunking production) được thực hiện bằng rebuild + alias switch, không bao giờ rebuild in place.

### 7.9.2. Quy trình rebuild

1. Tạo collection mới `legal_provisions_v{n+1}` với named dense vector và sparse vector đúng cấu hình mới.
2. Đọc toàn bộ provision ACCEPTED từ PostgreSQL: `SELECT ... FROM legal_provisions WHERE review_status = 'ACCEPTED'` (mỗi row là một provision version; không đọc ngược từ Qdrant, không đọc từ `provision_versions`).
3. Embed + upsert dense + sparse + payload vào collection mới.
4. Chạy regression retrieval (dev set) trước khi switch.
5. Switch alias `legal_provisions_active` sang collection mới.
6. Giữ collection cũ một thời gian, xóa theo chính sách.

Không trộn vector từ hai embedding space trong cùng collection.

```bash
# Rebuild
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
  python scripts/rebuild_index.py \
    --source postgres \
    --target legal_provisions_v2 \
    --embedding-model gemini-embedding-2 \
    --dimensions 768

# Sau regression pass
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
  python scripts/switch_collection_alias.py \
    --alias legal_provisions_active \
    --target legal_provisions_v2
```

### 7.9.3. Snapshot trước alias switch

- Trước mỗi release/rebuild: resolve alias `legal_provisions_active` về collection thực (`legal_provisions_v{n}`), snapshot collection đó (snapshots API), copy snapshot sang nơi lưu trữ độc lập. "Nơi lưu trữ độc lập" là ổ đĩa/host/tài khoản object storage KHÁC với volume `qdrant_snapshots` và KHÁC deployment MinIO production. Nếu dùng bucket backup trên MinIO thì bucket đó phải nằm trong một deployment MinIO RIÊNG (endpoint/tài khoản khác) và được đưa vào backup/restore scope (mục 7.10).
- Restore: tải snapshot về, tạo collection từ snapshot; kiểm chứng bằng cách so sánh số point và payload với PostgreSQL (`SELECT count(*) FROM legal_provisions WHERE review_status='ACCEPTED'`); nếu snapshot lỗi/thiếu, dựng lại hoàn toàn từ PostgreSQL.
- Retention: giữ snapshot của collection active và một phiên bản liền trước; snapshot không phải nguồn chân lý.

---

## 7.10. Backup và restore

### 7.10.1. Backup scope

Bắt buộc backup (NFR-03):

```text
1. PostgreSQL dump        pg_dump --format=custom
2. Qdrant snapshot        snapshot collection active + copy sang nơi độc lập
3. MinIO artifacts        mc mirror sang nơi lưu trữ độc lập
4. Source PDF + manifest  từ MinIO bucket source-pdfs + data/manifests
5. Gold set               gold set version + hash (data/gold-sets)
6. Evaluation results     data/evaluation
7. Release config         deploy/env/*.env.example, release-manifest.json
8. Git tag                v1.0.0-rc2 (tag trên working tree sạch)
9. Checksums              SHA256SUMS
```

### 7.10.2. PostgreSQL backup

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml exec -T postgres \
  pg_dump \
    --username "$POSTGRES_USER" \
    --dbname "$POSTGRES_DB" \
    --format=custom \
  > "backups/postgres_${TIMESTAMP}.dump"
```

### 7.10.3. Qdrant snapshot

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
  python scripts/create_qdrant_snapshot.py \
    --collection legal_provisions_active \
    --output /app/backups
```

Nếu alias không snapshot trực tiếp được, resolve target collection trước. Copy snapshot sang nơi lưu trữ độc lập theo định nghĩa tại mục 7.9.3 (không để snapshot chỉ nằm trong volume `qdrant_snapshots` hoặc bucket thuộc deployment MinIO production).

### 7.10.4. MinIO artifact backup

```bash
# mc mirror toàn bộ bucket sang thư mục độc lập (xem mục 7.5.5)
for b in source-pdfs parser-outputs page-images \
         ingestion-artifacts review-artifacts evaluation-artifacts; do
  mc mirror --overwrite --remove "local/$b" "/backups/minio/$(date +%Y%m%d)/$b"
done
```

### 7.10.5. Checksums

```bash
# Liệt kê mọi file thường (không đi vào thư mục), thứ tự deterministic, loại trừ chính SHA256SUMS
find backups -type f ! -name SHA256SUMS | sort | xargs sha256sum > backups/SHA256SUMS

# Kiểm chứng checksum trước khi restore
cd backups && sha256sum -c SHA256SUMS && cd -
```

### 7.10.6. Release backup bundle

```text
vnlaw-release-2026-09-12/
├── postgres.dump
├── qdrant.snapshot
├── minio-mirror/          # mc mirror của toàn bộ bucket
├── artifacts.tar.gz       # pdfs, manifests, gold-sets, evaluation
├── SHA256SUMS
├── release-manifest.json
├── docker-compose.yml
├── .env.example
└── README-RESTORE.md
```

### 7.10.7. Restore

```bash
# PostgreSQL
docker compose --project-directory . -f deploy/compose/compose.release.yml up -d postgres
docker compose --project-directory . -f deploy/compose/compose.release.yml wait postgres
cat backups/postgres.dump | \
  docker compose --project-directory . -f deploy/compose/compose.release.yml exec -T postgres \
    pg_restore \
      --username "$POSTGRES_USER" \
      --dbname "$POSTGRES_DB" \
      --clean \
      --if-exists

# Qdrant: restore snapshot hoặc rebuild từ PostgreSQL
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
  python scripts/restore_qdrant_snapshot.py \
    --snapshot /app/backups/<snapshot-file>

# hoặc rebuild thay cho restore (cần embedding API/cache)
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
  python scripts/rebuild_index.py \
    --source postgres \
    --target legal_provisions_restore

# MinIO mirror restore (đích trỏ về từng bucket của alias local)
for b in source-pdfs parser-outputs page-images \
         ingestion-artifacts review-artifacts evaluation-artifacts; do
  mc mirror --overwrite --remove "/backups/minio/20260912/$b" "local/$b"
done
```

Vì PostgreSQL là source of truth, Qdrant luôn có thể rebuild; release backup vẫn giữ snapshot + embedding cache (nếu có) để rút ngắn RTO.

### 7.10.8. Restore verification (`verify_release.py`)

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend python scripts/verify_release.py
```

Kiểm tra:

- document count, provision count, accepted count;
- corpus hash khớp manifest;
- Qdrant collection point count khớp `SELECT count(*) FROM legal_provisions WHERE review_status='ACCEPTED'`;
- sample retrieval trả kết quả kỳ vọng;
- migration revision khớp release manifest.

### 7.10.9. Recovery objectives

```text
RPO: lần backup release gần nhất (không có SLA enterprise)
RTO: dưới 60 phút cho local restore đã rehearsal
```

### 7.10.10. Clean-room restore test

Quy trình kiểm tra restore từ đầu (mục 7.16):

```text
máy trống -> cài Docker -> clone repo tại release tag -> .env từ template
  -> up infra + one-shot migrate -> restore bundle -> up app
  -> verify_release -> health checks -> demo script
```

---

## 7.11. CI/CD (GitHub Actions)

### 7.11.1. PR workflow

Mỗi push/PR chạy (doc 06 mục 6.10.5):

```text
backend-quality        ruff, mypy, unit tests (coverage core >= 80%)
backend-integration    postgres + qdrant + redis + minio; alembic upgrade head; pytest tests/integration
frontend               lint, typecheck, build
docker-build           docker compose --project-directory . -f deploy/compose/compose.release.yml build
```

```yaml
name: CI

on:
  pull_request:
  push:
    branches: [main]

jobs:
  backend-quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
          enable-cache: true
      - run: uv sync --frozen --all-extras
      - run: uv run ruff check .
      - run: uv run mypy app
      - run: uv run pytest tests/unit -q --cov --cov-fail-under=80

  backend-integration:
    runs-on: ubuntu-latest
    env:
      DATABASE_URL: postgresql+psycopg://vnlaw:test@localhost:5432/vnlaw_test
      QDRANT_URL: http://localhost:6333
      REDIS_URL: redis://localhost:6379/0
      MINIO_ENDPOINT: localhost:9000
    services:
      postgres:
        image: postgres:18.4
        env:
          POSTGRES_DB: vnlaw_test
          POSTGRES_USER: vnlaw
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U vnlaw -d vnlaw_test"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
      qdrant:
        image: qdrant/qdrant:v1.19.0
        ports:
          - 6333:6333
      redis:
        image: redis:8.10.0
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 10
      minio:
        image: minio/minio:RELEASE.2025-05-20T20-30-00Z
        env:
          MINIO_ROOT_USER: minioadmin
          MINIO_ROOT_PASSWORD: minioadmin
        ports:
          - 9000:9000
        command: server /data
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.11"
      - run: uv sync --frozen --all-extras
        working-directory: backend
      - run: uv run alembic upgrade head
        working-directory: backend
      - run: uv run pytest tests/integration -q
        working-directory: backend

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run build

  docker-build:
    runs-on: ubuntu-latest
    needs: [backend-quality, backend-integration, frontend]
    steps:
      - uses: actions/checkout@v4
      - run: docker compose --project-directory . -f deploy/compose/compose.release.yml build
```

Lưu ý: service container image trong CI cũng phải pin tag đã test (postgres 18, qdrant v1.19.0, redis 8, minio date-tagged); action pin bằng commit SHA hoặc trusted major version (doc 04 mục 4.18.5).

### 7.11.2. PR ảnh hưởng retrieval

PR thay đổi retrieval logic, temporal filter, verifier hoặc ingestion phải chạy thêm regression (doc 06 mục 6.10):

```text
retrieval regression subset
temporal regression
citation regression invariant (Returned Invalid Citation Rate = 0)
gold-set integrity
```

### 7.11.3. Manual workflow: Full Evaluation

Full LLM evaluation KHÔNG chạy trên mỗi PR (chi phí, latency, nondeterminism, provider quota; doc 06 mục 6.10.6). Chạy qua workflow_dispatch trên self-hosted runner:

```yaml
name: Full Evaluation

on:
  workflow_dispatch:
    inputs:
      suite:
        required: true
        type: choice
        options: [A, B, C, D]
      variant:
        required: true
        type: string
        description: "Ví dụ P1, E1, R6, G7"
      gold_set_version:
        required: true
        type: string
      corpus_version:
        required: true
        type: string

jobs:
  evaluate:
    runs-on: self-hosted
    environment: evaluation
    steps:
      - uses: actions/checkout@v4

      - name: Verify frozen data
        run: ./deploy/scripts/verify-release.sh

      - name: Run evaluation
        run: |
          docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
            python scripts/run_evaluation.py \
              --suite "${{ inputs.suite }}" \
              --variant "${{ inputs.variant }}" \
              --gold-set-version "${{ inputs.gold_set_version }}" \
              --corpus-version "${{ inputs.corpus_version }}"

      - name: Upload result
        uses: actions/upload-artifact@v4
        with:
          name: evaluation-${{ inputs.suite }}-${{ inputs.variant }}
          path: data/evaluation/
```

Ưu tiên chạy full evaluation local hoặc self-hosted để dùng corpus private, kiểm soát cost, tránh runner timeout và giữ artifact lớn. Không đưa provider key vào PR từ fork; provider key chỉ tồn tại trong GitHub secrets của self-hosted environment.

### 7.11.4. Policy tóm tắt

- CI chạy deterministic subset: regression subset, unit, integration với mock provider.
- Full LLM evaluation chỉ chạy manual tại feature freeze / release candidate (doc 06 mục 6.10.6).
- Action pin bằng SHA hoặc trusted major.
- Retrieval PR phải thêm regression (mục 7.11.2).

---

## 7.12. Release quản lý (release manifest + process)

### 7.12.1. Release versioning

Theo doc 05 mục 5.15.4 và 5.16.3:

```text
1.0.0-rc1  Code freeze (10/09/2026)
1.0.0-rc2  Release candidate chốt (12/09/2026); rehearsal (13/09) và bảo vệ (14/09) dùng đúng tag này
1.0.0      Tag sau bảo vệ (14/09), không kèm thay đổi code
```

- Release candidate chỉ được tag trên working tree sạch (không file uncommitted), có dependency lock, docker image digest, migration version, corpus hash, gold-set hash.
- Không build release từ working tree chưa commit; mọi artifact release xuất phát từ git tag đã xác minh.
- Rehearsal (13/09) và bảo vệ (14/09) dùng đúng tag `v1.0.0-rc2`; `v1.0.0` tạo sau bảo vệ không kèm thay đổi code.

```bash
git tag -a v1.0.0-rc2 -m "VN Traffic Law RAG release candidate 2"
git push origin v1.0.0-rc2
```

### 7.12.2. Release manifest (`release-manifest.json`)

```json
{
  "release": "v1.0.0-rc2",
  "git_commit": "…",
  "created_at": "2026-09-12T10:00:00+07:00",
  "python_version": "3.11.x",
  "node_version": "20.x",
  "uv_lock_hash": "…",
  "package_lock_hash": "…",
  "alembic_revision": "…",
  "postgres_image": "postgres:18.4@sha256:…",
  "qdrant_image": "qdrant/qdrant:v1.19.0@sha256:…",
  "redis_image": "redis:8.10.0@sha256:…",
  "minio_image": "minio/minio:RELEASE.…@sha256:…",
  "backend_image": "vnlaw-backend:v1.0.0-rc2@sha256:…",
  "frontend_image": "vnlaw-frontend:v1.0.0-rc2@sha256:…",
  "corpus_version": "corpus-v1",
  "corpus_hash": "…",
  "gold_set_version": "gold-v1",
  "gold_set_hash": "…",
  "qdrant_collection": "legal_provisions_v1",
  "embedding_model": "gemini-embedding-2",
  "embedding_dimensions": 768,
  "reranker_model": "jina-reranker-v3",
  "generator_model": "gemini-3.5-flash",
  "judge_model": "gpt-5.4-mini-2026-03-17",
  "prompt_versions": {
    "legal-query-analyzer-v1": "…",
    "legal-query-rewriter-v1": "…",
    "legal-hyde-generator-v1": "…",
    "legal-generator-v1": "…",
    "legal-claim-support-judge-v1": "…",
    "legal-citation-renderer-v1": "…"
  },
  "prompt_source": "LANGFUSE",
  "prompt_fallback_dir": "deploy/prompts/fallback",
  "fallback_prompt_versions": {
    "query-analyzer": "…",
    "query-rewriter": "…",
    "hyde": "…",
    "generator": "…",
    "claim-verifier": "…"
  },
  "minio_buckets": [
    "source-pdfs",
    "parser-outputs",
    "page-images",
    "ingestion-artifacts",
    "review-artifacts",
    "evaluation-artifacts"
  ]
}
```

Model ID và prompt version phải khớp với cấu hình final evaluation (NFR-08, doc 06 mục 6.6.4). Embedding production quyết định sau Suite B; nếu chọn Jina v5 text-small (1024 dims), `embedding_dimensions` và collection dimension phải ghi tương ứng. `minio_image` ghi image của implementation hiện tại của `ObjectStoragePort` (mục 7.5); nếu object-storage ADR chốt implementation khác, trường này được đổi hoặc ghi chú tương ứng.

### 7.12.3. Release checklist (Gate F, doc 06 mục 6.12.6)

- [ ] CI pass (backend-quality, backend-integration, frontend, docker-build).
- [ ] Migration pass từ database rỗng.
- [ ] Restore test pass (bundle -> restore -> verify_release).
- [ ] Qdrant reconciliation pass (point count khớp PostgreSQL ACCEPTED).
- [ ] Corpus hash pass.
- [ ] Gold-set hash pass.
- [ ] Bốn lớp query E2E pass: current, historical, comparison, abstention.
- [ ] Invalid citation leak bằng 0 trong contract test (Returned Invalid Citation Rate = 0).
- [ ] Docker image build pass.
- [ ] Clean clone test pass (mục 7.16).
- [ ] Final evaluation report tồn tại; report number khớp artifact JSON (không sao chép thủ công).
- [ ] Backup bundle tồn tại (postgres dump, qdrant snapshot, minio mirror, SHA256SUMS).
- [ ] Demo video tồn tại và mở được.
- [ ] Rehearsal 13/09 pass trên đúng tag `v1.0.0-rc2`.

---

## 7.13. Health checks và monitoring

### 7.13.1. Liveness

```http
GET /api/v1/health/live
```

Chỉ kiểm tra process backend còn chạy. Response: `{"status": "alive"}`. Không bắt buộc `trace_id` (endpoint probe vận hành, doc 03 mục 3.28).

### 7.13.2. Readiness

```http
GET /api/v1/health/ready
```

Kiểm tra local infra:

```text
PostgreSQL connect
Alembic revision đúng (khớp release manifest)
Qdrant connect
Active collection tồn tại (legal_provisions_active)
Required config có
Corpus có ít nhất một accepted document nếu REQUIRE_CORPUS=true
Redis connect
MinIO connect (head bucket)
```

Response khởi điểm:

```json
{
  "status": "ok",
  "services": {
    "postgres": "ok",
    "qdrant": "ok",
    "redis": "ok",
    "minio": "ok"
  },
  "version": "v1.0.0-rc2"
}
```

`version` trả về giá trị `APP_VERSION` cấu hình nguyên vẹn (ví dụ `v1.0.0-rc2`), không bỏ tiền tố `v`.

Readiness KHÔNG gọi provider bên ngoài (mục 7.7.2).

### 7.13.3. Provider health

Admin-only `GET /api/v1/admin/health/providers` (mục 7.7.2); chạy thủ công trước demo.

### 7.13.4. Queue health và MinIO health

- Queue health: Redis connectivity, queue depth (`LLEN`), dead-letter count, worker liveness `dramatiq --check` (mục 7.4.3).
- MinIO health: healthcheck container + head bucket trong readiness (mục 7.5.4).

### 7.13.5. Logging

- JSON structured logs, stdout: `timestamp`, `level`, `service`, `trace_id`, `intent`, `response_status`, latencies (`retrieval_ms`, `generation_ms`, `verification_ms`, `total_ms`), `generator_model`, `prompt_source` (`LANGFUSE | CACHE | RELEASE_FALLBACK`), `prompt_version`, `prompt_hash` (mục 7.3.6).

```json
{
  "timestamp": "2026-09-01T10:00:00+07:00",
  "level": "INFO",
  "service": "backend",
  "event": "query_completed",
  "trace_id": "tr_...",
  "intent": "HISTORICAL",
  "response_status": "VERIFIED",
  "retrieval_ms": 180,
  "generation_ms": 3200,
  "verification_ms": 45,
  "total_ms": 3520,
  "generator_model": "gemini-3.5-flash"
}
```

- Redaction (không log): API key, admin token, PostgreSQL password, full authorization header, complete provider response khi có sensitive metadata, full uploaded PDF.
- File rotation nếu ghi file: max 10 MB/file, giữ 5 file.
- Không cần ELK, Prometheus hoặc Grafana trong P0; Langfuse đảm nhiệm tracing (ADR-009). Log stdout đủ cho vận hành local.

---

## 7.14. Bảo mật (security hardening)

### 7.14.1. Container

Các biện pháp sau được enforce trong compose/app cho service ứng dụng (backend, worker, frontend); Dockerfile backend/frontend chạy non-root (`USER appuser` / `USER nextjs`):

```yaml
# Áp dụng cho backend, worker và frontend
    read_only: true
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    tmpfs:
      - /tmp
```

- `read_only: true`: root filesystem read-only; mọi đường ghi cần thiết phải nằm trong volume hoặc `tmpfs` đã mount (ví dụ `tmpfs: /tmp`, cache mount cho uv/npm).
- `cap_drop: [ALL]`: drop mọi Linux capability; `security_opt: no-new-privileges` chặn setuid.
- Các image vendor stateful (postgres, qdrant, redis, minio) là ngoại lệ có lý do: chúng ghi vào volume riêng của mình và một số chạy root theo mặc định của image. Với các image này vẫn bắt buộc: pin image + digest, không mount Docker socket, không privileged, và áp dụng `cap_drop` khi image hỗ trợ; ngoại lệ được ghi chú trong tài liệu vận hành.
- no Docker socket mount; no privileged mode.
- pinned images (tag + digest, mục 7.2.1).
- vulnerability scan trước release (ví dụ docker scout / trivy trên image build).

### 7.14.2. Backend

```text
request-body limit
upload MIME + magic byte validation
generated internal filename (chặn path traversal)
admin auth Bearer token + constant-time compare (secrets.compare_digest)
rate limiting (config, không hardcode)
Pydantic extra="forbid"
parameterized SQL (SQLAlchemy, không nối chuỗi)
prompt injection defense (PDF/content xử lý là dữ liệu, tách khỏi system instructions,
                          structured output schema giới hạn output)
provider timeouts
```

Các endpoint quản trị dùng đường dẫn canonical của doc 03 (mục 3.28), xác thực bằng Bearer token trên chính endpoint, không dùng tiền tố `/admin`:

```text
POST /api/v1/documents                     (upload document, admin)
GET  /api/v1/jobs/{job_id}                 (job status)
GET  /api/v1/reviews?status=PENDING        (danh sách review, admin)
POST /api/v1/reviews/{review_id}/decision  (quyết định review, admin)
POST /api/v1/evaluations                   (chạy evaluation, admin)
GET  /api/v1/evaluations/{run_id}          (trạng thái evaluation, admin)
GET  /api/v1/corpus-qa/report              (corpus QA report, admin)
GET  /api/v1/admin/health/providers        (provider health, admin; endpoint `/admin` duy nhất theo doc 03 mục 3.28.7)
```

Mô hình vai trò (doc 02 mục 2.3, doc 06 mục 6.2.3): `User` (hỏi đáp, search, feedback), `Reviewer` (upload tài liệu, accept/reject ingestion, xem corpus QA), `Developer` (chạy evaluation, thay model/config, quản lý prompt version). Trong phạm vi khóa luận, `ADMIN_TOKEN` (Bearer, constant-time compare) là cơ chế xác thực duy nhất triển khai quyền admin/reviewer/developer; tách token riêng theo vai và RBAC hoàn chỉnh là future work ngoài phạm vi.

Constant-time compare:

```python
import secrets

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


bearer = HTTPBearer(auto_error=False)


def verify_admin_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer),
) -> None:
    expected = settings.admin_token.get_secret_value()

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing administrator token",
        )

    if not secrets.compare_digest(credentials.credentials, expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid administrator token",
        )
```

Bearer token là P0 phù hợp local/demo; không tuyên bố đây là authentication production hoàn chỉnh (OAuth/OIDC, RBAC, token rotation là future work ngoài phạm vi).

### 7.14.3. Hạ tầng

```text
private Docker network (vnlaw-network); không expose postgres/qdrant/redis/minio/admin ra public
strong password cho POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD
MinIO access key không public; console chỉ dev override
Qdrant API key nếu public/staging (QDRANT_API_KEY)
secret không nằm trong image, không nằm trong Next.js public env
HTTPS bắt buộc khi public deployment (staging future)
.env permission 600
rotate secret trước defense nếu từng chia sẻ
```

Không bao giờ expose postgres, qdrant, redis, minio hoặc admin endpoint ra public. Khi có staging public (optional, ngoài phạm vi defense), dùng reverse proxy TLS (Nginx hoặc Caddy), `client_max_body_size 50m`, chỉ proxy tới frontend/backend, và chặn tường minh mọi đường tới endpoint quản trị tại proxy:

```nginx
# Chặn endpoint quản trị tại proxy public (documents/reviews/evaluations/corpus-qa và /admin)
location ~ ^/api/v1/(documents|reviews|evaluations|corpus-qa) {
    return 404;
}

location /api/v1/admin/ {
    return 404;
}
```

Endpoint quản trị chỉ được truy cập qua localhost (SSH tunnel/VPN) hoặc listener riêng trên host; không đi qua proxy public.

---

## 7.15. Demo profiles (defense)

### 7.15.1. Defense environment

- Defense chạy local Docker Compose trên đúng tag `v1.0.0-rc2`, không phụ thuộc VPS (NFR-03).
- Data load: restore release bundle (mục 7.10) hoặc fresh corpus từ corpus artifacts.
- Trước demo: provider check thủ công (mục 7.7.2), health checks, và năm câu demo đã chạy rehearsal.

### 7.15.2. Demo profiles

```text
Full online
    retrieval + generator + verifier
    cần provider khả dụng (Gemini, Jina, OpenAI, Langfuse)

Provider-degraded
    search API (FR-21)
    source viewer / passage viewer
    precomputed evaluation results
    retrieval-only demonstration
    không gọi generator

Offline backup
    video demo
    screenshots
    raw evaluation artifacts
    architecture explanation
```

Không tạo fake live answer khi provider down. Provider failure phải trả structured error + `trace_id` và UI route sang search (mục 7.7.4). Draft chưa verify không bao giờ hiển thị (NFR-01, FR-32).

### 7.15.3. Pre-demo checklist

- [ ] Máy có ít nhất 8 GB RAM trống.
- [ ] Docker daemon chạy.
- [ ] Port 3000, 8000 không bị chiếm.
- [ ] `.env` tồn tại, secret đúng.
- [ ] Provider key hợp lệ (admin provider health).
- [ ] PostgreSQL dump và Qdrant snapshot tồn tại.
- [ ] Release manifest hash pass.
- [ ] Năm câu demo đã chạy rehearsal.
- [ ] Video backup mở được.

### 7.15.4. Resource plan (định hướng)

| Service | RAM định hướng |
|---|---:|
| PostgreSQL | 256-512 MB |
| Qdrant | 512 MB-2 GB tùy corpus |
| Redis | 64-256 MB (nhỏ) |
| MinIO | 256-512 MB |
| FastAPI (backend) | 300-800 MB |
| Worker | idle thấp; spike khi ingestion |
| Next.js (frontend) | 150-400 MB |
| Docker overhead | 500 MB-1 GB |
| Tổng online stack | Khoảng 2-5 GB |

Máy bảo vệ cần >= 8 GB RAM trống. Ingestion (Docling/MinerU) không chạy đồng thời với demo hoặc evaluation nặng (doc 03 mục 3.2.5). Optional resource limits (mem_limit) chỉ bật sau khi đo `docker stats` thực tế.

---

## 7.16. Clean-room deployment

Quy trình triển khai từ máy trống tới demo, có kiểm chứng từng bước. Đây là test bắt buộc trước release (Gate F, doc 06 mục 6.12.6: Docker clean start).

### 7.16.1. Quy trình

```text
1. Máy trống (không có dữ liệu VNLRAG) với Docker + Compose
2. git clone <repository>
3. git checkout v1.0.0-rc2
4. cp deploy/env/release.env.example .env  ->  điền secret
5. docker compose --project-directory . -f deploy/compose/compose.release.yml build --pull
6. docker compose --project-directory . -f deploy/compose/compose.release.yml up -d postgres qdrant redis minio
7. docker compose --project-directory . -f deploy/compose/compose.release.yml wait postgres qdrant redis minio
8. docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm migrate
   (chạy một lần: alembic upgrade head + ensure_qdrant_collection + ensure_buckets)
9. Restore release bundle (deploy/scripts/restore.sh) HOẶC dùng fresh corpus
10. docker compose --project-directory . -f deploy/compose/compose.release.yml up -d backend worker frontend
11. Health checks + verify_release
12. Chạy demo script
```

### 7.16.2. Phương án A - restore release bundle

```bash
deploy/scripts/restore.sh backups/release-bundle
```

Restore postgres dump, qdrant snapshot (hoặc rebuild), minio mirror; sau đó `verify_release.py`.

### 7.16.3. Phương án B - fresh corpus từ artifacts

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend \
  python scripts/import_release_corpus.py \
    --manifest-dir /app/data/manifests \
    --artifact-dir /app/data/artifacts
```

### 7.16.4. Verification steps

```bash
curl --fail http://localhost:8000/api/v1/health/ready
curl --fail http://localhost:3000
docker compose --project-directory . -f deploy/compose/compose.release.yml ps
docker compose --project-directory . -f deploy/compose/compose.release.yml run --rm backend python scripts/verify_release.py
```

### 7.16.5. Deployment tests

```text
Test 1: Clean start      docker compose --project-directory . -f deploy/compose/compose.release.yml down -v
                         deploy/scripts/bootstrap.sh
                         Expected: migration pass (one-shot migrate), services healthy, empty corpus state rõ ràng
Test 2: Restore release  docker compose --project-directory . -f deploy/compose/compose.release.yml down -v
                         deploy/scripts/restore.sh; deploy/scripts/defense-start.sh
                         Expected: corpus count đúng, Qdrant point count đúng, sample query pass
Test 3: Restart          docker compose --project-directory . -f deploy/compose/compose.release.yml restart
                         Expected: data không mất, app ready, alias không đổi
Test 4: Qdrant rebuild   xóa Qdrant volume, giữ PostgreSQL
                         Expected: rebuild index, retrieval regression pass
Test 5: Provider failure mock 503 hoặc endpoint sai
                         Expected: structured error, không trả draft, search vẫn chạy
Test 6: Migration        DB version N -> N+1 (qua one-shot migrate)
                         Expected: data còn, readiness pass, rollback procedure được ghi
```

---

## 7.17. Definition of Done

Triển khai hoàn tất khi (suy ra từ Gate F, doc 06 mục 6.12.6 và doc 05 mục 5.17):

- [ ] Compose release chạy trên clean machine (clean-room pass).
- [ ] Mọi health check pass: PostgreSQL, Qdrant, Redis, MinIO, backend, frontend, worker.
- [ ] Alembic migration pass từ database rỗng; revision khớp manifest.
- [ ] Active Qdrant collection tồn tại; reconciliation với PostgreSQL ACCEPTED.
- [ ] Corpus restore pass; corpus hash và gold-set hash khớp.
- [ ] Bốn lớp query E2E pass: current, historical, comparison, abstention.
- [ ] Provider failure không leak draft; UI route sang search.
- [ ] Backup, restore và Qdrant rebuild pass (Test 1-6).
- [ ] Release manifest + image/corpus/gold-set hash được lưu.
- [ ] Demo video tồn tại và mở được.
- [ ] Defense rehearsal 13/09 pass trên đúng tag `v1.0.0-rc2`.
- [ ] Không còn dependency triển khai cũ (mục 7.18).

---

## 7.18. Mapping triển khai cũ sang mới

Bảng này chỉ ghi nhận lịch sử chuyển đổi từ v1 sang v2 (nhất quán với doc 04 mục 4.20, doc 03 mục 3.35 và doc 00 mục 5, 14). UDEF và các thành phần cũ không còn áp dụng.

| Thành phần triển khai | Cũ (v1) | Mới (v2) |
|---|---|---|
| Vector store | ChromaDB (volume `chroma_data`, single worker) | Qdrant v1.19.0 (dense + sparse + RRF) |
| Metadata DB | SQLite làm database chính | PostgreSQL 18 (source of truth) |
| Sparse retrieval | rank-bm25 pickle + PyVi | Qdrant sparse BM25 |
| Background jobs | Đồng bộ hoặc ad hoc | Redis + Dramatiq worker |
| Object storage | Mounted directory `data/` | MinIO (S3-compatible) |
| Web search fallback | DuckDuckGo / SerpAPI | Không có trong answer path |
| Ingestion | PDF -> UDEF -> Docling -> CDM | PDF -> Parser Router -> Docling/MinerU -> Canonical Document IR |
| Parser | Docling + UDEF adapter, commit pin | Parser Router + Legal Structure Extractor + Document IR schema version |

Những thành phần bị loại khỏi deployment (không còn trong compose, env, script hay manifest):

```text
chroma_data volume
sqlite_data volume
BM25 pickle index file
single worker do ChromaDB
pre-download multilingual-e5-small trong Docker image
UDEF commit pin
UDEF rulespec path (UDEF_RULESPEC_PATH)
DuckDuckGo hoặc SerpAPI config
query-time HITL endpoint
automatic Gemini -> OpenAI failover
OpenAI usage JSON file
Oracle VPS là production bắt buộc
```

Các thay thế:

```text
postgres_data volume
qdrant_data volume + qdrant_snapshots
Qdrant sparse BM25
uv lock (pin dependency)
Redis + Dramatiq actor pipeline
MinIO buckets (6 bucket theo loại artifact)
explicit provider configuration
local defense release (Docker Compose, không VPS)
PostgreSQL usage tracking (thay file JSON)
```

---

## 7.19. Kết luận

Phương án triển khai v2 ưu tiên tính tái lập, khả năng phục hồi và độ ổn định trong buổi bảo vệ.

Kiến trúc triển khai chốt:

```text
frontend (Next.js)  +  backend (FastAPI)  +  worker (Dramatiq)
PostgreSQL 18       +  Qdrant v1.19.0     +  Redis 8        +  MinIO
External: Langfuse Cloud, Gemini API, OpenAI API, Jina API
RAGFlow: môi trường benchmark riêng
```

PostgreSQL là nguồn dữ liệu nghiệp vụ chính. Qdrant là retrieval index dẫn xuất, dựng lại được từ PostgreSQL bằng alias switch. MinIO lưu PDF nguồn, parser output và artifact; backup bằng replication hoặc `mc mirror` sang nơi độc lập. Release candidate `v1.0.0-rc2` tag 12/09/2026 từ working tree sạch; rehearsal 13/09 và bảo vệ 14/09 dùng đúng tag đó.

Hệ thống không phụ thuộc VPS, không có web fallback, không tự động failover provider, và không còn bất kỳ dependency triển khai nào của ChromaDB, SQLite-as-primary, BM25 pickle, DuckDuckGo, SerpAPI hoặc UDEF.
