"""Corpus QA report repository: ``corpus_qa_reports`` persistence (VNLRAG-127).

Follows the conventions of ``documents.py`` / ``provisions.py`` (VNLRAG-39):
write methods flush to the injected session but never commit — the caller
owns the transaction.  ``corpus_qa_reports`` stores the FR-10 metrics as
JSONB (doc 03 §3.10.5, §3.9.16); ``id`` and ``generated_at`` server defaults
apply on insert.

``report_row_kwargs`` is a pure mapping from the report shape to the ORM
constructor kwargs so serialization is unit-testable without PostgreSQL;
the integration paths (real sessions) are exercised by the orchestrator.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.evaluation.corpus_qa import CorpusQaReportShape
from app.persistence.models import CorpusQaReport


def report_row_kwargs(report_shape: CorpusQaReportShape) -> dict[str, Any]:
    """Map a report shape onto ``CorpusQaReport`` constructor kwargs.

    Pure function (no session required): ``metrics`` is serialized to exactly
    the 16 JSONB keys; ``documents_analyzed`` / ``notes`` pass through as-is.
    """

    return {
        "report_id": report_shape.report_id,
        "corpus_version": report_shape.corpus_version,
        "corpus_hash": report_shape.corpus_hash,
        "metrics": report_shape.metrics.model_dump(),
        "documents_analyzed": report_shape.documents_analyzed,
        "notes": report_shape.notes,
        "generated_at": report_shape.generated_at,
    }


class CorpusQaReportRepository:
    """CRUD for corpus QA reports."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, report_shape: CorpusQaReportShape) -> CorpusQaReport:
        """Persist a new corpus QA report row; returns it with the generated id."""
        row = CorpusQaReport(**report_row_kwargs(report_shape))
        self._session.add(row)
        self._session.flush()
        return row

    def get_latest(self, corpus_version: str) -> CorpusQaReport | None:
        """Most recent report for ``corpus_version`` (by ``generated_at``)."""
        stmt = (
            select(CorpusQaReport)
            .where(CorpusQaReport.corpus_version == corpus_version)
            .order_by(CorpusQaReport.generated_at.desc(), CorpusQaReport.id.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)


__all__ = ["CorpusQaReportRepository", "report_row_kwargs"]
