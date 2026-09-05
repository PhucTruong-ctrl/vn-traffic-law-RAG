"""VNLaw backend application entrypoint."""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from app.api import chat, documents, errors, feedback, jobs, review, search
from app.observability.health import metrics, readiness

app = FastAPI()


@app.middleware("http")
async def trace_id_middleware(request: Request, call_next):
    """Propagate one safe trace id through every request and response."""
    supplied = request.headers.get("X-Trace-ID", "")
    trace_id = (
        supplied
        if supplied and len(supplied) <= 128 and supplied.isprintable()
        else errors.new_trace_id()
    )
    errors.set_trace_id(trace_id)
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


errors.register_error_handlers(app)
app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(feedback.router)
app.include_router(jobs.router)
app.include_router(review.router)
app.include_router(search.router)


@app.get("/api/v1/health/ready")
def health_ready() -> dict:
    """Readiness reports dependency degradation without exposing internals."""
    return readiness()


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics() -> PlainTextResponse:
    """Expose bounded, non-sensitive process metrics."""
    return PlainTextResponse(metrics.prometheus(), media_type="text/plain; version=0.0.4")


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness probe used by container healthchecks."""
    return {"status": "ok"}
