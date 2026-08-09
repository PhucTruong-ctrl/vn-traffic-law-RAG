"""Tests for the canonical Document IR schema (VNLRAG-128).

Contract frozen at ``docs/canonical-document-ir-design.md`` (M0 scope
baseline); the JSON example from §7 of the contract is the canonical
fixture shape exercised here.
"""

import json

import pytest
from pydantic import ValidationError

from app.ingestion.document_ir import (
    BoundingBox,
    DocumentElement,
    ParsedDocument,
    ParsedPage,
    ParserEngine,
)

_PARSED_DOCUMENT_ID = "9f1c2e0a-4b3c-4d5e-8f90-1234567890ab"
_DOCUMENT_ID = "nd-168-2024"


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


def test_example_matches_frozen_json_shape() -> None:
    """The contract §7 example shape validates: UUID id, nd-168-2024, page 12, p12-e3/e4."""
    document = ParsedDocument.model_validate_json(json.dumps(make_document()))
    assert document.parsed_document_id == _PARSED_DOCUMENT_ID
    assert document.document_id == _DOCUMENT_ID
    assert document.parser is ParserEngine.DOCLING
    assert document.ir_schema_version == "document-ir-v1"
    assert len(document.pages) == 1
    page = document.pages[0]
    assert page.page_number == 12
    assert page.width == 595.0
    assert page.height == 842.0
    assert [element.element_id for element in page.elements] == ["p12-e3", "p12-e4"]
    assert [element.element_type for element in page.elements] == ["heading", "paragraph"]
    assert all(element.bbox is not None for element in page.elements)
    assert document.quality_report == {}


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
def test_empty_parser_version_rejected(parser_version: str) -> None:
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(parser_version=parser_version))


def test_empty_document_parser_version_rejected() -> None:
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(make_document(parser_version=""))


@pytest.mark.parametrize(
    "bbox",
    [
        {"left": 100.0, "top": 80.0, "right": 60.0, "bottom": 100.0},  # left > right
        {"left": 60.0, "top": 100.0, "right": 540.0, "bottom": 80.0},  # top > bottom
        {"left": 60.0, "top": 80.0, "right": 60.0, "bottom": 100.0},  # left == right
    ],
)
def test_inverted_bbox_rejected(bbox: object) -> None:
    with pytest.raises(ValidationError):
        BoundingBox.model_validate(bbox)


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
def test_valid_parser_engines_accepted(parser: str) -> None:
    document = ParsedDocument.model_validate(make_document(parser=parser))
    assert document.parser is ParserEngine(parser)
    element = DocumentElement.model_validate(make_element(source_parser=parser))
    assert element.source_parser is ParserEngine(parser)


def test_unknown_parser_engine_rejected() -> None:
    with pytest.raises(ValidationError):
        ParsedDocument.model_validate(make_document(parser="FOO"))
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(source_parser="FOO"))


def test_negative_reading_order_rejected() -> None:
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(reading_order=-1))
    assert DocumentElement.model_validate(make_element(reading_order=0)).reading_order == 0


def test_page_number_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(make_element(page_number=0))
    with pytest.raises(ValidationError):
        ParsedPage.model_validate(make_page(page_number=0))


def test_element_references_its_page_number() -> None:
    """Nested structure: every element on a page carries that page's number."""
    document = ParsedDocument.model_validate(make_document())
    for page in document.pages:
        assert all(element.page_number == page.page_number for element in page.elements)


def test_quality_report_defaults_to_empty_dict() -> None:
    data = make_document()
    del data["quality_report"]
    document = ParsedDocument.model_validate(data)
    assert document.quality_report == {}
