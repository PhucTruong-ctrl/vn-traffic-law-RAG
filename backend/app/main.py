"""VNLaw backend application entrypoint."""

from fastapi import FastAPI, Request

from app.api import documents, errors, jobs, search

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
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(search.router)


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness probe used by container healthchecks."""
    return {"status": "ok"}
