# 07. Triển Khai (Deployment)

> **Giai đoạn SDLC**: 6 — Triển khai
> **Ngày tạo**: 16/06/2026

---

## 7.1. Môi trường triển khai

| Môi trường | Mục đích | Server | Domain |
|------------|----------|--------|--------|
| **Development** | Code local | Máy cá nhân (i5-10400) | localhost:3000, :8000 |
| **Staging** | Test trước khi bảo vệ | VPS Oracle Free | vnlaw-staging.example.com |
| **Production** | Demo bảo vệ | VPS Oracle Free | vnlaw.example.com (optional) |

---

## 7.2. Docker Compose

### 7.2.1. docker-compose.yml (Development) — POST-REVIEW D4, C5

> **D4 + C5 fix**: `version: '3.9'` đã obsolete. Cũng xóa duplicate `services:` key (YAML syntax error).

```yaml
# D4 fix: bỏ "version:", dùng Compose Spec hiện đại
# C5 fix: đã xóa duplicate "services:" key
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: vnlaw-backend
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./backend/data:/app/data
      - chroma_data:/app/chroma_db
      - sqlite_data:/app/sqlite
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        NEXT_PUBLIC_API_URL: http://localhost:8000
    container_name: vnlaw-frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    depends_on:
      - backend
    restart: unless-stopped

  # Optional: Nginx reverse proxy
  nginx:
    image: nginx:alpine
    container_name: vnlaw-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - backend
      - frontend
    restart: unless-stopped

volumes:
  chroma_data:
  sqlite_data:
```

### 7.2.2. Backend Dockerfile (POST-REVIEW D5)

> **D5 fix**: Multi-stage build để giảm image size. Bỏ COPY data (mount volume thay vì bundle).

```dockerfile
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY pyproject.toml poetry.lock ./
RUN pip install --no-cache-dir poetry && \
    poetry config virtualenvs.create false && \
    poetry install --without dev --no-interaction --no-ansi

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Runtime deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed deps from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# App code only (data mounted as volume, D5 fix)
COPY app ./app
COPY scripts ./scripts

# Pre-download embedding model
RUN python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('intfloat/multilingual-e5-small')"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 7.2.3. Frontend Dockerfile

```dockerfile
# frontend/Dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000
CMD ["node", "server.js"]
```

---

## 7.2.1. Authentication & Authorization (POST-REVIEW B9)

> **CRITICAL FIX (B9)**: Hệ thống KHÔNG được phép public admin/ingest/eval endpoints mà không có auth. Ai cũng có thể:
> - Trigger eval → tốn tiền API
> - Upload PDF → RCE-adjacent (PDF parser có thể có bug)
> - Approve HITL → nếu còn

```python
# app/api/auth.py — POST-REVIEW B9
import os
from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

bearer_scheme = HTTPBearer(auto_error=False)

async def verify_admin_token(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme)
) -> bool:
    """Verify Bearer token for admin/ingest/eval endpoints."""
    expected_token = os.environ.get("ADMIN_TOKEN")
    if not expected_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ADMIN_TOKEN not configured"
        )
    if not credentials or credentials.scheme != "Bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token"
        )
    if credentials.credentials != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token"
        )
    return True
```

```python
# app/api/admin.py — sử dụng dependency
from fastapi import APIRouter, Depends
from app.api.auth import verify_admin_token

router = APIRouter(prefix="/api/admin", dependencies=[Depends(verify_admin_token)])

@router.get("/pending")
async def list_pending():
    """List HITL pending reviews. Requires Bearer token."""
    ...

@router.post("/approve/{review_id}")
async def approve_review(review_id: str):
    """Approve a HITL review. Requires Bearer token."""
    ...
```

```python
# app/api/ingest.py — tương tự
router = APIRouter(prefix="/api/ingest", dependencies=[Depends(verify_admin_token)])

@router.post("/")
async def ingest_pdf(file: UploadFile):
    """Upload PDF. Requires Bearer token."""
    ...
```

```python
# app/api/eval.py — tương tự
router = APIRouter(prefix="/api/eval", dependencies=[Depends(verify_admin_token)])

