"""SQLAlchemy 2.0 ORM models for the VNLaw v2 persistence contract.

Implements the 20-table PostgreSQL schema documented in ``docs/03`` §3.9-3.10
(domain models + DDL) and ``docs/00`` §8 (canonical entities). ``legal_provisions``
is the authoritative version table (``UNIQUE (provision_id, version)``, full
content + interval + ``review_status``); ``provision_versions`` is a lineage
registry whose rows must match a real content row via a composite foreign key.

Extension/exclusion/function-dependent objects are deliberately NOT declared
here (they belong to the VNLRAG-38 migration):

- ``legal_provisions_no_overlap_accepted`` — EXCLUDE USING gist over varchar
  requires the ``btree_gist`` extension (bootstrap step);
- ``provision_references_unresolved_pk`` — partial unique index over
  ``md5(normalize_ref_text(source_text))``, a project function declared in the
  migration bootstrap.

Constraint/index names follow the doc DDL: explicitly named objects keep their
documented names; inline UNIQUE/CHECK constraints use the PostgreSQL
auto-naming convention (``<table>_<column>_key`` / ``<table>_<column>_check``)
so the hand-written migration stays byte-compatible.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

_REVIEW_STATUS_VALUES = "'PENDING', 'ACCEPTED', 'REJECTED', 'DROPPED'"
_RESOLUTION_STATUS_VALUES = "'RESOLVED', 'UNRESOLVED', 'PENDING_REVIEW'"


def _utcnow() -> datetime:
    """Python-side default matching the documented ``now()`` server default."""
    return datetime.now(UTC)


def _uuid_pk() -> Mapped[uuid.UUID]:
    """``uuid PRIMARY KEY DEFAULT gen_random_uuid()`` column (doc 03 §3.10.2)."""
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def _created_at() -> Mapped[datetime]:
    """``timestamptz NOT NULL DEFAULT now()`` column (doc 03 §3.10.2)."""
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )


class Base(DeclarativeBase):
    """Single declarative root owning the VNLaw v2 metadata."""


class LegalSource(Base):
    """Nguồn văn bản pháp luật (doc 03 §3.9.2)."""

    __tablename__ = "legal_sources"
    __table_args__ = (UniqueConstraint("source_id", name="legal_sources_source_id_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_id: Mapped[str] = mapped_column(String, nullable=False)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default=text("100")
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    documents: Mapped[list[LegalDocument]] = relationship(back_populates="source")


class LegalDocument(Base):
    """Văn bản pháp luật (doc 03 §3.9.3)."""

    __tablename__ = "legal_documents"
    __table_args__ = (
        UniqueConstraint("document_id", name="legal_documents_document_id_key"),
        UniqueConstraint("file_hash", name="legal_documents_file_hash_key"),
        Index("idx_legal_documents_number", "document_number"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    document_number: Mapped[str] = mapped_column(String, nullable=False)
    document_title: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(String, nullable=False)
    issuer: Mapped[str | None] = mapped_column(String)
    issued_date: Mapped[date | None] = mapped_column(Date)
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_sources.id")
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )

    source: Mapped[LegalSource | None] = relationship(back_populates="documents")
    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="document")
    source_relations: Mapped[list[DocumentRelation]] = relationship(
        back_populates="source_document",
        primaryjoin="LegalDocument.document_id == DocumentRelation.source_document_id",
        foreign_keys="[DocumentRelation.source_document_id]",
        viewonly=True,
    )
    target_relations: Mapped[list[DocumentRelation]] = relationship(
        back_populates="target_document",
        primaryjoin="LegalDocument.document_id == DocumentRelation.target_document_id",
        foreign_keys="[DocumentRelation.target_document_id]",
        viewonly=True,
    )
    effect_events: Mapped[list[LegalEffectEvent]] = relationship(
        back_populates="document",
        primaryjoin="LegalDocument.document_id == LegalEffectEvent.document_id",
        foreign_keys="[LegalEffectEvent.document_id]",
        viewonly=True,
    )
    parsed_documents: Mapped[list[ParsedDocument]] = relationship(back_populates="legal_document")


class DocumentVersion(Base):
    """Phiên bản nội dung của văn bản (doc 03 §3.9.3)."""

    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version", name="document_versions_pk"),
        CheckConstraint(
            "review_status IN (" + _REVIEW_STATUS_VALUES + ")",
            name="document_versions_review_status_check",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="document_versions_interval_check",
        ),
        CheckConstraint(
            "review_status <> 'ACCEPTED' OR effective_from IS NOT NULL",
            name="document_versions_effective_from_accepted_check",
        ),
        Index("idx_document_versions_document", "document_id", "version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("legal_documents.document_id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[LegalDocument] = relationship(back_populates="versions")
    provisions: Mapped[list[LegalProvision]] = relationship(back_populates="document_version")
    provision_versions: Mapped[list[ProvisionVersion]] = relationship(
        back_populates="document_version"
    )
    provenance_records: Mapped[list[ProvisionProvenance]] = relationship(
        back_populates="source_document_version"
    )


class LegalProvision(Base):
    """Provision version có thẩm quyền; mỗi row = một version (doc 03 §3.9.4)."""

    __tablename__ = "legal_provisions"
    __table_args__ = (
        UniqueConstraint("provision_id", "version", name="legal_provisions_pk"),
        CheckConstraint(
            "node_kind IN ('ARTICLE', 'CLAUSE', 'POINT', 'APPENDIX', 'TABLE', "
            "'TRANSITIONAL', 'HEADING', 'OTHER')",
            name="legal_provisions_node_kind_check",
        ),
        CheckConstraint(
            "review_status IN (" + _REVIEW_STATUS_VALUES + ")",
            name="legal_provisions_review_status_check",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="legal_provisions_interval_check",
        ),
        CheckConstraint(
            "article IS NOT NULL OR node_kind IN ('APPENDIX', 'TABLE', 'HEADING', "
            "'TRANSITIONAL', 'OTHER')",
            name="legal_provisions_article_required",
        ),
        CheckConstraint(
            "review_status <> 'ACCEPTED' OR effective_from IS NOT NULL",
            name="legal_provisions_effective_from_accepted_check",
        ),
        Index(
            "idx_legal_provisions_hierarchy",
            "document_version_id",
            "article",
            "clause",
            "point",
        ),
        Index("idx_legal_provisions_interval", "effective_from", "effective_to"),
        Index(
            "idx_legal_provisions_review_status",
            "review_status",
            postgresql_where=text("review_status = 'ACCEPTED'"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provision_id: Mapped[str] = mapped_column(String, nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    node_kind: Mapped[str] = mapped_column(
        String, nullable=False, default="ARTICLE", server_default=text("'ARTICLE'")
    )
    chapter: Mapped[str | None] = mapped_column(String)
    section: Mapped[str | None] = mapped_column(String)
    article: Mapped[str | None] = mapped_column(String)
    clause: Mapped[str | None] = mapped_column(String)
    point: Mapped[str | None] = mapped_column(String)
    heading: Mapped[str | None] = mapped_column(String)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_text: Mapped[str] = mapped_column(Text, nullable=False)
    parent_context: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_element_ids: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime] = _created_at()

    document_version: Mapped[DocumentVersion] = relationship(back_populates="provisions")
    version_registry_entries: Mapped[list[ProvisionVersion]] = relationship(
        back_populates="provision"
    )
    provenance_records: Mapped[list[ProvisionProvenance]] = relationship(
        back_populates="provision_version"
    )
    source_references: Mapped[list[ProvisionReference]] = relationship(
        back_populates="source_provision",
        foreign_keys="[ProvisionReference.source_legal_provision_id]",
    )
    target_references: Mapped[list[ProvisionReference]] = relationship(
        back_populates="target_provision",
        foreign_keys="[ProvisionReference.target_legal_provision_id]",
    )


class ProvisionVersion(Base):
    """Version registry/lineage phụ trợ (doc 03 §3.9.5)."""

    __tablename__ = "provision_versions"
    __table_args__ = (
        UniqueConstraint("provision_id", "version", name="provision_versions_pk"),
        ForeignKeyConstraint(
            ["provision_id", "version"],
            ["legal_provisions.provision_id", "legal_provisions.version"],
            name="provision_versions_fk",
        ),
        Index("idx_provision_versions_provision", "provision_id", "version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provision_id: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    superseded_by_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = _created_at()
    created_by: Mapped[str | None] = mapped_column(String)

    provision: Mapped[LegalProvision] = relationship(back_populates="version_registry_entries")
    document_version: Mapped[DocumentVersion] = relationship(back_populates="provision_versions")


class ProvisionProvenance(Base):
    """Nguồn của từng thành phần nội dung theo version (doc 03 §3.9.14)."""

    __tablename__ = "provision_provenances"
    __table_args__ = (
        CheckConstraint(
            "role IN ('BASE_TEXT', 'AMENDMENT_TEXT', 'CORRECTION_TEXT', 'EFFECT_SOURCE')",
            name="provision_provenances_role_check",
        ),
        Index("idx_provision_provenances_version", "provision_version_row_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provision_version_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_provisions.id"), nullable=False
    )
    source_document_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False
    )
    source_element_id: Mapped[str] = mapped_column(String, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    role: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    provision_version: Mapped[LegalProvision] = relationship(back_populates="provenance_records")
    source_document_version: Mapped[DocumentVersion] = relationship(
        back_populates="provenance_records"
    )


class ProvisionReference(Base):
    """Quan hệ cấp provision, gắn chặt vào row version (doc 03 §3.9.6)."""

    __tablename__ = "provision_references"
    __table_args__ = (
        UniqueConstraint(
            "source_legal_provision_id",
            "target_legal_provision_id",
            "relation_type",
            name="provision_references_resolved_pk",
        ),
        CheckConstraint(
            "relation_type IN ('PARENT_OF', 'REFERS_TO', 'SIBLING_OF', 'PENALTY_COMPANION')",
            name="provision_references_relation_type_check",
        ),
        CheckConstraint(
            "resolution_status IN (" + _RESOLUTION_STATUS_VALUES + ")",
            name="provision_references_resolution_status_check",
        ),
        CheckConstraint(
            "review_status IN (" + _REVIEW_STATUS_VALUES + ")",
            name="provision_references_review_status_check",
        ),
        Index("idx_provision_references_source", "source_provision_id"),
        Index("idx_provision_references_target", "target_provision_id"),
        Index("idx_provision_references_type", "relation_type"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_legal_provision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_provisions.id"), nullable=False
    )
    target_legal_provision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("legal_provisions.id")
    )
    source_provision_id: Mapped[str] = mapped_column(String, nullable=False)
    source_provision_version_id: Mapped[str | None] = mapped_column(String)
    target_provision_id: Mapped[str | None] = mapped_column(String)
    target_provision_version_id: Mapped[str | None] = mapped_column(String)
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    extraction_method: Mapped[str] = mapped_column(String, nullable=False)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    resolution_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="UNRESOLVED",
        server_default=text("'UNRESOLVED'"),
    )
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime] = _created_at()

    source_provision: Mapped[LegalProvision] = relationship(
        back_populates="source_references",
        foreign_keys=[source_legal_provision_id],
    )
    target_provision: Mapped[LegalProvision | None] = relationship(
        back_populates="target_references",
        foreign_keys=[target_legal_provision_id],
    )


class DocumentRelation(Base):
    """Quan hệ cấp văn bản/hiệu lực (doc 03 §3.9.7); document_id là cột logical."""

    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id",
            "target_document_id",
            "relation_type",
            name="document_relations_pk",
        ),
        CheckConstraint(
            "relation_type IN ('AMENDS', 'REPEALS', 'SUPERSEDES', 'CORRECTS', "
            "'GUIDES', 'RELATED_TO')",
            name="document_relations_relation_type_check",
        ),
        CheckConstraint(
            "resolution_status IN (" + _RESOLUTION_STATUS_VALUES + ")",
            name="document_relations_resolution_status_check",
        ),
        CheckConstraint(
            "review_status IN (" + _REVIEW_STATUS_VALUES + ")",
            name="document_relations_review_status_check",
        ),
        Index("idx_document_relations_source", "source_document_id"),
        Index("idx_document_relations_target", "target_document_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    source_document_id: Mapped[str] = mapped_column(String, nullable=False)
    target_document_id: Mapped[str] = mapped_column(String, nullable=False)
    relation_type: Mapped[str] = mapped_column(String, nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    source_note: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String, nullable=False)
    resolution_status: Mapped[str] = mapped_column(
        String, nullable=False, default="RESOLVED", server_default=text("'RESOLVED'")
    )
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime] = _created_at()
    reviewed_by: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_document: Mapped[LegalDocument | None] = relationship(
        back_populates="source_relations",
        primaryjoin="LegalDocument.document_id == DocumentRelation.source_document_id",
        foreign_keys="[DocumentRelation.source_document_id]",
        viewonly=True,
    )
    target_document: Mapped[LegalDocument | None] = relationship(
        back_populates="target_relations",
        primaryjoin="LegalDocument.document_id == DocumentRelation.target_document_id",
        foreign_keys="[DocumentRelation.target_document_id]",
        viewonly=True,
    )


class LegalEffectEvent(Base):
    """Sự kiện pháp lý ảnh hưởng tới hiệu lực (doc 03 §3.9.8)."""

    __tablename__ = "legal_effect_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('EFFECTIVE', 'AMENDED', 'SUPERSEDED', 'REPEALED', "
            "'CORRECTED', 'EXPIRED', 'PARTIAL_AMENDED')",
            name="legal_effect_events_event_type_check",
        ),
        CheckConstraint(
            "review_status IN (" + _REVIEW_STATUS_VALUES + ")",
            name="legal_effect_events_review_status_check",
        ),
        Index("idx_legal_effect_events_document", "document_id", "event_date"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_document_id: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    source_reference: Mapped[str | None] = mapped_column(Text)
    affected_provision_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'")
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    review_status: Mapped[str] = mapped_column(
        String, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    created_at: Mapped[datetime] = _created_at()

    document: Mapped[LegalDocument | None] = relationship(
        back_populates="effect_events",
        primaryjoin="LegalDocument.document_id == LegalEffectEvent.document_id",
        foreign_keys="[LegalEffectEvent.document_id]",
        viewonly=True,
    )


class ParsedDocument(Base):
    """Kết quả parse của một văn bản (doc 03 §3.9.9)."""

    __tablename__ = "parsed_documents"

    id: Mapped[uuid.UUID] = _uuid_pk()
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("legal_documents.document_id"), nullable=False
    )
    parser: Mapped[str] = mapped_column(String, nullable=False)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    ir_schema_version: Mapped[str] = mapped_column(String, nullable=False)
    source_object_key: Mapped[str] = mapped_column(String, nullable=False)
    parse_status: Mapped[str] = mapped_column(String, nullable=False)
    quality_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    legal_document: Mapped[LegalDocument] = relationship(back_populates="parsed_documents")
    elements: Mapped[list[DocumentElement]] = relationship(back_populates="parsed_document")


class DocumentElement(Base):
    """Element trong parsed document (doc 03 §3.9.9)."""

    __tablename__ = "document_elements"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "element_id", name="document_elements_pk"),
        Index(
            "idx_document_elements_parsed",
            "parsed_document_id",
            "page_number",
            "reading_order",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    parsed_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("parsed_documents.id"), nullable=False
    )
    element_id: Mapped[str] = mapped_column(String, nullable=False)
    element_type: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_element_id: Mapped[str | None] = mapped_column(String)
    table_html: Mapped[str | None] = mapped_column(Text)
    source_parser: Mapped[str] = mapped_column(String, nullable=False)
    parser_version: Mapped[str] = mapped_column(String, nullable=False)
    parser_confidence: Mapped[float | None] = mapped_column(Float)
    raw_reference: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    parsed_document: Mapped[ParsedDocument] = relationship(back_populates="elements")


class IngestionRun(Base):
    """Một lần chạy ingestion (doc 03 §3.9.10)."""

    __tablename__ = "ingestion_runs"
    __table_args__ = (
        UniqueConstraint("job_id", name="ingestion_runs_job_id_key"),
        Index("idx_ingestion_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    job_id: Mapped[str] = mapped_column(String, nullable=False)
    document_id: Mapped[str] = mapped_column(
        String, ForeignKey("legal_documents.document_id"), nullable=False
    )
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    file_hash: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(String)
    parser_routing: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    artifacts: Mapped[list[IngestionArtifact]] = relationship(back_populates="ingestion_run")
    review_items: Mapped[list[ReviewItem]] = relationship(back_populates="ingestion_run")


class IngestionArtifact(Base):
    """Artifact do ingestion_run tạo ra (doc 03 §3.9.10)."""

    __tablename__ = "ingestion_artifacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    bucket: Mapped[str] = mapped_column(String, nullable=False)
    object_key: Mapped[str] = mapped_column(String, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(String)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = _created_at()

    ingestion_run: Mapped[IngestionRun] = relationship(back_populates="artifacts")


class ReviewItem(Base):
    """Review item của corpus (doc 03 §3.9.11)."""

    __tablename__ = "review_items"
    __table_args__ = (
        CheckConstraint(
            "status IN (" + _REVIEW_STATUS_VALUES + ")",
            name="review_items_status_check",
        ),
        Index("idx_review_items_status", "status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(String, nullable=False)
    target_type: Mapped[str] = mapped_column(String, nullable=False)
    target_id: Mapped[str] = mapped_column(String, nullable=False)
    reason_code: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="PENDING", server_default=text("'PENDING'")
    )
    reviewer: Mapped[str | None] = mapped_column(String)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _created_at()

    ingestion_run: Mapped[IngestionRun] = relationship(back_populates="review_items")


class QueryTrace(Base):
    """Trace của một query (doc 03 §3.9.12)."""

    __tablename__ = "query_traces"
    __table_args__ = (
        UniqueConstraint("trace_id", name="query_traces_trace_id_key"),
        Index("idx_query_traces_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    trace_id: Mapped[str] = mapped_column(String, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String, nullable=False)
    query_date: Mapped[date | None] = mapped_column(Date)
    comparison_from: Mapped[date | None] = mapped_column(Date)
    comparison_to: Mapped[date | None] = mapped_column(Date)
    vehicle_type: Mapped[str | None] = mapped_column(String)
    response_status: Mapped[str] = mapped_column(String, nullable=False)
    answer_type: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    verification_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String)
    config_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = _created_at()

    feedback_items: Mapped[list[QueryFeedback]] = relationship(back_populates="query_trace")


class QueryFeedback(Base):
    """Phản hồi của người dùng về một query trace (doc 03 §3.9.12)."""

    __tablename__ = "query_feedback"
    __table_args__ = (
        CheckConstraint(
            "category IN ('wrong_citation', 'missing_information', "
            "'wrong_effective_date', 'wrong_penalty', 'incomplete_answer', 'other')",
            name="query_feedback_category_check",
        ),
        Index("idx_query_feedback_trace", "query_trace_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    query_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("query_traces.id"), nullable=False
    )
    useful: Mapped[bool] = mapped_column(Boolean, nullable=False)
    category: Mapped[str | None] = mapped_column(String)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created_at()

    query_trace: Mapped[QueryTrace] = relationship(back_populates="feedback_items")


class EvaluationDataset(Base):
    """Dataset evaluation (gold set) (doc 03 §3.9.13)."""

    __tablename__ = "evaluation_datasets"
    __table_args__ = (
        UniqueConstraint("dataset_id", name="evaluation_datasets_dataset_id_key"),
        CheckConstraint(
            "split IN ('DEVELOPMENT', 'VALIDATION', 'FINAL_TEST')",
            name="evaluation_datasets_split_check",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    dataset_id: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    split: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    hash: Mapped[str] = mapped_column(String, nullable=False)
    questions_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class EvaluationRun(Base):
    """Một lần chạy evaluation (doc 03 §3.9.13)."""

    __tablename__ = "evaluation_runs"
    __table_args__ = (UniqueConstraint("run_id", name="evaluation_runs_run_id_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[str] = mapped_column(String, nullable=False)
    git_commit: Mapped[str] = mapped_column(String, nullable=False)
    corpus_version: Mapped[str] = mapped_column(String, nullable=False)
    corpus_hash: Mapped[str] = mapped_column(String, nullable=False)
    gold_set_version: Mapped[str] = mapped_column(String, nullable=False)
    gold_set_hash: Mapped[str] = mapped_column(String, nullable=False)
    suite: Mapped[str] = mapped_column(String, nullable=False)
    variant: Mapped[str] = mapped_column(String, nullable=False)
    run_manifest_hash: Mapped[str] = mapped_column(String, nullable=False)
    config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    model_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    prompt_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    parser_versions: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="RUNNING", server_default=text("'RUNNING'")
    )
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_results_path: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    results: Mapped[list[EvaluationResult]] = relationship(back_populates="evaluation_run")


class EvaluationResult(Base):
    """Kết quả một câu hỏi trong evaluation run (doc 03 §3.9.13)."""

    __tablename__ = "evaluation_results"
    __table_args__ = (Index("idx_evaluation_results_run", "evaluation_run_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String, nullable=False)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    retrieval: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_results_path: Mapped[str | None] = mapped_column(Text)

    evaluation_run: Mapped[EvaluationRun] = relationship(back_populates="results")


class CorpusQaReport(Base):
    """Báo cáo chất lượng corpus theo FR-10 (doc 03 §3.10.5)."""

    __tablename__ = "corpus_qa_reports"
    __table_args__ = (UniqueConstraint("report_id", name="corpus_qa_reports_report_id_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    report_id: Mapped[str] = mapped_column(String, nullable=False)
    corpus_version: Mapped[str] = mapped_column(String, nullable=False)
    corpus_hash: Mapped[str] = mapped_column(String, nullable=False)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    documents_analyzed: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=text("now()"),
    )
