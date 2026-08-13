"""Review item repository: ``review_items`` persistence (VNLRAG-155).

Follows the conventions of ``documents.py`` / ``provisions.py`` (VNLRAG-39):
write methods flush to the injected session but never commit — the caller
owns the transaction. ``review_items`` records quality-gate review decisions
(doc 03 §3.9.11, §3.4.2); each row is created ``PENDING`` and a reviewer
moves it to a terminal state through the review CLI / review API.

Decision -> DB status mapping.  The DB CHECK constraint allows only
``PENDING`` / ``ACCEPTED`` / ``REJECTED`` / ``DROPPED`` (models.py
``_REVIEW_STATUS_VALUES``), so the ``NEEDS_REVIEW`` routing decision maps
back to ``PENDING`` — the row stays in the review queue:

- ACCEPTED      -> ACCEPTED   (indexable)
- NEEDS_REVIEW  -> PENDING    (still awaiting review; no NEEDS_REVIEW state
                               exists in the DB)
- REJECTED      -> REJECTED   (dropped, never indexed)
- DROPPED       -> DROPPED    (dropped, never indexed)

Indexing boundary: this repository only records the decision.  Enforcement
that ACCEPTED rows are indexed and everything else is not lives in the
ingestion pipeline (VNLRAG-44).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import ReviewItem

Decision = Literal["ACCEPTED", "NEEDS_REVIEW", "REJECTED", "DROPPED"]

#: CLI/API decision -> ``review_items.status`` value (see module docstring).
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
    ) -> ReviewItem:
        """Persist a new review item with status PENDING; returns it."""
        row = ReviewItem(
            ingestion_run_id=ingestion_run_id,
            document_id=document_id,
            target_type=target_type,
            target_id=target_id,
            reason_code=reason_code,
            description=description,
            evidence=evidence,
        )
        self._session.add(row)
        self._session.flush()
        return row

    def list(self, status: str | None = None, limit: int = 100) -> list[ReviewItem]:
        """Review items, oldest first (FIFO review queue), optionally filtered
        by status; capped at ``limit`` rows."""
        stmt = select(ReviewItem).order_by(ReviewItem.created_at.asc(), ReviewItem.id.asc())
        if status is not None:
            stmt = stmt.where(ReviewItem.status == status)
        return list(self._session.scalars(stmt.limit(limit)))

    def get(self, item_id: UUID) -> ReviewItem | None:
        """Fetch one review item by id, or None."""
        stmt = select(ReviewItem).where(ReviewItem.id == item_id)
        return self._session.scalar(stmt)

    def record_decision(
        self,
        item_id: UUID,
        decision: Decision,
        reviewer: str,
        reason: str | None = None,
    ) -> ReviewItem:
        """Record a reviewer decision: status + reviewer + reviewed_at (UTC now).

        ``reason`` is appended to the item's description for audit.  Raises
        ``ReviewItemNotFoundError`` for unknown items and ``ValueError`` for
        decisions outside ``DECISION_TO_STATUS``.
        """
        status = DECISION_TO_STATUS.get(decision)
        if status is None:
            raise ValueError(f"invalid review decision: {decision!r}")
        row = self.get(item_id)
        if row is None:
            raise ReviewItemNotFoundError(f"review item {item_id} not found")
        row.status = status
        row.reviewer = reviewer
        row.reviewed_at = datetime.now(UTC)
        if reason:
            row.description = "\n".join(part for part in (row.description, reason) if part)
        self._session.flush()
        return row


__all__ = [
    "DECISION_TO_STATUS",
    "Decision",
    "ReviewItemNotFoundError",
    "ReviewItemRepository",
]
