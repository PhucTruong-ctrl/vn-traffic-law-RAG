"""Unit tests: legal metadata normalization (VNLRAG-27).

Covers the VNLRAG-23 v2 rules implemented by
:mod:`app.ingestion.metadata_normalizer`: document-type prefix mapping with
manifest authority, issuer canonicalization, no-guess date normalization,
d/đ OCR ambiguity (never a silent wrong guess), Unicode Roman numerals,
glued point labels, terminology canonicalization + versioning, idempotence,
and the golden-fixture label forms.  Also proves the full projection pipeline
never mutates ``source_text``.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.metadata_extractor import ExtractedDocumentMetadata
from app.ingestion.metadata_normalizer import (
    NormalizationResult,
    canonical_point_label,
    is_header_footer_leakage,
    normalize_metadata,
    normalize_provision_text,
    normalize_roman_numeral,
)
from app.ingestion.projection import project_provisions, validate_provisions
from app.ingestion.structure_extractor import LegalStructureExtractor
from app.ingestion.terminology import TERMINOLOGY, TERMINOLOGY_VERSION, canonical_term

REPO_ROOT = Path(__file__).resolve().parents[2]
BATCH_01 = REPO_ROOT / "data" / "manifests" / "batch-01"
FIXTURES = Path(__file__).parent / "fixtures" / "metadata_normalization"
GOLD_DIR = Path(__file__).parent / "fixtures" / "parser_benchmark" / "gold"
STABLE_ID_DIR = Path(__file__).parent / "fixtures" / "parser_benchmark" / "golden-stable-id"

#: Vietnamese point-run alphabet (rulespec §4.1): d = position 4, đ = 5.
POINT_RUN_ALPHABET = "abcdđe"


def _manifest(**overrides: object) -> dict[str, object]:
    manifest = json.loads((BATCH_01 / "nd-168-2024.manifest.json").read_text(encoding="utf-8"))
    manifest.update(overrides)
    return manifest


def _metadata(**fields: object) -> ExtractedDocumentMetadata:
    """Build extracted metadata with every field set (defaults ``None``).

    ``model_construct`` deliberately bypasses pydantic coercion so raw
    pre-pydantic values (e.g. "15/11/2024" string dates) can be injected —
    the normalizer accepts them defensively.
    """

    base: dict[str, object] = {
        "document_title": None,
        "document_number": None,
        "document_type": None,
        "issuer": None,
        "issued_date": None,
        "effective_from": None,
        "effective_to": None,
    }
    base.update(fields)
    return ExtractedDocumentMetadata.model_construct(**base)


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


# ─────────────────────── document_type: prefix mapping + manifest authority ───────────────────────


@pytest.mark.parametrize(
    ("prefix", "expected"),
    [
        ("THÔNG TƯ", "CIRCULAR"),
        ("THÔNG TƯ LIÊN TỊCH", "CIRCULAR"),
        ("NGHỊ ĐỊNH", "DECREE"),
        ("LUẬT", "LAW"),
        ("QUYẾT ĐỊNH", "DECISION"),
        ("NGHỊ QUYẾT", "RESOLUTION"),
        ("VĂN BẢN HỢP NHẤT", "OTHER"),
    ],
)
def test_document_type_prefix_mapping(prefix: str, expected: str) -> None:
    result = normalize_metadata(_metadata(document_type=prefix), {})
    assert result.metadata.document_type == expected
    assert result.needs_review == []

def test_document_type_already_enum_is_kept() -> None:
    result = normalize_metadata(_metadata(document_type="DECREE"), {})
    assert result.metadata.document_type == "DECREE"
    assert result.needs_review == []


def test_document_type_manifest_is_authoritative() -> None:
    """Manifest wins over the extracted Vietnamese prefix (rulespec §2)."""
    manifest = _manifest(document_type="LAW")
    result = normalize_metadata(_metadata(document_type="THÔNG TƯ"), manifest)
    assert result.metadata.document_type == "LAW"


def test_document_type_unrecognized_becomes_none_with_review_flag() -> None:
    result = normalize_metadata(_metadata(document_type="SẮC LỆNH"), {})
    assert result.metadata.document_type is None
    assert any("document_type" in flag and "never guess" in flag for flag in result.needs_review)


# ──────────────────────────────────── issuer canonicalization ────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("bộ công an", "Bộ Công an"),
        ("CHÍNH PHỦ", "Chính phủ"),
        ("BỘ GIAO THÔNG VẬN TẢI", "Bộ Giao thông vận tải"),
        ("Bộ Giao thông vận tải", "Bộ Giao thông vận tải"),  # already canonical
        ("Quốc hội", "Quốc hội"),
        ("văn phòng quốc hội", "Văn phòng Quốc hội"),
        ("Thủ tướng Chính phủ", "Thủ tướng Chính phủ"),
        ("bộ nông nghiệp", "Bộ Nông nghiệp và Phát triển nông thôn"),
    ],
)
def test_issuer_canonicalized_via_keyword_map(raw: str, expected: str) -> None:
    result = normalize_metadata(_metadata(issuer=raw), {})
    assert result.metadata.issuer == expected


def test_issuer_noise_stripped() -> None:
    result = normalize_metadata(
        _metadata(
            issuer=(
                "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
                "Độc lập - Tự do - Hạnh phúc\n"
                "BỘ CÔNG AN"
            )
        ),
        {},
    )
    assert result.metadata.issuer == "Bộ Công an"


def test_issuer_only_boilerplate_becomes_none_with_review_flag() -> None:
    result = normalize_metadata(
        _metadata(issuer="CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM Độc lập - Tự do - Hạnh phúc"), {}
    )
    assert result.metadata.issuer is None
    assert any("issuer" in flag and "never guess" in flag for flag in result.needs_review)


def test_issuer_manifest_is_authoritative() -> None:
    manifest = _manifest(issuer="Bộ Công an")
    result = normalize_metadata(_metadata(issuer="bộ công an"), manifest)
    assert result.metadata.issuer == "Bộ Công an"


def test_issuer_unknown_name_kept_cleaned() -> None:
    result = normalize_metadata(_metadata(issuer="  Bộ  Kế hoạch và Đầu tư "), {})
    assert result.metadata.issuer == "Bộ Kế hoạch và Đầu tư"


# ─────────────────────────────── date normalization (never guess) ───────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2024-12-26", date(2024, 12, 26)),
        ("2024-12-26T00:00:00+07:00", date(2024, 12, 26)),
        ("26/12/2024", date(2024, 12, 26)),
        ("ngày 26 tháng 12 năm 2024", date(2024, 12, 26)),
        ("NGÀY 26 THÁNG 12 NĂM 2024", date(2024, 12, 26)),
    ],
)
def test_date_formats_normalized(raw: str, expected: date) -> None:
    result = normalize_metadata(_metadata(issued_date=raw), {})
    assert result.metadata.issued_date == expected
    assert result.needs_review == []


def test_date_object_passes_through() -> None:
    result = normalize_metadata(_metadata(issued_date=date(2024, 12, 26)), {})
    assert result.metadata.issued_date == date(2024, 12, 26)
    assert result.needs_review == []


@pytest.mark.parametrize(
    "raw",
    [
        "26/12/24",  # two-digit year — never guess the century
        "31/02/2024",  # impossible day
        "13/13/2024",  # impossible month
        "tháng 2 năm 2024",  # missing day → ambiguous
        "not-a-date",
        "2024-12-26not-a-date",  # trailing garbage — no silent truncation
        "",
    ],
)
def test_ambiguous_or_unparseable_date_becomes_none_with_review_flag(raw: str) -> None:
    result = normalize_metadata(_metadata(issued_date=raw), {})
    assert result.metadata.issued_date is None
    assert any("issued_date" in flag and "never guess" in flag for flag in result.needs_review)


def test_effective_dates_normalized_independently() -> None:
    result = normalize_metadata(
        _metadata(effective_from="15/8/2023", effective_to="2025-01-01T00:00:00"), {}
    )
    assert result.metadata.effective_from == date(2023, 8, 15)
    assert result.metadata.effective_to == date(2025, 1, 1)
    assert result.needs_review == []


# ─────────────────────────────── d/đ OCR ambiguity (never guess) ───────────────────────────────


def test_canonical_point_label_confident_labels() -> None:
    assert canonical_point_label("a)") == "a)"
    assert canonical_point_label("b)") == "b)"
    assert canonical_point_label("c)") == "c)"
    assert canonical_point_label("e)") == "e)"
    assert canonical_point_label("g)") == "g)"
    assert canonical_point_label("A)") == "a)"  # case-folded
    assert canonical_point_label("a）") == "a)"  # full-width paren
    assert canonical_point_label("Điểm a)") == "a)"  # Điểm prefix
    assert canonical_point_label("a)Điều khiển xe") == "a)"  # glued label
    assert canonical_point_label("not a label") is None


def test_canonical_point_label_keeps_dd() -> None:
    """đ is self-identifying: kept distinct from d (rulespec §4.2)."""
    assert canonical_point_label("đ)") == "đ)"
    assert canonical_point_label("Đ)") == "đ)"
    assert canonical_point_label("đ)Ảnh chân dung") == "đ)"
    assert canonical_point_label("đ)") != canonical_point_label("d)", ordinal=4)


def test_canonical_point_label_d_ambiguous_without_ordinal() -> None:
    """Bare d) is d↔đ OCR-ambiguous → None (needs_review), never a guess."""
    assert canonical_point_label("d)") is None
    assert canonical_point_label("D)") is None
    assert canonical_point_label("d)Điều khiển") is None


def test_canonical_point_label_ordinal_disambiguates() -> None:
    """PRIMARY rule: ordinal position in the run a→b→c→d→đ→e (d = 4, đ = 5)."""
    assert canonical_point_label("d)", ordinal=4) == "d)"
    assert canonical_point_label("d)", ordinal=5) == "đ)"
    assert canonical_point_label("đ)", ordinal=4) == "đ)"  # crisp đ wins over ordinal
    assert canonical_point_label("d)", ordinal=3) is None  # inconsistent → review
    assert canonical_point_label("a)", ordinal=4) == "a)"  # non-d/đ unaffected


# ───────────────────────────────── Roman numerals & glued labels ─────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ⅰ", "I"),
        ("Ⅱ", "II"),
        ("Ⅲ", "III"),
        ("Ⅳ", "IV"),
        ("Ⅷ", "VIII"),
        ("ⅩⅤ", "XV"),
        ("ⅰ", "i"),
        ("ⅳ", "iv"),
        ("Chương Ⅱ", "Chương II"),
        ("Ⅰ.", "I."),
    ],
)
def test_roman_numeral_unicode_variants(raw: str, expected: str) -> None:
    assert normalize_roman_numeral(raw) == expected


def test_roman_numeral_ascii_unchanged() -> None:
    assert (
        normalize_roman_numeral("Chương I. NHỮNG QUY ĐỊNH CHUNG")
        == "Chương I. NHỮNG QUY ĐỊNH CHUNG"
    )


def test_normalize_provision_text_glued_labels() -> None:
    assert (
        normalize_provision_text("a)Điều khiển xe đi ngược chiều")
        == "a) Điều khiển xe đi ngược chiều"
    )
    assert (
        normalize_provision_text("đ)Ảnh chân dung theo quy định.")
        == "đ) Ảnh chân dung theo quy định."
    )


def test_normalize_provision_text_whitespace_and_fullwidth() -> None:
    # full-width space (U+3000) and full-width dot (U+FF0E) → half-width,
    # whitespace runs collapse (NFKC does not insert spaces around the dot).
    assert normalize_provision_text("Điều　5．Xử　phạt") == "Điều 5.Xử phạt"
    assert (
        normalize_provision_text("Điều 7. Xử phạt 1. Phạt tiền a) Không chấp hành")
        == "Điều 7. Xử phạt 1. Phạt tiền a) Không chấp hành"  # canonical input untouched
    )


def test_normalize_provision_text_roman_variants() -> None:
    assert normalize_provision_text("Chương Ⅰ. NHỮNG QUY ĐỊNH CHUNG") == (
        "Chương I. NHỮNG QUY ĐỊNH CHUNG"
    )


def test_header_footer_leakage_detected_conservatively() -> None:
    assert is_header_footer_leakage(
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nĐộc lập - Tự do - Hạnh phúc"
    )
    assert not is_header_footer_leakage("a) Không chấp hành hiệu lệnh của đèn tín hiệu")
    assert not is_header_footer_leakage("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM")  # partial block
    assert not is_header_footer_leakage("")


# ──────────────────────────────────── terminology (VNLRAG-27) ────────────────────────────────────


def test_terminology_version_and_entries() -> None:
    assert TERMINOLOGY_VERSION == "1.0.0"
    assert "xe ô tô" in TERMINOLOGY
    assert "phạt tiền" in TERMINOLOGY
    assert "xử phạt vi phạm hành chính" in TERMINOLOGY
    assert "đăng ký" in TERMINOLOGY
    # canonical term is the first variant of its own entry
    for canonical, variants in TERMINOLOGY.items():
        assert variants[0] == canonical


@pytest.mark.parametrize(
    ("term", "expected"),
    [
        ("xe ôtô", "xe ô tô"),
        ("xe ô tô", "xe ô tô"),
        ("XỬ PHẠT VI PHẠM HÀNH CHÍNH", "xử phạt vi phạm hành chính"),
        ("xử phạt VPHC", "xử phạt vi phạm hành chính"),
        ("dang ky", "đăng ký"),
        ("phat tien", "phạt tiền"),
        ("nồng độ cồn trong máu", "nồng độ cồn"),
        ("bồi thường thiệt hại", "bồi thường thiệt hại"),  # unknown → unchanged
    ],
)
def test_canonical_term_maps_variants(term: str, expected: str) -> None:
    assert canonical_term(term) == expected


def test_canonical_term_versioning() -> None:
    assert canonical_term("xe ôtô", version="1.0.0") == "xe ô tô"
    with pytest.raises(ValueError, match="1.0.0"):
        canonical_term("xe ôtô", version="0.9.0")


# ───────────────────────────────────────── idempotence ─────────────────────────────────────────


def test_normalize_metadata_is_idempotent() -> None:
    manifest = _manifest()
    raw = _metadata(
        document_title="  THÔNG TƯ  79/2024/TT-BCA ",
        document_number="79/2024/TT-BCA",
        document_type="THÔNG TƯ",
        issuer="bộ công an",
        issued_date="15/11/2024",
        effective_from="ngày 01 tháng 01 năm 2025",
        effective_to=None,
    )
    first = normalize_metadata(raw, manifest)
    second = normalize_metadata(first.metadata, manifest)
    assert second == first  # metadata AND flags are both stable here
    assert first.needs_review == []


def test_normalize_metadata_metadata_is_fixpoint_for_review_flagged_inputs() -> None:
    """needs_review describes the ORIGINAL extraction quality (input-derived)."""
    raw = _metadata(document_type="SẮC LỆNH", issued_date="32/13/2024")
    first = normalize_metadata(raw, {})
    assert first.needs_review
    second = normalize_metadata(first.metadata, {})
    assert second.metadata == first.metadata  # metadata is a fixpoint
    assert second.needs_review == []


def test_normalize_provision_text_is_idempotent() -> None:
    text = "a)Điều khiển xe  đi  ngược chiều　trên đường Ⅰ"
    once = normalize_provision_text(text)
    assert normalize_provision_text(once) == once


def test_normalize_roman_numeral_is_idempotent() -> None:
    once = normalize_roman_numeral("Chương Ⅱ. NGƯỜI ĐIỀU KHIỂN")
    assert normalize_roman_numeral(once) == once


def test_canonical_point_label_is_idempotent_on_canonical_output() -> None:
    for label, ordinal in (
        ("a)", None),
        ("đ)", None),
        ("d)", 4),
        ("d)", 5),
        ("e)", None),
    ):
        first = canonical_point_label(label, ordinal=ordinal)
        if first is None:
            continue
        assert canonical_point_label(first, ordinal=ordinal) == first


# ───────────────────────── source_text is never mutated by the pipeline ─────────────────────────


def _ocr_variant_ir() -> ParsedDocument:
    """IR with a glued label and the d)/đ) pair, mirroring scan-route output."""
    return _ir(
        [
            ("NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH", "title"),
            ("Điều 7. Xử phạt người điều khiển xe mô tô", "heading"),
            ("1. Phạt tiền từ 400.000 đồng đến 600.000 đồng", "paragraph"),
            ("a)Điều khiển xe đi ngược chiều trên đường một chiều", "paragraph"),
            ("d) Dừng xe, đỗ xe tại nơi có biển cấm dừng", "paragraph"),
            ("đ) Lùi xe không quan sát phía sau", "paragraph"),
        ]
    )


def test_pipeline_never_mutates_source_text() -> None:
    """Normalization applies to retrieval_text only; source_text is verbatim."""
    ir = _ocr_variant_ir()
    extracted = LegalStructureExtractor().extract(ir, document_version_id="version-1")
    assert len(extracted) >= 3  # article + clause + points

    provisions = project_provisions(extracted, document_version_id=uuid4())

    for provision, source in zip(provisions, extracted, strict=True):
        assert provision.source_text == source.source_text
        assert provision.content_hash == source.content_hash  # hash still over source_text

    glued = next(p for p in provisions if "a)Điều khiển" in p.source_text)
    assert "a)Điều khiển xe" in glued.source_text  # glued label kept verbatim in source
    assert "a) Điều khiển xe" in glued.retrieval_text  # spacing fixed in retrieval only
    assert validate_provisions(provisions) == []


# ─────────────────────────── fixture: manifest + metadata input/output ───────────────────────────


def test_fixture_metadata_normalization_end_to_end() -> None:
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    raw = json.loads((FIXTURES / "input_metadata.json").read_text(encoding="utf-8"))["metadata"]
    expected = json.loads((FIXTURES / "expected_metadata.json").read_text(encoding="utf-8"))

    result = normalize_metadata(_metadata(**raw), manifest)
    assert isinstance(result, NormalizationResult)
    assert result.metadata.model_dump(mode="json") == expected["metadata"]
    assert result.needs_review == expected["needs_review"]


def _text_cases() -> list[dict[str, object]]:
    data = json.loads((FIXTURES / "provision_text_cases.json").read_text(encoding="utf-8"))
    return data["cases"]


@pytest.mark.parametrize("case", _text_cases(), ids=lambda case: case["name"])
def test_fixture_provision_text_cases(case: dict[str, object]) -> None:
    functions = {
        "canonical_point_label": canonical_point_label,
        "is_header_footer_leakage": is_header_footer_leakage,
        "normalize_provision_text": normalize_provision_text,
        "normalize_roman_numeral": normalize_roman_numeral,
    }
    for call in case["calls"]:
        function = functions[call["function"]]
        kwargs = call.get("kwargs", {})
        result = function(case["input"], **kwargs)
        assert result == call["expected"], (
            f"{case['name']}: {call['function']}({case['input']!r}, {kwargs}) "
            f"-> {result!r}, expected {call['expected']!r}"
        )


# ───────────────────────────── golden fixtures: canonical label forms ─────────────────────────────


def test_golden_point_label_fixture_canonical_forms() -> None:
    """point_label_d_dd.json: every label canonicalizes to its diem-X form;
    d) and đ) stay distinct under ordinal context (PRIMARY rule)."""
    data = json.loads((GOLD_DIR / "point_label_d_dd.json").read_text(encoding="utf-8"))
    for entry in data["labels"]:
        label = entry["label"]
        char = label[0]
        ordinal = POINT_RUN_ALPHABET.index(char) + 1
        assert canonical_point_label(label, ordinal=ordinal) == label
        assert f"diem-{label[0]}" == entry["normalized"]

    d = canonical_point_label("d)", ordinal=4)
    d_da = canonical_point_label("đ)", ordinal=5)
    assert d == "d)" and d_da == "đ)" and d != d_da
    assert data["assertions"]["both_labels_distinct"] is True
    # without ordinal context, d) routes to review instead of a silent guess
    assert canonical_point_label("d)") is None


def test_golden_stable_id_fixture_d_dd_distinct() -> None:
    """stable_id_diem_d_dd.json: diem-d and diem-đ never collide (FR-03)."""
    data = json.loads((STABLE_ID_DIR / "stable_id_diem_d_dd.json").read_text(encoding="utf-8"))
    ids = data["stable_ids"]
    assert ids["diem_d"] == "nd-168-2024__dieu-7__khoan-4__diem-d"
    assert ids["diem_d_da"] == "nd-168-2024__dieu-7__khoan-4__diem-đ"
    assert ids["diem_d"] != ids["diem_d_da"]
    assert data["assertions"]["distinct"] is True
    assert "đ" in ids["diem_d_da"] and "đ" not in ids["diem_d"]
    assert canonical_point_label("đ)") == "đ)"  # đ character preserved, never stripped


def test_golden_short_point_labels_canonicalize() -> None:
    """short_point_annotation.json: label in each provision_id resolves to
    its own canonical form (retention is orthogonal to normalization)."""
    data = json.loads((GOLD_DIR / "short_point_annotation.json").read_text(encoding="utf-8"))
    for sp in data["short_points"]:
        char = sp["provision_id"].rsplit("__diem-", 1)[1]
        ordinal = POINT_RUN_ALPHABET.index(char) + 1
        assert canonical_point_label(f"{char})", ordinal=ordinal) == f"{char})"
        assert sp["source_text"].startswith(f"{char})")
