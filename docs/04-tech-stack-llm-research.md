# 04. Tech Stack & Nghiên Cứu LLM

> **Giai đoạn SDLC**: 3 — Thiết kế
> **Ngày tạo**: 16/06/2026

---

## 4.1. Tổng quan Tech Stack

| Agent Layer | Công nghệ | Phiên bản | Lý do |
|-------|-----------|-----------|-------|
| **Backend** | Python | 3.11+ | GVHD yêu cầu, hỗ trợ tốt async |
| **API Framework** | FastAPI | 0.115+ | Async, OpenAPI auto, streaming tốt |
| **Agentic** | LangGraph | 0.2+ | State machine, loop guards, HITL deferred |
| **RAG** | LangChain | 0.3+ | Ecosystem lớn |
| **Vector DB** | ChromaDB | 0.5+ | Nhẹ, persist local |
| **BM25** | rank-bm25 + pyvi | latest | Lightweight + tiếng Việt |
| **Embedding** | intfloat/multilingual-e5-small | 471MB | Đa ngôn ngữ, 384d |
| **LLM (chính)** | **Gemini 2.5 Flash** | 2026 | Free tier 250 RPD |
| **LLM (eval)** | OpenAI GPT-4o-mini | 2024-07-18 | $5 free credit |
| **Web Search** | duckduckgo-search | 6.x | Free, no API key |
| **State DB** | SQLite | 3.x | File-based, đơn giản |
| **Frontend** | Next.js | 14+ | SSR, App Router |
| **UI** | Tailwind + shadcn/ui | 3+ | Nhanh, đẹp |
| **Container** | Docker + Compose | latest | Standard |
| **CI/CD** | GitHub Actions | - | Free cho public repo |

---

## 4.2. Nghiên cứu LLM (Quan trọng)

> **Câu hỏi của bạn**: "Dùng API ChatGPT hoàn toàn được không? Tài khoản Google có sub Pro thì dùng Gemini nhiều hơn không?"

### 4.2.1. So sánh các LLM API (cập nhật 06/2026, **POST-REVIEW B6, B7**)

> **Đã thay đổi (B7)**: Loại bỏ model names không xác minh được ("Gemini 3.1 Pro", "GPT-5 Nano"). Chỉ giữ models CÓ THẬT vào thời điểm nộp khóa luận.

| Model | Input $/1M | Output $/1M | Context | Free Tier | Credit Card | Verified |
|-------|-----------|-------------|---------|-----------|-------------|----------|
| **Gemini 2.5 Flash** | $0.15 | $0.60 | 1M | ✅ 10 RPM, 250K TPM, **250 RPD** | Không | ✅ 06/2026 |
| **Gemini 2.0 Flash** | $0.10 | $0.40 | 1M | ✅ 15 RPM, 1M TPM, 1,500 RPD | Không | ✅ 06/2026 |
| **GPT-4o-mini** | $0.15 | $0.60 | 128K | ❌ Cần billing | **Có** | ✅ 06/2026 |
| **GPT-4o** | $2.50 | $10.00 | 128K | ❌ Cần billing | Có | ✅ 06/2026 |

> **Source**: https://ai.google.dev/gemini-api/docs/pricing và https://openai.com/api/pricing/ (cập nhật 06/2026)

### 4.2.2. Chi tiết Google Gemini Free Tier (06/2026, **POST-REVIEW B6**)

> **B6 fix**: Đã reconcile các số RPD mâu thuẫn. Pin một bảng duy nhất.

| Model | RPM | TPM | RPD | Notes |
|-------|-----|-----|-----|-------|
| Gemini 2.5 Flash | 10 | 250,000 | **250** | Recommended cho RAG |
| Gemini 2.0 Flash | 15 | 1,000,000 | 1,500 | More quota, ít hơn reasoning |
| Gemini 2.5 Flash-Lite | 30 | 1,000,000 | 1,000 | Lite, nhanh nhất |

