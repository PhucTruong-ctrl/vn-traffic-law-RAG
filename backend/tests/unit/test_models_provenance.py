"""Unit tests: ProvisionProvenance — provenance roles and version-row wiring.

Covers docs/03 §3.9.14: the ``role`` CHECK constraint with the four documented
roles, the physical UUID FKs to the exact version row (``legal_provisions.id``)
and the source document version (``document_versions.id``), the documented
index, and the relationship wiring to LegalProvision/DocumentVersion.
"""

from uuid import uuid4

from sqlalchemy import CheckConstraint, Integer, inspect
from sqlalchemy.dialects.postgresql import UUID

from app.persistence import Base, DocumentVersion, LegalProvision, ProvisionProvenance

ROLES = ("BASE_TEXT", "AMENDMENT_TEXT", "CORRECTION_TEXT", "EFFECT_SOURCE")


def _table():
    return Base.metadata.tables["provision_provenances"]


def test_provenance_role_check_constraint() -> None:
    table = _table()
    checks = {c.name: str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)}
    assert "provision_provenances_role_check" in checks
    for role in ROLES:
        assert role in checks["provision_provenances_role_check"]
    assert "role IN (" in checks["provision_provenances_role_check"]


def test_provenance_physical_uuid_fks() -> None:
    table = _table()
    for column_name, target_table, target_column in (
        ("provision_version_row_id", "legal_provisions", "id"),
        ("source_document_version_id", "document_versions", "id"),
    ):
        column = table.c[column_name]
        assert isinstance(column.type, UUID), column_name
        assert column.nullable is False, column_name
        fks = list(column.foreign_keys)
        assert len(fks) == 1, column_name
        assert fks[0].column.table.name == target_table
        assert fks[0].column.name == target_column
        assert fks[0].column.primary_key
        assert isinstance(fks[0].column.type, UUID)


def test_provenance_documented_index() -> None:
    table = _table()
    index = next(i for i in table.indexes if i.name == "idx_provision_provenances_version")
    assert [e.name for e in index.columns] == ["provision_version_row_id"]


def test_provenance_required_columns() -> None:
    table = _table()
    for name in (
        "provision_version_row_id",
        "source_document_version_id",
        "source_element_id",
        "page_number",
        "role",
    ):
        assert table.c[name].nullable is False, name
    assert table.c.bbox.nullable is True
    assert isinstance(table.c.page_number.type, Integer)


def test_provenance_relationships_wired() -> None:
    relationships = inspect(ProvisionProvenance).relationships
    assert {r.key for r in relationships} == {
        "provision_version",
        "source_document_version",
    }
    assert relationships["provision_version"].mapper.class_ is LegalProvision
    assert relationships["provision_version"].back_populates == "provenance_records"
    assert relationships["source_document_version"].mapper.class_ is DocumentVersion
    assert relationships["source_document_version"].back_populates == "provenance_records"

    # reverse sides exist on the parents
    legal_provision_rels = inspect(LegalProvision).relationships
    assert legal_provision_rels["provenance_records"].mapper.class_ is ProvisionProvenance
    document_version_rels = inspect(DocumentVersion).relationships
    assert document_version_rels["provenance_records"].mapper.class_ is ProvisionProvenance


def test_provenance_instantiation_and_wiring() -> None:
    provision = LegalProvision(
        provision_id="nd-168-2024__dieu-7",
        document_version_id=uuid4(),
        source_text="nội dung gốc",
        retrieval_text="nội dung gốc",
        status="EFFECTIVE",
        page_number=1,
        content_hash="h1",
        version=1,
    )
    document_version = DocumentVersion(
        document_id="nd-168-2024",
        version=1,
        manifest_json={"title": "ND 168"},
        content_hash="c1",
    )
    provenance = ProvisionProvenance(
        provision_version_row_id=uuid4(),
        source_document_version_id=uuid4(),
        source_element_id="el-42",
        page_number=7,
        role="BASE_TEXT",
    )
    provision.provenance_records.append(provenance)
    document_version.provenance_records.append(provenance)

    assert provenance.provision_version is provision
    assert provenance.source_document_version is document_version
    assert provision.provenance_records == [provenance]
    assert document_version.provenance_records == [provenance]