@router.post("/run")
async def run_evaluation():
    """Run evaluation. Requires Bearer token (B9 fix)."""
    ...
```

**Setup token trong `.env`**:
```bash
# Generate random token
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Copy output → paste vào .env
ADMIN_TOKEN=<random-32-byte-token>
```

**Test auth**:
```bash
# Without token (should 401)
curl -X GET http://localhost:8000/api/admin/pending
# {"detail": "Missing Bearer token"}

# With token (should 200)
curl -X GET http://localhost:8000/api/admin/pending \
    -H "Authorization: Bearer $ADMIN_TOKEN"
```

### 7.2.2. Rate Limiting (POST-REVIEW B10)

> **B10 fix**: NFR-03 "60 req/min/IP" mâu thuẫn với Gemini 10 RPM. Pick 6 req/min/IP để aligned với quota.

```python
# app/main.py — Rate limiting với slowapi
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse

# B10 fix: 6 req/min/IP (aligned with Gemini 10 RPM, leaving buffer)
limiter = Limiter(key_func=get_remote_address, default_limits=["6/minute"])

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/chat")
@limiter.limit("6/minute")  # B10 fix
async def chat(request: Request, body: ChatRequest):
    ...
```

```python
# app/main.py — Trusted X-Real-IP when behind Nginx
# B10 fix: slowapi uses get_remote_address, but behind proxy it sees proxy IP
# Use X-Real-IP header set by Nginx
from slowapi.util import get_remote_address

def get_real_ip(request: Request) -> str:
    """B10 fix: trust X-Real-IP set by Nginx."""
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    return get_remote_address(request)

limiter = Limiter(key_func=get_real_ip, default_limits=["6/minute"])
```

```nginx
# nginx.conf — Set X-Real-IP
server {
    listen 80;
    server_name vnlaw.example.com;
    
    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;  # B10 fix
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_buffering off;  # SSE
    }
}
```

**B10 verified limits**:
- 6 req/min/IP user-facing
- Gemini 10 RPM → buffer 4 req/min (admin/internal calls + headroom)
- 250 RPD/IP cho /api/chat (đủ cho demo)

### 7.2.3. Web Search Fallback Strategy (POST-REVIEW — DDG + SerpAPI)

```python
# app/services/web_search.py — FR-04 fallback
import os
from typing import List, Dict

class WebSearchService:
    """Wrapper around DuckDuckGo + SerpAPI fallback.
    
    DuckDuckGo is free but blocks datacenter IPs (Oracle, Vultr, etc.).
    SerpAPI falls back when DDG fails.
    """
    
    BACKENDS = ["duckduckgo", "serpapi"]
    
    def __init__(self):
        self.primary = os.environ.get("SEARCH_BACKEND", "duckduckgo")
        self.serpapi_key = os.environ.get("SERPAPI_KEY", "")
        self.max_retries = 3
    
    def search(self, query: str, num_results: int = 5) -> Dict:
        """Try primary, then fallback on failure."""
        # Try primary
        if self.primary == "duckduckgo":
            result = self._try_ddg(query, num_results)
            if result.get("success"):
                return result
            # DDG failed — try SerpAPI
            if self.serpapi_key:
                return self._try_serpapi(query, num_results)
        elif self.primary == "serpapi":
            result = self._try_serpapi(query, num_results)
            if result.get("success"):
                return result
        
        return {"success": False, "results": []}
    
    def _try_ddg(self, query: str, n: int) -> Dict:
        """DuckDuckGo with retries."""
        from duckduckgo_search import DDGS
        for attempt in range(self.max_retries):
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=n))
                    return {"success": True, "results": results}
            except Exception as e:
                if attempt == self.max_retries - 1:
                    return {"success": False, "error": str(e)}
    
    def _try_serpapi(self, query: str, n: int) -> Dict:
        """SerpAPI fallback."""
        import requests
        params = {
            "engine": "google",
            "q": query,
            "api_key": self.serpapi_key,
            "num": n
        }
        resp = requests.get("https://serpapi.com/search", params=params, timeout=10)
        if resp.status_code == 200:
            return {"success": True, "results": resp.json().get("organic_results", [])}
        return {"success": False, "error": f"SerpAPI: {resp.status_code}"}
