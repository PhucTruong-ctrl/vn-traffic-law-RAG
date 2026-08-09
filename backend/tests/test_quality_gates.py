"""Tests for ingestion quality gates (VNLRAG-131).

Covers the OPERATIONAL Group A (parser-level) gates and the Group B
(structural) CONTRACT. All documents are synthetic ``ParsedDocument`` IR —
gates must be testable without any parser backend.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.quality_gates import (
    GroupAResult,
    GroupAThresholds,
    GroupBContract,
    GroupBThresholds,
    evaluate_group_a,
    evaluate_group_b,
    layout_coherence,
    provenance_coverage,
    table_detection_rate,
    text_extraction_rate,
)

_PARSED_DOCUMENT_ID = "a1b2c3d4-0000-4000-8000-000000000000"


def _element(
    reading_order: int,
    *,
    bbox: BoundingBox | None = None,
    text: str = "Nội dung đoạn văn.",
    element_type: str = "paragraph",
) -> DocumentElement:
    return DocumentElement(
        element_id=f"e{reading_order}",
        element_type=element_type,
        text=text,
        page_number=1,
        bbox=bbox,
        reading_order=reading_order,
        parent_element_id=None,
        table_html=None,
        source_parser="DOCLING",
        parser_version="docling-2.118.1",
        parser_confidence=None,
        raw_reference={"docling_item_index": reading_order},
    )


def _box() -> BoundingBox:
    return BoundingBox(left=1.0, top=2.0, right=3.0, bottom=4.0)


def _page(page_number: int, elements: list[DocumentElement], text: str | None = None) -> ParsedPage:
    page_text = (
        text
        if text is not None
        else ("\n".join(e.text for e in elements if e.text.strip()) or None)
    )
    return ParsedPage(
        page_number=page_number,
        width=595.0,
        height=842.0,
        text=page_text,
        elements=elements,
    )


def _document(pages: list[ParsedPage], document_id: str = "nd-168-2024") -> ParsedDocument:
    return ParsedDocument(
        parsed_document_id=_PARSED_DOCUMENT_ID,
        document_id=document_id,
        parser="DOCLING",
        parser_version="docling-2.118.1",
        ir_schema_version="document-ir-v1",
        source_object_key="fixtures/nd-168-2024.pdf",
        pages=pages,
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )


def _passing_doc() -> ParsedDocument:
    """2 pages, 2 bbox'd elements each, contiguous reading_order 0..3."""
    return _document(
        [
            _page(1, [_element(0, bbox=_box()), _element(1, bbox=_box())]),
            _page(2, [_element(2, bbox=_box()), _element(3, bbox=_box())]),
        ]
    )


# ────────────────────────────────────────────────────────────────────────────
# Group A — provenance coverage
# ────────────────────────────────────────────────────────────────────────────


def test_provenance_coverage_all_elements_have_bbox() -> None:
    assert provenance_coverage(_passing_doc()) == 1.0


def test_provenance_coverage_mixed_bbox() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(0, bbox=_box()),
                    _element(1, bbox=_box()),
                    _element(2),  # no bbox
                    _element(3),  # no bbox
                ],
            )
        ]
    )
    assert provenance_coverage(doc) == pytest.approx(0.5)


def test_provenance_coverage_bbox_is_the_discriminator() -> None:
    # page_number is schema-required and always present; a missing bbox is what
    # lowers the score (doc 03 §3.7.3 + yaml comment: "provenance_coverage <
    # 0.9 hoặc bbox thiếu" are the same low-provenance review trigger).
    doc = _document([_page(1, [_element(0), _element(1)])])
    assert provenance_coverage(doc) == 0.0


def test_provenance_coverage_empty_document_is_na() -> None:
    assert provenance_coverage(_document([])) is None


# ────────────────────────────────────────────────────────────────────────────
# Group A — text extraction rate
# ────────────────────────────────────────────────────────────────────────────


def test_text_extraction_rate_all_pages_have_text() -> None:
    assert text_extraction_rate(_passing_doc()) == 1.0


