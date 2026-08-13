"""Unit tests: Qdrant legal-provision store (VNLRAG-40) — no live Qdrant needed.

Covers the doc 03 §3.11 contract implemented in ``app.retrieval.qdrant_store``:
- ``payload_for_unit`` payload mapping completeness (exact doc-03 key set,
  ``extra='forbid'``-style validation of bounded relation metadata);
- the collection config builders, asserted directly as config dicts;
- module constants (collection/alias names, dense/sparse vector contract).
"""

from __future__ import annotations

import pytest
from qdrant_client import models

from app.ingestion.retrieval_units import RetrievalUnit
from app.retrieval import qdrant_store
from app.retrieval.qdrant_store import (
    DENSE_VECTOR_DISTANCE,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    PAYLOAD_INDEX_FIELDS,
    PROVISION_ALIAS,
    PROVISION_COLLECTION,
    SPARSE_VECTOR_NAME,
    build_collection_config,
    build_sparse_vectors_config,
    build_vectors_config,
    payload_for_unit,
)

#: The exact doc 03 §3.11.3 payload key set the contract mandates (doc names).
DOC_03_311_KEYS = frozenset(
    {
        "provision_id",
        "provision_version",
        "document_id",
        "document_version",
        "document_number",
        "document_type",
        "document_title",
        "article",
        "clause",
        "point",
        "chapter",
        "section",
        "vehicle_types",
        "effective_from",
        "effective_to",
        "document_status",
        "review_status",
        "page_number",
        "content_hash",
        "parser",
        "parser_version",
        "legal_parser_version",
        "sparse_encoder_version",
        "text",
        "parent_context",
        "relations",
    }
)

#: The full key set ``payload_for_unit`` emits: the doc 03 §3.11.3 keys plus
#: the ingest-only extras (node_kind/heading hierarchy filters, content
#: version, verbatim citation text, document-version UUID).
PAYLOAD_KEYS = DOC_03_311_KEYS | frozenset(
    {
        "node_kind",
        "heading",
        "content_version",
        "source_text",
        "document_version_id",
    }
)


def _unit(**overrides: object) -> RetrievalUnit:
    values: dict[str, object] = {
        "unit_id": "nd-168-2024__dieu-7__khoan-4__diem-b__v1",
        "provision_id": "nd-168-2024__dieu-7__khoan-4__diem-b",
        "version": 1,
        "node_kind": "POINT",
        "retrieval_text": "Khoản 4 Điều 7: a) Điều khiển xe lạng lách, đánh võng",
        "source_text": "a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "parent_context": "Khoản 4 Điều 7 Nghị định 168/2024/NĐ-CP",
        "page_number": 12,
        "document_id": "8f3c1a2b-4d5e-4f6a-9b8c-7d6e5f4a3b2c",
        "short_point": True,
    }
    values.update(overrides)
    return RetrievalUnit(**values)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Constants — cross-ticket collection contract
# ---------------------------------------------------------------------------


def test_collection_contract_constants() -> None:
    assert PROVISION_COLLECTION == "legal_provisions_v1"
    assert PROVISION_ALIAS == "legal_provisions_active"
    assert DENSE_VECTOR_NAME == "dense"
    assert DENSE_VECTOR_SIZE == 768
    assert DENSE_VECTOR_DISTANCE == models.Distance.COSINE
    assert SPARSE_VECTOR_NAME == "sparse"


def test_payload_index_fields_cover_required_set() -> None:
    assert set(PAYLOAD_INDEX_FIELDS) >= {
        "provision_id",
        "document_id",
        "node_kind",
        "chapter",
        "section",
        "article",
        "clause",
        "point",
        "heading",
        "effective_from",
        "effective_to",
        "review_status",
        "vehicle_types",
    }


# ---------------------------------------------------------------------------
# Collection config builders (config dicts asserted directly, no Qdrant)
# ---------------------------------------------------------------------------


