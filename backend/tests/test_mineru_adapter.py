"""Tests for the MinerU → Canonical IR adapter (VNLRAG-130).

Pure-dict synthetic fixtures only: the adapter is the JSON→IR mapping layer and
must be testable without the MinerU pipeline (environment-blocked on this
machine per VNLRAG-20) and without ``import mineru`` succeeding.
"""

import json
from typing import Any

import pytest
from pydantic import ValidationError

import app.ingestion.adapters.mineru_adapter as mineru_adapter
from app.ingestion.adapters.mineru_adapter import (
    IR_SCHEMA_VERSION,
    MINERU_ENV_ERROR_MESSAGE,
    MinerUAdapter,
    MinerUEnvironmentError,
)
from app.ingestion.document_ir import (
    BoundingBox,
    DocumentElement,
    ParsedDocument,
    ParsedPage,
)

_PARSED_DOCUMENT_ID = "a1b2c3d4-0000-4000-8000-000000000000"
_DOCUMENT_ID = "nd-168-2024"
_SOURCE_OBJECT_KEY = "documents/nd-168-2024/source/<sha256>.pdf"


def make_content_list() -> list[dict]:
    """Synthetic MinerU content_list covering text/title/table/image + 2 pages."""
    return [
        {
            "type": "title",
            "text": "Điều 1. Phạm vi điều chỉnh",
            "bbox": [10.0, 20.0, 500.0, 40.0],
            "page_idx": 0,
        },
        {
            "type": "text_span",
            "text": "Luật này quy định phạm vi điều chỉnh của văn bản.",
            "bbox": [10.0, 45.0, 500.0, 60.0],
            "page_idx": 0,
            "line_idx": 0,
        },
        {
            "type": "table",
            "text": "Bảng 1. Mức phạt",
            "html": "<table><tr><td>hành vi</td><td>mức phạt</td></tr></table>",
            "bbox": [10.0, 70.0, 500.0, 150.0],
            "page_idx": 0,
        },
        {
            "type": "image",
            "text": "Hình 1. Sơ đồ quy trình",
            "img_path": "images/1.jpg",
            "bbox": [10.0, 160.0, 400.0, 260.0],
            "page_idx": 0,
        },
        {
            "type": "text",
            "text": "Điều 2. Quy định chuyển tiếp",
            "bbox": [10.0, 10.0, 500.0, 30.0],
            "page_idx": 1,
        },
    ]


def parse_default(payload: Any) -> ParsedDocument:
    return MinerUAdapter().parse(
        payload,
        source_object_key=_SOURCE_OBJECT_KEY,
        parsed_document_id=_PARSED_DOCUMENT_ID,
        document_id=_DOCUMENT_ID,
    )


def test_parse_maps_types_pages_and_provenance() -> None:
    doc = parse_default({"content_list": make_content_list()})

    # Document-level fields.
    assert doc.parsed_document_id == _PARSED_DOCUMENT_ID
    assert doc.document_id == _DOCUMENT_ID
    assert doc.parser == "MINERU"
    assert doc.parser_version.startswith("mineru-")
    assert doc.ir_schema_version == IR_SCHEMA_VERSION
    assert doc.source_object_key == _SOURCE_OBJECT_KEY
    assert doc.quality_report == {}
    assert doc.parse_started_at <= doc.parse_completed_at

    # Page grouping by page_idx (0-based) → IR page_number (1-based).
    assert [page.page_number for page in doc.pages] == [1, 2]
    page1, page2 = doc.pages
    assert [element.element_type for element in page1.elements] == [
        "heading",
        "paragraph",
        "table",
        "figure",
    ]
    assert [element.element_type for element in page2.elements] == ["paragraph"]
    assert page1.width is None and page1.height is None
    assert page2.text is not None and "Điều 2" in page2.text

    # reading_order is the global 0-based sequential index.
    assert [element.reading_order for element in doc.pages[0].elements] == [0, 1, 2, 3]
    assert doc.pages[1].elements[0].reading_order == 4

    # element_id scheme p{page}-e{global-index}.
    assert [element.element_id for element in doc.pages[0].elements] == [
        "p1-e0",
        "p1-e1",
        "p1-e2",
        "p1-e3",
    ]
    assert doc.pages[1].elements[0].element_id == "p2-e4"

    # Every element carries MINERU provenance and the flat-list parent value.
    for page in doc.pages:
        assert all(element.source_parser == "MINERU" for element in page.elements)
        assert all(element.parser_version == doc.parser_version for element in page.elements)
        assert all(element.parser_confidence is None for element in page.elements)
        assert all(element.parent_element_id is None for element in page.elements)
        assert all(element.page_number == page.page_number for element in page.elements)


