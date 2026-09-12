"""VNLaw backend application entrypoint."""

import logging
import time
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from qdrant_client import QdrantClient

from app.auth.api import router as auth_router
from app.chats.api import router as chats_router
from app.config import get_qdrant_settings, get_supabase_settings
from app.legal.api import router as legal_router
from app.rag.api import router as rag_router

logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(rag_router)
app.include_router(auth_router)
app.include_router(chats_router)
app.include_router(legal_router)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or uuid4().hex
    request.state.trace_id = trace_id
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request completed",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status": 500,
                "duration_ms": duration_ms,
            },
        )
        raise
    response.headers["X-Trace-ID"] = trace_id
    logger.info(
        "request completed",
        extra={
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        },
    )
    return response


@app.exception_handler(httpx.HTTPStatusError)
async def supabase_http_error_handler(request: Request, exc: httpx.HTTPStatusError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID") or uuid4().hex)
    if exc.response.status_code == 401:
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid or expired token"},
            headers={"WWW-Authenticate": "Bearer", "X-Trace-ID": trace_id},
        )
    return JSONResponse(
        status_code=502,
        content={"detail": "Upstream authentication service error", "X-Trace-ID": trace_id},
    )


@app.exception_handler(Exception)
async def internal_error_handler(request: Request, _exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", request.headers.get("X-Trace-ID") or uuid4().hex)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "Internal server error",
                "request_id": trace_id,
            }
        },
    )


def _supabase_ready() -> bool:
    settings = get_supabase_settings()
    url, key = settings.url, settings.service_role_key or settings.anon_key
    if not url or not key:
        return False
    try:
        response = httpx.get(
            f"{url}/rest/v1/",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=2.0,
        )
        return response.status_code < 500
    except Exception:
        return False


def _qdrant_ready() -> bool:
    try:
        settings = get_qdrant_settings()
        if settings.url:
            client = QdrantClient(url=settings.url, timeout=settings.timeout)
            try:
                client.get_collection(settings.collection)
            finally:
                client.close()
            return True
        from app.rag.api import rag_service

        store = rag_service.retriever._store_for_query()
        store.client.get_collection(settings.collection)
        return True
    except Exception:
        return False


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    """Backward-compatible aggregate health endpoint."""
    return {"status": "ok"}


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness probe used by container healthchecks."""
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def health_ready() -> JSONResponse:
    """Readiness probe reporting dependency checks without exposing credentials."""
    checks = {"supabase": _supabase_ready(), "qdrant": _qdrant_ready()}
    status = "ok" if all(checks.values()) else "unavailable"
    return JSONResponse(
        status_code=200 if status == "ok" else 503,
        content={"status": status, **checks},
    )
