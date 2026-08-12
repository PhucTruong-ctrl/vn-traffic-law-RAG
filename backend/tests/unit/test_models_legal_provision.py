"""Unit tests: LegalProvision persistence contract.

Covers the docs/00 §8.3 20-field contract + ``node_kind`` (docs/03 §3.9.4),
the authoritative version table rule ``UNIQUE (provision_id, version)``
(§3.9.5, §3.9.15), DDL types/constraints/defaults (§3.10.2) and the interval /
review / article-required CHECKs (§3.10.4).
"""

from sqlalchemy import CheckConstraint, Date, Integer, String, Text, UniqueConstraint, inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.persistence import (
    Base,
    LegalProvision,
    ProvisionProvenance,
    ProvisionReference,
    ProvisionVersion,
)

# docs/00 §8.3 — the 20 fields per FR-03; docs/03 §3.9.4 adds node_kind.
DOCUMENTED_FIELDS = [
    "provision_id",
    "document_version_id",
    "chapter",
    "section",
    "article",
    "clause",
    "point",
    "heading",
    "source_text",
    "retrieval_text",
    "parent_context",
    "effective_from",
    "effective_to",
    "status",
    "page_number",
    "bbox",
    "source_element_ids",
    "content_hash",
    "version",
    "review_status",
]

REVIEW_STATUS_VALUES = ("PENDING", "ACCEPTED", "REJECTED", "DROPPED")
NODE_KIND_VALUES = (
    "ARTICLE",
    "CLAUSE",
    "POINT",
    "APPENDIX",
    "TABLE",
    "TRANSITIONAL",
    "HEADING",
    "OTHER",
)


def _table():
    return Base.metadata.tables["legal_provisions"]


def test_column_set_matches_documented_contract() -> None:
    table = _table()
    expected = set(DOCUMENTED_FIELDS) | {"node_kind", "id", "created_at"}
    assert set(table.columns.keys()) == expected
    assert len(table.columns) == 23  # 20 documented + node_kind + id + created_at


def test_required_and_optional_columns() -> None:
    table = _table()
    for name in (
        "provision_id",
        "document_version_id",
        "node_kind",
        "source_text",
        "retrieval_text",
        "status",
        "page_number",
        "source_element_ids",
        "content_hash",
        "version",
        "review_status",
    ):
        assert table.c[name].nullable is False, name
    for name in (
        "chapter",
        "section",
        "article",
        "clause",
        "point",
        "heading",
        "parent_context",
        "effective_from",
        "effective_to",
        "bbox",
    ):
        assert table.c[name].nullable is True, name


def test_column_types() -> None:
    table = _table()
    assert isinstance(table.c.id.type, UUID)
    assert table.c.id.primary_key
    assert isinstance(table.c.provision_id.type, String)
    assert isinstance(table.c.document_version_id.type, UUID)
    assert isinstance(table.c.node_kind.type, String)
    assert isinstance(table.c.source_text.type, Text)
    assert isinstance(table.c.retrieval_text.type, Text)
    assert isinstance(table.c.parent_context.type, Text)
    assert isinstance(table.c.effective_from.type, Date)
    assert isinstance(table.c.effective_to.type, Date)
    assert isinstance(table.c.page_number.type, Integer)
    assert isinstance(table.c.bbox.type, JSONB)
    assert isinstance(table.c.source_element_ids.type, JSONB)
    assert isinstance(table.c.content_hash.type, String)
    assert isinstance(table.c.version.type, Integer)
    assert isinstance(table.c.review_status.type, String)


