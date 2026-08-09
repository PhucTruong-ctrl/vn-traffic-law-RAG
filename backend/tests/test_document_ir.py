# ruff: noqa: E501
# E501 is disabled file-wide because the byte-verbatim §7 JSON constant below
# contains a 105-char line (p12-e4 "text"); a per-line # noqa cannot be embedded
# inside a string literal, and verbatim fidelity wins per the frozen contract.

"""Tests for the canonical Document IR schema (VNLRAG-128).

Contract frozen at ``docs/canonical-document-ir-design.md`` (M0 scope
baseline). The §7 JSON example is illustrative, not a complete
ParsedDocument (page-level "text" is omitted); the valid fixtures used here
are complete documents matching that shape.
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

# Byte-verbatim JSON example from docs/canonical-document-ir-design.md §7
# (the block between the ```json fences at lines 153-200): 1598 characters
# (1631 UTF-8 bytes). It is illustrative, not a complete ParsedDocument:
# page-level "text" (and the parse timestamps) are omitted, so it must NOT be
# model-validated as-is.
_FROZEN_JSON_EXAMPLE = """{
  "parsed_document_id": "9f1c2e0a-4b3c-4d5e-8f90-1234567890ab",
  "document_id": "nd-168-2024",
  "parser": "DOCLING",
  "parser_version": "docling-2.1.0",
  "ir_schema_version": "document-ir-v1",
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
          "bbox": {"left": 60.0, "top": 80.0, "right": 540.0, "bottom": 100.0},
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
          "bbox": {"left": 60.0, "top": 105.0, "right": 540.0, "bottom": 135.0},
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


def make_element(**overrides: object) -> dict:
    """Default element mirrors the frozen contract §7 example (p12-e3)."""
    element = {
        "element_id": "p12-e3",
        "element_type": "heading",
        "text": "Điều 7. Các hành vi xử phạt ...",
        "page_number": 12,
        "bbox": {"left": 60.0, "top": 80.0, "right": 540.0, "bottom": 100.0},
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
        "ir_schema_version": "document-ir-v1",
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
                        bbox={"left": 60.0, "top": 105.0, "right": 540.0, "bottom": 135.0},
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
    """The contract §7 example (docs/canonical-document-ir-design.md lines 153-200)
    is illustrative, not a complete ParsedDocument: page-level "text" is omitted.
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
def test_parser_version_accepts_any_string(parser_version: str) -> None:
    """parser_version is typed str only per the frozen contract — empty/whitespace
    values are accepted (requiredness, not content, is enforced)."""
    element = DocumentElement.model_validate(make_element(parser_version=parser_version))
    assert element.parser_version == parser_version


def test_document_parser_version_accepts_any_string() -> None:
    document = ParsedDocument.model_validate(make_document(parser_version=""))
    assert document.parser_version == ""


def test_omitted_parser_confidence_rejected() -> None:
    element = make_element()
    del element["parser_confidence"]
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element)


def test_explicit_null_parser_confidence_accepted() -> None:
    element = DocumentElement.model_validate(make_element(parser_confidence=None))
    assert element.parser_confidence is None


def test_parser_confidence_accepts_out_of_range_float() -> None:
    """No range constraint per the frozen contract — any float is accepted."""
    element = DocumentElement.model_validate(make_element(parser_confidence=1.5))
    assert element.parser_confidence == 1.5


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
            {"left": 1.0, "top": 2.0, "right": 3.0, "bottom": 4.0, "extra": 1}
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


def test_reading_order_accepts_any_int() -> None:
    """reading_order is a plain int per the frozen contract — no ge=0 bound."""
    assert DocumentElement.model_validate(make_element(reading_order=-1)).reading_order == -1
    assert DocumentElement.model_validate(make_element(reading_order=0)).reading_order == 0


def test_page_number_accepts_any_int() -> None:
    """page_number is a plain int per the frozen contract — no ge=1 bound."""
    assert DocumentElement.model_validate(make_element(page_number=0)).page_number == 0
    assert ParsedPage.model_validate(make_page(page_number=0)).page_number == 0


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
