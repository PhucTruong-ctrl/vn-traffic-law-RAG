"""Temporal validity queries (VNLRAG-39).

Implements the documented validity condition (doc 00 §8.6, doc 03 §3.15.2,
doc 02 FR-06):

    effective_from <= d
    AND (effective_to IS NULL OR d < effective_to)
    AND review_status = 'ACCEPTED'

The interval is half-open ``[effective_from, effective_to)``: a provision is
valid at its ``effective_from`` but not at its ``effective_to``.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from sqlalchemy import ColumnElement, and_, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.persistence.models import DocumentVersion, LegalProvision

_REVIEW_STATUS_ACCEPTED = "ACCEPTED"


def _valid_interval(
    effective_from: InstrumentedAttribute[date | None],
    effective_to: InstrumentedAttribute[date | None],
    d: date,
) -> ColumnElement[bool]:
    return and_(
        effective_from <= d,
        or_(effective_to.is_(None), d < effective_to),
    )


class TemporalRepository:
    """Read-only queries for provisions/versions valid at a given date."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def valid_provisions(
        self,
        d: date,
        *,
        provision_ids: Iterable[str] | None = None,
        document_id: str | None = None,
        limit: int | None = None,
    ) -> list[LegalProvision]:
        """Provisions valid at ``d``: ACCEPTED and interval containing ``d``.

        Optional filters: ``provision_ids`` (stable provision IDs),
        ``document_id`` (all provisions of one document valid at ``d``).
        Results are ordered by ``(provision_id, version)``.
        """
        stmt = select(LegalProvision).where(
            LegalProvision.review_status == _REVIEW_STATUS_ACCEPTED,
            _valid_interval(LegalProvision.effective_from, LegalProvision.effective_to, d),
        )
        if provision_ids is not None:
            stmt = stmt.where(LegalProvision.provision_id.in_(list(provision_ids)))
        if document_id is not None:
            stmt = stmt.join(DocumentVersion).where(DocumentVersion.document_id == document_id)
        stmt = stmt.order_by(LegalProvision.provision_id, LegalProvision.version)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt))

    def valid_document_versions(
        self, d: date, *, document_id: str | None = None
    ) -> list[DocumentVersion]:
        """Document versions valid at ``d``: ACCEPTED and interval containing
        ``d`` (doc 03 §3.15.6). Optional ``document_id`` filter."""
        stmt = select(DocumentVersion).where(
            DocumentVersion.review_status == _REVIEW_STATUS_ACCEPTED,
            _valid_interval(DocumentVersion.effective_from, DocumentVersion.effective_to, d),
        )
        if document_id is not None:
            stmt = stmt.where(DocumentVersion.document_id == document_id)
        stmt = stmt.order_by(DocumentVersion.document_id, DocumentVersion.version)
        return list(self._session.scalars(stmt))

    @staticmethod
    def is_valid_at(provision: LegalProvision, d: date) -> bool:
        """Pure validity predicate — unit-testable without a database.

        Mirrors the SQL condition. ACCEPTED rows always carry an
        ``effective_from`` (DB CHECK, doc 03 §3.10.4); a missing
        ``effective_from`` therefore never validates.
        """
        if provision.review_status != _REVIEW_STATUS_ACCEPTED:
            return False
        if provision.effective_from is None or provision.effective_from > d:
            return False
        return not (provision.effective_to is not None and d >= provision.effective_to)
