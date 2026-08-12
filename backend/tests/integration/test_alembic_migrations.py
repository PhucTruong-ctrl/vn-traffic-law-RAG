"""Integration tests for the initial Alembic migration (VNLRAG-38).

Run against a real PostgreSQL server (fixtures in conftest.py create a
dedicated scratch database per session/cycle). Covers doc 06 §6.2.2.1:
migration up from an empty database, downgrade, the btree_gist extension,
the project ``normalize_ref_text()`` function, and the exact documented
index/constraint names (doc 03 §3.10.2–§3.10.4).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from alembic import command

try:  # pytest inserts the test dir on sys.path in non-package mode
    from conftest import _alembic_config
except ImportError:  # package mode: tests/__init__.py makes it importable
    from tests.integration.conftest import _alembic_config

pytestmark = pytest.mark.integration

# The 20 tables of doc 03 §3.10.2, in FK-safe creation order.
EXPECTED_TABLES = frozenset(
    {
        "legal_sources",
        "legal_documents",
        "document_versions",
        "legal_provisions",
        "provision_versions",
        "provision_references",
        "document_relations",
        "legal_effect_events",
        "parsed_documents",
        "document_elements",
        "provision_provenances",
        "ingestion_runs",
        "ingestion_artifacts",
        "review_items",
        "query_traces",
        "query_feedback",
        "evaluation_datasets",
        "evaluation_runs",
        "evaluation_results",
        "corpus_qa_reports",
    }
)

# CREATE INDEX statements documented in doc 03 §3.10.3, plus the inline
# index of §3.10.2 (idx_provision_provenances_version) and the partial
# unique index for unresolved references.
DOCUMENTED_INDEXES = frozenset(
    {
        "idx_legal_documents_number",
        "idx_document_versions_document",
        "idx_legal_provisions_hierarchy",
        "idx_legal_provisions_interval",
        "idx_legal_provisions_review_status",
        "idx_provision_versions_provision",
        "idx_provision_references_source",
        "idx_provision_references_target",
        "idx_provision_references_type",
        "idx_document_relations_source",
        "idx_document_relations_target",
        "idx_legal_effect_events_document",
        "idx_document_elements_parsed",
        "idx_ingestion_runs_status",
        "idx_review_items_status",
        "idx_query_traces_created_at",
        "idx_query_feedback_trace",
        "idx_evaluation_results_run",
        "idx_provision_provenances_version",
        "provision_references_unresolved_pk",
    }
)

# Every named constraint of doc 03 §3.10.2/§3.10.4: PK/UNIQUE/CHECK/FK
# auto-names follow PostgreSQL conventions (``<table>_pkey``,
# ``<table>_<column>_key``, ``<table>_<column>_check``,
# ``<table>_<column>_fkey``) and match the peer's SQLAlchemy models
# (VNLRAG-37) so future autogenerate stays clean.
DOCUMENTED_CONSTRAINTS = frozenset(
    {
        # primary keys
        "legal_sources_pkey",
        "legal_documents_pkey",
        "document_versions_pkey",
        "legal_provisions_pkey",
        "provision_versions_pkey",
        "provision_references_pkey",
        "document_relations_pkey",
        "legal_effect_events_pkey",
        "parsed_documents_pkey",
        "document_elements_pkey",
        "provision_provenances_pkey",
        "ingestion_runs_pkey",
        "ingestion_artifacts_pkey",
        "review_items_pkey",
        "query_traces_pkey",
        "query_feedback_pkey",
        "evaluation_datasets_pkey",
        "evaluation_runs_pkey",
        "evaluation_results_pkey",
        "corpus_qa_reports_pkey",
        # unique constraints (doc-named and inline)
        "legal_sources_source_id_key",
        "legal_documents_document_id_key",
        "legal_documents_file_hash_key",
        "document_versions_pk",
        "legal_provisions_pk",
        "provision_versions_pk",
        "provision_references_resolved_pk",
        "document_relations_pk",
        "document_elements_pk",
        "ingestion_runs_job_id_key",
        "query_traces_trace_id_key",
        "evaluation_datasets_dataset_id_key",
        "evaluation_runs_run_id_key",
        "corpus_qa_reports_report_id_key",
        # check constraints
        "document_versions_review_status_check",
        "document_versions_interval_check",
        "document_versions_effective_from_accepted_check",
        "legal_provisions_node_kind_check",
        "legal_provisions_review_status_check",
        "legal_provisions_interval_check",
        "legal_provisions_article_required",
        "legal_provisions_effective_from_accepted_check",
        "provision_references_relation_type_check",
        "provision_references_resolution_status_check",
        "provision_references_review_status_check",
        "document_relations_relation_type_check",
        "document_relations_resolution_status_check",
        "document_relations_review_status_check",
        "legal_effect_events_event_type_check",
        "legal_effect_events_review_status_check",
        "provision_provenances_role_check",
        "review_items_status_check",
        "query_feedback_category_check",
        "evaluation_datasets_split_check",
        # exclusion constraint (temporal, doc 03 §3.10.4)
        "legal_provisions_no_overlap_accepted",
        # foreign keys
        "legal_documents_source_id_fkey",
        "document_versions_document_id_fkey",
        "legal_provisions_document_version_id_fkey",
        "provision_versions_document_version_id_fkey",
        "provision_versions_fk",
        "provision_references_source_legal_provision_id_fkey",
        "provision_references_target_legal_provision_id_fkey",
        "parsed_documents_document_id_fkey",
        "document_elements_parsed_document_id_fkey",
        "provision_provenances_provision_version_row_id_fkey",
        "provision_provenances_source_document_version_id_fkey",
        "ingestion_runs_document_id_fkey",
        "ingestion_artifacts_ingestion_run_id_fkey",
        "review_items_ingestion_run_id_fkey",
        "query_feedback_query_trace_id_fkey",
        "evaluation_results_evaluation_run_id_fkey",
    }
)


def _public_tables(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return set(
            conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
            ).scalars()
        )


def test_upgrade_creates_all_twenty_tables(upgraded_engine: Engine) -> None:
    """``alembic upgrade head`` from an empty database creates all 20 tables."""
    tables = _public_tables(upgraded_engine)
    assert tables >= EXPECTED_TABLES
    # plus the alembic version table, and nothing unexpected
    assert tables == EXPECTED_TABLES | {"alembic_version"}


def test_btree_gist_extension_installed(upgraded_engine: Engine) -> None:
    """The bootstrap extension required by the GiST exclusion constraint."""
    with upgraded_engine.connect() as conn:
        extname = conn.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'btree_gist'")
        ).scalar_one_or_none()
    assert extname == "btree_gist"


def test_normalize_ref_text_installed_and_deterministic(
    upgraded_engine: Engine,
) -> None:
    """Project function: IMMUTABLE, and case/whitespace/punctuation/NFKC-stable."""
    with upgraded_engine.connect() as conn:
        volatility = conn.execute(
            text(
                "SELECT provolatile FROM pg_proc "
                "WHERE proname = 'normalize_ref_text' AND pronargs = 1"
            )
        ).scalar_one_or_none()
        assert volatility == "i", "normalize_ref_text must be IMMUTABLE"

        n1, n2, n3, n4, n5, n6, n7 = conn.execute(
            text(
                """
                SELECT
                    normalize_ref_text('  Điều 7 ,  Khoản 4  '),
                    normalize_ref_text('điều 7 khoản 4'),
                    normalize_ref_text('Điều\t7\nKhoản   4'),
                    normalize_ref_text('Nghị định （số 168）'),
                    normalize_ref_text('nghị định số 168'),
                    normalize_ref_text('Điều 7'),
                    normalize_ref_text('điều  7')
                """
            )
        ).one()
    assert n1 == n2
    assert n1 == n3
    assert n4 == n5
    assert n6 == n7


def test_alembic_version_at_head(upgraded_engine: Engine) -> None:
    """The session scratch database sits exactly at the initial revision."""
    with upgraded_engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0001"


def test_upgrade_downgrade_roundtrip(cycle_db_url: str) -> None:
    """Upgrade from empty DB, then downgrade to base removes every object."""
    cfg = _alembic_config(cycle_db_url)
    command.upgrade(cfg, "head")
    engine = create_engine(cycle_db_url)
    try:
        assert _public_tables(engine) == EXPECTED_TABLES | {"alembic_version"}

        command.downgrade(cfg, "base")
        # Alembic (1.19) does not drop its version table on downgrade to
        # base; the 20 schema tables must be gone and the version table
        # empty.
        assert _public_tables(engine) == {"alembic_version"}
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT count(*) FROM alembic_version")).scalar_one()
        assert rows == 0

        # the extension and the function are gone with the schema
        with engine.connect() as conn:
            ext = conn.execute(
                text("SELECT 1 FROM pg_extension WHERE extname = 'btree_gist'")
            ).scalar_one_or_none()
            fn = conn.execute(
                text("SELECT 1 FROM pg_proc WHERE proname = 'normalize_ref_text'")
            ).scalar_one_or_none()
        assert ext is None
        assert fn is None
    finally:
        engine.dispose()


def test_documented_indexes_and_constraints_exist(upgraded_engine: Engine) -> None:
    """Every index/constraint name from doc 03 §3.10.2–§3.10.4 is present."""
    with upgraded_engine.connect() as conn:
        indexes = set(
            conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public'")
            ).scalars()
        )
        constraints = set(
            conn.execute(
                text(
                    "SELECT conname FROM pg_constraint WHERE connamespace = 'public'::regnamespace"
                )
            ).scalars()
        )
    assert indexes >= DOCUMENTED_INDEXES
    assert constraints >= DOCUMENTED_CONSTRAINTS
