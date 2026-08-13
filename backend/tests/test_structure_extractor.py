from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft7Validator

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.structure_extractor import LegalStructureExtractor
from app.ingestion.structure_state_parser import parse_structure_state

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "parser_benchmark"
    / "documents"
    / "nd"
    / "nd-168-2024-fixture.pdf.txt"
)
SCHEMA = json.loads(
    (Path(__file__).resolve().parents[2] / "templates" / "legal-provision.schema.json").read_text(
        encoding="utf-8"
    )
)


def _document(lines: list[tuple[str, str]], *, document_id: str = "nd-168-2024") -> ParsedDocument:
    elements: list[DocumentElement] = []
    for index, (text, element_type) in enumerate(lines):
        elements.append(
            DocumentElement(
                element_id=f"e{index}",
                element_type=element_type,
                text=text,
                page_number=1,
                bbox=BoundingBox(left=0.1, top=index / 100, right=0.9, bottom=(index + 1) / 100),
                reading_order=index,
                parent_element_id=None,
                source_parser="TEST",
                parser_version="test-1",
                parser_confidence=None,
                raw_reference={"index": index},
            )
        )
    return ParsedDocument(
        parsed_document_id="parsed-1",
        document_id=document_id,
        parser="TEST",
        parser_version="test-1",
        ir_schema_version="document-ir-v2",
        source_object_key="fixture",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime(2024, 1, 1, tzinfo=UTC),
        parse_completed_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC),
        quality_report={},
    )


def test_full_fixture_preserves_article_clause_point_boundaries() -> None:
    lines = [
        (line, "paragraph")
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    provisions = LegalStructureExtractor().extract(
        _document(lines), document_version_id="version-1"
    )
    ids = {provision.provision_id for provision in provisions}
    assert "nd-168-2024__dieu-5" in ids
    assert "nd-168-2024__dieu-5__khoan-1" in ids
    assert "nd-168-2024__dieu-5__khoan-1__diem-d" in ids
    assert "nd-168-2024__dieu-5__khoan-1__diem-đ" in ids
    assert "nd-168-2024__dieu-7__khoan-1__diem-e" in ids


def test_extracted_records_match_legal_provision_schema() -> None:
    lines = [
        (line, "paragraph")
        for line in FIXTURE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    validator = Draft7Validator(SCHEMA)
    provisions = LegalStructureExtractor().extract(
        _document(lines), document_version_id="version-1"
    )
    assert provisions
    assert all(
        not list(validator.iter_errors(provision.to_schema_dict())) for provision in provisions
    )


def test_page_order_precedes_per_page_reading_order() -> None:
    base = _document(
        [
            ("Điều 6. Tiêu đề", "paragraph"),
            ("1. Khoản", "paragraph"),
            ("a) Điểm", "paragraph"),
        ]
    )
    first, second, third = base.pages[0].elements
    second_page_element = third.model_copy(update={"page_number": 2, "reading_order": 0})
    document = base.model_copy(
        update={
            "pages": [
                base.pages[0].model_copy(update={"elements": [first, second]}),
                ParsedPage(
                    page_number=2, width=1, height=1, text=None, elements=[second_page_element]
                ),
            ]
        }
    )
    provisions = LegalStructureExtractor().extract(document)
    assert provisions[-1].provision_id == "nd-168-2024__dieu-6__khoan-1__diem-a"


def test_manifest_suffix_is_removed_from_legacy_document_id() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [("Điều 3. Giải thích", "paragraph"), ("1. Nội dung", "paragraph")],
            document_id="luat-36-2024-qh15",
        )
    )
    assert provisions[0].provision_id == "luat-36-2024__dieu-3"


def test_d_and_dd_ids_are_distinct_and_source_text_is_unchanged() -> None:
    document = _document(
        [
            ("Điều 7. Xử phạt", "heading"),
            ("1. Hành vi", "paragraph"),
            ("d) Một hành vi ngắn", "paragraph"),
            ("đ) Hành vi có đ", "paragraph"),
            ("d) OCR duplicate after explicit đ", "paragraph"),
        ]
    )
    provisions = LegalStructureExtractor().extract(document)
    points = [provision for provision in provisions if provision.point is not None]
    assert [point.provision_id for point in points] == [
        "nd-168-2024__dieu-7__khoan-1__diem-d",
        "nd-168-2024__dieu-7__khoan-1__diem-đ",
    ]
    assert points[0].source_text == "d) Một hành vi ngắn"
    assert points[0].retrieval_text.endswith(points[0].source_text)
    assert points[0].content_hash != points[1].content_hash


