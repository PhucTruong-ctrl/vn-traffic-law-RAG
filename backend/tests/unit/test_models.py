"""Unit tests: persistence metadata root and the documented 20-table set.

Covers Jira VNLRAG-37 acceptance criterion 1 (models import cleanly,
``Base.metadata`` contains exactly the documented table names) plus the
extension/exclusion/function-dependent exclusion rule (docs/03 §3.10.4).
"""

from sqlalchemy.orm import configure_mappers

from app.persistence import Base
from app.persistence.models import (
    CorpusQaReport,
    DocumentElement,
    DocumentRelation,
    DocumentVersion,
    EvaluationDataset,
    EvaluationResult,
    EvaluationRun,
    IngestionArtifact,
    IngestionRun,
    LegalDocument,
    LegalEffectEvent,
    LegalProvision,
    LegalSource,
    ParsedDocument,
    ProvisionProvenance,
    ProvisionReference,
    ProvisionVersion,
    QueryFeedback,
    QueryTrace,
    ReviewItem,
)

# docs/03 §3.9.15 mapping hints + §3.10.2 DDL — exactly these 20 tables.
DOCUMENTED_TABLES = [
    "legal_sources",
    "legal_documents",
    "document_versions",
    "legal_provisions",
    "provision_versions",
    "provision_provenances",
    "provision_references",
    "document_relations",
    "legal_effect_events",
    "parsed_documents",
    "document_elements",
    "ingestion_runs",
    "ingestion_artifacts",
    "review_items",
    "query_traces",
    "query_feedback",
    "evaluation_datasets",
    "evaluation_runs",
    "evaluation_results",
    "corpus_qa_reports",
]

MODEL_CLASSES = [
    LegalSource,
    LegalDocument,
    DocumentVersion,
    LegalProvision,
    ProvisionVersion,
    ProvisionProvenance,
    ProvisionReference,
    DocumentRelation,
    LegalEffectEvent,
    ParsedDocument,
    DocumentElement,
    IngestionRun,
    IngestionArtifact,
    ReviewItem,
    QueryTrace,
    QueryFeedback,
    EvaluationDataset,
    EvaluationRun,
    EvaluationResult,
    CorpusQaReport,
]


def test_models_import_cleanly() -> None:
    """Every documented model class is exported from the persistence package."""
    assert len(MODEL_CLASSES) == 20
    for cls in MODEL_CLASSES:
        assert cls.__table__ is not None


def test_metadata_contains_exactly_the_20_documented_tables() -> None:
    tables = set(Base.metadata.tables)
    assert tables == set(DOCUMENTED_TABLES)
    assert len(tables) == 20


def test_model_classes_map_to_documented_table_names() -> None:
    assert [cls.__tablename__ for cls in MODEL_CLASSES] == DOCUMENTED_TABLES
    for cls, table_name in zip(MODEL_CLASSES, DOCUMENTED_TABLES, strict=True):
        assert cls.__table__ is Base.metadata.tables[table_name]


def test_single_declarative_root_shared_metadata() -> None:
    """A single exported DeclarativeBase root owns every table's metadata."""
    assert isinstance(Base, type)
    assert Base.metadata is not None
    for cls in MODEL_CLASSES:
        assert cls.__table__.metadata is Base.metadata


def test_mappers_configure_without_errors() -> None:
    """All relationship wiring resolves (raises on invalid primaryjoin/FK)."""
    configure_mappers()


def test_extension_exclusion_objects_kept_out_of_models() -> None:
    """VNLRAG-38-only objects (btree_gist exclusion, normalize_ref_text
    partial unique index) must not be declared in the models (docs/03 §3.10.4)."""
    legal_provisions = Base.metadata.tables["legal_provisions"]
    constraint_names = {c.name for c in legal_provisions.constraints}
    assert "legal_provisions_no_overlap_accepted" not in constraint_names
    assert not any(
        "EXCLUDE" in str(getattr(c, "sqltext", "")) for c in legal_provisions.constraints
    )

    provision_references = Base.metadata.tables["provision_references"]
    index_names = {i.name for i in provision_references.indexes}
    assert "provision_references_unresolved_pk" not in index_names
    assert not any("normalize_ref_text" in str(i.expressions) for i in provision_references.indexes)
    reference_constraints = {c.name for c in provision_references.constraints}
    assert "provision_references_target_resolution_check" in reference_constraints


def test_no_undocumented_tables_or_functions() -> None:
    """Metadata must not contain extension/bootstrap-only objects."""
    for table in Base.metadata.tables.values():
        assert "normalize_ref_text" not in " ".join(
            str(getattr(c, "sqltext", "")) for c in table.constraints
        )