def test_document_version_fk_is_physical_uuid() -> None:
    """document_version_id is a physical UUID FK to document_versions.id."""
    fks = list(_table().c.document_version_id.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "document_versions"
    assert fk.column.name == "id"
    assert isinstance(fk.column.type, UUID)
    assert fk.column.primary_key


def test_authoritative_version_unique_constraint() -> None:
    """UNIQUE (provision_id, version) named legal_provisions_pk (§3.9.5)."""
    table = _table()
    uniques = {
        c.name: tuple(c.columns.keys())
        for c in table.constraints
        if isinstance(c, UniqueConstraint)
    }
    assert uniques["legal_provisions_pk"] == ("provision_id", "version")
    # individual columns are not unique by themselves (no single-column UNIQUE)
    assert table.c.provision_id.unique is not True
    assert table.c.version.unique is not True


def test_documented_check_constraints() -> None:
    table = _table()
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "legal_provisions_node_kind_check" in checks
    for value in NODE_KIND_VALUES:
        assert value in checks["legal_provisions_node_kind_check"]
    assert "legal_provisions_review_status_check" in checks
    for value in REVIEW_STATUS_VALUES:
        assert value in checks["legal_provisions_review_status_check"]
    # §3.10.4: [effective_from, effective_to) with exclusive upper bound
    assert "legal_provisions_interval_check" in checks
    assert "effective_to > effective_from" in checks["legal_provisions_interval_check"]
    # article required unless node is outside the ordinary Article tree
    assert "legal_provisions_article_required" in checks
    assert "article IS NOT NULL" in checks["legal_provisions_article_required"]
    for value in ("APPENDIX", "TABLE", "HEADING", "TRANSITIONAL", "OTHER"):
        assert value in checks["legal_provisions_article_required"]
    # review_status = ACCEPTED forces effective_from (§3.15.6)
    assert "legal_provisions_effective_from_accepted_check" in checks
    assert (
        "review_status <> 'ACCEPTED' OR effective_from IS NOT NULL"
        in checks["legal_provisions_effective_from_accepted_check"]
    )


def test_documented_server_defaults() -> None:
    table = _table()
    assert "ARTICLE" in str(table.c.node_kind.server_default.arg)
    assert "PENDING" in str(table.c.review_status.server_default.arg)
    assert "'[]'" in str(table.c.source_element_ids.server_default.arg)
    assert "gen_random_uuid" in str(table.c.id.server_default.arg)


def test_documented_indexes() -> None:
    table = _table()
    index_names = {i.name for i in table.indexes}
    assert {
        "idx_legal_provisions_hierarchy",
        "idx_legal_provisions_interval",
        "idx_legal_provisions_review_status",
    } <= index_names
    hierarchy = next(i for i in table.indexes if i.name == "idx_legal_provisions_hierarchy")
    assert [e.name for e in hierarchy.columns] == [
        "document_version_id",
        "article",
        "clause",
        "point",
    ]
    partial = next(i for i in table.indexes if i.name == "idx_legal_provisions_review_status")
    assert partial.dialect_options["postgresql"]["where"] is not None


def test_legal_provision_relationships_wired() -> None:
    relationships = inspect(LegalProvision).relationships
    assert {r.key for r in relationships} == {
        "document_version",
        "version_registry_entries",
        "provenance_records",
        "source_references",
        "target_references",
    }
    assert relationships["document_version"].mapper.class_.__name__ == "DocumentVersion"
    assert relationships["version_registry_entries"].mapper.class_ is ProvisionVersion
    assert relationships["provenance_records"].mapper.class_ is ProvisionProvenance
    assert relationships["source_references"].mapper.class_ is ProvisionReference
    assert relationships["target_references"].mapper.class_ is ProvisionReference


def test_legal_provision_instantiation_and_graph() -> None:
    provision = LegalProvision(
        provision_id="nd-168-2024__dieu-7__khoan-4__diem-b",
        document_version_id=None,
        source_text="p) Dàn hàng ngang từ 03 xe trở lên",
        retrieval_text="Khoản 4. ... p) Dàn hàng ngang từ 03 xe trở lên",
        status="EFFECTIVE",
        page_number=12,
        content_hash="abc123",
        version=1,
    )
    assert provision.provision_id == "nd-168-2024__dieu-7__khoan-4__diem-b"
    assert provision.node_kind is None  # server default 'ARTICLE' applies at flush
    assert provision.review_status is None  # server default 'PENDING' applies at flush

    registry_entry = ProvisionVersion(
        provision_id=provision.provision_id, version=provision.version, document_version_id=None
    )
    provision.version_registry_entries.append(registry_entry)
    assert registry_entry.provision is provision
    assert provision.version_registry_entries == [registry_entry]

    reference = ProvisionReference(
        source_legal_provision_id=None,
        source_provision_id=provision.provision_id,
        relation_type="REFERS_TO",
        extraction_method="TEXT_PATTERN",
        source_text="tham chiếu",
    )
    provision.source_references.append(reference)
    assert reference.source_provision is provision