def test_short_point_is_retained_without_length_filter() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [("Điều 1. Tên", "heading"), ("1. Nội dung", "paragraph"), ("a) Có", "paragraph")]
        )
    )
    point = next(provision for provision in provisions if provision.point is not None)
    assert point.short_point is True
    assert point.source_text == "a) Có"


def test_repeated_headers_and_footers_are_not_provisions() -> None:
    document = _document(
        [
            ("Nghị định 168/2024/NĐ-CP", "page_header"),
            ("Điều 1. Tên", "heading"),
            ("1. Nội dung", "paragraph"),
            ("Nghị định 168/2024/NĐ-CP", "page_header"),
            ("Trang 1", "page_footer"),
            ("Trang 1", "page_footer"),
        ]
    )
    nodes = parse_structure_state(document)
    assert all("Nghị định 168" not in node.text for node in nodes)
    assert all("Trang 1" not in node.text for node in nodes)


def test_appendix_table_and_transitional_ids_are_deterministic() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [
                ("Phụ lục 1. Danh mục", "heading"),
                ("Bảng 2. Mức phạt", "table"),
                ("Điều khoản chuyển tiếp", "heading"),
            ]
        )
    )
    assert {provision.provision_id for provision in provisions} == {
        "nd-168-2024__phu-luc-1",
        "nd-168-2024__phu-luc-1__bang-2",
        "nd-168-2024__chuyen-tiep-1",
    }
    assert {provision.node_kind for provision in provisions} == {
        "APPENDIX",
        "TABLE",
        "TRANSITIONAL",
    }


def test_vietnamese_point_alphabet_and_ocr_duplicate_d_are_handled() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [
                ("Điều 2. Nhãn", "heading"),
                ("1. Nội dung", "paragraph"),
                ("ô) Chữ ô", "paragraph"),
                ("d) Chữ d", "paragraph"),
                ("d) OCR có thể là đ", "paragraph"),
            ]
        )
    )
    points = [provision for provision in provisions if provision.point is not None]
    assert [point.provision_id for point in points] == [
        "nd-168-2024__dieu-2__khoan-1__diem-o",
        "nd-168-2024__dieu-2__khoan-1__diem-d",
        "nd-168-2024__dieu-2__khoan-1__diem-đ",
    ]
    assert points[-1].needs_review is True
    assert points[-1].ambiguity is not None


def test_marker_stripped_list_items_reconstruct_clause_and_points() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [
                ("Điều 4. Phạm vi", "paragraph"),
                ("Trong Luật này gồm:", "list_item"),
                ("Một điểm ngắn", "list_item"),
                ("Điểm thứ hai", "list_item"),
            ]
        )
    )
    assert [provision.provision_id for provision in provisions] == [
        "nd-168-2024__dieu-4",
        "nd-168-2024__dieu-4__khoan-1",
        "nd-168-2024__dieu-4__khoan-1__diem-a",
        "nd-168-2024__dieu-4__khoan-1__diem-b",
    ]
    assert all(provision.needs_review for provision in provisions[1:])


def test_invalid_article_suffix_is_not_emitted_and_roman_appendix_is_normalized() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [
                ("Điều 12A. OCR suffix", "heading"),
                ("1. Clause under ambiguous article", "paragraph"),
                ("a) Point under ambiguous article", "paragraph"),
                ("Phụ lục I. Danh mục", "heading"),
            ]
        )
    )
    ids = {provision.provision_id for provision in provisions}
    assert not any("__dieu-12A" in provision_id for provision_id in ids)
    assert "nd-168-2024__phu-luc-1" in ids


def test_unnumbered_tables_and_appendices_receive_unique_ids() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [
                ("Phụ lục. Một", "heading"),
                ("Bảng không số", "table"),
                ("Bảng không số", "table"),
                ("Phụ lục. Hai", "heading"),
            ]
        )
    )
    ids = {provision.provision_id for provision in provisions}
    assert {
        "nd-168-2024__phu-luc-1",
        "nd-168-2024__phu-luc-1__bang-1",
        "nd-168-2024__phu-luc-1__bang-2",
        "nd-168-2024__phu-luc-2",
    } == ids


def test_section_clears_previous_appendix_context() -> None:
    provisions = LegalStructureExtractor().extract(
        _document(
            [
                ("Phụ lục 1. Một", "heading"),
                ("Mục 1. Nội dung mới", "heading"),
                ("Bảng 1. Không thuộc phụ lục cũ", "table"),
            ]
        )
    )
    assert [provision.provision_id for provision in provisions] == ["nd-168-2024__phu-luc-1"]
