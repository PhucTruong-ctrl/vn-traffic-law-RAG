"""Document repository: CRUD over ``LegalDocument`` / ``DocumentVersion``
(VNLRAG-39).

Matches the domain models in doc 03 §3.9.3. Write methods flush to the
injected session but never commit — the caller owns the transaction.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import DocumentVersion, LegalDocument


class DocumentRepository:
    """CRUD for documents and their versions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- LegalDocument ---

    def create_document(self, document: LegalDocument) -> LegalDocument:
        """Persist a new document row; returns it with the generated id."""
        self._session.add(document)
        self._session.flush()
        return document

    def get_document(self, document_id: str) -> LegalDocument | None:
        """Fetch a document by its stable logical ``document_id``."""
        stmt = select(LegalDocument).where(LegalDocument.document_id == document_id)
        return self._session.scalar(stmt)

    def update_document(self, document_id: str, **fields: Any) -> LegalDocument | None:
        """Apply ``fields`` to the document; returns the updated row or None."""
        document = self.get_document(document_id)
        if document is None:
            return None
        for name, value in fields.items():
            setattr(document, name, value)
        self._session.flush()
        return document

    def delete_document(self, document_id: str) -> bool:
        """Delete the document; returns False when it does not exist."""
        document = self.get_document(document_id)
        if document is None:
            return False
        self._session.delete(document)
        self._session.flush()
        return True

    # --- DocumentVersion ---

    def create_version(self, version: DocumentVersion) -> DocumentVersion:
        """Persist a new document version row."""
        self._session.add(version)
        self._session.flush()
        return version

    def get_version(self, document_id: str, version: int) -> DocumentVersion | None:
        """Fetch one version by ``(document_id, version)``."""
        stmt = select(DocumentVersion).where(
            DocumentVersion.document_id == document_id,
            DocumentVersion.version == version,
        )
        return self._session.scalar(stmt)

    def list_versions(self, document_id: str) -> list[DocumentVersion]:
        """All versions of a document, ascending by version number."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version)
        )
        return list(self._session.scalars(stmt))

    def latest_version(self, document_id: str) -> DocumentVersion | None:
        """Highest version number of a document, or None."""
        stmt = (
            select(DocumentVersion)
            .where(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version.desc())
            .limit(1)
        )
        return self._session.scalar(stmt)

    def delete_version(self, document_id: str, version: int) -> bool:
        """Delete one version; returns False when it does not exist."""
        row = self.get_version(document_id, version)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True
