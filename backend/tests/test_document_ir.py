# ruff: noqa: E501
# E501 is disabled file-wide because the byte-verbatim §7 JSON constant below
# contains over-long lines (the p12-e4 "text" line and the normalized bbox
# lines with coordinate_space); a per-line # noqa cannot be embedded inside a
# string literal, and verbatim fidelity wins per the frozen contract.

"""Tests for the canonical Document IR schema (VNLRAG-128), v2.

Contract frozen at ``docs/canonical-document-ir-design.md`` (M0 scope
baseline; ``ir_schema_version = "document-ir-v2"``). The §7 JSON example is
illustrative, not a complete ParsedDocument (page-level "text" is omitted); the
valid fixtures used here are complete documents matching that shape.

v2 (user blocker review #2/#3): bbox coordinates are page-normalized
(``coordinate_space = "NORMALIZED_PAGE"``, 0..1) and parser-independent
validation invariants are enforced at the schema boundary — page_number >= 1,
reading_order >= 0, parser_confidence in [0, 1], non-empty parser_version,
bbox bounds/ordering, unique element_id, element↔page number match, and parse
time ordering. The old permissive behavior (accept anything) is a fixed MEDIUM
finding, so the tests that asserted it now assert rejection.
"""

import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ingestion.document_ir import (
    BoundingBox,
    DocumentElement,
    ParsedDocument,
    ParsedPage,
)

_PARSED_DOCUMENT_ID = "9f1c2e0a-4b3c-4d5e-8f90-1234567890ab"
_DOCUMENT_ID = "nd-168-2024"
_IR_SCHEMA_VERSION = "document-ir-v2"

# Byte-verbatim JSON example from docs/canonical-document-ir-design.md §7
# (the block between the ```json fences). It is illustrative, not a complete
# ParsedDocument: page-level "text" (and the parse timestamps) are omitted, so
# it must NOT be model-validated as-is.
_FROZEN_JSON_EXAMPLE = """{
  "parsed_document_id": "9f1c2e0a-4b3c-4d5e-8f90-1234567890ab",
  "document_id": "nd-168-2024",
  "parser": "DOCLING",
  "parser_version": "docling-2.1.0",
  "ir_schema_version": "document-ir-v2",
  "source_object_key": "documents/nd-168-2024/source/<sha256>.pdf",
  "pages": [
    {
      "page_number": 12,
      "width": 595.0,
      "height": 842.0,
      "elements": [
        {
          "element_id": "p12-e3",
          "element_type": "heading",
          "text": "Điều 7. Các hành vi xử phạt ...",
          "page_number": 12,
          "bbox": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.12, "coordinate_space": "NORMALIZED_PAGE"},
          "reading_order": 40,
          "parent_element_id": null,
          "table_html": null,
          "source_parser": "DOCLING",
          "parser_version": "docling-2.1.0",
          "parser_confidence": 0.99,
          "raw_reference": {"item_id": "docling_item_123", "docling_type": "paragraph"}
        },
        {
          "element_id": "p12-e4",
          "element_type": "paragraph",
          "text": "4. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với một trong các hành vi sau:",
          "page_number": 12,
          "bbox": {"left": 0.1, "top": 0.12, "right": 0.9, "bottom": 0.16, "coordinate_space": "NORMALIZED_PAGE"},
          "reading_order": 41,
          "parent_element_id": "p12-e3",
          "table_html": null,
          "source_parser": "DOCLING",
          "parser_version": "docling-2.1.0",
          "parser_confidence": 0.98,
          "raw_reference": {"item_id": "docling_item_124", "docling_type": "paragraph"}
        }
      ]
    }
  ],
  "quality_report": {}
}"""

#: The two normalized bbox payloads from the §7 example (595x842 A4 page).
_BBOX_E3 = {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.12}
_BBOX_E4 = {"left": 0.1, "top": 0.12, "right": 0.9, "bottom": 0.16}


def make_element(**overrides: object) -> dict:
    """Default element mirrors the frozen contract §7 example (p12-e3)."""
    element = {
        "element_id": "p12-e3",
        "element_type": "heading",
        "text": "Điều 7. Các hành vi xử phạt ...",
        "page_number": 12,
        "bbox": {**_BBOX_E3, "coordinate_space": "NORMALIZED_PAGE"},
        "reading_order": 40,
        "parent_element_id": None,
        "table_html": None,
        "source_parser": "DOCLING",
        "parser_version": "docling-2.1.0",
        "parser_confidence": 0.99,
        "raw_reference": {"item_id": "docling_item_123", "docling_type": "paragraph"},
    }
    element.update(overrides)
    return element