def test_parse_bbox_origin_is_top_left() -> None:
    doc = parse_default(make_content_list())
    title_element = doc.pages[0].elements[0]
    assert title_element.bbox == BoundingBox(left=10.0, top=20.0, right=500.0, bottom=40.0)
    # TOPLEFT-origin convention: top < bottom and left < right on every box.
    for page in doc.pages:
        for element in page.elements:
            assert element.bbox is not None
            assert element.bbox.left < element.bbox.right
            assert element.bbox.top < element.bbox.bottom


def test_parse_table_html_captured() -> None:
    doc = parse_default(make_content_list())
    table_element = doc.pages[0].elements[2]
    assert table_element.element_type == "table"
    assert table_element.table_html == "<table><tr><td>hành vi</td><td>mức phạt</td></tr></table>"
    # Non-table elements never carry table_html.
    assert all(
        element.table_html is None
        for page in doc.pages
        for element in page.elements
        if element.element_type != "table"
    )


def test_parse_raw_reference_shape() -> None:
    doc = parse_default(make_content_list())
    elements = doc.pages[0].elements
    # text_span item: line_idx is carried through when present.
    assert elements[1].raw_reference == {
        "mineru_item_index": 1,
        "mineru_item_type": "text_span",
        "mineru_page_idx": 0,
        "mineru_line_idx": 0,
    }
    # title item: only the three always-present keys.
    assert elements[0].raw_reference == {
        "mineru_item_index": 0,
        "mineru_item_type": "title",
        "mineru_page_idx": 0,
    }
    # stable id is carried through when the JSON carries one.
    items = make_content_list()
    items[0]["id"] = "mineru_item_7"
    assert (
        parse_default(items).pages[0].elements[0].raw_reference["mineru_item_id"] == "mineru_item_7"
    )


def test_parse_json_file_path_equals_dict_input(tmp_path) -> None:
    payload_path = tmp_path / "content_list.json"
    payload_path.write_text(
        json.dumps({"content_list": make_content_list()}, ensure_ascii=False), encoding="utf-8"
    )
    doc_from_file = parse_default(str(payload_path))
    doc_from_dict = parse_default({"content_list": make_content_list()})
    # Parse timestamps necessarily differ between the two calls; everything
    # else — including element_ids, provenance and bboxes — must be identical.
    exclude = {"parse_started_at", "parse_completed_at"}
    assert doc_from_file.model_dump(exclude=exclude) == doc_from_dict.model_dump(exclude=exclude)


def test_parse_accepts_bare_list_file(tmp_path) -> None:
    """Real MinerU 3.4.4 writes the content list as a bare JSON array."""
    payload_path = tmp_path / "nd-168-2024_content_list.json"
    payload_path.write_text(json.dumps(make_content_list(), ensure_ascii=False), encoding="utf-8")
    doc = parse_default(str(payload_path))
    assert len(doc.pages) == 2
    assert doc.pages[0].elements[0].element_type == "heading"


def test_parse_real_mineru_output_shape() -> None:
    """Compatibility with the real mineru 3.4.4 item shape (verified sources)."""
    items = [
        # Table: HTML under table_body, caption list instead of text.
        {
            "type": "table",
            "table_body": "<table><tr><td>x</td></tr></table>",
            "table_caption": ["Bảng 1. Tiêu chí"],
            "bbox": [0, 10, 100, 90],
            "page_idx": 0,
        },
        # Image: caption list + img_path, no text field.
        {
            "type": "image",
            "img_path": "images/2.jpg",
            "image_caption": ["Hình 1. Sơ đồ"],
            "bbox": [0, 100, 500, 300],
            "page_idx": 0,
        },
        # Title emitted as type=text + text_level → heading.
        {
            "type": "text",
            "text": "Điều 3. Giải thích từ ngữ",
            "text_level": 1,
            "bbox": [0, 310, 500, 330],
            "page_idx": 0,
        },
        # List item: list_items instead of text.
        {
            "type": "list",
            "list_items": ["a) điểm a", "b) điểm b"],
            "bbox": [0, 340, 500, 400],
            "page_idx": 0,
        },
    ]
    doc = parse_default(items)
    table_element, image_element, heading_element, list_element = doc.pages[0].elements
    assert table_element.element_type == "table"
    assert table_element.table_html == "<table><tr><td>x</td></tr></table>"
    assert table_element.text == "Bảng 1. Tiêu chí"
    assert image_element.element_type == "figure"
    assert image_element.text == "Hình 1. Sơ đồ"
    assert heading_element.element_type == "heading"
    assert heading_element.text == "Điều 3. Giải thích từ ngữ"
    assert list_element.element_type == "list_item"
    assert list_element.text == "a) điểm a\nb) điểm b"