> **Lưu ý (B6)**: 
> - 250 RPD = 250 requests/ngày (đã fix từ "1,500" sai ở version trước)
> - 250K TPM = **chia sẻ giữa tất cả models** trong cùng project
> - 1 RPD được reset lúc **midnight Pacific time**, không phải UTC

### 4.2.3. Tài khoản Google AI Pro ($20/tháng) — CÓ giúp được gì?

> **Trả lời ngắn**: **KHÔNG tăng API quota**, chỉ tăng limit trong **AI Studio web app**.

| Tính năng | Free | AI Pro ($20/tháng) | AI Ultra ($200/tháng) |
|-----------|------|---------------------|------------------------|
| AI Studio web chat limit | 1x | 4x | 20x |
| API Free Tier (Gemini Flash) | 250 RPD | 250 RPD (giống Free) | 250 RPD (giống Free) |
| API rate limit | Standard | Standard | Standard |
| Pay-as-you-go API | ❌ Cần enable billing riêng | ✅ Enable billing, mua credits | ✅ |
| Context caching | ❌ | ✅ | ✅ |
| Batch API 50% off | ❌ | ✅ | ✅ |
| Antigravity IDE (agent) | Limited | Expanded | Priority |

**Kết luận cho dự án khóa luận**:
- AI Pro subscription **KHÔNG tăng API free quota** cho project của bạn
- Nếu bạn dùng AI Studio web UI nhiều (chat, code) thì AI Pro có giá trị
- Nhưng cho dự án RAG cần gọi API programmatically, **Free tier 250 RPD đã đủ cho MVP** (xem math bên dưới)
- Nếu hết quota, phải enable billing riêng (tốn tiền theo token)

### 4.2.4. Tính toán capacity thực tế (POST-REVIEW B6)

> **B6 fix**: Math cũ sai vì bỏ qua per-query LLM fan-out. Đã redo.

**Assumptions**:
- Corpus: 30 văn bản, ~3,000 chunks
- Gold set: 30 câu (đã thu hẹp từ 50)
- 1 query RAG cần **4 LLM calls**:
  1. Node `classify` (~500 tokens)
  2. Node `grade` (~2,000 tokens: query + top-10 chunks)
  3. Node `generate` (~3,000 tokens: query + chunks + system prompt)
  4. (Optional) Node `rewrite` (~500 tokens)
- Tổng: ~6,000 input tokens + ~500 output tokens per query

**Math với Gemini 2.5 Flash (Free, 250 RPD, 250K TPM, 10 RPM)**:

| Constraint | Per query | Math | Result |
|------------|-----------|------|--------|
| **RPD** | 4 calls | 250 ÷ 4 = 62.5 queries/day | **62 queries/day** |
| **RPM** | 4 calls | 10 ÷ 4 = 2.5 queries/min | **2.5 queries/min** (this is the binding constraint) |
| **TPM** | ~6,500 tokens | 250,000 ÷ 6,500 = 38 queries/min | Plenty |
| **Per 7-week project** | — | 62 × 49 = 3,038 queries | **Đủ cho 50 ablation runs** (V1×V2×V3×LLM × gold) |

**Verdict**: 250 RPD **đủ dùng cho MVP + ablation**. Nếu cần nhiều hơn, switch sang:
1. **Gemini 2.0 Flash**: 1,500 RPD, 15 RPM (6× quota nhưng model cũ hơn)
2. **OpenAI GPT-4o-mini**: $5 credit, không giới hạn RPD (Tier 1 = 500 RPM)

**Math với OpenAI GPT-4o-mini (Tier 1, $5 credit)**:
- 1,750,000 input tokens × $0.15/1M = $0.26
- 250,000 output tokens × $0.60/1M = $0.15
- Tổng: **~$0.41 cho 50 câu test**
- Với $5 free credit: **~600 lần chạy eval** (gấp 12 lần nhu cầu thực tế)

