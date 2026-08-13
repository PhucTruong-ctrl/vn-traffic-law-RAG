"""Unit tests: parser provenance aggregation for legal provisions (VNLRAG-29).

Covers single-source aggregation (``source_element_ids`` -> one record per
id, page/bbox inheritance), multi-source amendment aggregation (per-source
roles), and the exact ``provenance_coverage`` cross-ticket contract (0.0 for
empty, full = 1.0, partial arithmetic, both conditions required).
"""

from __future__ import annotations

import hashlib
from uuid import uuid4

from app.ingestion.provenance import (
    ProvenanceRecord,
    aggregate_multi_source_provenance,
    aggregate_provenance,
    provenance_coverage,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision


def _provision(**overrides: object) -> ExtractedLegalProvision:
    """Synthetic extractor provision with 3 source elements on page 3."""
    source_text = "Nội dung điều 1."
    fields: dict[str, object] = {
        "provision_id": "nd-168-2024__dieu-1",
        "document_version_id": "version-1",
        "chapter": None,
        "section": None,
        "article": "Điều 1",
        "clause": None,
        "point": None,
        "heading": None,
        "source_text": source_text,
        "retrieval_text": source_text,
        "parent_context": None,
        "effective_from": None,
        "effective_to": None,
        "status": "UNKNOWN",
        "page_number": 3,
        "bbox": {"left": 0.1, "top": 0.2, "right": 0.9, "bottom": 0.4},
        "source_element_ids": ["e1", "e2", "e3"],
        "content_hash": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "version": 1,
        "review_status": "PENDING",
        "node_kind": "ARTICLE",
    }
    fields.update(overrides)
    return ExtractedLegalProvision(**fields)


# ─────────────────────────── single-source aggregation ───────────────────────────


def test_single_source_maps_each_element_id_with_inherited_page_and_bbox() -> None:
    provision = _provision(source_element_ids=["e1", "e2"])
    row_id, source_version_id = uuid4(), uuid4()

    records = aggregate_provenance(
        provision,
        provision_version_row_id=row_id,
        source_document_version_id=source_version_id,
    )

    assert [record.source_element_id for record in records] == ["e1", "e2"]
    assert all(record.provision_version_row_id == row_id for record in records)
    assert all(record.source_document_version_id == source_version_id for record in records)
    assert all(record.page_number == 3 for record in records)
    assert all(record.bbox == provision.bbox for record in records)
    assert all(record.role == "BASE_TEXT" for record in records)


def test_single_source_role_is_applied_to_all_records() -> None:
    provision = _provision(source_element_ids=["e1", "e2"])

    records = aggregate_provenance(
        provision,
        provision_version_row_id=uuid4(),
        source_document_version_id=uuid4(),
        role="CORRECTION_TEXT",
    )

    assert len(records) == 2
    assert all(record.role == "CORRECTION_TEXT" for record in records)


def test_single_source_inherits_null_bbox() -> None:
    provision = _provision(bbox=None)

    records = aggregate_provenance(
        provision,
        provision_version_row_id=uuid4(),
        source_document_version_id=uuid4(),
    )

    assert len(records) == 3
    assert all(record.bbox is None for record in records)


def test_records_are_typed_provenance_records() -> None:
    records = aggregate_provenance(
        _provision(),
        provision_version_row_id=uuid4(),
        source_document_version_id=uuid4(),
    )
    assert records
    assert all(isinstance(record, ProvenanceRecord) for record in records)


# ─────────────────────────── multi-source aggregation ───────────────────────────


def test_multi_source_amendment_records_carry_per_source_role() -> None:
    """Amended clause: base text element + amendment element -> per-source
    roles, never assuming one source document per provision version."""
    provision = _provision(source_element_ids=["e1", "e2", "e3"])
    row_id, base_version_id, amendment_version_id = uuid4(), uuid4(), uuid4()

    records = aggregate_multi_source_provenance(
        provision,
        provision_version_row_id=row_id,
        sources=[
            (base_version_id, "BASE_TEXT", ["e1", "e2"]),
            (amendment_version_id, "AMENDMENT_TEXT", ["e3"]),
        ],
    )

    assert len(records) == 3
    by_element = {record.source_element_id: record for record in records}
    assert by_element["e1"].role == "BASE_TEXT"
    assert by_element["e2"].role == "BASE_TEXT"
    assert by_element["e3"].role == "AMENDMENT_TEXT"
    assert by_element["e1"].source_document_version_id == base_version_id
    assert by_element["e2"].source_document_version_id == base_version_id
    assert by_element["e3"].source_document_version_id == amendment_version_id
    # page/bbox still inherited from the provision; row id shared.
    assert all(record.page_number == 3 for record in records)
    assert all(record.bbox == provision.bbox for record in records)
    assert all(record.provision_version_row_id == row_id for record in records)


def test_multi_source_supports_three_roles() -> None:
    provision = _provision(source_element_ids=["e1", "e2", "e3"])
    base, amendment, correction = uuid4(), uuid4(), uuid4()

    records = aggregate_multi_source_provenance(
        provision,
        provision_version_row_id=uuid4(),
        sources=[
            (base, "BASE_TEXT", ["e1"]),
            (amendment, "AMENDMENT_TEXT", ["e2"]),
            (correction, "CORRECTION_TEXT", ["e3"]),
        ],
    )

    roles = {record.source_element_id: record.role for record in records}
    assert roles == {"e1": "BASE_TEXT", "e2": "AMENDMENT_TEXT", "e3": "CORRECTION_TEXT"}


def test_multi_source_requires_full_attribution() -> None:
    """Every source element must be attributed to exactly one source."""
    provision = _provision(source_element_ids=["e1", "e2", "e3"])

    try:
        aggregate_multi_source_provenance(
            provision,
            provision_version_row_id=uuid4(),
            sources=[(uuid4(), "BASE_TEXT", ["e1"])],
        )
    except ValueError as error:
        assert "do not match" in str(error)
    else:  # pragma: no cover - failure would mean the guard is missing
        raise AssertionError("expected ValueError for incomplete attribution")

    # Duplicate attribution is equally invalid.
    try:
        aggregate_multi_source_provenance(
            provision,
            provision_version_row_id=uuid4(),
            sources=[
                (uuid4(), "BASE_TEXT", ["e1", "e2"]),
                (uuid4(), "AMENDMENT_TEXT", ["e2", "e3"]),
            ],
        )
    except ValueError as error:
        assert "do not match" in str(error)
    else:  # pragma: no cover - failure would mean the guard is missing
        raise AssertionError("expected ValueError for overlapping attribution")


# ─────────────────────────── provenance coverage ───────────────────────────


def test_coverage_empty_list_is_zero() -> None:
    assert provenance_coverage([]) == 0.0


def test_coverage_full_is_one() -> None:
    provisions = [_provision(provision_id=f"nd-168-2024__dieu-{i}") for i in range(1, 4)]
    assert provenance_coverage(provisions) == 1.0


def test_coverage_partial_arithmetic() -> None:
    """Only provisions with BOTH >=1 source_element_id and a non-null
    page_number count as covered."""
    covered_1 = _provision(provision_id="nd-168-2024__dieu-1")
    covered_2 = _provision(provision_id="nd-168-2024__dieu-2")
    no_elements = _provision(provision_id="nd-168-2024__dieu-3").model_copy(
        update={"source_element_ids": []}
    )
    no_page = _provision(provision_id="nd-168-2024__dieu-4").model_copy(
        update={"page_number": None}
    )

    assert provenance_coverage([covered_1, no_elements]) == 0.5
    assert provenance_coverage([no_elements, no_page]) == 0.0
    assert provenance_coverage([covered_1, covered_2, no_elements, no_page]) == 0.5


def test_coverage_requires_both_conditions() -> None:
    """Element ids without a page, and a page without element ids, are both
    uncovered — the contract needs the conjunction."""
    with_elements_no_page = _provision().model_copy(update={"page_number": None})
    no_elements_with_page = _provision().model_copy(update={"source_element_ids": []})
    assert provenance_coverage([with_elements_no_page]) == 0.0
    assert provenance_coverage([no_elements_with_page]) == 0.0