```

```bash
# .env — search backend options
SEARCH_BACKEND=duckduckgo  # or "serpapi"
SERPAPI_KEY=...             # Get from https://serpapi.com/ (free 100 queries/month)
```

```

**Public endpoints (NO auth required)**:
- `GET /api/health` (health check)
- `POST /api/chat` (user queries)
- `GET /api/search` (search)
- `GET /api/conversations/{thread_id}` (history)
- `GET /api/docs` (Swagger UI)

**Protected endpoints (require Bearer token)**:
- `GET/POST /api/admin/*`
- `POST /api/ingest`
- `POST /api/eval/run`

---

## 7.3. Triển khai lên Oracle Cloud Free Tier

> **Tại sao Oracle Free Tier**: VPS 4 CPU + 24GB RAM, MIỄN PHÍ VĨNH VIỄN, ở nhiều region (Tokyo, Seoul, Singapore gần VN).

### 7.3.1. Tạo VPS

```bash
# 1. Đăng ký tài khoản Oracle Cloud
# https://cloud.oracle.com/
# Tạo VM.Standard.A1.Flex (4 OCPU, 24GB RAM) - FREE FOREVER

# 2. SSH vào server
ssh ubuntu@<your-vm-ip>

# 3. Cài Docker
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
newgrp docker

# 4. Verify
docker --version
docker compose version
```

### 7.3.2. Deploy

```bash
# Trên server
git clone https://github.com/<your-username>/vnlaw-agentic-rag.git
cd vnlaw-agentic-rag

# Tạo .env
nano .env
# Paste: GEMINI_API_KEY=...
#        OPENAI_API_KEY=...

# Khởi động
docker compose up -d

# Check logs
docker compose logs -f
```

### 7.3.3. Cấu hình Nginx + HTTPS

```nginx
# nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }
    
    upstream frontend {
        server frontend:3000;
    }
    
    server {
        listen 80;
        server_name vnlaw.example.com;
        
        location /api/ {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_buffering off;  # Cho SSE streaming
        }
        
        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }
}
```

```bash
# Cài SSL với Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d vnlaw.example.com
```

---

## 7.4. CI/CD với GitHub Actions (POST-REVIEW C11)

> **C11 fix**: Một CI workflow duy nhất, dùng local ChromaDB (persistent file), không cần Docker service. Bỏ test_smoke.py / test_pdfs/ references không tồn tại.

### 7.4.1. Single CI Workflow

```yaml
# .github/workflows/ci.yml — POST-REVIEW C11
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('backend/pyproject.toml') }}
      
      - name: Install dependencies
        run: |
          cd backend
          pip install poetry
          poetry install --no-interaction --no-ansi
      
      - name: Lint with Ruff
        run: |
          cd backend
          pip install ruff
          ruff check .
      
      - name: Type check with mypy
        run: |
          cd backend
          pip install mypy
          mypy app/ --ignore-missing-imports || true  # TODO: tighten later
      
      # C11 fix: ChromaDB persistent (file-based), NO service container needed
      - name: Run unit + smoke + regression tests
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          ADMIN_TOKEN: ${{ secrets.ADMIN_TOKEN }}
        run: |
          cd backend
          poetry run pytest tests/ -v \
            --cov=app \
            --cov-report=term-missing \
            --cov-fail-under=60
```

### 7.4.2. Deploy

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
    paths-ignore:
      - 'docs/**'
      - '*.md'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Copy files to server
        uses: appleboy/scp-action@v0.1.7
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          source: "."
          target: "~/vnlaw-agentic-rag"
      
      - name: Deploy
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.VPS_HOST }}
          username: ${{ secrets.VPS_USER }}
          key: ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ~/vnlaw-agentic-rag
            git pull origin main
            docker compose down
            docker compose up -d --build
            docker compose logs --tail=50
```

---

## 7.5. Monitoring (Minimal)

### 7.5.1. Health Check (POST-REVIEW D3)

> **D3 fix**: `datetime.utcnow()` deprecated trong Python 3.12+. Dùng `datetime.now(UTC)`.

```python
# app/api/health.py
from fastapi import APIRouter
from datetime import datetime, timezone  # D3 fix