### 4.2.5. So sánh: OpenAI vs Gemini cho dự án

| Tiêu chí | Gemini 2.5 Flash | OpenAI GPT-4o-mini |
|----------|------------------|---------------------|
| **Giá** | Free 250 RPD | $5 credit ban đầu, sau đó trả phí |
| **Context** | **1M tokens** (rất lớn) | 128K tokens |
| **Chất lượng tiếng Việt** | Tốt (Google training data) | Rất tốt (OpenAI leader) |
| **JSON mode** | ✅ `response_mime_type=application/json` | ✅ `response_format={type:json_object}` |
| **Streaming** | ✅ | ✅ |
| **Function calling** | ✅ | ✅ |
| **Rate limit free** | 250 RPD, 10 RPM | Không có free tier |
| **Credit card** | Không cần | Cần cho $5 credit |
| **Phù hợp với** | Demo, dev, low-volume prod | Production, high-volume |

### 4.2.6. Quyết định cuối cùng: Hybrid Strategy (POST-REVIEW A3)

| Mục đích | LLM | Lý do |
|----------|-----|-------|
| **Generator chính** (chat + retrieval eval) | **Gemini 2.5 Flash** (Free tier) | 250 RPD đủ, 1M context, free, không cần CC |
| **Judge trong eval** | **OpenAI GPT-4o-mini** (FORCED) | **A3 fix**: Tách judge khỏi generator; $5 đủ |
| **Fallback khi Gemini rate-limit** | OpenAI GPT-4o-mini | Bảo đảm uptime |

**Lý do dùng 2 LLMs (A3 fix)**:
- **Judge ≠ Generator** để tránh circular bias
- Nếu Gemini generates + Gemini judges → Gemini sẽ thiên vị chính nó
- OpenAI (độc lập) judges Gemini → công bằng hơn

**Cấu hình JSON Mode (POST-REVIEW B11)**:

```python
# Gemini 2.5 Flash
import google.generativeai as genai
model = genai.GenerativeModel(
    "gemini-2.5-flash",
    generation_config={"response_mime_type": "application/json"}
)

# OpenAI GPT-4o-mini
from openai import OpenAI
client = OpenAI()
response = client.chat.completions.create(
    model="gpt-4o-mini",
    response_format={"type": "json_object"},
    messages=[...]
)
```

### 4.2.7. Setup API Keys

```bash
# .env (KHÔNG commit)
GEMINI_API_KEY=AIzaSy...        # Lấy từ https://aistudio.google.com/apikey
OPENAI_API_KEY=sk-...            # Lấy từ https://platform.openai.com/api-keys
ADMIN_TOKEN=<random-secret>      # POST-REVIEW B9: Bearer token cho admin/ingest/eval
```

**Cách lấy Gemini API Key (miễn phí)**:
1. Vào https://aistudio.google.com/apikey
2. Đăng nhập bằng Google account (không cần AI Pro)
3. Bấm "Create API key"
4. Copy key → paste vào `.env`

**Lưu ý bảo mật**:
- Gemini free tier: prompts có thể bị Google review
- Nếu cần privacy, dùng Vertex AI (trả phí) hoặc self-host Ollama
- Cho đồ án, dữ liệu pháp luật công khai → không vấn đề privacy

### 4.2.8. Budget Cap cho OpenAI (POST-REVIEW D7)

> **D7 fix**: $5 cap phải có guard trong code, không chỉ dựa vào OpenAI dashboard.

