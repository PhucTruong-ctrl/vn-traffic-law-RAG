"""Relation queries for legal context expansion (VNLRAG-39).

Implements doc 03 §3.20.2: expanding from seed provisions follows only
relations that are ACCEPTED and RESOLVED, and only expanded provisions
whose own validity interval contains the query date. UNRESOLVED /
PENDING_REVIEW relations are never used for automatic expansion. Each
expansion carries the ``added_by`` / ``source_id`` / ``depth`` metadata
documented in §3.20.2.

Traversal is direction-aware. ``ProvisionReference`` stores edges
``source --relation_type--> target``; for a seed, expansion follows:

- ``REFERS_TO``: outbound — the seed refers to the target;
- ``PARENT_OF``: inbound — edges point parent -> child (doc 03 §3.14.1,
  Điều -> Khoản -> Điểm), and context expansion needs the parent
  (doc 03 §3.20.1), so the seed is the child and the expanded provision
  is the edge source;
- ``SIBLING_OF``: both directions — sibling pairs are stored once with
  an arbitrary direction, so a seed on either side finds the other;
- ``PENALTY_COMPANION``: both directions — the companion relationship
  is mutual (penalty provision <-> accompanying provision, doc 03
  §3.9.6), so a seed on either side finds the other.

In every direction the reference is pinned to the seed's exact version
row (``source_legal_provision_id`` / ``target_legal_provision_id``
physical FKs, doc 03 §3.9.6) and the expanded provision must be ACCEPTED
with an interval containing ``d``.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session

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

# Traversal direction per relation type (module docstring):
#   REFERS_TO         outbound — the seed refers to the target
#   PARENT_OF         inbound  — parent lookup (edges point parent -> child)
#   SIBLING_OF        both     — pairs stored once, direction arbitrary
#   PENALTY_COMPANION both     — the companion relationship is mutual
_OUTBOUND_RELATION_TYPES = frozenset({"REFERS_TO", "SIBLING_OF", "PENALTY_COMPANION"})
_INBOUND_RELATION_TYPES = frozenset({"PARENT_OF", "SIBLING_OF", "PENALTY_COMPANION"})


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
        """Provisions reachable from any seed at date ``d`` (depth 1).

        Traverses each requested relation type in its documented direction
        (module docstring): outbound for ``REFERS_TO``, inbound for
        ``PARENT_OF`` (parent lookup), both directions for ``SIBLING_OF``
        and ``PENALTY_COMPANION``. Filters, per doc 03 §3.20.2: the relation
        row must be ACCEPTED and RESOLVED (UNRESOLVED / PENDING_REVIEW are
        never auto-expanded), the expanded provision must be ACCEPTED with
        an interval containing ``d``, and the relation must be pinned to the
        seed's exact version row (physical FK). ``source_id`` is the seed
        provision_id that led to the expansion. Results are ordered by
        ``(relation_type, source_id, provision_id)``.
        """
        seeds = list(seed_provisions)
        if not seeds:
            return []
        requested = set(relation_types) if relation_types is not None else set(_ADDED_BY)
        outbound_types = sorted(requested & _OUTBOUND_RELATION_TYPES)
        inbound_types = sorted(requested & _INBOUND_RELATION_TYPES)
        seed_provision_ids = {seed.id: seed.provision_id for seed in seeds}

        related: list[RelatedProvision] = []
        if outbound_types:
            related.extend(
                self._expand(
                    d,
                    seed_provision_ids=seed_provision_ids,
                    relation_types=outbound_types,
                    inbound=False,
                )
            )
        if inbound_types:
            related.extend(
                self._expand(
                    d,
                    seed_provision_ids=seed_provision_ids,
                    relation_types=inbound_types,
                    inbound=True,
                )
            )
        return sorted(
            related,
            key=lambda r: (r.relation_type, r.source_id, r.provision.provision_id),
        )

    def _expand(
        self,
        d: date,
        *,
        seed_provision_ids: dict[UUID, str],
        relation_types: list[str],
        inbound: bool,
    ) -> list[RelatedProvision]:
        """One directed traversal: outbound (seed is the edge source) or
        inbound (seed is the edge target, e.g. parent lookup).

        ``source_id`` is derived from the matched seed row (via its physical
        id), never from the reference's nullable logical provision columns,
        so expansion provenance stays correct even when a RESOLVED row lacks
        ``source_provision_id`` / ``target_provision_id``.
        """
        reference = ProvisionReference
        seed_column: InstrumentedAttribute[UUID | None]
        expanded_column: InstrumentedAttribute[UUID | None]
        if inbound:
            seed_column = reference.target_legal_provision_id
            expanded_column = reference.source_legal_provision_id
        else:
            seed_column = reference.source_legal_provision_id
            expanded_column = reference.target_legal_provision_id
        stmt = (
            select(reference.relation_type, seed_column, LegalProvision)
            .join(LegalProvision, LegalProvision.id == expanded_column)
            .where(
                seed_column.in_(seed_provision_ids),
                reference.relation_type.in_(relation_types),
                reference.review_status == _REVIEW_STATUS_ACCEPTED,
                reference.resolution_status == _RESOLUTION_STATUS_RESOLVED,
                LegalProvision.review_status == _REVIEW_STATUS_ACCEPTED,
                LegalProvision.effective_from <= d,
                or_(
                    LegalProvision.effective_to.is_(None),
                    d < LegalProvision.effective_to,
                ),
            )
        )
        rows = self._session.execute(stmt).all()
        related: list[RelatedProvision] = []
        for relation_type, seed_row_id, provision in rows:
            if seed_row_id is None:
                continue  # IN filter guarantees a match; keep mypy happy
            source_id = seed_provision_ids[seed_row_id]
            related.append(
                RelatedProvision(
                    provision=provision,
                    relation_type=relation_type,
                    source_id=source_id,
                )
            )
        return related

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
