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
    GroupBResult,
    GroupBThresholds,
    evaluate_group_a,
    evaluate_group_b,
    layout_coherence,
    provenance_coverage,
    table_detection_rate,
    text_extraction_rate,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision

_PARSED_DOCUMENT_ID = "a1b2c3d4-0000-4000-8000-000000000000"


def _element(
    reading_order: int,
    *,
    bbox: BoundingBox | None = None,
    text: str = "Nội dung đoạn văn.",
    element_type: str = "paragraph",
    element_id: str | None = None,
) -> DocumentElement:
    return DocumentElement(
        element_id=element_id if element_id is not None else f"e{reading_order}",
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
    # v2: NORMALIZED_PAGE (0..1) — values must stay in the unit interval.
    return BoundingBox(left=0.1, top=0.2, right=0.3, bottom=0.4)


def _page(page_number: int, elements: list[DocumentElement], text: str | None = None) -> ParsedPage:
    page_text = (
        text
        if text is not None
        else ("\n".join(e.text for e in elements if e.text.strip()) or None)
    )
    # v2: element.page_number must equal the page's number (cross-level check).
    for element in elements:
        element.page_number = page_number
    return ParsedPage(
        page_number=page_number,
        width=595.0,
        height=842.0,
        text=page_text,
        elements=elements,
    )


def _document(pages: list[ParsedPage], document_id: str = "nd-168-2024") -> ParsedDocument:
    started_at = datetime.now(UTC)
    return ParsedDocument(
        parsed_document_id=_PARSED_DOCUMENT_ID,
        document_id=document_id,
        parser="DOCLING",
        parser_version="docling-2.118.1",
        ir_schema_version="document-ir-v2",
        source_object_key="fixtures/nd-168-2024.pdf",
        pages=pages,
        parse_started_at=started_at,
        parse_completed_at=started_at,  # v2: completed >= started
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
# Group A — layout coherence (spatial-progression rule, user finding #7)
# ────────────────────────────────────────────────────────────────────────────


def _box_at(top: float, left: float = 0.1) -> BoundingBox:
    # v2: NORMALIZED_PAGE (0..1) — values must stay in the unit interval.
    return BoundingBox(left=left, top=top, right=min(left + 0.2, 1.0), bottom=min(top + 0.1, 1.0))


def _spatial_doc(pages: list[list[tuple[int, float, float]]]) -> ParsedDocument:
    """Build a doc from per-page ``(reading_order, top, left)`` triples.

    ``reading_order`` is kept globally unique (as the adapters assign it), so
    ``element_id`` stays unique across pages.
    """
    return _document(
        [
            _page(
                page_number,
                [
                    _element(order, bbox=_box_at(top, left), element_id=f"e{order}")
                    for order, top, left in triples
                ],
            )
            for page_number, triples in enumerate(pages, start=1)
        ]
    )


def test_layout_coherence_in_order_rows_is_1() -> None:
    # Top-to-bottom rows, each read before the next: plausible reading path.
    doc = _spatial_doc([[(0, 0.1, 0.1), (1, 0.2, 0.1), (2, 0.4, 0.1), (3, 0.5, 0.1)]])
    assert layout_coherence(doc) == 1.0


def test_layout_coherence_bottom_before_top_scores_below_1() -> None:
    # reading_order is adapter-contiguous (0,1,2,3) yet the spatial path is
    # bottom-up — a real layout bug that the old tautological rule could not
    # catch. Every pair is spatially inverted -> 0.0.
    doc = _spatial_doc([[(0, 0.9, 0.1), (1, 0.7, 0.1), (2, 0.4, 0.1), (3, 0.2, 0.1)]])
    assert layout_coherence(doc) == 0.0


def test_layout_coherence_bottom_to_top_pair_scores_zero() -> None:
    # Minimal non-tautology proof: contiguous reading_order 0,1 with the
    # second element physically ABOVE the first -> 0.0, never 1.0.
    doc = _spatial_doc([[(0, 0.8, 0.1), (1, 0.2, 0.1)]])
    assert layout_coherence(doc) == 0.0


def test_layout_coherence_single_element_is_1() -> None:
    doc = _spatial_doc([[(0, 0.2, 0.1)]])
    assert layout_coherence(doc) == 1.0


def test_layout_coherence_empty_document_vacuously_coherent() -> None:
    assert layout_coherence(_document([])) == 1.0


def test_layout_coherence_multi_row_mixed_partial_agreement() -> None:
    # Three rows top/mid/bottom; reading_order swaps the bottom two rows ->
    # one of three pairs disagrees -> 2/3 (partial, not binary).
    doc = _spatial_doc([[(0, 0.1, 0.1), (2, 0.4, 0.1), (1, 0.7, 0.1)]])
    assert layout_coherence(doc) == pytest.approx(2 / 3)


def test_layout_coherence_within_row_left_to_right_disorder_scores_zero() -> None:
    # Two-column-ish page: same row band, right column read before left — a
    # multi-column layout bug row-band monotonicity alone would NOT catch.
    doc = _spatial_doc([[(0, 0.1, 0.6), (1, 0.1, 0.1)]])
    assert layout_coherence(doc) == 0.0


def test_layout_coherence_no_bbox_signal_is_na() -> None:
    # Elements exist but carry no bbox -> no spatial signal -> N/A (None),
    # never a fabricated 0.0/1.0.
    doc = _document([_page(1, [_element(0), _element(1)])])
    assert layout_coherence(doc) is None


def test_layout_coherence_identical_boxes_no_spatial_signal_is_1() -> None:
    # All elements share one bbox (fixture artifact): every pair is
    # non-comparable (identical spatial keys) -> trivially coherent.
    assert layout_coherence(_passing_doc()) == 1.0


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
# Group B — structural gates (OPERATIONAL in VNLRAG-33)
# ────────────────────────────────────────────────────────────────────────────

_DOC_VERSION = "dv-nd-168-2024"
_SLUG = "nd-168-2024"


def _provision(**overrides: object) -> ExtractedLegalProvision:
    """Build an ExtractedLegalProvision (default: point ``a)``, Điều 5 Khoản 1)."""

    base: dict[str, object] = {
        "provision_id": f"{_SLUG}__dieu-5__khoan-1__diem-a",
        "document_version_id": _DOC_VERSION,
        "chapter": None,
        "section": None,
        "article": "Điều 5",
        "clause": "Khoản 1",
        "point": "Điểm a)",
        "heading": None,
        "source_text": "a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "retrieval_text": (
            "Khoản 1. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng ... "
            "a) Điều khiển xe lạng lách, đánh võng trên đường bộ"
        ),
        "parent_context": "Khoản 1. Xử phạt người điều khiển xe ô tô ...",
        "page_number": 1,
        "bbox": None,
        "source_element_ids": ["e1"],
        "content_hash": "hash",
        "node_kind": "POINT",
        "point_label": "a)",
        "short_point": False,
        "needs_review": False,
        "ambiguity": None,
        "effective_from": "2025-01-01",
    }
    base.update(overrides)
    return ExtractedLegalProvision(**base)


def _clause(**overrides: object) -> ExtractedLegalProvision:
    """CLAUSE-kind provision under Điều 5 Khoản 1."""

    base: dict[str, object] = {
        "provision_id": f"{_SLUG}__dieu-5__khoan-1",
        "article": "Điều 5",
        "clause": "Khoản 1",
        "point": None,
        "source_text": "1. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng ...",
        "node_kind": "CLAUSE",
        "point_label": None,
    }
    base.update(overrides)
    return _provision(**base)


def _article(**overrides: object) -> ExtractedLegalProvision:
    """ARTICLE-kind provision for Điều 5."""

    base: dict[str, object] = {
        "provision_id": f"{_SLUG}__dieu-5",
        "article": "Điều 5",
        "clause": None,
        "point": None,
        "source_text": "Điều 5. Xử phạt người điều khiển xe ô tô ...",
        "node_kind": "ARTICLE",
        "point_label": None,
    }
    base.update(overrides)
    return _provision(**base)


def _point(index: int, label: str) -> ExtractedLegalProvision:
    """POINT provision ``index`` (1-based) with the given label under Khoản 1."""

    letters = "abcdefghij"
    return _provision(
        provision_id=f"{_SLUG}__dieu-5__khoan-1__diem-{letters[index - 1]}",
        point_label=label,
        source_text=f"{label} Nội dung điểm thứ {index}.",
    )


def _clean_tree() -> list[ExtractedLegalProvision]:
    """Điều 5 → Khoản 1 → points a) b): no orphans, no duplicates, labels valid."""

    return [_article(), _clause(), _point(1, "a)"), _point(2, "b)")]


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


def test_group_b_contract_marks_implementation_ticket() -> None:
    assert GroupBContract().implemented_in == "VNLRAG-33"


def test_evaluate_group_b_clean_tree_passes() -> None:
    result = evaluate_group_b(_clean_tree())
    assert isinstance(result, GroupBResult)
    assert result.passed is True
    assert result.failed_checks == []
    assert result.metrics["point_label_detection_rate"] == 1.0
    assert result.metrics["hierarchy_completeness"] == 1.0
    assert result.metrics["short_point_retention_rate"] == 1.0
    assert result.metrics["orphan_point_count"] == 0
    assert result.metrics["orphan_clause_count"] == 0
    assert result.metrics["duplicate_count"] == 0


def test_group_b_result_metrics_contract_keys() -> None:
    metrics = evaluate_group_b(_clean_tree()).metrics
    assert set(metrics) == {
        "point_label_detection_rate",
        "hierarchy_completeness",
        "short_point_retention_rate",
        "orphan_point_count",
        "orphan_clause_count",
        "duplicate_count",
    }


def test_evaluate_group_b_point_label_detection_boundary() -> None:
    # 9 of 10 points with a PRIMARY-run label = exactly 0.9 -> passed (>=);
    # labels beyond the PRIMARY run (g)) do not count as detected.
    tree = [_article(), _clause()]
    tree += [_point(i, "a)") for i in range(1, 10)]
    tree.append(_point(10, "g)"))
    result = evaluate_group_b(tree)
    assert result.metrics["point_label_detection_rate"] == pytest.approx(0.9)
    assert "point_label_detection" not in result.failed_checks

    below = [_article(), _clause()]
    below += [_point(i, "a)") for i in range(1, 9)]
    below += [_point(9, "g)"), _point(10, "g)")]
    result_below = evaluate_group_b(below)
    assert result_below.metrics["point_label_detection_rate"] == pytest.approx(0.8)
    assert result_below.passed is False
    assert "point_label_detection" in result_below.failed_checks


def test_evaluate_group_b_hierarchy_completeness_counts_orphans_and_duplicates() -> None:
    # Orphan point: neither its provision_id parent nor its (article, clause)
    # labels exist anywhere in the document.  Orphan clause: article Điều 9
    # missing.  Duplicate: the second _clause() repeats the same provision_id.
    orphan_point = _point(1, "a)").model_copy(
        update={
            "provision_id": f"{_SLUG}__dieu-9__khoan-9__diem-a",
            "article": "Điều 9",
            "clause": "Khoản 9",
        }
    )
    orphan_clause = _clause().model_copy(
        update={
            "provision_id": f"{_SLUG}__dieu-9__khoan-2",
            "article": "Điều 9",
            "clause": "Khoản 2",
        }
    )
    tree = [
        _article(),
        _clause(),
        _point(1, "a)"),
        _point(2, "b)"),
        orphan_point,
        orphan_clause,
        _clause(),  # duplicate provision_id (same id as _clause())
    ]
    result = evaluate_group_b(tree)
    assert result.metrics["orphan_point_count"] == 1
    assert result.metrics["orphan_clause_count"] == 1
    assert result.metrics["duplicate_count"] == 1
    # 7 tree provisions, 3 defects (orphan point + orphan clause + duplicate
    # id) -> completeness 4/7 < 0.9 -> hierarchy gate fails.
    assert result.metrics["hierarchy_completeness"] == pytest.approx(4 / 7)
    assert result.passed is False
    assert "hierarchy_completeness" in result.failed_checks


def test_evaluate_group_b_short_point_retention_never_fails() -> None:
    # Rulespec §5: no token-length threshold — flagged short points are
    # retained, so the rate is 1.0 (vacuously 1.0 when none are flagged).
    with_short = [_article(), _clause(), _point(1, "a)"), _point(2, "b)")]
    with_short[2] = with_short[2].model_copy(update={"short_point": True})
    result = evaluate_group_b(with_short)
    assert result.metrics["short_point_retention_rate"] == 1.0
    assert result.passed is True

    without_short = _clean_tree()
    result_vacuous = evaluate_group_b(without_short)
    assert result_vacuous.metrics["short_point_retention_rate"] == 1.0


def test_evaluate_group_b_empty_input_fails() -> None:
    # Nothing extracted → nothing detected (0.0 < 0.9): never auto-accept.
    result = evaluate_group_b([])
    assert result.passed is False
    assert result.metrics["point_label_detection_rate"] == 0.0
    assert result.metrics["hierarchy_completeness"] == 0.0
    assert set(result.failed_checks) == {"point_label_detection", "hierarchy_completeness"}


def test_evaluate_group_b_custom_thresholds() -> None:
    tree = [_article(), _clause(), _point(1, "a)"), _point(2, "g)")]
    strict = evaluate_group_b(tree, GroupBThresholds(min_point_label_detection=1.0))
    assert "point_label_detection" in strict.failed_checks
    lenient = evaluate_group_b(tree, GroupBThresholds(min_point_label_detection=0.5))
    assert lenient.metrics["point_label_detection_rate"] == pytest.approx(0.5)
    assert "point_label_detection" not in lenient.failed_checks