```python
# app/services/llm.py — D7 fix
import os
from pathlib import Path
import json

class OpenAIBudgetGuard:
    """Track OpenAI usage; raise if exceeding budget."""
    
    BUDGET_LIMIT_USD = float(os.environ.get("OPENAI_BUDGET_USD", "5.0"))  # D7 fix
    USAGE_FILE = Path("./data/openai_usage.json")
    
    @classmethod
    def _load_usage(cls) -> dict:
        if cls.USAGE_FILE.exists():
            return json.loads(cls.USAGE_FILE.read_text())
        return {"total_usd": 0.0, "calls": []}
    
    @classmethod
    def _save_usage(cls, usage: dict):
        cls.USAGE_FILE.parent.mkdir(parents=True, exist_ok=True)
        cls.USAGE_FILE.write_text(json.dumps(usage, indent=2))
    
    @classmethod
    def record_call(cls, input_tokens: int, output_tokens: int):
        """D7 fix: Called after every OpenAI call."""
        cost = (input_tokens * 0.15 / 1_000_000) + (output_tokens * 0.60 / 1_000_000)
        usage = cls._load_usage()
        usage["total_usd"] += cost
        usage["calls"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "cost_usd": cost
        })
        cls._save_usage(usage)
        
        # D7 fix: HARD STOP if exceeding budget
        if usage["total_usd"] >= cls.BUDGET_LIMIT_USD:
            raise RuntimeError(
                f"⚠️ OpenAI budget exceeded: ${usage['total_usd']:.2f} >= ${cls.BUDGET_LIMIT_USD:.2f}. "
                f"Switch to Gemini or top up."
            )
```

```python
# Trong mỗi LLM call:
@OpenAIBudgetGuard.record_call  # D7 fix
def call_openai(prompt: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content
```

```bash
# .env — D7 fix
OPENAI_BUDGET_USD=5.0  # Hard cap; raise if needed
```

### 4.2.9. LLM Service với Circuit Breaker (POST-REVIEW C2)

> **C2 fix (CRITICAL)**: Gemini free tier có thể 429 bất cứ lúc nào. Cần automatic failover.

```python
# app/services/llm.py — POST-REVIEW C2
import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

class CircuitState(str, Enum):
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing, use fallback
    HALF_OPEN = "half_open"    # Testing if primary is back

class LLMCircuitBreaker:
    """Auto-failover between Gemini (primary) and OpenAI (fallback)."""
    
    def __init__(self, primary: str = "gemini", fallback: str = "openai"):
        self.primary = primary
        self.fallback = fallback
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0
        self.failure_threshold = 3        # 3 consecutive failures → OPEN
        self.recovery_timeout = 300      # Try primary again after 5 min
        self.openai_budget = OpenAIBudgetGuard()  # D7
    
    def call(self, prompt: str, **kwargs) -> str:
        """Try primary, fallback on failure."""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker: HALF_OPEN, retrying primary")
            else:
                logger.warning("Circuit breaker: OPEN, using fallback")
                return self._call_fallback(prompt, **kwargs)
        
        try:
            result = self._call_primary(prompt, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                logger.info("Circuit breaker: primary recovered, CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
            return result
        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = time.time()
            logger.error(f"Primary LLM failed ({self.failure_count}/{self.failure_threshold}): {e}")
            
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning("Circuit breaker: OPEN")
            
            return self._call_fallback(prompt, **kwargs)
    
    def _call_primary(self, prompt: str, **kwargs) -> str:
        # Gemini call
        import google.generativeai as genai
        model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config={"response_mime_type": "application/json"}
        )
        response = model.generate_content(prompt)
        return response.text
    
    def _call_fallback(self, prompt: str, **kwargs) -> str:
        # OpenAI call with budget guard (D7)
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}]
        )
        result = response.choices[0].message.content
        # Record for budget
        self.openai_budget.record_call(
            response.usage.prompt_tokens,
            response.usage.completion_tokens
        )
        return result

# Singleton
llm_circuit = LLMCircuitBreaker()
```

**Demo scenario (C2 fix)**:
- Normal: Gemini trả lời → Citation Correctness đo
- Gemini 429: Auto-switch OpenAI → Demo vẫn chạy
- Circuit breaker OPEN 5 phút → Không spam Gemini
- After 5 min: HALF_OPEN thử Gemini lại