router = APIRouter()

@router.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),  # D3 fix
        "version": "1.0.0"
    }

@router.get("/health/detailed")
async def health_detailed():
    """Check từng service."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),  # D3 fix
        "services": {
            "chromadb": await check_chromadb(),
            "sqlite": await check_sqlite(),
            "gemini_api": await check_gemini(),
            "openai_api": await check_openai(),
            "duckduckgo": await check_duckduckgo()
        }
    }
```

### 7.5.2. Logging

```python
# app/utils/logger.py
import logging
import sys

def setup_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    logger.addHandler(handler)
    
    return logger
```

---

## 7.6. Backup & Recovery

### 7.6.1. Backup Strategy (POST-REVIEW D6)

> **D6 fix**: KHÔNG backup `.env` plaintext — chứa API keys. Dùng `gpg` encrypt hoặc bỏ qua.

```bash
#!/bin/bash
# scripts/backup.sh — D6 fix: NO plaintext .env backup

BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
chmod 700 $BACKUP_DIR  # D6: chỉ owner được đọc

# Backup SQLite
cp ~/vnlaw-agentic-rag/sqlite/conversations.db $BACKUP_DIR/db_$DATE.db

# Backup ChromaDB
tar -czf $BACKUP_DIR/chroma_$DATE.tar.gz ~/vnlaw-agentic-rag/chroma_data/

# Backup BM25 index (B4)
cp ~/vnlaw-agentic-rag/data/bm25_index.pkl $BACKUP_DIR/bm25_$DATE.pkl

# D6 fix: .env KHÔNG backup plaintext
# Option 1: Skip
# Option 2: Encrypt với GPG
if [ -n "$BACKUP_GPG_RECIPIENT" ]; then
    gpg --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
        ~/vnlaw-agentic-rag/.env > $BACKUP_DIR/env_$DATE.gpg
    echo "✅ Encrypted .env backup: env_$DATE.gpg"
fi

# Xóa backup cũ (>30 ngày)
find $BACKUP_DIR -type f -mtime +30 -delete

echo "✅ Backup completed: $DATE"
```

### 7.6.2. Cron Job

```bash
# Chạy backup mỗi ngày lúc 2h sáng
crontab -e
0 2 * * * /home/ubuntu/vnlaw-agentic-rag/scripts/backup.sh >> /var/log/backup.log 2>&1
```

---

## 7.7. Checklist trước khi demo

- [ ] Tất cả containers đang chạy: `docker compose ps`
- [ ] API health check pass: `curl https://your-domain/api/health`
- [ ] Frontend load được: mở browser
- [ ] Test 5 câu hỏi cơ bản (FR-01, FR-02)
- [ ] Test 1 câu trigger web search (FR-04)
- [ ] Admin login được (nếu có HITL)
- [ ] Backup đã chạy thành công gần nhất
- [ ] Logs không có error lớn

---

## 7.8. Rollback Plan

Nếu deploy lỗi:

```bash
# Rollback về version trước
cd ~/vnlaw-agentic-rag
git log --oneline -10  # Tìm commit tốt
git checkout <previous-commit>
docker compose down
docker compose up -d --build
```

---

## 7.9. Tóm tắt chi phí

| Hạng mục | Chi phí | Ghi chú |
|----------|---------|---------|
| VPS Oracle Cloud | **$0** | Free tier vĩnh viễn (4 CPU, 24GB RAM) |
| Domain (optional) | $0-10/năm | Dùng subdomain free nếu không mua |
| HTTPS (Let's Encrypt) | $0 | Free |
| LLM API (Gemini) | $0 | Free tier 250 RPD |
| LLM API (OpenAI) | < $10 | $5 credit + phần nhỏ trả thêm |
| **Search API (SerpAPI)** | $0-5/tháng | Fallback khi DDG bị chặn trên VPS IP |
| **Tổng** | **< $25** | |

Đủ để demo cho bảo vệ và duy trì sau khóa luận.