def make_page(**overrides: object) -> dict:
    page = {
        "page_number": 12,
        "width": 595.0,
        "height": 842.0,
        "text": None,
        "elements": [make_element()],
    }
    page.update(overrides)
    return page


def make_document(**overrides: object) -> dict:
    """Default document mirrors the frozen contract §7 example (page 12, p12-e3 + p12-e4)."""
    document = {
        "parsed_document_id": _PARSED_DOCUMENT_ID,
        "document_id": _DOCUMENT_ID,
        "parser": "DOCLING",
        "parser_version": "docling-2.1.0",
        "ir_schema_version": _IR_SCHEMA_VERSION,
        "source_object_key": "documents/nd-168-2024/source/<sha256>.pdf",
        "pages": [
            {
                "page_number": 12,
                "width": 595.0,
                "height": 842.0,
                "text": None,
                "elements": [
                    make_element(),
                    make_element(
                        element_id="p12-e4",
                        element_type="paragraph",
                        text=(
                            "4. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với một "
                            "trong các hành vi sau:"
                        ),
                        bbox={**_BBOX_E4, "coordinate_space": "NORMALIZED_PAGE"},
                        reading_order=41,
                        parent_element_id="p12-e3",
                        parser_confidence=0.98,
                        raw_reference={"item_id": "docling_item_124", "docling_type": "paragraph"},
                    ),
                ],
            }
        ],
        "parse_started_at": "2024-08-01T00:00:00Z",
        "parse_completed_at": "2024-08-01T00:00:01Z",
        "quality_report": {},
    }
    document.update(overrides)
    return document


def test_valid_document_round_trips_through_json() -> None:
    """model_dump_json -> model_validate_json must reproduce an equal document."""
    document = ParsedDocument.model_validate(make_document())
    restored = ParsedDocument.model_validate_json(document.model_dump_json())
    assert restored == document


def test_frozen_json_example_is_illustrative_not_model_valid() -> None:
    """The contract §7 example (docs/canonical-document-ir-design.md) is
    illustrative, not a complete ParsedDocument: page-level "text" is omitted.
    Assert the intended omission on the raw JSON — do NOT model-validate it.
    """
    payload = json.loads(_FROZEN_JSON_EXAMPLE)
    page = payload["pages"][0]
    assert "text" not in page


def test_frozen_json_example_matches_contract_verbatim() -> None:
    """The constant must stay byte-identical to the contract's §7 JSON block
    (guards against fixture drift)."""
    contract_path = Path(__file__).resolve().parents[2] / "docs" / "canonical-document-ir-design.md"
    match = re.search(
        r"```json\n(.*?)\n```",
        contract_path.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match is not None
    assert match.group(1) == _FROZEN_JSON_EXAMPLE


def test_missing_source_parser_rejected() -> None:
    element = make_element()
    del element["source_parser"]
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element)


def test_missing_parser_version_rejected() -> None:
    element = make_element()
    del element["parser_version"]
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element)


@pytest.mark.parametrize("parser_version", ["", "   "])
def test_parser_version_rejects_empty_string(parser_version: str) -> None:
    """v2: empty/whitespace parser_version is REJECTED (old permissive test flipped)."""
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(parser_version=parser_version))


def test_document_parser_version_rejects_empty_string() -> None:
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(make_document(parser_version=""))


def test_omitted_parser_confidence_rejected() -> None:
    element = make_element()
    del element["parser_confidence"]
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element)


def test_explicit_null_parser_confidence_accepted() -> None:
    element = DocumentElement.model_validate(make_element(parser_confidence=None))
    assert element.parser_confidence is None


@pytest.mark.parametrize("confidence", [1.5, -0.1])
def test_parser_confidence_out_of_range_rejected(confidence: float) -> None:
    """v2: parser_confidence must be in [0, 1] when present (old test flipped)."""
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(parser_confidence=confidence))