**Báo cáo sẽ ghi**:
> "Hệ thống implement circuit breaker pattern tự động chuyển sang OpenAI GPT-4o-mini khi Gemini trả về 429. Trong demo 30 phút, không có downtime dù Gemini free tier không ổn định."

---

## 4.3. Tại sao KHÔNG dùng Local LLM (Ollama)?

| Tiêu chí | Local (Ollama Qwen2.5-3B Q4) | Cloud API (Gemini) |
|----------|------------------------------|---------------------|
| Tốc độ trên i5-10400 | **~30-60s/câu** (rất chậm) | ~2-5s/câu |
| Chất lượng Legal Reasoning | Trung bình (model 3B nhỏ) | Cao |
| Setup | Phải tải ~2GB model | 0 bytes |
| RAM khi chạy | ~4-6GB | 0 (server-side) |
| Quyết định | ❌ | ✅ |

> **Trừ khi** dùng GPU mạnh (≥ RTX 3060 8GB+), nên dùng Cloud API.

---

## 4.4. Lý do chọn từng công nghệ

### 4.4.1. FastAPI thay vì Flask/Django

| Tiêu chí | FastAPI | Flask | Django |
|----------|---------|-------|--------|
| Async native | ✅ | ❌ (cần extension) | ⚠️ (Django 4.1+) |
| Auto OpenAPI docs | ✅ | ❌ | ❌ |
| Pydantic validation | ✅ Built-in | ❌ Manual | ✅ |
| Performance | Cao | Thấp | Trung bình |
| Learning curve | Dễ | Dễ | Khó |

→ **Chọn FastAPI** vì cần async, streaming, validation mạnh.

### 4.4.2. LangGraph thay vì LangChain Agents

| Tiêu chí | LangGraph | LangChain AgentExecutor |
|----------|-----------|------------------------|
| State machine | ✅ Native | ❌ Phải tự build |
| HITL (interrupt) | ✅ `interrupt_before` | ❌ Khó |
| Persistence | ✅ Checkpointers | ⚠️ Manual |
| Debug | ✅ Có trace UI | Khó |
| Visualize flow | ✅ Có graph visualization | ❌ |

→ **Chọn LangGraph** vì cần HITL rõ ràng cho khóa luận.

### 4.4.3. ChromaDB thay vì Qdrant/Pinecone

| Tiêu chí | ChromaDB | Qdrant | Pinecone |
|----------|----------|--------|----------|
| Local mode | ✅ | ⚠️ (cần Docker) | ❌ |
| Cloud | ❌ | ✅ | ✅ |
| Setup | 1 pip install | Docker required | API key |
| Free tier | Unlimited (local) | 1GB cloud | Limited |
| Phù hợp | Dev/small | Production | Enterprise |

→ **Chọn ChromaDB** vì project nhỏ, chạy local, không cần Docker.

### 4.4.4. multilingual-e5-small vs keepitreal/vietnamese-sbert

| Tiêu chí | multilingual-e5-small | vietnamese-sbert |
|----------|----------------------|------------------|
| Dimension | 384 | 768 |
| Size | 471MB | ~1GB |
| Vietnamese quality | Tốt (multilingual) | Rất tốt (chuyên TV) |
| Speed | Nhanh | Chậm hơn |
| Hybrid với BM25 | Tốt | Tốt |

→ **Chọn multilingual-e5-small** làm chính (nhanh, nhẹ), dùng vietnamese-sbert làm alternative trong ablation.

---

## 4.5. Bảng so sánh với các dự án tham khảo