def test_build_vectors_config_named_dense_cosine_768() -> None:
    vectors = build_vectors_config()
    assert set(vectors) == {DENSE_VECTOR_NAME}
    params = vectors[DENSE_VECTOR_NAME]
    assert isinstance(params, models.VectorParams)
    assert params.size == DENSE_VECTOR_SIZE
    assert params.distance == models.Distance.COSINE


def test_build_sparse_vectors_config_bm25_idf() -> None:
    sparse = build_sparse_vectors_config()
    assert set(sparse) == {SPARSE_VECTOR_NAME}
    params = sparse[SPARSE_VECTOR_NAME]
    assert isinstance(params, models.SparseVectorParams)
    assert params.modifier == models.Modifier.IDF
    assert params.index is not None and params.index.on_disk is False


def test_build_collection_config_combines_dense_and_sparse() -> None:
    config = build_collection_config()
    assert set(config) == {"vectors_config", "sparse_vectors_config"}
    assert config["vectors_config"] == build_vectors_config()
    assert config["sparse_vectors_config"] == build_sparse_vectors_config()


# ---------------------------------------------------------------------------
# payload_for_unit — mapping completeness (extra='forbid' style)
# ---------------------------------------------------------------------------


def test_payload_contains_exactly_the_contract_keys() -> None:
    payload = payload_for_unit(_unit())
    assert set(payload) == PAYLOAD_KEYS


def test_payload_emits_full_doc_3113_key_set() -> None:
    """The FULL doc 03 §3.11.3 payload key set is emitted, with doc names."""
    payload = payload_for_unit(_unit())
    assert DOC_03_311_KEYS <= set(payload)


def test_payload_maps_unit_fields_and_defaults() -> None:
    unit = _unit()
    payload = payload_for_unit(unit)
    assert payload["provision_id"] == unit.provision_id
    assert payload["provision_version"] == unit.version
    assert payload["node_kind"] == unit.node_kind
    assert payload["text"] == unit.retrieval_text
    assert payload["source_text"] == unit.source_text
    assert payload["document_id"] == unit.document_id
    # document_version_id defaults to the unit's document id (the document
    # version UUID carried by RetrievalUnit.build_retrieval_units).
    assert payload["document_version_id"] == unit.document_id
    # Unit-mapped doc 03 §3.11.3 fields.
    assert payload["page_number"] == unit.page_number
    assert payload["parent_context"] == unit.parent_context
    # Metadata defaults.
    assert payload["review_status"] == "PENDING"
    assert payload["content_version"] == 1
    assert payload["relations"] == []
    assert payload["vehicle_types"] == []
    for field in (
        "effective_from",
        "effective_to",
        "document_status",
        "parser_version",
        "chapter",
        "section",
        "article",
        "clause",
        "point",
        "heading",
        "document_number",
        "document_type",
        "document_title",
        "document_version",
        "parser",
        "legal_parser_version",
        "sparse_encoder_version",
        "content_hash",
    ):
        assert payload[field] is None