@pytest.mark.parametrize("confidence", [0.0, 1.0, 0.5])
def test_parser_confidence_boundaries_accepted(confidence: float) -> None:
    element = DocumentElement.model_validate(make_element(parser_confidence=confidence))
    assert element.parser_confidence == confidence


def test_missing_raw_reference_rejected() -> None:
    element = make_element()
    del element["raw_reference"]
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element)


def test_omitted_parent_element_id_rejected() -> None:
    """parent_element_id is required but may be null (frozen code block: no default)."""
    element = make_element()
    del element["parent_element_id"]
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element)


def test_explicit_null_parent_element_id_accepted() -> None:
    element = DocumentElement.model_validate(make_element(parent_element_id=None))
    assert element.parent_element_id is None


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(make_document(extra_field="nope"))
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(extra_field="nope"))
    with pytest.raises(ValidationError):
        BoundingBox.model_validate(
            {"left": 0.1, "top": 0.2, "right": 0.3, "bottom": 0.4, "extra": 1}
        )


def test_nullable_bbox_and_table_html_accepted() -> None:
    element = DocumentElement.model_validate(make_element(bbox=None, table_html=None))
    assert element.bbox is None
    assert element.table_html is None


@pytest.mark.parametrize("parser", ["DOCLING", "MINERU"])
def test_docling_mineru_parser_values_accepted(parser: str) -> None:
    document = ParsedDocument.model_validate(make_document(parser=parser))
    assert document.parser == parser
    element = DocumentElement.model_validate(make_element(source_parser=parser))
    assert element.source_parser == parser


def test_future_parser_value_accepted() -> None:
    """parser/source_parser are free strings — a non-DOCLING/MINERU value (future
    parser) must validate, documenting parser-neutrality."""
    document = ParsedDocument.model_validate(make_document(parser="future-parser"))
    assert document.parser == "future-parser"
    element = DocumentElement.model_validate(make_element(source_parser="future-parser"))
    assert element.source_parser == "future-parser"


def test_omitted_ir_schema_version_rejected() -> None:
    data = make_document()
    del data["ir_schema_version"]
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(data)


def test_omitted_quality_report_rejected() -> None:
    data = make_document()
    del data["quality_report"]
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(data)


def test_reading_order_accepts_zero() -> None:
    assert DocumentElement.model_validate(make_element(reading_order=0)).reading_order == 0


def test_reading_order_negative_rejected() -> None:
    """v2: reading_order < 0 is REJECTED (old permissive test flipped)."""
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(reading_order=-1))


@pytest.mark.parametrize("page_number", [0, -1, -100])
def test_element_page_number_lt_1_rejected(page_number: int) -> None:
    """v2: page_number must be >= 1 (old permissive test flipped)."""
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(page_number=page_number))


@pytest.mark.parametrize("page_number", [0, -1])
def test_page_page_number_lt_1_rejected(page_number: int) -> None:
    with pytest.raises(ValidationError):
        ParsedPage.model_validate(make_page(page_number=page_number))


def test_page_number_one_accepted() -> None:
    assert DocumentElement.model_validate(make_element(page_number=1)).page_number == 1
    page = make_page(page_number=1, elements=[make_element(page_number=1)])
    assert ParsedPage.model_validate(page).page_number == 1


@pytest.mark.parametrize("field", ["width", "height", "text"])
def test_omitted_page_field_rejected(field: str) -> None:
    page = make_page()
    del page[field]
    with pytest.raises(ValidationError):
        ParsedPage.model_validate(page)


@pytest.mark.parametrize("field", ["width", "height", "text"])
def test_explicit_null_page_field_accepted(field: str) -> None:
    page = ParsedPage.model_validate(make_page(**{field: None}))
    assert getattr(page, field) is None


def test_element_references_its_page_number() -> None:
    """Nested structure: every element on a page carries that page's number."""
    document = ParsedDocument.model_validate(make_document())
    for page in document.pages:
        assert all(element.page_number == page.page_number for element in page.elements)


# ────────────────────────────────────────────────────────────────────────────
# v2 bbox invariants — NORMALIZED_PAGE, 0..1, TOPLEFT ordering
# ────────────────────────────────────────────────────────────────────────────


def test_bbox_default_coordinate_space_is_normalized_page() -> None:
    box = BoundingBox.model_validate({**_BBOX_E3})
    assert box.coordinate_space == "NORMALIZED_PAGE"
    element = DocumentElement.model_validate(make_element())
    assert element.bbox is not None
    assert element.bbox.coordinate_space == "NORMALIZED_PAGE"


