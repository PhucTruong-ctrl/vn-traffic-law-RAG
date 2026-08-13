"""Unit tests: projection of IR + extractor output into persistence objects
(VNLRAG-32).

Covers the full 20-field LegalProvision contract (doc 00 §8.3, doc 03 §3.9.4),
deterministic content_hash, deterministic provision_id (diem-d vs diem-đ),
status/review_status independence (only ACCEPTED gates serving), and
validation before persistence.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.metadata_extractor import extract_document_metadata
from app.ingestion.projection import (
    project_document,
    project_provisions,
    validate_provisions,
)
from app.ingestion.structure_extractor import (
    ExtractedLegalProvision,
    LegalStructureExtractor,
)
from app.persistence.models import DocumentVersion, LegalDocument, LegalProvision

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH_01 = REPO_ROOT / "data" / "manifests" / "batch-01"
ND_MANIFEST = json.loads((BATCH_01 / "nd-168-2024.manifest.json").read_text(encoding="utf-8"))

_PROVISION_SCHEMA = json.loads(
    (REPO_ROOT / "templates" / "legal-provision.schema.json").read_text(encoding="utf-8")
)
_PROVISION_ID_PATTERN = _PROVISION_SCHEMA["properties"]["provision_id"]["pattern"]


def _load_manifest(document_id: str) -> dict[str, object]:
    return json.loads((BATCH_01 / f"{document_id}.manifest.json").read_text(encoding="utf-8"))


def _ir(elements: list[tuple[str, str]], *, document_id: str = "nd-168-2024") -> ParsedDocument:
    """Build a canonical IR document from (text, element_type) pairs."""
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


def _nd_ir() -> ParsedDocument:
    return _ir(
        [
            ("CHÍNH PHỦ", "page_header"),
            ("NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH", "title"),
            ("Điều 7. Xử phạt người điều khiển xe mô tô", "heading"),
            ("1. Phạt tiền từ 400.000 đồng đến 600.000 đồng", "paragraph"),
            ("a) Không chấp hành hiệu lệnh của đèn tín hiệu", "paragraph"),
            ("d) Dừng xe, đỗ xe tại nơi có biển cấm dừng", "paragraph"),
            ("đ) Lùi xe không quan sát phía sau", "paragraph"),
        ]
    )


def _extracted(ir: ParsedDocument) -> list[ExtractedLegalProvision]:
    return LegalStructureExtractor().extract(ir, document_version_id="version-1")


# ─────────────────────────── document projection ───────────────────────────


def test_project_document_maps_manifest_fields() -> None:
    document, document_version = project_document(
        _nd_ir(), ND_MANIFEST, extract_document_metadata(_nd_ir())
    )

    assert isinstance(document, LegalDocument)
    assert isinstance(document_version, DocumentVersion)
    assert document.document_id == "nd-168-2024"
    assert document.document_number == "168/2024/NĐ-CP"
    assert document.document_type == "DECREE"
    assert document.issuer == "Chính phủ"
    assert document.issued_date == date(2024, 12, 26)
    assert document.source_url == ND_MANIFEST["source_url"]
    assert document.file_hash == ND_MANIFEST["file_hash"]
    assert document.status == "EFFECTIVE"
    assert document.document_title == "NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH"


def test_project_document_version_maps_manifest() -> None:
    _, document_version = project_document(
        _nd_ir(), ND_MANIFEST, extract_document_metadata(_nd_ir())
    )

    assert document_version.document_id == "nd-168-2024"
    assert document_version.version == 1
    assert document_version.manifest_json == ND_MANIFEST
    assert document_version.effective_from == date(2025, 1, 1)
    assert document_version.effective_to is None
    assert document_version.review_status == "ACCEPTED"


def test_document_version_content_hash_is_sha256_of_canonical_manifest() -> None:
    _, first = project_document(_nd_ir(), ND_MANIFEST, extract_document_metadata(_nd_ir()))
    _, second = project_document(_nd_ir(), ND_MANIFEST, extract_document_metadata(_nd_ir()))

    expected = hashlib.sha256(
        json.dumps(ND_MANIFEST, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    assert first.content_hash == expected
    assert first.content_hash == second.content_hash

    changed = dict(ND_MANIFEST)
    changed["relation_notes"] = "changed"
    _, changed_version = project_document(_nd_ir(), changed, extract_document_metadata(_nd_ir()))
    assert changed_version.content_hash != first.content_hash


def test_project_document_rejects_malformed_manifest() -> None:
    manifest = dict(ND_MANIFEST)
    manifest["document_type"] = 42
    with pytest.raises(ValueError, match="document_type"):
        project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("document_type", "STATUTE", "DocumentType"),
        ("status", "ACTIVE", "DocumentStatus"),
        ("review_status", "REVIEWED", "ReviewStatus"),
    ],
)
def test_project_document_rejects_invalid_enums(field: str, bad_value: str, message: str) -> None:
    manifest = dict(ND_MANIFEST)
    manifest[field] = bad_value
    with pytest.raises(ValueError, match=message):
        project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))


def test_project_document_rejects_accepted_without_effective_from() -> None:
    manifest = dict(ND_MANIFEST)
    manifest["effective_from"] = None
    with pytest.raises(ValueError, match="effective_from"):
        project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))


def test_project_document_rejects_malformed_effective_from() -> None:
    """Trailing garbage must not be silently truncated to a valid date."""
    manifest = dict(ND_MANIFEST)
    manifest["effective_from"] = "2025-01-01not-a-date"
    with pytest.raises(ValueError, match="effective_from"):
        project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))


def test_project_document_accepts_full_datetime_effective_from() -> None:
    manifest = dict(ND_MANIFEST)
    manifest["effective_from"] = "2025-01-01T00:00:00+07:00"
    _, document_version = project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))
    assert document_version.effective_from == date(2025, 1, 1)


def test_project_document_rejects_inverted_interval() -> None:
    manifest = dict(ND_MANIFEST)
    manifest["effective_from"] = "2025-01-02"
    manifest["effective_to"] = "2025-01-01"
    with pytest.raises(ValueError, match="effective_to"):
        project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))


def test_project_document_rejects_manifest_conflicting_with_ir() -> None:
    """A manifest contradicting the extracted IR must be routed to review,
    never projected as ACCEPTED (doc 03 §3.7.5 auto-accept policy)."""
    manifest = dict(ND_MANIFEST)
    manifest["document_number"] = "999/2024/NĐ-CP"
    with pytest.raises(ValueError, match="manifest conflicts with extracted IR"):
        project_document(_nd_ir(), manifest, extract_document_metadata(_nd_ir()))


def test_project_document_accepts_ir_without_extracted_number() -> None:
    """IR lacking a confident value does not contradict the manifest."""
    ir = _ir(
        [
            ("Điều 7. Xử phạt người điều khiển xe mô tô", "heading"),
            ("1. Phạt tiền từ 400.000 đồng", "paragraph"),
        ]
    )
    document, document_version = project_document(ir, ND_MANIFEST, extract_document_metadata(ir))
    assert document.document_number == "168/2024/NĐ-CP"
    assert document_version.review_status == "ACCEPTED"


# ─────────────────────────── provision projection ───────────────────────────


def _projected_provisions(
    *,
    status: str = "UNKNOWN",
    review_status: str = "PENDING",
) -> tuple[list[LegalProvision], list[ExtractedLegalProvision]]:
    extracted = _extracted(_nd_ir())
    version_id = uuid4()
    provisions = project_provisions(
        extracted,
        document_version_id=version_id,
        status=status,
        review_status=review_status,
    )
    return provisions, extracted


def test_projection_round_trips_all_20_fields() -> None:
    version_id = uuid4()
    extracted = _extracted(_nd_ir())
    provisions = project_provisions(extracted, document_version_id=version_id)

    assert len(provisions) == len(extracted)
    for provision, source in zip(provisions, extracted, strict=True):
        assert provision.provision_id == source.provision_id
        assert provision.document_version_id == version_id
        assert provision.node_kind == source.node_kind
        assert provision.chapter == source.chapter
        assert provision.section == source.section
        assert provision.article == source.article
        assert provision.clause == source.clause
        assert provision.point == source.point
        assert provision.heading == source.heading
        assert provision.source_text == source.source_text
        assert provision.retrieval_text == source.retrieval_text
        assert provision.parent_context == source.parent_context
        assert provision.effective_from == (
            date.fromisoformat(source.effective_from) if source.effective_from else None
        )
        assert provision.effective_to == (
            date.fromisoformat(source.effective_to) if source.effective_to else None
        )
        assert provision.status == source.status
        assert provision.page_number == source.page_number
        assert provision.bbox == source.bbox
        assert provision.source_element_ids == source.source_element_ids
        assert provision.content_hash == source.content_hash
        assert provision.version == source.version
        assert provision.review_status == source.review_status


def test_projection_preserves_per_item_temporal_and_lifecycle_fields() -> None:
    """Extractor-supplied interval/status/review_status survive without overrides."""
    extracted = _extracted(_nd_ir())
    extracted = [
        item.model_copy(
            update={
                "effective_from": "2025-01-01",
                "effective_to": None,
                "status": "EFFECTIVE",
                "review_status": "ACCEPTED",
            }
        )
        for item in extracted
    ]
    provisions = project_provisions(extracted, document_version_id=uuid4())

    for provision, _source in zip(provisions, extracted, strict=True):
        assert provision.effective_from == date(2025, 1, 1)
        assert provision.effective_to is None
        assert provision.status == "EFFECTIVE"
        assert provision.review_status == "ACCEPTED"


def test_projection_preserves_source_text_verbatim() -> None:
    provisions, extracted = _projected_provisions()
    for provision, source in zip(provisions, extracted, strict=True):
        assert provision.source_text == source.source_text
        assert provision.retrieval_text.endswith(source.source_text)


def test_content_hash_stable_and_matches_extractor() -> None:
    provisions, extracted = _projected_provisions()
    for provision, source in zip(provisions, extracted, strict=True):
        assert re.fullmatch(r"[a-f0-9]{64}", provision.content_hash)
        assert provision.content_hash == source.content_hash


def test_content_hash_mismatch_raises() -> None:
    extracted = _extracted(_nd_ir())
    extracted[0] = extracted[0].model_copy(update={"content_hash": "0" * 64})
    with pytest.raises(ValueError, match="content_hash mismatch"):
        project_provisions(extracted, document_version_id=uuid4())


def test_provision_id_pattern_holds_through_projection() -> None:
    provisions, _ = _projected_provisions()
    for provision in provisions:
        assert re.fullmatch(_PROVISION_ID_PATTERN, provision.provision_id)


def test_diem_d_and_diem_dd_ids_are_distinct() -> None:
    """Deterministic provision_id: diem-d and diem-đ never collide (FR-03)."""
    provisions, _ = _projected_provisions()
    ids = {provision.provision_id for provision in provisions}
    assert "nd-168-2024__dieu-7__khoan-1__diem-d" in ids
    assert "nd-168-2024__dieu-7__khoan-1__diem-đ" in ids
    assert ids == {
        "nd-168-2024__tieu-de-1",
        "nd-168-2024__dieu-7",
        "nd-168-2024__dieu-7__khoan-1",
        "nd-168-2024__dieu-7__khoan-1__diem-a",
        "nd-168-2024__dieu-7__khoan-1__diem-d",
        "nd-168-2024__dieu-7__khoan-1__diem-đ",
    }


def test_status_and_review_status_are_independent() -> None:
    """status (legal lifecycle) never constrains review_status (corpus gate)."""
    provisions, _ = _projected_provisions(status="EXPIRED", review_status="PENDING")
    assert all(provision.status == "EXPIRED" for provision in provisions)
    assert all(provision.review_status == "PENDING" for provision in provisions)
    assert validate_provisions(provisions) == []

    provisions_accepted, _ = _projected_provisions(status="EFFECTIVE", review_status="ACCEPTED")
    for provision in provisions_accepted:
        provision.effective_from = date(2025, 1, 1)
    assert validate_provisions(provisions_accepted) == []


def test_only_accepted_gates_serving() -> None:
    """review_status is the serving gate: ACCEPTED required, status irrelevant."""
    from app.persistence.repositories.temporal import TemporalRepository

    provisions, _ = _projected_provisions(status="EFFECTIVE", review_status="ACCEPTED")
    for provision in provisions:
        provision.effective_from = date(2025, 1, 1)
    assert all(TemporalRepository.is_valid_at(p, date(2025, 6, 1)) for p in provisions)

    rejected, _ = _projected_provisions(status="EFFECTIVE", review_status="REJECTED")
    for provision in rejected:
        provision.effective_from = date(2025, 1, 1)
    assert not any(TemporalRepository.is_valid_at(p, date(2025, 6, 1)) for p in rejected)


# ─────────────────────────── validation before persistence ───────────────────────────


def _valid_provision(**overrides: object) -> LegalProvision:
    source_text = "a) Không chấp hành hiệu lệnh của đèn tín hiệu"
    provision = LegalProvision(
        provision_id="nd-168-2024__dieu-7__khoan-1__diem-a",
        document_version_id=uuid4(),
        node_kind="POINT",
        chapter=None,
        section=None,
        article="Điều 7",
        clause="Khoản 1",
        point="Điểm a)",
        heading=None,
        source_text=source_text,
        retrieval_text="Khoản 1. Nội dung. a) Không chấp hành hiệu lệnh",
        parent_context=None,
        effective_from=None,
        effective_to=None,
        status="UNKNOWN",
        page_number=1,
        bbox={"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.12},
        source_element_ids=["e1"],
        content_hash=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        version=1,
        review_status="PENDING",
    )
    for name, value in overrides.items():
        setattr(provision, name, value)
    return provision


def test_validation_accepts_complete_provision() -> None:
    assert validate_provisions([_valid_provision()]) == []


@pytest.mark.parametrize(
    "override",
    [
        {"source_text": ""},
        {"retrieval_text": ""},
        {"source_element_ids": []},
        {"page_number": 0},
        {"version": 0},
        {"status": "ACTIVE"},
        {"review_status": "REVIEWED"},
        {"node_kind": "UNKNOWN_KIND"},
        {"article": None, "node_kind": "ARTICLE"},
        {"effective_from": date(2025, 2, 1), "effective_to": date(2025, 1, 1)},
        {"review_status": "ACCEPTED", "effective_from": None},
    ],
)
def test_validation_rejects_incomplete_provision(override: dict[str, object]) -> None:
    errors = validate_provisions([_valid_provision(**override)])
    assert errors, f"expected rejection for {override}"


@pytest.mark.parametrize(
    "override",
    [
        {"provision_id": "dieu-7"},  # violates frozen ID grammar
        {"content_hash": "sha256:" + "a" * 64},  # prefixed hash
        {"content_hash": "XYZ"},  # non-hex
        {"content_hash": "b" * 64},  # does not hash source_text
        {"source_element_ids": ["e1", "e1"]},  # duplicate element ids
        {"bbox": {"left": 0.1, "top": 0.1}},  # missing right/bottom
        {"bbox": {"left": 0.1, "top": 0.1, "right": "x", "bottom": 0.2}},  # non-numeric
        {
            "bbox": {
                "left": 0.1,
                "top": 0.1,
                "right": 0.9,
                "bottom": 0.2,
                "coordinate_space": "NORMALIZED_PAGE",
            }
        },  # schema-forbidden key
    ],
)
def test_validation_rejects_frozen_contract_violations(override: dict[str, object]) -> None:
    errors = validate_provisions([_valid_provision(**override)])
    assert errors, f"expected rejection for {override}"


def test_validation_accepts_bbox_with_page_dimensions() -> None:
    provision = _valid_provision(
        bbox={
            "left": 0.1,
            "top": 0.1,
            "right": 0.9,
            "bottom": 0.2,
            "page_height": 842.0,
            "page_width": 595.0,
        }
    )
    assert validate_provisions([provision]) == []


def test_validation_allows_articleless_non_article_kinds() -> None:
    for kind in ("APPENDIX", "TABLE", "HEADING", "TRANSITIONAL", "OTHER"):
        provision = _valid_provision(node_kind=kind, article=None)
        assert validate_provisions([provision]) == [], f"node_kind {kind} must not need article"


def test_validation_accepts_null_effective_dates_when_pending() -> None:
    provision = _valid_provision(review_status="PENDING")
    assert provision.effective_from is None and provision.effective_to is None
    assert validate_provisions([provision]) == []


def test_projected_nd_provisions_validate() -> None:
    provisions, _ = _projected_provisions()
    assert validate_provisions(provisions) == []


# ─────────────────────────── LAW/CIRCULAR fixtures (round-trip) ───────────────────────────


@pytest.mark.parametrize(
    ("document_id", "lines"),
    [
        (
            "luat-36-2024-qh15",
            [
                ("QUỐC HỘI", "page_header"),
                ("LUẬT TRẬT TỰ, AN TOÀN GIAO THÔNG ĐƯỜNG BỘ 2024", "title"),
                ("Số: 36/2024/QH15", "paragraph"),
                ("Chương I. NHỮNG QUY ĐỊNH CHUNG", "heading"),
                ("Điều 3. Giải thích từ ngữ", "heading"),
                ("1. Trong Luật này, các từ ngữ dưới đây được hiểu như sau:", "paragraph"),
                ("a) Phương tiện giao thông đường bộ gồm phương tiện cơ giới", "paragraph"),
                ("đ) Người đi bộ là người đi bộ trên đường bộ", "paragraph"),
            ],
        ),
        (
            "tt-24-2023",
            [
                ("BỘ CÔNG AN", "page_header"),
                ("THÔNG TƯ 24/2023/TT-BCA QUY ĐỊNH VỀ CẤP, THU HỒI ĐĂNG KÝ", "title"),
                ("Điều 3. Giải thích từ ngữ", "heading"),
                ("1. Đào tạo lái xe là quá trình truyền đạt kiến thức", "paragraph"),
                ("a) Sát hạch lái xe là việc kiểm tra kết quả học tập", "paragraph"),
            ],
        ),
    ],
)
def test_round_trip_on_fixture_document_types(
    document_id: str, lines: list[tuple[str, str]]
) -> None:
    ir = _ir(lines, document_id=document_id)
    manifest = _load_manifest(document_id)
    metadata = extract_document_metadata(ir)
    assert metadata.document_number is not None
    assert metadata.document_type is not None

    document, document_version = project_document(ir, manifest, metadata)
    assert document.document_id == document_id
    assert document.document_type == manifest["document_type"]
    assert document_version.manifest_json == manifest

    extracted = _extracted(ir)
    assert extracted
    provisions = project_provisions(
        extracted,
        document_version_id=document_version.id or uuid4(),
        status=document.status,
        effective_from=document_version.effective_from,
        effective_to=document_version.effective_to,
        review_status=document_version.review_status,
    )
    assert validate_provisions(provisions) == []
    assert len({provision.provision_id for provision in provisions}) == len(provisions)