def test_payload_applies_metadata_overrides() -> None:
    unit = _unit()
    payload = payload_for_unit(
        unit,
        review_status="ACCEPTED",
        effective_from="2025-01-01",
        effective_to="2026-01-01",
        parser_version="docling-2.1.0",
        content_version=3,
        relations=[{"relation_type": "PENALTY_COMPANION", "target_provision_id": "p-9"}],
        vehicle_types=["MOTORCYCLE", "CAR"],
        document_version_id="11111111-2222-3333-4444-555555555555",
        document_status="EFFECTIVE",
        chapter="Chương I",
        section="Mục 1",
        article="7",
        clause="4",
        point="b",
        heading=None,
        document_number="168/2024/NĐ-CP",
        document_type="DECREE",
        document_title="Nghị định quy định xử phạt vi phạm hành chính",
        document_version=2,
        parser="DOCLING",
        legal_parser_version="vnlrag-legal-parser-v1",
        sparse_encoder_version="qdrant-bm25-v1",
        content_hash="a" * 64,
    )
    assert payload["review_status"] == "ACCEPTED"
    assert payload["effective_from"] == "2025-01-01"
    assert payload["effective_to"] == "2026-01-01"
    assert payload["parser_version"] == "docling-2.1.0"
    assert payload["content_version"] == 3
    assert payload["relations"] == [
        {"relation_type": "PENALTY_COMPANION", "target_provision_id": "p-9"}
    ]
    assert payload["vehicle_types"] == ["MOTORCYCLE", "CAR"]
    assert payload["document_version_id"] == "11111111-2222-3333-4444-555555555555"
    assert payload["document_status"] == "EFFECTIVE"
    assert payload["chapter"] == "Chương I"
    assert payload["section"] == "Mục 1"
    assert payload["article"] == "7"
    assert payload["clause"] == "4"
    assert payload["point"] == "b"
    assert payload["heading"] is None
    assert payload["document_number"] == "168/2024/NĐ-CP"
    assert payload["document_type"] == "DECREE"
    assert payload["document_title"] == "Nghị định quy định xử phạt vi phạm hành chính"
    assert payload["document_version"] == 2
    assert payload["parser"] == "DOCLING"
    assert payload["legal_parser_version"] == "vnlrag-legal-parser-v1"
    assert payload["sparse_encoder_version"] == "qdrant-bm25-v1"
    assert payload["content_hash"] == "a" * 64


def test_payload_document_version_id_override_independent_of_unit() -> None:
    payload = payload_for_unit(_unit(), document_version_id="custom-version-id")
    assert payload["document_version_id"] == "custom-version-id"
    assert payload["document_id"] == _unit().document_id


# ---------------------------------------------------------------------------
# payload_for_unit — bounded metadata validation (extra='forbid' style)
# ---------------------------------------------------------------------------


def test_payload_rejects_relation_with_extra_keys() -> None:
    unit = _unit()
    with pytest.raises(ValueError, match="must contain exactly"):
        payload_for_unit(
            unit,
            relations=[{"relation_type": "REFERS_TO", "target_provision_id": "p-1", "extra": 1}],
        )


def test_payload_rejects_relation_with_missing_keys() -> None:
    unit = _unit()
    with pytest.raises(ValueError, match="must contain exactly"):
        payload_for_unit(unit, relations=[{"relation_type": "REFERS_TO"}])


def test_payload_rejects_non_dict_relation_entry() -> None:
    unit = _unit()
    with pytest.raises(ValueError, match="must be dicts"):
        payload_for_unit(unit, relations=["REFERS_TO"])  # type: ignore[list-item]


def test_payload_rejects_empty_relation_values() -> None:
    unit = _unit()
    with pytest.raises(ValueError, match="non-empty string"):
        payload_for_unit(
            unit,
            relations=[{"relation_type": "", "target_provision_id": "p-1"}],
        )


def test_payload_rejects_invalid_vehicle_types() -> None:
    unit = _unit()
    with pytest.raises(ValueError, match="vehicle_types"):
        payload_for_unit(unit, vehicle_types=["MOTORCYCLE", ""])
    with pytest.raises(ValueError, match="vehicle_types"):
        payload_for_unit(unit, vehicle_types="MOTORCYCLE")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_exports() -> None:
    for name in (
        "PROVISION_COLLECTION",
        "PROVISION_ALIAS",
        "DENSE_VECTOR_NAME",
        "DENSE_VECTOR_SIZE",
        "DENSE_VECTOR_DISTANCE",
        "SPARSE_VECTOR_NAME",
        "PAYLOAD_INDEX_FIELDS",
        "build_vectors_config",
        "build_sparse_vectors_config",
        "build_collection_config",
        "payload_for_unit",
        "ensure_qdrant_collection",
        "rebuild_alias",
        "get_collection_info",
    ):
        assert hasattr(qdrant_store, name), name
