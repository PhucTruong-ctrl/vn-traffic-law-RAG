"""Unit tests: physical UUID foreign keys and logical varchar foreign keys.

Covers the docs/03 §3.9.15/§3.10.2 FK contract: every ``uuid`` FK column
references the referenced table's UUID primary key, while the logical
``document_id`` FKs reference the UNIQUE ``legal_documents.document_id``
column. Also covers the ``provision_versions`` composite FK
``(provision_id, version) -> legal_provisions(provision_id, version)``.
"""

from sqlalchemy import ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.persistence import Base

# {table: {fk_column: "target_table.target_column"}} per docs/03 §3.10.2 DDL.
EXPECTED_UUID_FKS = {
    "legal_documents": {"source_id": "legal_sources.id"},
    "legal_provisions": {"document_version_id": "document_versions.id"},
    "provision_versions": {"document_version_id": "document_versions.id"},
    "provision_references": {
        "source_legal_provision_id": "legal_provisions.id",
        "target_legal_provision_id": "legal_provisions.id",
    },
    "provision_provenances": {
        "provision_version_row_id": "legal_provisions.id",
        "source_document_version_id": "document_versions.id",
    },
    "document_elements": {"parsed_document_id": "parsed_documents.id"},
    "ingestion_artifacts": {"ingestion_run_id": "ingestion_runs.id"},
    "review_items": {"ingestion_run_id": "ingestion_runs.id"},
    "query_feedback": {"query_trace_id": "query_traces.id"},
    "evaluation_results": {"evaluation_run_id": "evaluation_runs.id"},
}

EXPECTED_VARCHAR_FKS = {
    "document_versions": {"document_id": "legal_documents.document_id"},
    "parsed_documents": {"document_id": "legal_documents.document_id"},
    "ingestion_runs": {"document_id": "legal_documents.document_id"},
}


def test_physical_uuid_fks_reference_uuid_primary_keys() -> None:
    for table_name, fk_map in EXPECTED_UUID_FKS.items():
        table = Base.metadata.tables[table_name]
        for column_name, target in fk_map.items():
            column = table.c[column_name]
            assert isinstance(column.type, UUID), f"{table_name}.{column_name} type"
            fks = list(column.foreign_keys)
            assert len(fks) == 1, f"{table_name}.{column_name} FK count"
            fk = fks[0]
            target_table_name, target_column_name = target.split(".")
            assert fk.column.table.name == target_table_name
            assert fk.column.name == target_column_name
            target_column = Base.metadata.tables[target_table_name].c[target_column_name]
            assert target_column.primary_key, f"{target} is not a primary key"
            assert isinstance(target_column.type, UUID), f"{target} is not UUID"


def test_logical_varchar_fks_reference_unique_document_id() -> None:
    for table_name, fk_map in EXPECTED_VARCHAR_FKS.items():
        table = Base.metadata.tables[table_name]
        for column_name, target in fk_map.items():
            column = table.c[column_name]
            assert isinstance(column.type, String), f"{table_name}.{column_name} type"
            fks = list(column.foreign_keys)
            assert len(fks) == 1, f"{table_name}.{column_name} FK count"
            fk = fks[0]
            target_table_name, target_column_name = target.split(".")
            assert fk.column.table.name == target_table_name
            assert fk.column.name == target_column_name
            # referenced column is UNIQUE via a table constraint (not the PK)
            target_uniques = {
                frozenset(c.columns.keys())
                for c in Base.metadata.tables[target_table_name].constraints
                if isinstance(c, UniqueConstraint)
            }
            assert {target_column_name} in target_uniques, f"{target} is not UNIQUE"


def test_provision_versions_composite_fk_to_legal_provisions() -> None:
    """provision_versions FK (provision_id, version) REFERENCES
    legal_provisions(provision_id, version) — §3.9.5/§3.9.15."""
    table = Base.metadata.tables["provision_versions"]
    fkc = next(
        c
        for c in table.constraints
        if isinstance(c, ForeignKeyConstraint) and c.name == "provision_versions_fk"
    )
    assert tuple(c.name for c in fkc.columns) == ("provision_id", "version")
    targets = [e.target_fullname for e in fkc.elements]
    assert targets == [
        "legal_provisions.provision_id",
        "legal_provisions.version",
    ]


def test_all_primary_keys_are_uuid_with_gen_random_uuid_default() -> None:
    """Every documented table uses ``uuid PRIMARY KEY DEFAULT gen_random_uuid()``."""
    for table_name, table in Base.metadata.tables.items():
        pk_columns = list(table.primary_key.columns)
        assert len(pk_columns) == 1, table_name
        pk = pk_columns[0]
        assert pk.name == "id", table_name
        assert isinstance(pk.type, UUID), table_name
        assert pk.server_default is not None, table_name
        assert "gen_random_uuid" in str(pk.server_default.arg), table_name


def test_no_fk_on_logical_relation_columns() -> None:
    """document_relations / legal_effect_events / review_items.document_id carry
    NO physical FK (logical columns, per docs/03 §3.9.15)."""
    for table_name, column_name in (
        ("document_relations", "source_document_id"),
        ("document_relations", "target_document_id"),
        ("legal_effect_events", "document_id"),
        ("legal_effect_events", "source_document_id"),
        ("review_items", "document_id"),
    ):
        column = Base.metadata.tables[table_name].c[column_name]
        assert list(column.foreign_keys) == [], f"{table_name}.{column_name} has an FK"