def test_bbox_coordinate_space_rejects_other_values() -> None:
    with pytest.raises(ValidationError):
        BoundingBox.model_validate({**_BBOX_E3, "coordinate_space": "PDF_POINTS"})
    with pytest.raises(ValidationError):
        BoundingBox.model_validate({**_BBOX_E3, "coordinate_space": "PERMILLE"})


@pytest.mark.parametrize("field", ["left", "top", "right", "bottom"])
@pytest.mark.parametrize("value", [-0.01, 1.01, 42.0])
def test_bbox_out_of_unit_interval_rejected(field: str, value: float) -> None:
    payload = dict(_BBOX_E3)
    payload[field] = value
    with pytest.raises(ValidationError):
        BoundingBox.model_validate(payload)


@pytest.mark.parametrize("field", ["left", "top", "right", "bottom"])
def test_bbox_unit_interval_boundaries_accepted(field: str) -> None:
    payload = {"left": 0.0, "top": 0.0, "right": 1.0, "bottom": 1.0}
    box = BoundingBox.model_validate(payload)
    assert getattr(box, field) is not None


def test_bbox_inverted_ordering_rejected() -> None:
    # right < left
    with pytest.raises(ValidationError):
        BoundingBox.model_validate({"left": 0.9, "top": 0.1, "right": 0.1, "bottom": 0.2})
    # bottom < top (BOTTOMLEFT origin leaked into the IR)
    with pytest.raises(ValidationError):
        BoundingBox.model_validate({"left": 0.1, "top": 0.9, "right": 0.2, "bottom": 0.1})


def test_bbox_degenerate_zero_area_accepted() -> None:
    """right == left and/or bottom == top is allowed (ordering is >=, not >)."""
    box = BoundingBox.model_validate({"left": 0.5, "top": 0.5, "right": 0.5, "bottom": 0.5})
    assert box.right == box.left and box.bottom == box.top


def test_bbox_page_dims_optional_or_positive() -> None:
    box = BoundingBox.model_validate({**_BBOX_E3, "page_height": None, "page_width": None})
    assert box.page_height is None and box.page_width is None
    box = BoundingBox.model_validate({**_BBOX_E3, "page_height": 842.0, "page_width": 595.0})
    assert box.page_height == 842.0 and box.page_width == 595.0
    with pytest.raises(ValidationError):
        BoundingBox.model_validate({**_BBOX_E3, "page_height": 0.0})
    with pytest.raises(ValidationError):
        BoundingBox.model_validate({**_BBOX_E3, "page_width": -5.0})


# ────────────────────────────────────────────────────────────────────────────
# v2 document-level invariants
# ────────────────────────────────────────────────────────────────────────────


def test_duplicate_element_id_across_pages_rejected() -> None:
    data = make_document()
    data["pages"].append(
        {
            "page_number": 13,
            "width": 595.0,
            "height": 842.0,
            "text": None,
            "elements": [
                make_element(
                    element_id="p12-e3",  # collides with the element on page 12
                    page_number=13,
                )
            ],
        }
    )
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(data)


def test_duplicate_element_id_within_page_rejected() -> None:
    data = make_document()
    data["pages"] = [
        {
            "page_number": 12,
            "width": 595.0,
            "height": 842.0,
            "text": None,
            "elements": [make_element(), make_element(element_id="p12-e3")],
        }
    ]
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(data)


def test_element_page_number_mismatch_rejected() -> None:
    """element.page_number must equal its ParsedPage.page_number (v2)."""
    with pytest.raises(ValidationError):
        ParsedPage.model_validate(make_page(elements=[make_element(page_number=13)]))


def test_parse_completed_before_started_rejected() -> None:
    data = make_document(
        parse_started_at="2024-08-01T00:00:02Z",
        parse_completed_at="2024-08-01T00:00:01Z",
    )
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(data)


def test_parse_completed_equal_started_accepted() -> None:
    data = make_document(
        parse_started_at="2024-08-01T00:00:00Z",
        parse_completed_at="2024-08-01T00:00:00Z",
    )
    document = ParsedDocument.model_validate(data)
    assert document.parse_completed_at >= document.parse_started_at
