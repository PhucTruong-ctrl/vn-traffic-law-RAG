"""Ingestion job status endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.db import get_db
from app.api.errors import JOB_NOT_FOUND, error_response
from app.persistence.models import IngestionRun

router = APIRouter(prefix="/api/v1", tags=["jobs"])


class JobRepository:
    """Read access to ingestion runs."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_run(self, job_id: str) -> IngestionRun | None:
        stmt = select(IngestionRun).where(IngestionRun.job_id == job_id)
        return self._session.scalar(stmt)


def _to_status_payload(run: IngestionRun) -> dict[str, object]:
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
    job_id: str,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, object] | JSONResponse:
    run = JobRepository(db).get_run(job_id)
    if run is None:
        return error_response(
            404,
            JOB_NOT_FOUND,
            f"Unknown ingestion job {job_id!r}.",
            request.headers.get("X-Trace-ID"),
        )
    return _to_status_payload(run)
