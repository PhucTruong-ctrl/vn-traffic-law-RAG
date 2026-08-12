"""Relation queries for legal context expansion (VNLRAG-39).

Implements doc 03 §3.20.2: expanding from seed provisions follows only
relations that are ACCEPTED and RESOLVED, and only targets whose own
validity interval contains the query date. UNRESOLVED / PENDING_REVIEW
relations are never used for automatic expansion. Each expansion carries
the ``added_by`` / ``source_id`` / ``depth`` metadata documented in
§3.20.2.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.persistence.models import (
    DocumentRelation,
    DocumentVersion,
    LegalProvision,
    ProvisionReference,
)

_REVIEW_STATUS_ACCEPTED = "ACCEPTED"
_RESOLUTION_STATUS_RESOLVED = "RESOLVED"

# added_by value per expansion source (doc 03 §3.20.1).
_ADDED_BY = {
    "PARENT_OF": "PARENT_CONTEXT",
    "REFERS_TO": "CROSS_REFERENCE",
    "SIBLING_OF": "SIBLING",
    "PENALTY_COMPANION": "PENALTY_COMPANION",
}


@dataclass(frozen=True)
class RelatedProvision:
    """A provision reachable from a seed via an accepted relation."""

    provision: LegalProvision
    relation_type: str
    source_id: str
    depth: int = 1

    @property
    def added_by(self) -> str:
        return _ADDED_BY.get(self.relation_type, "RELATION")

    def as_metadata(self) -> dict[str, object]:
        """Context-expansion metadata (doc 03 §3.20.2)."""
        return {
            "provision_id": self.provision.provision_id,
            "added_by": self.added_by,
            "source_id": self.source_id,
            "depth": self.depth,
        }


class RelationRepository:
    """Read-only relation queries for context expansion."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def related_provisions(
        self,
        d: date,
        seed_provisions: Iterable[LegalProvision],
        *,
        relation_types: Iterable[str] | None = None,
    ) -> list[RelatedProvision]:
        """Provisions referenced by any seed at date ``d`` (depth 1).

        Filters, per doc 03 §3.20.2: the relation row must be ACCEPTED and
        RESOLVED (UNRESOLVED / PENDING_REVIEW are never auto-expanded), the
        target must be ACCEPTED with an interval containing ``d``, and the
        reference must be pinned to the seed's exact version row
        (``source_legal_provision_id``). When ``relation_types`` is given,
        only those relation types are followed.
        """
        seeds = list(seed_provisions)
        if not seeds:
            return []
        stmt = (
            select(ProvisionReference, LegalProvision)
            .join(
                LegalProvision,
                LegalProvision.id == ProvisionReference.target_legal_provision_id,
            )
            .where(
                ProvisionReference.source_legal_provision_id.in_([seed.id for seed in seeds]),
                ProvisionReference.review_status == _REVIEW_STATUS_ACCEPTED,
                ProvisionReference.resolution_status == _RESOLUTION_STATUS_RESOLVED,
                ProvisionReference.target_legal_provision_id.is_not(None),
                LegalProvision.review_status == _REVIEW_STATUS_ACCEPTED,
                LegalProvision.effective_from <= d,
                or_(
                    LegalProvision.effective_to.is_(None),
                    d < LegalProvision.effective_to,
                ),
            )
        )
        if relation_types is not None:
            stmt = stmt.where(ProvisionReference.relation_type.in_(list(relation_types)))
        rows = self._session.execute(stmt).all()
        return [
            RelatedProvision(
                provision=target,
                relation_type=reference.relation_type,
                source_id=reference.source_provision_id,
            )
            for reference, target in rows
        ]

    def related_documents(
        self,
        d: date,
        document_id: str,
        *,
        relation_types: Iterable[str] | None = None,
    ) -> list[DocumentRelation]:
        """ACCEPTED document relations from ``document_id`` active at ``d``.

        A relation is returned only when it is ACCEPTED and RESOLVED, its
        ``effective_from`` (if set) is not after ``d`` (``document_relations``
        has no ``effective_to``, doc 03 §3.9.7), and the target document has
        at least one ACCEPTED version whose interval contains ``d``
        (doc 03 §3.20.2 review + interval filter).
        """
        target_has_valid_version = (
            select(DocumentVersion.id)
            .where(
                DocumentVersion.document_id == DocumentRelation.target_document_id,
                DocumentVersion.review_status == _REVIEW_STATUS_ACCEPTED,
                DocumentVersion.effective_from <= d,
                or_(
                    DocumentVersion.effective_to.is_(None),
                    d < DocumentVersion.effective_to,
                ),
            )
            .exists()
        )
        stmt = select(DocumentRelation).where(
            DocumentRelation.source_document_id == document_id,
            DocumentRelation.review_status == _REVIEW_STATUS_ACCEPTED,
            DocumentRelation.resolution_status == _RESOLUTION_STATUS_RESOLVED,
            or_(
                DocumentRelation.effective_from.is_(None),
                DocumentRelation.effective_from <= d,
            ),
            target_has_valid_version,
        )
        if relation_types is not None:
            stmt = stmt.where(DocumentRelation.relation_type.in_(list(relation_types)))
        stmt = stmt.order_by(DocumentRelation.relation_type, DocumentRelation.target_document_id)
        return list(self._session.scalars(stmt))
