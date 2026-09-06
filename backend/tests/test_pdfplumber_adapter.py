from collections import Counter

from app.ingestion.adapters.pdfplumber_adapter import (
    SearchableTextRequiredError,
    _clean_line_entries,
    clean_lines,
    table_to_markdown,
)


def test_clean_lines_preserves_vietnamese_headings_and_merges_continuation():
    lines = clean_lines(
        [
            "Chương I. Quy định chung",
            "Nội dung về an toàn",
            "giao thông đường bộ.",
            "Điều 1. Phạm vi",
        ],
    )
    assert lines == [
        "Chương I. Quy định chung",
        "Nội dung về an toàn giao thông đường bộ.",
        "Điều 1. Phạm vi",
    ]


def test_clean_lines_removes_page_chrome_and_page_numbers():
    lines = clean_lines(
        ["BỘ GIAO THÔNG VẬN TẢI", "Trang 2 / 10", "Điều 2. Nội dung"],
        Counter({"bộ giao thông vận tải": 2}),
    )
    assert lines == ["Điều 2. Nội dung"]


def test_table_to_markdown_preserves_cells_and_merged_values():
    result = table_to_markdown([["Mức phạt", "GPLX"], ["100.000", ""], ["", "Tước"]])
    assert "| Mức phạt | GPLX |" in result
    assert "| 100.000 | GPLX |" in result
    assert "| 100.000 | Tước |" in result
    assert "|---|---|" in result


def test_scanned_failure_is_explicitly_not_ocr():
    assert issubclass(SearchableTextRequiredError, RuntimeError)


def test_searchable_alternate_can_be_named_without_changing_scan_route():
    from datetime import UTC, datetime

    from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
    from app.ingestion.parser_router import ParserRouter, RoutingInputs

    now = datetime.now(UTC)
    element = DocumentElement(
        element_id="p1-e0",
        element_type="paragraph",
        text="Điều 1. Nội dung",
        page_number=1,
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
        reading_order=0,
        parent_element_id=None,
        source_parser="PDFPLUMBER",
        parser_version="pdfplumber-0",
        parser_confidence=None,
        raw_reference={"pdfplumber_page": 1},
    )
    alternate = ParsedDocument(
        parsed_document_id="00000000-0000-4000-8000-000000000001",
        document_id="task1",
        parser="PDFPLUMBER",
        parser_version="pdfplumber-0",
        ir_schema_version="document-ir-v2",
        source_object_key="task1.pdf",
        pages=[
            ParsedPage(page_number=1, width=100, height=100, text=element.text, elements=[element])
        ],
        parse_started_at=now,
        parse_completed_at=now,
        quality_report={},
    )
    inputs = RoutingInputs(
        document_id="task1",
        file_mime="application/pdf",
        has_text_layer=True,
        page_count=1,
        file_size_bytes=10,
    )
    _, outcome = ParserRouter().route_and_gate(
        inputs,
        lambda: (_ for _ in ()).throw(RuntimeError("docling unavailable")),
        alternate_runner=lambda: alternate,
        alternate_parser="pdfplumber",
    )
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "pdfplumber"


def test_clean_line_entries_keeps_bbox_aligned_after_removed_header():
    entries = _clean_line_entries(
        [
            ("Trang 2 / 10", (0, 1, 100, 10)),
            ("Điều 2. Nội dung", (10, 20, 90, 30)),
        ]
    )
    assert entries == [("Điều 2. Nội dung", (10, 20, 90, 30))]


def test_clean_line_entries_unions_bbox_for_merged_continuation():
    entries = _clean_line_entries(
        [
            ("Nội dung về an toàn", (10, 20, 60, 30)),
            ("giao thông đường bộ.", (5, 31, 95, 40)),
        ]
    )
    assert entries == [("Nội dung về an toàn giao thông đường bộ.", (5, 20, 95, 40))]
