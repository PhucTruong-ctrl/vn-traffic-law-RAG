"""Ingestion job status endpoint (doc 03 §3.28.4, FR-07; VNLRAG-135).

``GET /api/v1/jobs/{job_id}`` reads the ``ingestion_runs`` row (the
authoritative job state, written by the ingestion actors, VNLRAG-133) and
returns a status summary. Unknown jobs yield the standard 404 error shape.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import JOB_NOT_FOUND, error_response
from app.persistence.models import IngestionRun

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobRepository:
    """Read access to ``ingestion_runs`` for the status endpoint."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_run(self, job_id: str) -> IngestionRun | None:
        """Fetch the ingestion run for ``job_id``, or None when unknown."""
        stmt = select(IngestionRun).where(IngestionRun.job_id == job_id)
        return self._session.scalar(stmt)


def _to_status_payload(run: IngestionRun) -> dict[str, object]:
    """Map an ``IngestionRun`` row to the doc 03 §3.28.4 status payload."""
    return {
        "ingestion_job_id": run.job_id,
        "status": run.status,
        "current_stage": run.current_stage,
        "parser_routing": run.parser_routing,
        "created_at": run.started_at.isoformat() if run.started_at is not None else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at is not None else None,
        "error": run.error,
    }


@router.get("/jobs/{job_id}", response_model=None)
def get_job_status(
    job_id: str, db: Annotated[Session, Depends(get_db)]
) -> dict[str, object] | JSONResponse:
    """Return the ingestion status for ``job_id`` (404 when unknown)."""
    run = JobRepository(db).get_run(job_id)
    if run is None:
        return error_response(404, JOB_NOT_FOUND, f"Unknown ingestion job {job_id!r}.")
    return _to_status_payload(run)
