from __future__ import annotations

from datetime import UTC, datetime

from app.ingestion.document_ir import DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.structure_state_parser import StructureKind, parse_structure_state


def test_ocr_article_variants_are_recognized_with_canonical_heading_prefix_only() -> None:
    elements = [
        DocumentElement(
            element_id="e1",
            element_type="paragraph",
            text="Dièu 1. Phạm vi",
            page_number=1,
            reading_order=0,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
        DocumentElement(
            element_id="e2",
            element_type="paragraph",
            text="Dieu 2. Nội dung",
            page_number=1,
            reading_order=1,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
        DocumentElement(
            element_id="e3",
            element_type="paragraph",
            text="Ðiều khoản này giữ Dieu nguyên văn",
            page_number=1,
            reading_order=2,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
    ]
    document = ParsedDocument(
        parsed_document_id="p",
        document_id="d",
        parser="TEST",
        parser_version="1",
        ir_schema_version="document-ir-v2",
        source_object_key="x",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )
    nodes = parse_structure_state(document)
    assert [(node.kind, node.number, node.text) for node in nodes] == [
        (StructureKind.ARTICLE, "1", "Điều 1. Phạm vi"),
        (StructureKind.ARTICLE, "2", "Điều 2. Nội dung"),
    ]
    assert "Dieu" not in nodes[0].text


def test_article_reference_is_prose_not_article_boundary() -> None:
    elements = [
        DocumentElement(
            element_id="e1",
            element_type="paragraph",
            text="Điều 5. Phạm vi điều chỉnh",
            page_number=1,
            reading_order=0,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
        DocumentElement(
            element_id="e2",
            element_type="paragraph",
            text="Điều 5 Nghị định này và Luật giao thông.",
            page_number=1,
            reading_order=1,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
        DocumentElement(
            element_id="e3",
            element_type="paragraph",
            text="Điều 6",
            page_number=1,
            reading_order=2,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
    ]
    document = ParsedDocument(
        parsed_document_id="p",
        document_id="d",
        parser="TEST",
        parser_version="1",
        ir_schema_version="document-ir-v2",
        source_object_key="x",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )
    nodes = parse_structure_state(document)
    assert [(node.kind, node.number) for node in nodes] == [
        (StructureKind.ARTICLE, "5"),
        (StructureKind.ARTICLE, "6"),
    ]


def test_appendix_forms_reset_article_state() -> None:
    elements = []
    for i, text in enumerate(
        ["Điều 4. Thân bài", "1. Khoản cũ", "PHỤ LỤC", "Mẫu số 01A. Biểu", "1. Trường form"]
    ):
        elements.append(
            DocumentElement(
                element_id=f"x{i}",
                element_type="paragraph",
                text=text,
                page_number=1,
                reading_order=i,
                parent_element_id=None,
                source_parser="TEST",
                parser_version="1",
                parser_confidence=None,
                raw_reference={},
            )
        )
    document = ParsedDocument(
        parsed_document_id="p",
        document_id="d",
        parser="TEST",
        parser_version="1",
        ir_schema_version="document-ir-v2",
        source_object_key="x",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )
    nodes = parse_structure_state(document)
    assert [(n.kind, n.number) for n in nodes] == [
        (StructureKind.ARTICLE, "4"),
        (StructureKind.CLAUSE, "1"),
        (StructureKind.APPENDIX, "1"),
        (StructureKind.APPENDIX, "01A"),
        (StructureKind.CLAUSE, "1"),
    ]


def test_point_label_variants_dot_fullwidth_and_ocr_accents_are_recognized() -> None:
    elements = []
    for i, text in enumerate(
        ["Điều 1. Phạm vi", "1. Nội dung", "a. Mục thứ nhất", "b） Mục thứ hai", "đ) Mục thứ ba"]
    ):
        elements.append(
            DocumentElement(
                element_id=f"v{i}",
                element_type="paragraph",
                text=text,
                page_number=1,
                reading_order=i,
                parent_element_id=None,
                source_parser="TEST",
                parser_version="1",
                parser_confidence=None,
                raw_reference={},
            )
        )
    document = ParsedDocument(
        parsed_document_id="p",
        document_id="d",
        parser="TEST",
        parser_version="1",
        ir_schema_version="document-ir-v2",
        source_object_key="x",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )
    nodes = parse_structure_state(document)
    assert [(node.kind, node.label) for node in nodes] == [
        (StructureKind.ARTICLE, "Phạm vi"),
        (StructureKind.CLAUSE, None),
        (StructureKind.POINT, "a)"),
        (StructureKind.POINT, "b)"),
        (StructureKind.POINT, "đ)"),
    ]


def test_article_in_quoted_amendment_form_is_not_heading() -> None:
    document = ParsedDocument(
        parsed_document_id="p",
        document_id="nd-161-2024",
        parser="TEST",
        parser_version="1",
        ir_schema_version="document-ir-v2",
        source_object_key="x",
        pages=[
            ParsedPage(
                page_number=1,
                width=1,
                height=1,
                text=None,
                elements=[
                    DocumentElement(
                        element_id="e1",
                        element_type="paragraph",
                        text="Điều 2. “Sửa đổi khoản 1 Điều 2”,",
                        page_number=1,
                        reading_order=0,
                        parent_element_id=None,
                        source_parser="TEST",
                        parser_version="1",
                        parser_confidence=None,
                        raw_reference={},
                    ),
                ],
            )
        ],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )
    assert parse_structure_state(document) == []


def test_semicolon_delimited_points_follow_upstream_re_diem():
    elements = [
        DocumentElement(
            element_id="e1",
            element_type="paragraph",
            text="Điều 1. Phạm vi",
            page_number=1,
            reading_order=0,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
        DocumentElement(
            element_id="e2",
            element_type="paragraph",
            text="1. Nội dung",
            page_number=1,
            reading_order=1,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
        DocumentElement(
            element_id="e3",
            element_type="paragraph",
            text="a) Hành vi thứ nhất; đ) Hành vi thứ hai",
            page_number=1,
            reading_order=2,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="1",
            parser_confidence=None,
            raw_reference={},
        ),
    ]
    document = ParsedDocument(
        parsed_document_id="p",
        document_id="nd-44-2024",
        parser="TEST",
        parser_version="1",
        ir_schema_version="document-ir-v2",
        source_object_key="x",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )
    nodes = parse_structure_state(document)
    assert [(node.kind, node.label, node.text) for node in nodes[-2:]] == [
        (StructureKind.POINT, "a)", "a) Hành vi thứ nhất"),
        (StructureKind.POINT, "đ)", "đ) Hành vi thứ hai"),
    ]
