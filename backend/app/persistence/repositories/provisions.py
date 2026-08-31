"""Provision repository: CRUD, version registry and revision helpers
(VNLRAG-39).

``legal_provisions`` is the authoritative version table — each row is one
provision version with full content, interval and ``review_status``
(doc 03 §3.9.5). ``provision_versions`` is the lineage registry whose rows
must match a real content row via a composite foreign key. Write methods
flush to the injected session but never commit; the caller owns the
transaction.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.persistence.models import (
    DocumentVersion,
    LegalDocument,
    LegalProvision,
    ProvisionVersion,
)


class ProvisionRepository:
    """CRUD for provisions and their version-registry entries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- LegalProvision ---

    def create_provision(self, provision: LegalProvision) -> LegalProvision:
        """Persist a new provision version row."""
        self._session.add(provision)
        self._session.flush()
        return provision

    def get_provision(self, provision_id: str, version: int) -> LegalProvision | None:
        """Fetch one provision version by ``(provision_id, version)``."""
        stmt = select(LegalProvision).where(
            LegalProvision.provision_id == provision_id,
            LegalProvision.version == version,
        )
        return self._session.scalar(stmt)
    def lookup_exact(
        self,
        *,
        document_number: str,
        article: str | None = None,
        clause: str | None = None,
        point: str | None = None,
        query_date: date,
    ) -> list[LegalProvision]:
        """Return accepted provisions matching an exact legal hierarchy."""
        stmt = (
            select(LegalProvision)
            .join(LegalProvision.document_version)
            .join(DocumentVersion.document)
            .options(
                joinedload(LegalProvision.document_version).joinedload(
                    DocumentVersion.document
                )
            )
            .where(
                LegalDocument.document_number == document_number,
                LegalProvision.review_status == "ACCEPTED",
                DocumentVersion.review_status == "ACCEPTED",
                and_(
                    LegalProvision.effective_from <= query_date,
                    or_(
                        LegalProvision.effective_to.is_(None),
                        query_date < LegalProvision.effective_to,
                    ),
                ),
                and_(
                    DocumentVersion.effective_from <= query_date,
                    or_(
                        DocumentVersion.effective_to.is_(None),
                        query_date < DocumentVersion.effective_to,
                    ),
                ),
            )
            .order_by(LegalProvision.clause, LegalProvision.point, LegalProvision.version)
        )
        if article is not None:
            stmt = stmt.where(LegalProvision.article == article)
        if clause is not None:
            stmt = stmt.where(LegalProvision.clause == clause)
        if point is not None:
            stmt = stmt.where(LegalProvision.point == point)
        return list(self._session.scalars(stmt).unique())

    def list_provision_versions(self, provision_id: str) -> list[LegalProvision]:
        """All versions of a provision, ascending by version number."""
        stmt = (
            select(LegalProvision)
            .where(LegalProvision.provision_id == provision_id)
            .order_by(LegalProvision.version)
        )
        return list(self._session.scalars(stmt))

    def update_provision(
        self, provision_id: str, version: int, **fields: Any
    ) -> LegalProvision | None:
        """Apply ``fields`` to one provision version; returns it or None."""
        provision = self.get_provision(provision_id, version)
        if provision is None:
            return None
        for name, value in fields.items():
            setattr(provision, name, value)
        self._session.flush()
        return provision

    def delete_provision(self, provision_id: str, version: int) -> bool:
        """Delete one provision version; returns False when it does not exist."""
        provision = self.get_provision(provision_id, version)
        if provision is None:
            return False
        self._session.delete(provision)
        self._session.flush()
        return True

    # --- ProvisionVersion (lineage registry, doc 03 §3.9.5) ---

    def register_version(self, entry: ProvisionVersion) -> ProvisionVersion:
        """Insert a registry entry; ``superseded_by_version`` is caller-set."""
        self._session.add(entry)
        self._session.flush()
        return entry

    def get_registry_entry(self, provision_id: str, version: int) -> ProvisionVersion | None:
        """Fetch one registry entry by ``(provision_id, version)``."""
        stmt = select(ProvisionVersion).where(
            ProvisionVersion.provision_id == provision_id,
            ProvisionVersion.version == version,
        )
        return self._session.scalar(stmt)

    def list_registry(self, provision_id: str) -> list[ProvisionVersion]:
        """Registry entries of a provision, ascending by version number."""
        stmt = (
            select(ProvisionVersion)
            .where(ProvisionVersion.provision_id == provision_id)
            .order_by(ProvisionVersion.version)
        )
        return list(self._session.scalars(stmt))

    # --- Revision helpers ---

    def next_version(self, provision_id: str) -> int:
        """Next version number for a provision: ``max(version) + 1``, or 1.

        Computed from ``legal_provisions`` — the authoritative version table
        (doc 03 §3.9.5) — so it stays correct regardless of registry state.
        """
        stmt = select(func.max(LegalProvision.version)).where(
            LegalProvision.provision_id == provision_id
        )
        current = self._session.scalar(stmt)
        return 1 if current is None else current + 1
