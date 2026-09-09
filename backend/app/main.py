"""VNLaw backend application entrypoint."""

from fastapi import FastAPI, Request

from app.api import chat, conversations, documents, errors, feedback, jobs, search
from app.observability.health import readiness

app = FastAPI()

errors.register_error_handlers(app)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(search.router)
app.include_router(feedback.router)


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-ID") or errors.new_trace_id()
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
    return readiness()
