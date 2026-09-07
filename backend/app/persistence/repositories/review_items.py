from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import (
    DocumentVersion,
    IngestionRun,
    LegalProvision,
    OutboxEvent,
    ReviewItem,
)

Decision = Literal["ACCEPTED", "NEEDS_REVIEW", "REJECTED", "DROPPED"]
DECISION_TO_STATUS = {
    "ACCEPTED": "ACCEPTED",
    "NEEDS_REVIEW": "PENDING",
    "REJECTED": "REJECTED",
    "DROPPED": "DROPPED",
}


class ReviewItemNotFoundError(ValueError):
    pass


class ReviewItemRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, *args: Any, **kwargs: Any) -> ReviewItem:
        if args:
            names = (
                "ingestion_run_id",
                "document_id",
                "target_type",
                "target_id",
                "reason_code",
                "description",
                "evidence",
            )
            kwargs.update(dict(zip(names, args, strict=False)))
        row = ReviewItem(**kwargs)
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
        self, item_id: UUID, decision: Decision, reviewer: str, reason: str | None = None
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
        row.status, row.reviewer, row.reviewed_at = status, reviewer, datetime.now(UTC)
        if reason:
            row.description = "\n".join(part for part in (row.description, reason) if part)
        self._session.flush()
        return row

    def _apply_temporal_correction(
        self, row: ReviewItem, effective_from: date | None, effective_to: date | None
    ) -> None:
        if row.reason_code == "UNKNOWN_EFFECTIVE_DATE":
            if effective_from is None or row.document_version_id is None:
                raise ValueError("effective_from and document version are required")
            version = self._session.scalar(
                select(DocumentVersion)
                .where(DocumentVersion.id == row.document_version_id)
                .with_for_update()
            )
            if version is None:
                raise ValueError("review document version not found")
            version.effective_from, version.effective_to = effective_from, effective_to
        elif row.reason_code in {
            "UNSCOPED_AMENDMENT",
            "MISSING_TARGET_CONTENT",
            "MISSING_SUCCESSOR_CONTENT",
        }:
            raise ValueError(f"{row.reason_code} requires typed correction payload")

    def decide(
        self,
        item_id: UUID,
        decision: Decision,
        reviewer: str,
        *,
        evidence: dict[str, Any] | None = None,
        effective_from: date | None = None,
        effective_to: date | None = None,
    ) -> ReviewItem:
        row = self._session.scalar(
            select(ReviewItem).where(ReviewItem.id == item_id).with_for_update()
        )
        if row is None:
            raise ReviewItemNotFoundError(f"review item {item_id} not found")
        status = DECISION_TO_STATUS.get(decision)
        if status is None:
            raise ValueError(f"invalid review decision: {decision!r}")
        if row.status != "PENDING":
            if row.status == status and row.reviewer == reviewer:
                return row
            raise ValueError(f"review item {item_id} is already terminal ({row.status})")
        row.evidence = {**(row.evidence or {}), **(evidence or {})}
        if decision == "ACCEPTED":
            self._apply_temporal_correction(row, effective_from, effective_to)
        row.status, row.reviewer, row.reviewed_at = status, reviewer, datetime.now(UTC)
        self._session.flush()
        self.continue_run_after_decision(item_id, decision)
        return row

    def continue_run_after_decision(self, item_id: UUID, decision: Decision) -> bool:
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
            run.status, run.current_stage = "DROPPED", "QUALITY_CHECK"
            run.error = {"code": "REVIEW_REJECTED", "review_item_id": str(item.id)}
            return False
        if any(other.status == "PENDING" for other in items):
            run.status, run.current_stage = "PENDING_REVIEW", "QUALITY_CHECK"
            return False
        temporal = item.reason_code in {
            "UNKNOWN_EFFECTIVE_DATE",
            "TEMPORAL_REVIEW",
            "MISSING_SUCCESSOR_CONTENT",
            "UNSCOPED_AMENDMENT",
            "MISSING_TARGET_CONTENT",
        } or item.reason_code.startswith("TEMPORAL_")
        stage = "RESOLVING_TEMPORAL" if temporal else "QUALITY_CHECK"
        run.status = run.current_stage = stage
        run.error = None
        self._session.add(
            OutboxEvent(
                event_type="RESUME_TEMPORAL" if temporal else "RESUME_EMBED",
                job_id=run.job_id,
                payload={"job_id": run.job_id},
            )
        )
        self._session.flush()
        return True


__all__ = ["DECISION_TO_STATUS", "Decision", "ReviewItemNotFoundError", "ReviewItemRepository"]