def test_text_extraction_rate_mixed_pages() -> None:
    doc = _document(
        [
            _page(1, [_element(0)], text="non-empty"),
            _page(2, [_element(1, text="")], text="   "),  # whitespace-only
            _page(3, [_element(2, text="")], text=None),  # no text at all
        ]
    )
    assert text_extraction_rate(doc) == pytest.approx(1 / 3)


def test_text_extraction_rate_empty_document_is_na() -> None:
    assert text_extraction_rate(_document([])) is None


# ────────────────────────────────────────────────────────────────────────────
# Group A — table detection rate
# ────────────────────────────────────────────────────────────────────────────


def test_table_detection_rate_detected_over_expected() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(0, bbox=_box()),
                    _element(1, bbox=_box(), element_type="table", text=""),
                    _element(2, bbox=_box(), element_type="table", text=""),
                ],
            )
        ]
    )
    assert table_detection_rate(doc, expected_tables=4) == pytest.approx(0.5)


def test_table_detection_rate_no_expectations_is_na_never_zero() -> None:
    doc = _passing_doc()
    assert table_detection_rate(doc, expected_tables=None) is None
    assert table_detection_rate(doc, expected_tables=0) is None


# ────────────────────────────────────────────────────────────────────────────
# Group A — layout coherence (deterministic rule)
# ────────────────────────────────────────────────────────────────────────────


def test_layout_coherence_contiguous_and_all_pages_non_empty() -> None:
    assert layout_coherence(_passing_doc()) == 1.0


def test_layout_coherence_reading_order_gap_fails() -> None:
    # reading_order jumps 0 -> 2 (a skipped index): rule (a) fails.
    doc = _document([_page(1, [_element(0, bbox=_box()), _element(2, bbox=_box())])])
    assert layout_coherence(doc) == 0.0


def test_layout_coherence_duplicate_reading_order_fails() -> None:
    doc = _document([_page(1, [_element(1, bbox=_box()), _element(1, bbox=_box())])])
    assert layout_coherence(doc) == 0.0


def test_layout_coherence_empty_page_fails() -> None:
    doc = _document([_page(1, [_element(0, bbox=_box())]), _page(2, [])])
    assert layout_coherence(doc) == 0.0


def test_layout_coherence_empty_document_vacuously_coherent() -> None:
    assert layout_coherence(_document([])) == 1.0


# ────────────────────────────────────────────────────────────────────────────
# Group A — thresholds & evaluate_group_a
# ────────────────────────────────────────────────────────────────────────────


def test_group_a_thresholds_defaults_from_yaml() -> None:
    thresholds = GroupAThresholds()
    assert thresholds.min_provenance_coverage == 0.9
    assert thresholds.min_text_extraction_rate == 0.8
    assert thresholds.min_table_detection_rate == 0.6
    # layout threshold is not in the yaml config ("tùy loại văn bản") -> None.
    assert thresholds.min_layout_coherence is None


def test_evaluate_group_a_all_pass() -> None:
    result = evaluate_group_a(_passing_doc())
    assert isinstance(result, GroupAResult)
    assert result.verdict == "passed"
    assert result.provenance_coverage.status == "passed"
    assert result.text_extraction_rate.status == "passed"
    # table and layout are N/A (no expected_tables / no layout threshold).
    assert result.table_detection_rate.status == "na"
    assert result.layout_coherence.status == "na"


def test_evaluate_group_a_table_gate_is_na_without_expectations() -> None:
    result = evaluate_group_a(_passing_doc())
    assert result.table_detection_rate.status == "na"
    assert result.table_detection_rate.value is None


def test_evaluate_group_a_layout_gate_is_na_without_threshold() -> None:
    result = evaluate_group_a(_passing_doc())
    assert result.layout_coherence.status == "na"  # min_layout_coherence=None
    assert result.layout_coherence.value == 1.0  # measured, but no threshold
    assert result.verdict == "passed"  # na gates do not fail the verdict


