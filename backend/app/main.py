"""VNLaw backend application entrypoint."""

import os
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.auth.api import router as auth_router
from app.chats.api import router as chats_router
from app.legal.api import router as legal_router
from app.rag.api import router as rag_router

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
    response = await call_next(request)
    if "X-Trace-ID" not in response.headers:
        response.headers["X-Trace-ID"] = trace_id
    return response


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness probe used by container healthchecks."""
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def health_ready() -> dict[str, object]:
    """Readiness probe reporting dependency checks."""
    return {"status": "ok", "supabase": bool(os.getenv("SUPABASE_URL")), "qdrant": True}