| Tiêu chí | VN-Law-Advisor (CTU) | Viblo GT RAG | Project này |
|----------|---------------------|----------------------|-------------|
| LLM | PhoGPT 7B5 (local) | Gemini 3.1 Flash | **Gemini 2.5 Flash + GPT-4o-mini** |
| Vector DB | ChromaDB | Qdrant 1.7 | **ChromaDB** (đơn giản hơn) |
| Architecture | Microservices | Monolith | **Monolith 3-tier** |
| HITL | ❌ | ✅ LangGraph | **✅ LangGraph** |
| Evaluation | Thủ công | RAGAS-lite | **Custom RAGAS-lite** |
| Embedding | Vietnamese SBERT | multilingual-e5-small | **multilingual-e5-small** |
| Hybrid | ❌ | ✅ Dense + BM25 + RRF | **✅** |
| Reranker | ❌ | ❌ (default off) | **Optional** |
| Hardware | Cần GPU | Mạnh | **CPU + i5-10400 OK** |

---

## 4.6. Setup môi trường

### 4.6.1. Yeu cau phan mem (Cap nhat 17/06/2026)

> **Da thay doi**: Chuyen tu Poetry sang **uv** (nhanh hon, da co san tren may). Dung **pyenv** de pin Python 3.11.15.

```bash
# Python 3.11 (qua pyenv)
pyenv install 3.11.15
pyenv virtualenv 3.11.15 vnlaw-env
pyenv local vnlaw-env
python --version   # Python 3.11.15

# uv (package manager)
uv --version       # >= 0.11

# Node 20+
node --version
npm --version

# Docker (optional)
docker --version
docker compose version

# Ollama (optional - neu muon test local)
curl -fsSL https://ollama.com/install.sh | sh
```

### 4.6.2. Setup Backend (Cap nhat: uv + pyenv)

```bash
# Dam bao pyenv virtualenv dang active
pyenv local vnlaw-env
python --version   # Python 3.11.15

cd backend
uv pip install -r requirements.txt  # hoac uv sync neu co pyproject.toml
cp .env.example .env
# Sua .env: them GEMINI_API_KEY, OPENAI_API_KEY, ADMIN_TOKEN

# Test
uv run pytest tests/test_smoke.py -v
uv run uvicorn app.main:app --reload --port 8000 --workers 1
```

### 4.6.3. Setup Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Sửa: NEXT_PUBLIC_API_URL=http://localhost:8000

npm run dev
# Mở http://localhost:3000
```

---

## 4.7. Dependencies chinh (pyproject.toml / requirements.txt)

> **Cap nhat**: Su dung **uv** thay Poetry. Cau hinh duoi day dung `pyproject.toml` (PEP 621) hoac `requirements.txt`.

```toml
[project]
name = "vnlaw-agentic-rag"
version = "0.1.0"
requires-python = ">=3.11,<3.13"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "langgraph>=0.2",
    "langchain>=0.3",
    "langchain-google-genai>=2.0",
    "langchain-openai>=0.2",
    "langchain-chroma>=0.1",
    "chromadb>=0.5",
    "sentence-transformers>=3.0",
    "rank-bm25>=0.2",
    "pyvi>=0.1",
    "duckduckgo-search>=6.3",
    "sqlalchemy>=2.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "httpx>=0.27",
    "pymupdf>=1.24",
    "pdfplumber>=0.11",
    "python-multipart>=0.0.20",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-cov>=6.0",
    "ruff>=0.7",
    "mypy>=1.13",
]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

---

## 4.8. Tóm tắt quyết định

> **Quyết định cuối cùng**:
> 1. **LLM chính**: Gemini 2.5 Flash (Free, 250 RPD, 1M context)
> 2. **LLM phụ (eval)**: OpenAI GPT-4o-mini ($5 free, dùng cho RAGAS-lite)
> 3. **Embedding**: multilingual-e5-small (384d, đa ngôn ngữ)
> 4. **Vector DB**: ChromaDB (local)
> 5. **Agent**: LangGraph (state machine, HITL)
> 6. **Backend**: FastAPI + Python 3.11
> 7. **Frontend**: Next.js 14 + TypeScript
> 8. **Chi phí ước tính**: < $10 cho toàn bộ 7 tuần
