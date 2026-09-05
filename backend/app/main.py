"""VNLaw backend application entrypoint."""

from fastapi import FastAPI

from app.api import documents, errors, jobs, search

app = FastAPI()

errors.register_error_handlers(app)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(search.router)


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness probe used by container healthchecks."""
    return {"status": "ok"}
