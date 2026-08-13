"""Unit tests: legal metadata extraction from the Canonical IR (VNLRAG-25).

Covers the three fixture document types (DECREE / LAW / CIRCULAR — doc 06
§6.2 fixture policy), deterministic field extraction, effective-date
extraction, and validation against the authoritative corpus manifest
(doc 03 §3.7.5 auto-accept policy).
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.metadata_extractor import (
    ExtractedDocumentMetadata,
    extract_document_metadata,
    validate_against_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH_01 = REPO_ROOT / "data" / "manifests" / "batch-01"


def _load_manifest(document_id: str) -> dict[str, object]:
    return json.loads((BATCH_01 / f"{document_id}.manifest.json").read_text(encoding="utf-8"))


def _document(
    elements: list[tuple[str, str]], *, document_id: str = "nd-168-2024"
) -> ParsedDocument:
    """Build a canonical IR document from (text, element_type) pairs on page 1."""
    ir_elements: list[DocumentElement] = []
    for index, (text, element_type) in enumerate(elements):
        ir_elements.append(
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
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=ir_elements)],
        parse_started_at=datetime(2024, 1, 1, tzinfo=UTC),
        parse_completed_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC),
        quality_report={},
    )


# ─────────────────────────── DECREE (nd-168-2024) ───────────────────────────


def _nd_document() -> ParsedDocument:
    return _document(
        [
            ("CHÍNH PHỦ", "page_header"),
            ("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "page_header"),
            ("NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH", "title"),
            ("Hà Nội, ngày 26 tháng 12 năm 2024", "paragraph"),
            ("Điều 1. Phạm vi điều chỉnh", "heading"),
        ],
        document_id="nd-168-2024",
    )


def test_decree_extracts_number_type_issuer_and_date() -> None:
    metadata = extract_document_metadata(_nd_document())

    assert metadata.document_number == "168/2024/NĐ-CP"
    assert metadata.document_type == "DECREE"
    assert metadata.issuer == "Chính phủ"
    assert metadata.issued_date == date(2024, 12, 26)
    assert metadata.document_title == "NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH"


def test_decree_metadata_matches_manifest() -> None:
    metadata = extract_document_metadata(_nd_document())
    assert validate_against_manifest(metadata, _load_manifest("nd-168-2024")) == []


def test_decree_effective_from_extracted_from_full_text() -> None:
    document = _nd_document()
    document = document.model_copy(
        update={
            "pages": [
                document.pages[0].model_copy(
                    update={
                        "elements": document.pages[0].elements
                        + [
                            DocumentElement(
                                element_id="e-last",
                                element_type="paragraph",
                                text="Điều 52. Điều khoản thi hành. Nghị định này có hiệu lực "
                                "thi hành từ ngày 01 tháng 01 năm 2025.",
                                page_number=1,
                                bbox=None,
                                reading_order=99,
                                parent_element_id=None,
                                source_parser="TEST",
                                parser_version="test-1",
                                parser_confidence=None,
                                raw_reference={},
                            )
                        ]
                    }
                )
            ]
        }
    )
    metadata = extract_document_metadata(document)
    assert metadata.effective_from == date(2025, 1, 1)


# ─────────────────────────────── LAW (luat-36-2024) ───────────────────────────────


def _law_document() -> ParsedDocument:
    return _document(
        [
            ("QUỐC HỘI", "page_header"),
            ("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "page_header"),
            ("LUẬT TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ 2024", "title"),
            ("Số: 36/2024/QH15", "paragraph"),
            ("Hà Nội, ngày 27 tháng 6 năm 2024", "paragraph"),
        ],
        document_id="luat-36-2024-qh15",
    )


def test_law_extracts_number_type_issuer_and_date() -> None:
    metadata = extract_document_metadata(_law_document())

    assert metadata.document_number == "36/2024/QH15"
    assert metadata.document_type == "LAW"
    assert metadata.issuer == "Quốc hội"
    assert metadata.issued_date == date(2024, 6, 27)


def test_law_metadata_matches_manifest() -> None:
    metadata = extract_document_metadata(_law_document())
    assert validate_against_manifest(metadata, _load_manifest("luat-36-2024-qh15")) == []


# ──────────────────────────── CIRCULAR (tt-24-2023) ────────────────────────────


def _circular_document() -> ParsedDocument:
    return _document(
        [
            ("BỘ CÔNG AN", "page_header"),
            ("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", "page_header"),
            ("THÔNG TƯ 24/2023/TT-BCA QUY ĐỊNH VỀ CẤP, THU HỒI ĐĂNG KÝ", "title"),
            ("Hà Nội, ngày 01 tháng 7 năm 2023", "paragraph"),
        ],
        document_id="tt-24-2023",
    )


def test_circular_extracts_number_type_issuer_and_date() -> None:
    metadata = extract_document_metadata(_circular_document())

    assert metadata.document_number == "24/2023/TT-BCA"
    assert metadata.document_type == "CIRCULAR"
    assert metadata.issuer == "Bộ Công an"
    assert metadata.issued_date == date(2023, 7, 1)


def test_circular_metadata_matches_manifest() -> None:
    metadata = extract_document_metadata(_circular_document())
    assert validate_against_manifest(metadata, _load_manifest("tt-24-2023")) == []


def test_circular_effective_from_with_ke_tu_wording() -> None:
    """Official TT wording: "có hiệu lực thi hành kể từ ngày 15/8/2023"."""
    document = _circular_document()
    document = document.model_copy(
        update={
            "pages": [
                document.pages[0].model_copy(
                    update={
                        "elements": document.pages[0].elements
                        + [
                            DocumentElement(
                                element_id="e-last",
                                element_type="paragraph",
                                text="Điều 10. Điều khoản thi hành. Thông tư này có hiệu lực "
                                "thi hành kể từ ngày 15/8/2023.",
                                page_number=1,
                                bbox=None,
                                reading_order=99,
                                parent_element_id=None,
                                source_parser="TEST",
                                parser_version="test-1",
                                parser_confidence=None,
                                raw_reference={},
                            )
                        ]
                    }
                )
            ]
        }
    )
    metadata = extract_document_metadata(document)
    assert metadata.effective_from == date(2023, 8, 15)


# ─────────────────────────── determinism & edge cases ───────────────────────────


def test_extraction_is_deterministic() -> None:
    first = extract_document_metadata(_nd_document())
    second = extract_document_metadata(_nd_document())
    assert first == second


def test_title_fallback_uses_first_heading_when_no_title_element() -> None:
    document = _document(
        [
            ("NGHỊ ĐỊNH 168/2024/NĐ-CP", "heading"),
            ("Điều 1. Nội dung", "paragraph"),
        ]
    )
    metadata = extract_document_metadata(document)
    assert metadata.document_title == "NGHỊ ĐỊNH 168/2024/NĐ-CP"


def test_empty_document_returns_empty_metadata() -> None:
    metadata = extract_document_metadata(
        ParsedDocument(
            parsed_document_id="parsed-empty",
            document_id="nd-168-2024",
            parser="TEST",
            parser_version="test-1",
            ir_schema_version="document-ir-v2",
            source_object_key="fixture",
            pages=[],
            parse_started_at=datetime(2024, 1, 1, tzinfo=UTC),
            parse_completed_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC),
            quality_report={},
        )
    )
    assert metadata == ExtractedDocumentMetadata()


def test_iso_date_form_is_supported() -> None:
    document = _document([("NGHỊ ĐỊNH 168/2024/NĐ-CP", "title"), ("2024-12-26", "paragraph")])
    assert extract_document_metadata(document).issued_date == date(2024, 12, 26)


# ─────────────────────────── manifest validation ───────────────────────────


def test_document_number_mismatch_flags_review() -> None:
    metadata = ExtractedDocumentMetadata(document_number="169/2024/NĐ-CP")
    issues = validate_against_manifest(metadata, _load_manifest("nd-168-2024"))
    assert any("document_number mismatch" in issue for issue in issues)


def test_document_type_mismatch_flags_review() -> None:
    metadata = ExtractedDocumentMetadata(document_type="CIRCULAR")
    issues = validate_against_manifest(metadata, _load_manifest("nd-168-2024"))
    assert any("document_type mismatch" in issue for issue in issues)


def test_issued_date_mismatch_flags_review() -> None:
    metadata = ExtractedDocumentMetadata(issued_date=date(2024, 12, 25))
    issues = validate_against_manifest(metadata, _load_manifest("nd-168-2024"))
    assert any("issued_date mismatch" in issue for issue in issues)


def test_issuer_mismatch_flags_review() -> None:
    metadata = ExtractedDocumentMetadata(issuer="Quốc hội")
    issues = validate_against_manifest(metadata, _load_manifest("nd-168-2024"))
    assert any("issuer mismatch" in issue for issue in issues)


def test_effective_from_mismatch_flags_review() -> None:
    metadata = ExtractedDocumentMetadata(effective_from=date(2025, 1, 2))
    issues = validate_against_manifest(metadata, _load_manifest("nd-168-2024"))
    assert any("effective_from mismatch" in issue for issue in issues)


def test_effective_to_mismatch_flags_review() -> None:
    metadata = ExtractedDocumentMetadata(effective_to=date(2026, 12, 31))
    issues = validate_against_manifest(metadata, _load_manifest("tt-24-2023"))
    assert any("effective_to mismatch" in issue for issue in issues)


def test_missing_extracted_values_do_not_flag_review() -> None:
    """IR without a confident value must not contradict the manifest."""
    assert (
        validate_against_manifest(ExtractedDocumentMetadata(), _load_manifest("nd-168-2024")) == []
    )


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("status", "ACTIVE"),
        ("review_status", "REVIEWED"),
        ("document_type", "STATUTE"),
    ],
)
def test_invalid_manifest_enums_flag_review(field: str, bad_value: str) -> None:
    manifest = _load_manifest("nd-168-2024")
    manifest[field] = bad_value
    issues = validate_against_manifest(ExtractedDocumentMetadata(), manifest)
    assert any(field in issue and "not a valid" in issue for issue in issues)


def test_manifest_accepts_pending_review_without_review_fields() -> None:
    manifest = _load_manifest("nd-168-2024")
    manifest["review_status"] = "PENDING"
    manifest.pop("reviewed_by", None)
    manifest.pop("reviewed_at", None)
    metadata = extract_document_metadata(_nd_document())
    assert validate_against_manifest(metadata, manifest) == []