def test_parse_box_alias_and_missing_bbox() -> None:
    items = [
        {"type": "text", "text": "dùng box", "box": [1.0, 2.0, 3.0, 4.0], "page_idx": 0},
        {"type": "text", "text": "không bbox", "page_idx": 0},
        {"type": "text", "text": "bbox hỏng", "bbox": "nope", "page_idx": 0},
    ]
    elements = parse_default(items).pages[0].elements
    assert elements[0].bbox == BoundingBox(left=1.0, top=2.0, right=3.0, bottom=4.0)
    assert elements[1].bbox is None
    assert elements[2].bbox is None


def test_parse_table_html_from_cells() -> None:
    items = [
        {
            "type": "table",
            "cells": [["cột a", "cột b"], ["1", "2"]],
            "bbox": [0, 0, 100, 50],
            "page_idx": 0,
        }
    ]
    table_element = parse_default(items).pages[0].elements[0]
    assert table_element.table_html == (
        "<table><tr><td>cột a</td><td>cột b</td></tr><tr><td>1</td><td>2</td></tr></table>"
    )


def test_parse_page_number_alias() -> None:
    """An explicit 1-based page_number key is accepted when page_idx is absent."""
    items = [{"type": "text", "text": "trang 3", "page_number": 3, "bbox": [0, 0, 1, 1]}]
    doc = parse_default(items)
    assert [page.page_number for page in doc.pages] == [3]
    assert doc.pages[0].elements[0].page_number == 3
    assert doc.pages[0].elements[0].raw_reference["mineru_page_idx"] is None


def test_parse_injected_parser_version() -> None:
    doc = MinerUAdapter().parse(
        {"content_list": make_content_list()},
        source_object_key=_SOURCE_OBJECT_KEY,
        parsed_document_id=_PARSED_DOCUMENT_ID,
        document_id=_DOCUMENT_ID,
        parser_version="mineru-3.4.4-custom",
    )
    assert doc.parser_version == "mineru-3.4.4-custom"
    assert all(
        element.parser_version == "mineru-3.4.4-custom"
        for page in doc.pages
        for element in page.elements
    )


def test_parse_output_validates_with_extra_forbid() -> None:
    """The produced IR is schema-clean and rejects undeclared fields."""
    doc = parse_default(make_content_list())
    # Round-trip through JSON reproduces an equal document (frozen contract).
    restored = ParsedDocument.model_validate_json(doc.model_dump_json())
    assert restored == doc
    # extra="forbid" on every IR level.
    element_payload = doc.pages[0].elements[0].model_dump()
    element_payload["extra"] = "nope"
    with pytest.raises(ValidationError):
        DocumentElement.model_validate(element_payload)
    page_payload = doc.pages[0].model_dump()
    page_payload["extra"] = "nope"
    with pytest.raises(ValidationError):
        ParsedPage.model_validate(page_payload)


def test_parse_rejects_malformed_input() -> None:
    with pytest.raises(ValueError, match="content_list"):
        parse_default({"not_content_list": []})
    with pytest.raises(ValueError, match="must be dicts"):
        parse_default(["not-a-dict"])


def test_run_mineru_raises_env_error_with_documented_message(monkeypatch) -> None:
    """run_mineru surfaces the documented blocker without executing MinerU."""
    monkeypatch.setattr(mineru_adapter, "_mineru_env_blocker", lambda: MINERU_ENV_ERROR_MESSAGE)
    with pytest.raises(MinerUEnvironmentError) as excinfo:
        mineru_adapter.run_mineru("some.pdf")
    message = str(excinfo.value)
    assert "find_pruneable_heads_and_indices" in message
    assert "transformers" in message
    assert "VNLRAG-20" in message


def test_run_mineru_not_wired_when_environment_ok(monkeypatch) -> None:
    monkeypatch.setattr(mineru_adapter, "_mineru_env_blocker", lambda: None)
    with pytest.raises(RuntimeError, match="VNLRAG-97"):
        mineru_adapter.run_mineru("some.pdf")
