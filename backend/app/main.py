"""VNLaw backend application entrypoint."""

from fastapi import FastAPI

app = FastAPI()


@app.get("/api/v1/health/live")
def health_live() -> dict[str, str]:
    """Liveness probe used by container healthchecks."""
    return {"status": "ok"}
