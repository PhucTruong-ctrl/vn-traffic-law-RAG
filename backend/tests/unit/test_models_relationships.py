"""Unit tests: relationship wiring and object instantiation for all 20 models.

Covers docs/03 §3.9.15 ("Mối quan hệ quan trọng"): every documented
relationship is declared on both sides, mappers configure cleanly, objects
instantiate with the documented required fields, and non-viewonly backrefs
synchronize. Viewonly logical relationships (document_relations /
legal_effect_events) are verified via their join conditions.
"""

from datetime import date
from uuid import uuid4

from sqlalchemy import Integer, inspect

from app.persistence import (
    Base,
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

# {Model: {relationship key: target model class name}} per docs/03 §3.9.15.
EXPECTED_RELATIONSHIPS = {
    "LegalSource": {"documents": "LegalDocument"},
    "LegalDocument": {
        "source": "LegalSource",
        "versions": "DocumentVersion",
        "source_relations": "DocumentRelation",
        "target_relations": "DocumentRelation",
        "effect_events": "LegalEffectEvent",
        "parsed_documents": "ParsedDocument",
    },
    "DocumentVersion": {
        "document": "LegalDocument",
        "provisions": "LegalProvision",
        "provision_versions": "ProvisionVersion",
        "provenance_records": "ProvisionProvenance",
    },
    "LegalProvision": {
        "document_version": "DocumentVersion",
        "version_registry_entries": "ProvisionVersion",
        "provenance_records": "ProvisionProvenance",
        "source_references": "ProvisionReference",
        "target_references": "ProvisionReference",
    },
    "ProvisionVersion": {
        "provision": "LegalProvision",
        "document_version": "DocumentVersion",
    },
    "ProvisionProvenance": {
        "provision_version": "LegalProvision",
        "source_document_version": "DocumentVersion",
    },
    "ProvisionReference": {
        "source_provision": "LegalProvision",
        "target_provision": "LegalProvision",
    },
    "DocumentRelation": {
        "source_document": "LegalDocument",
        "target_document": "LegalDocument",
    },
    "LegalEffectEvent": {"document": "LegalDocument"},
    "ParsedDocument": {
        "legal_document": "LegalDocument",
        "elements": "DocumentElement",
    },
    "DocumentElement": {"parsed_document": "ParsedDocument"},
    "IngestionRun": {
        "artifacts": "IngestionArtifact",
        "review_items": "ReviewItem",
    },
    "IngestionArtifact": {"ingestion_run": "IngestionRun"},
    "ReviewItem": {"ingestion_run": "IngestionRun"},
    "QueryTrace": {"feedback_items": "QueryFeedback"},
    "QueryFeedback": {"query_trace": "QueryTrace"},
    "EvaluationDataset": {},
    "EvaluationRun": {"results": "EvaluationResult"},
    "EvaluationResult": {"evaluation_run": "EvaluationRun"},
    "CorpusQaReport": {},
}

ALL_MODELS = {
    "LegalSource": LegalSource,
    "LegalDocument": LegalDocument,
    "DocumentVersion": DocumentVersion,
    "LegalProvision": LegalProvision,
    "ProvisionVersion": ProvisionVersion,
    "ProvisionProvenance": ProvisionProvenance,
    "ProvisionReference": ProvisionReference,
    "DocumentRelation": DocumentRelation,
    "LegalEffectEvent": LegalEffectEvent,
    "ParsedDocument": ParsedDocument,
    "DocumentElement": DocumentElement,
    "IngestionRun": IngestionRun,
    "IngestionArtifact": IngestionArtifact,
    "ReviewItem": ReviewItem,
    "QueryTrace": QueryTrace,
    "QueryFeedback": QueryFeedback,
    "EvaluationDataset": EvaluationDataset,
    "EvaluationRun": EvaluationRun,
    "EvaluationResult": EvaluationResult,
    "CorpusQaReport": CorpusQaReport,
}

BIDIRECTIONAL_PAIRS = [
    ("LegalSource", "documents", "LegalDocument", "source"),
    ("LegalDocument", "versions", "DocumentVersion", "document"),
    ("DocumentVersion", "provisions", "LegalProvision", "document_version"),
    ("DocumentVersion", "provision_versions", "ProvisionVersion", "document_version"),
    ("LegalProvision", "version_registry_entries", "ProvisionVersion", "provision"),
    ("LegalProvision", "provenance_records", "ProvisionProvenance", "provision_version"),
    ("DocumentVersion", "provenance_records", "ProvisionProvenance", "source_document_version"),
    ("LegalProvision", "source_references", "ProvisionReference", "source_provision"),
    ("LegalProvision", "target_references", "ProvisionReference", "target_provision"),
    ("LegalDocument", "source_relations", "DocumentRelation", "source_document"),
    ("LegalDocument", "target_relations", "DocumentRelation", "target_document"),
    ("LegalDocument", "effect_events", "LegalEffectEvent", "document"),
    ("LegalDocument", "parsed_documents", "ParsedDocument", "legal_document"),
    ("ParsedDocument", "elements", "DocumentElement", "parsed_document"),
    ("IngestionRun", "artifacts", "IngestionArtifact", "ingestion_run"),
    ("IngestionRun", "review_items", "ReviewItem", "ingestion_run"),
    ("QueryTrace", "feedback_items", "QueryFeedback", "query_trace"),
    ("EvaluationRun", "results", "EvaluationResult", "evaluation_run"),
]


def test_all_documented_relationships_wired() -> None:
    for class_name, expected in EXPECTED_RELATIONSHIPS.items():
        relationships = inspect(ALL_MODELS[class_name]).relationships
        actual = {r.key for r in relationships}
        assert actual == set(expected), f"{class_name}: {actual ^ set(expected)}"
        for key, target in expected.items():
            assert relationships[key].mapper.class_.__name__ == target, f"{class_name}.{key}"


def test_documented_relationships_are_bidirectional() -> None:
    for left, left_rel, right, right_rel in BIDIRECTIONAL_PAIRS:
        lrel = inspect(ALL_MODELS[left]).relationships[left_rel]
        rrel = inspect(ALL_MODELS[right]).relationships[right_rel]
        assert lrel.back_populates == right_rel, f"{left}.{left_rel}"
        assert rrel.back_populates == left_rel, f"{right}.{right_rel}"


def test_logical_relationships_are_viewonly_with_document_id_joins() -> None:
    """document_relations / legal_effect_events join on the logical
    document_id (no physical FK) and must be viewonly (docs/03 §3.9.15)."""
    for class_name, rel_key in (
        ("DocumentRelation", "source_document"),
        ("DocumentRelation", "target_document"),
        ("LegalEffectEvent", "document"),
        ("LegalDocument", "source_relations"),
        ("LegalDocument", "target_relations"),
        ("LegalDocument", "effect_events"),
    ):
        rel = inspect(ALL_MODELS[class_name]).relationships[rel_key]
        assert rel.viewonly, f"{class_name}.{rel_key}"
        assert "document_id" in str(rel.primaryjoin), f"{class_name}.{rel_key} join"


def test_all_models_instantiate_with_required_fields() -> None:
    LegalSource(source_id="gov", source_name="Cổng TTĐT Chính phủ", source_type="GOV_PORTAL")
    LegalDocument(
        document_id="nd-168-2024",
        document_number="168/2024/NĐ-CP",
        document_title="Nghị định 168/2024/NĐ-CP",
        document_type="DECREE",
        file_hash="sha256:abcd",
        status="EFFECTIVE",
    )
    DocumentVersion(document_id="nd-168-2024", version=1, manifest_json={"x": 1}, content_hash="c")
    LegalProvision(
        provision_id="nd-168-2024__dieu-7",
        document_version_id=uuid4(),
        source_text="s",
        retrieval_text="r",
        status="EFFECTIVE",
        page_number=3,
        content_hash="c",
        version=1,
    )
    ProvisionVersion(
        provision_id="nd-168-2024__dieu-7",
        version=1,
        document_version_id=uuid4(),
    )
    ProvisionProvenance(
        provision_version_row_id=uuid4(),
        source_document_version_id=uuid4(),
        source_element_id="e1",
        page_number=3,
        role="BASE_TEXT",
    )
    ProvisionReference(
        source_legal_provision_id=uuid4(),
        source_provision_id="nd-168-2024__dieu-7",
        relation_type="REFERS_TO",
        extraction_method="TEXT_PATTERN",
        source_text="ref",
    )
    DocumentRelation(
        source_document_id="nd-168-2024",
        target_document_id="nd-100-2019",
        relation_type="SUPERSEDES",
        source="MANIFEST",
    )
    LegalEffectEvent(
        document_id="nd-168-2024",
        event_type="EFFECTIVE",
        event_date=date(2025, 1, 1),
    )
    ParsedDocument(
        document_id="nd-168-2024",
        parser="docling",
        parser_version="2.118.1",
        ir_schema_version="1.0",
        source_object_key="source-pdfs/nd-168.pdf",
        parse_status="PARSING",
    )
    DocumentElement(
        parsed_document_id=None,
        element_id="el-1",
        element_type="paragraph",
        text="Điều 7.",
        page_number=3,
        reading_order=5,
        source_parser="docling",
        parser_version="2.118.1",
    )
    IngestionRun(
        job_id="job-1",
        document_id="nd-168-2024",
        manifest_json={"file": "nd-168.pdf"},
        file_hash="sha256:abcd",
        status="QUEUED",
    )
    IngestionArtifact(
        ingestion_run_id=None,
        artifact_type="SOURCE_PDF",
        bucket="source-pdfs",
        object_key="nd-168.pdf",
        size=1024,
    )
    ReviewItem(
        ingestion_run_id=None,
        document_id="nd-168-2024",
        target_type="PROVISION",
        target_id="nd-168-2024__dieu-7",
        reason_code="LOW_OCR_COVERAGE",
    )
    QueryTrace(
        trace_id="trace-1",
        question="Mức phạt lỗi vượt đèn vàng?",
        intent="CURRENT",
        response_status="VERIFIED",
    )
    QueryFeedback(query_trace_id=None, useful=True)
    EvaluationDataset(
        dataset_id="gold-v1",
        name="Gold v1",
        split="VALIDATION",
        version="1.0",
        hash="sha256:gold",
        questions_path="data/gold/validation.json",
    )
    EvaluationRun(
        run_id="run-1",
        git_commit="abc1234",
        corpus_version="v1",
        corpus_hash="sha256:corpus",
        gold_set_version="1.0",
        gold_set_hash="sha256:gold",
        suite="A",
        variant="P1",
        run_manifest_hash="sha256:manifest",
        config_snapshot={"top_k": 8},
        model_ids={"embedding": "gemini-embedding-2"},
        prompt_versions={"query_analyzer": "v3"},
        parser_versions={"docling": "2.118.1"},
        raw_results_path="data/eval/run-1/results.json",
    )
    EvaluationResult(
        evaluation_run_id=None,
        question_id="q-1",
        input={"question": "?"},
        retrieval={"hits": []},
        output={"answer": "..."},
        metrics={"precision": 0.9},
    )
    CorpusQaReport(
        report_id="qa-1",
        corpus_version="v1",
        corpus_hash="sha256:corpus",
        metrics={"article_count": 10},
    )


def test_relationship_object_graph_wiring() -> None:
    source = LegalSource(source_id="gov", source_name="Cổng", source_type="GOV_PORTAL")
    document = LegalDocument(
        document_id="nd-168-2024",
        document_number="168/2024/NĐ-CP",
        document_title="Nghị định 168",
        document_type="DECREE",
        file_hash="sha256:abcd",
        status="EFFECTIVE",
        source=source,
    )
    version = DocumentVersion(
        document_id="nd-168-2024",
        version=1,
        manifest_json={"title": "ND 168"},
        content_hash="c1",
        document=document,
    )
    provision = LegalProvision(
        provision_id="nd-168-2024__dieu-7",
        document_version_id=uuid4(),
        source_text="Điều 7.",
        retrieval_text="Điều 7.",
        status="EFFECTIVE",
        page_number=3,
        content_hash="c1",
        version=1,
        document_version=version,
    )
    provenance = ProvisionProvenance(
        provision_version_row_id=uuid4(),
        source_document_version_id=uuid4(),
        source_element_id="el-9",
        page_number=3,
        role="BASE_TEXT",
        provision_version=provision,
        source_document_version=version,
    )
    registry = ProvisionVersion(
        provision_id=provision.provision_id,
        version=provision.version,
        document_version_id=uuid4(),
        provision=provision,
    )
    reference = ProvisionReference(
        source_legal_provision_id=uuid4(),
        source_provision_id=provision.provision_id,
        relation_type="PENALTY_COMPANION",
        extraction_method="PENALTY_INFERENCE",
        source_text="điểm b",
        source_provision=provision,
    )
    parsed = ParsedDocument(
        document_id="nd-168-2024",
        parser="docling",
        parser_version="2.118.1",
        ir_schema_version="1.0",
        source_object_key="source-pdfs/nd-168.pdf",
        parse_status="PARSING",
        legal_document=document,
    )
    element = DocumentElement(
        parsed_document_id=None,
        element_id="el-9",
        element_type="paragraph",
        text="Điều 7.",
        page_number=3,
        reading_order=5,
        source_parser="docling",
        parser_version="2.118.1",
        parsed_document=parsed,
    )
    run = IngestionRun(
        job_id="job-1",
        document_id="nd-168-2024",
        manifest_json={"file": "nd-168.pdf"},
        file_hash="sha256:abcd",
        status="QUEUED",
    )
    artifact = IngestionArtifact(
        ingestion_run_id=None,
        artifact_type="SOURCE_PDF",
        bucket="source-pdfs",
        object_key="nd-168.pdf",
        size=1024,
        ingestion_run=run,
    )
    review = ReviewItem(
        ingestion_run_id=None,
        document_id="nd-168-2024",
        target_type="PROVISION",
        target_id="nd-168-2024__dieu-7",
        reason_code="UNRESOLVED_REFERENCE",
        ingestion_run=run,
    )
    trace = QueryTrace(
        trace_id="trace-1",
        question="Mức phạt?",
        intent="CURRENT",
        response_status="VERIFIED",
    )
    feedback = QueryFeedback(query_trace_id=None, useful=False, query_trace=trace)
    eval_run = EvaluationRun(
        run_id="run-1",
        git_commit="abc1234",
        corpus_version="v1",
        corpus_hash="h",
        gold_set_version="1.0",
        gold_set_hash="h",
        suite="A",
        variant="P1",
        run_manifest_hash="h",
        config_snapshot={},
        model_ids={},
        prompt_versions={},
        parser_versions={},
        raw_results_path="p",
    )
    eval_result = EvaluationResult(
        evaluation_run_id=None,
        question_id="q-1",
        input={},
        retrieval={},
        output={},
        metrics={},
        evaluation_run=eval_run,
    )

    assert document.source is source and source.documents == [document]
    assert version.document is document and document.versions == [version]
    assert provision.document_version is version and version.provisions == [provision]
    assert provenance.provision_version is provision and provision.provenance_records == [
        provenance
    ]
    assert provenance.source_document_version is version
    assert version.provenance_records == [provenance]
    assert registry.provision is provision and provision.version_registry_entries == [registry]
    assert reference.source_provision is provision and provision.source_references == [reference]
    assert element.parsed_document is parsed and parsed.elements == [element]
    assert parsed.legal_document is document and document.parsed_documents == [parsed]
    assert artifact.ingestion_run is run and run.artifacts == [artifact]
    assert review.ingestion_run is run and run.review_items == [review]
    assert feedback.query_trace is trace and trace.feedback_items == [feedback]
    assert eval_result.evaluation_run is eval_run and eval_run.results == [eval_result]


def test_documented_column_count_is_stable() -> None:
    """Column totals per table, from the docs/03 §3.10.2 DDL."""
    expected = {
        "legal_sources": 9,
        "legal_documents": 14,
        "document_versions": 9,
        "legal_provisions": 23,
        "provision_versions": 7,
        "provision_provenances": 8,
        "provision_references": 14,
        "document_relations": 13,
        "legal_effect_events": 11,
        "parsed_documents": 10,
        "document_elements": 14,
        "ingestion_runs": 13,
        "ingestion_artifacts": 8,
        "review_items": 12,
        "query_traces": 18,
        "query_feedback": 6,
        "evaluation_datasets": 8,
        "evaluation_runs": 20,
        "evaluation_results": 8,
        "corpus_qa_reports": 8,
    }
    assert len(expected) == 20
    for table_name, count in expected.items():
        assert len(Base.metadata.tables[table_name].columns) == count, table_name


def test_ingestion_run_columns_use_documented_types() -> None:
    table = Base.metadata.tables["ingestion_runs"]
    assert isinstance(table.c.retry_count.type, Integer)
    assert table.c.retry_count.nullable is False
    assert "0" in str(table.c.retry_count.server_default.arg)