def test_evaluate_group_a_provenance_threshold_boundary() -> None:
    # 9 of 10 bbox'd = exactly 0.9 -> passed (>= boundary); 0.89 would fail.
    at_boundary = _document(
        [
            _page(
                1,
                [*[_element(i, bbox=_box()) for i in range(9)], _element(9)],
            )
        ]
    )
    result = evaluate_group_a(at_boundary)
    assert result.provenance_coverage.value == pytest.approx(0.9)
    assert result.provenance_coverage.status == "passed"

    below_boundary = _document(
        [
            _page(
                1,
                [*[_element(i, bbox=_box()) for i in range(8)], _element(8), _element(9)],
            )
        ]
    )
    result_below = evaluate_group_a(below_boundary)
    assert result_below.provenance_coverage.value == pytest.approx(0.8)
    assert result_below.provenance_coverage.status == "failed"
    assert result_below.verdict == "failed"


def test_evaluate_group_a_provenance_below_threshold_fails() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(0, bbox=_box()),
                    _element(1, bbox=_box()),
                    _element(2),
                    _element(3),
                    _element(4),
                ],
            )
        ]
    )
    result = evaluate_group_a(doc)
    assert result.provenance_coverage.value == pytest.approx(0.4)
    assert result.provenance_coverage.status == "failed"
    assert result.verdict == "failed"


def test_evaluate_group_a_text_extraction_boundary() -> None:
    doc = _document(
        [
            _page(1, [_element(0)], text="non-empty"),
            _page(2, [_element(1)], text="non-empty"),
            _page(3, [_element(2)], text="non-empty"),
            _page(4, [_element(3)], text="non-empty"),
            _page(5, [_element(4, text="")], text=None),  # 4/5 = 0.8 exactly -> passed
        ]
    )
    result = evaluate_group_a(doc)
    assert result.text_extraction_rate.value == pytest.approx(0.8)
    assert result.text_extraction_rate.status == "passed"

    doc_fail = _document(
        [
            _page(1, [_element(0)], text="non-empty"),
            _page(2, [_element(1)], text="non-empty"),
            _page(3, [_element(2)], text="non-empty"),
            _page(4, [_element(3, text="")], text=None),  # 3/4 = 0.75 < 0.8 -> failed
        ]
    )
    result_fail = evaluate_group_a(doc_fail)
    assert result_fail.text_extraction_rate.value == pytest.approx(0.75)
    assert result_fail.text_extraction_rate.status == "failed"
    assert result_fail.verdict == "failed"


def test_evaluate_group_a_table_gate_threshold() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(0, bbox=_box()),
                    _element(1, bbox=_box(), element_type="table", text=""),
                    _element(2, bbox=_box(), element_type="table", text=""),
                ],
            )
        ]
    )
    result = evaluate_group_a(doc, expected_tables=4)  # 2/4 = 0.5 < 0.6
    assert result.table_detection_rate.status == "failed"
    assert result.verdict == "failed"


def test_evaluate_group_a_empty_document_verdict_na() -> None:
    result = evaluate_group_a(_document([]))
    assert result.verdict == "na"
    assert all(gate.status == "na" for gate in result.gates)


# ────────────────────────────────────────────────────────────────────────────
# Group B — structural gates (CONTRACT ONLY in W2)
# ────────────────────────────────────────────────────────────────────────────


def test_group_b_thresholds_defaults_from_yaml() -> None:
    thresholds = GroupBThresholds()
    assert thresholds.min_point_label_detection == 0.9
    assert thresholds.min_hierarchy_completeness == 0.9


def test_group_b_contract_is_defined_against_extractor_output() -> None:
    contract = GroupBContract()
    assert contract.runs_on == "LegalProvision[]"
    assert "Legal Structure Extractor (VNLRAG-26/28)" in contract.executes_after
    assert contract.gates == ("point_label_detection", "hierarchy_completeness")
    assert "short_point_retention" in contract.to_dict()


def test_group_b_contract_dict_is_jsonable() -> None:
    import json

    payload = GroupBContract().to_dict()
    assert isinstance(json.dumps(payload), str)


def test_evaluate_group_b_stub_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="contract-only in W2"):
        evaluate_group_b([])  # type: ignore[arg-type]  # LegalProvision[] lands in W3
