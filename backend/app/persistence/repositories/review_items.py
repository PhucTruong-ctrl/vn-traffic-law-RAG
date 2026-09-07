"""Review item repository: ``review_items`` persistence (VNLRAG-155).

Follows the conventions of ``documents.py`` / ``provisions.py`` (VNLRAG-39):
write methods flush to the injected session but never commit — the caller
owns the transaction. ``review_items`` records quality-gate review decisions
(doc 03 §3.9.11, §3.4.2); each row is created ``PENDING`` and a reviewer
moves it to a terminal state through the review CLI / review API.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import IngestionRun, LegalProvision, OutboxEvent, ReviewItem

Decision = Literal["ACCEPTED", "NEEDS_REVIEW", "REJECTED", "DROPPED"]
DECISION_TO_STATUS: dict[str, str] = {
    "ACCEPTED": "ACCEPTED",
    "NEEDS_REVIEW": "PENDING",
    "REJECTED": "REJECTED",
    "DROPPED": "DROPPED",
}


class ReviewItemNotFoundError(ValueError):
    """Raised when a review item does not exist."""


class ReviewItemRepository:
    """CRUD and reviewer decisions for review items."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        ingestion_run_id: UUID,
        document_id: str,
        target_type: str,
        target_id: str,
        reason_code: str,
        description: str | None = None,
        evidence: dict[str, Any] | None = None,
        document_version_id: UUID | None = None,
        target_version: int | None = None,
    ) -> ReviewItem:
        row = ReviewItem(
            ingestion_run_id=ingestion_run_id,
            document_id=document_id,
            target_type=target_type,
            target_id=target_id,
            document_version_id=document_version_id,
            target_version=target_version,
            reason_code=reason_code,
            description=description,
            evidence=evidence,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list(self, status: str | None = None, limit: int = 100) -> list[ReviewItem]:
        stmt = select(ReviewItem).order_by(ReviewItem.created_at.asc(), ReviewItem.id.asc())
        if status is not None:
            stmt = stmt.where(ReviewItem.status == status)
        return list(self._session.scalars(stmt.limit(limit)))

    def get(self, item_id: UUID) -> ReviewItem | None:
        return self._session.scalar(select(ReviewItem).where(ReviewItem.id == item_id))

    def record_decision(
        self,
        item_id: UUID,
        decision: Decision,
        reviewer: str,
        reason: str | None = None,
    ) -> ReviewItem:
        status = DECISION_TO_STATUS.get(decision)
        if status is None:
            raise ValueError(f"invalid review decision: {decision!r}")
        row = self._session.scalar(
            select(ReviewItem).where(ReviewItem.id == item_id).with_for_update()
        )
        if row is None:
            raise ReviewItemNotFoundError(f"review item {item_id} not found")
        if row.status != "PENDING":
            if row.status == status and row.reviewer == reviewer:
                return row
            raise ValueError(f"review item {item_id} is already terminal ({row.status})")
        row.status = status
        row.reviewer = reviewer
        row.reviewed_at = datetime.now(UTC)
        if reason:
            row.description = "\n".join(part for part in (row.description, reason) if part)
        self._session.flush()
        return row

    def continue_run_after_decision(self, item_id: UUID, decision: Decision) -> bool:
        """Resolve the target and return whether the embed actor should resume."""
        item = self._session.scalar(
            select(ReviewItem).where(ReviewItem.id == item_id).with_for_update()
        )
        if item is None:
            raise ReviewItemNotFoundError(f"review item {item_id} not found")
        run = self._session.scalar(
            select(IngestionRun).where(IngestionRun.id == item.ingestion_run_id).with_for_update()
        )
        if run is None:
            raise ValueError(f"ingestion run {item.ingestion_run_id} not found")

        if item.target_type.upper() == "PROVISION":
            target = self._session.scalar(
                select(LegalProvision).where(
                    LegalProvision.provision_id == item.target_id,
                    LegalProvision.document_version_id == item.document_version_id,
                    LegalProvision.version == item.target_version,
                )
            )
            if target is None:
                raise ValueError(f"provision {item.target_id!r} not found")
            target.review_status = "ACCEPTED" if decision == "ACCEPTED" else "DROPPED"

        items = list(
            self._session.scalars(
                select(ReviewItem).where(ReviewItem.ingestion_run_id == item.ingestion_run_id)
            )
        )
        if decision in {"REJECTED", "DROPPED"}:
            run.status = "DROPPED"
            run.current_stage = "QUALITY_CHECK"
            run.error = {"code": "REVIEW_REJECTED", "review_item_id": str(item.id)}
            self._session.flush()
            return False
        if any(other.status == "PENDING" for other in items):
            run.status = "PENDING_REVIEW"
            run.current_stage = "QUALITY_CHECK"
            self._session.flush()
            return False

        temporal_review = item.reason_code in {
            "UNKNOWN_EFFECTIVE_DATE",
            "TEMPORAL_REVIEW",
            "MISSING_SUCCESSOR_CONTENT",
        } or item.reason_code.startswith("TEMPORAL_")
        resume_stage = "RESOLVING_TEMPORAL" if temporal_review else "QUALITY_CHECK"
        run.status = resume_stage
        run.current_stage = resume_stage
        run.error = None
        self._session.add(
            OutboxEvent(
                event_type="RESUME_TEMPORAL" if temporal_review else "RESUME_EMBED",
                job_id=run.job_id,
                payload={"job_id": run.job_id},
            )
        )
        self._session.flush()
        return True


__all__ = [
    "DECISION_TO_STATUS",
    "Decision",
    "ReviewItemNotFoundError",
    "ReviewItemRepository",
]
