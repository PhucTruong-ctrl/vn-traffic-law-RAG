"""Tests for the parser benchmark fixtures + gold annotations (VNLRAG-24).

Validates: (a) every provision_id in every gold file matches the committed
legal-provision schema's provision_id pattern; (b) the stable-ID golden
fixture proves diem-d and diem-đ are distinct, both schema-valid; (c) Luật
and NĐ gold each contain at least one d) and one đ) point label; (d) at
least one short Point is retained; (e) fixtures exist and gold provisions
reference existing fixture files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "parser_benchmark"
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

PROVISION_SCHEMA = json.loads(
    (TEMPLATES_DIR / "legal-provision.schema.json").read_text(encoding="utf-8")
)
PROVISION_ID_PATTERN = PROVISION_SCHEMA["properties"]["provision_id"]["pattern"]
PROVISION_ID_RE = re.compile(PROVISION_ID_PATTERN)

GOLD_FILES = [
    FIXTURES_DIR / "gold" / "luat-gold.json",
    FIXTURES_DIR / "gold" / "nd-gold.json",
    FIXTURES_DIR / "gold" / "tt-gold.json",
]
STABLE_ID_FIXTURE = FIXTURES_DIR / "golden-stable-id" / "stable_id_diem_d_dd.json"
POINT_LABEL_FIXTURE = FIXTURES_DIR / "gold" / "point_label_d_dd.json"
SHORT_POINT_FIXTURE = FIXTURES_DIR / "gold" / "short_point_annotation.json"


def _gold_provisions(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["provisions"]


@pytest.mark.parametrize("gold_file", GOLD_FILES)
def test_gold_file_exists_and_is_valid_json(gold_file: Path) -> None:
    assert gold_file.exists(), f"missing gold file {gold_file}"
    data = json.loads(gold_file.read_text(encoding="utf-8"))
    assert data["document_id"]
    assert data["fixture"]
    assert isinstance(data["provisions"], list) and data["provisions"]


@pytest.mark.parametrize("gold_file", GOLD_FILES)
def test_all_provision_ids_match_schema_pattern(gold_file: Path) -> None:
    for provision in _gold_provisions(gold_file):
        pid = provision["provision_id"]
        assert PROVISION_ID_RE.fullmatch(pid), (
            f"{gold_file.name}: provision_id {pid!r} does not match schema pattern"
        )


@pytest.mark.parametrize("gold_file", GOLD_FILES)
def test_gold_provisions_reference_existing_fixture(gold_file: Path) -> None:
    data = json.loads(gold_file.read_text(encoding="utf-8"))
    fixture_path = FIXTURES_DIR / data["fixture"]
    assert fixture_path.exists(), f"{gold_file.name}: fixture {fixture_path} missing"


@pytest.mark.parametrize(
    "gold_file",
    [GOLD_FILES[0], GOLD_FILES[1]],  # luat + nd phải có cả d) và đ)
)
def test_gold_contains_both_d_and_dd_point_labels(gold_file: Path) -> None:
    labels = {p.get("point_label") for p in _gold_provisions(gold_file)}
    assert "d)" in labels, f"{gold_file.name}: thiếu nhãn d)"
    assert "đ)" in labels, f"{gold_file.name}: thiếu nhãn đ)"


def test_short_points_are_retained() -> None:
    all_provisions = []
    for gold_file in GOLD_FILES:
        all_provisions.extend(_gold_provisions(gold_file))
    short_retained = [p for p in all_provisions if p.get("short_point") is True]
    assert short_retained, "không có short-Point nào được đánh dấu retained"
    assert all(p["retained"] is True for p in short_retained)


def test_short_point_annotation_matches_gold() -> None:
    data = json.loads(SHORT_POINT_FIXTURE.read_text(encoding="utf-8"))
    assert data["short_points"]
    for sp in data["short_points"]:
        assert sp["expected_retained"] is True
        assert PROVISION_ID_RE.fullmatch(sp["provision_id"]), sp["provision_id"]


def test_stable_id_golden_fixture_diem_d_vs_diem_d_da() -> None:
    """Golden fixture stable-ID: diem-d và diem-đ là hai ID riêng biệt (FR-03)."""
    data = json.loads(STABLE_ID_FIXTURE.read_text(encoding="utf-8"))
    ids = data["stable_ids"]
    id_d, id_d_da = ids["diem_d"], ids["diem_d_da"]
    assert id_d != id_d_da, "diem-d và diem-đ phải khác nhau (không va chạm)"
    assert PROVISION_ID_RE.fullmatch(id_d), id_d
    assert PROVISION_ID_RE.fullmatch(id_d_da), id_d_da
    assert data["assertions"]["distinct"] is True
    assert data["assertions"]["id_d_equals_id_dd"] is False


def test_point_label_fixture_d_dd_distinct() -> None:
    data = json.loads(POINT_LABEL_FIXTURE.read_text(encoding="utf-8"))
    labels = {entry["label"]: entry["normalized"] for entry in data["labels"]}
    assert labels["d)"] == "diem-d"
    assert labels["đ)"] == "diem-đ"
    assert labels["d)"] != labels["đ)"]
    assert data["assertions"]["both_labels_distinct"] is True


def test_diem_da_keeps_d_character() -> None:
    data = json.loads(STABLE_ID_FIXTURE.read_text(encoding="utf-8"))
    assert "đ" in data["stable_ids"]["diem_d_da"]
    assert "đ" not in data["stable_ids"]["diem_d"]


def test_schema_pattern_allows_d_and_d_da() -> None:
    """Regex schema cho phép cả diem-d và diem-đ (không strip diacritics cho đ)."""
    assert PROVISION_ID_RE.fullmatch("nd-168-2024__dieu-7__khoan-4__diem-d")
    assert PROVISION_ID_RE.fullmatch("nd-168-2024__dieu-7__khoan-4__diem-đ")
    assert "đ" in PROVISION_ID_PATTERN


def test_parent_context_annotations_are_internally_consistent() -> None:
    """Parent-context gold phải khớp với fixture nguồn (oracle VNLRAG-24 finding 2/3).

    Mỗi annotation: provision_id tồn tại trong gold file, source_text xuất hiện
    trong fixture nguồn, retrieval_text_expected chứa source_text (kế thừa ngữ
    cảnh cha), citation_target vẫn trỏ tới provision thực tế.
    """
    data = json.loads(
        (FIXTURES_DIR / "gold" / "parent_context_annotation.json").read_text(encoding="utf-8")
    )
    # Map document_id -> (provision-id set, fixture text)
    gold_by_doc = {}
    for gold_file in GOLD_FILES:
        gold = json.loads(gold_file.read_text(encoding="utf-8"))
        fixture_path = FIXTURES_DIR / gold["fixture"]
        gold_by_doc[gold["document_id"]] = (
            {p["provision_id"] for p in gold["provisions"]},
            fixture_path.read_text(encoding="utf-8"),
        )

    assert data["annotations"], "parent_context_annotation.json rỗng"

    for ann in data["annotations"]:
        pid = ann["provision_id"]
        # provision_id phải hợp lệ theo schema
        assert PROVISION_ID_RE.fullmatch(pid), f"parent_context: id {pid} không khớp schema"
        # Định vị ĐÚNG document sở hữu provision_id (đúng một lần — không được mơ hồ)
        owners = [doc for doc, (ids, _) in gold_by_doc.items() if pid in ids]
        assert len(owners) == 1, (
            f"parent_context: provision_id {pid} phải thuộc đúng một gold document (tìm thấy {len(owners)})"
        )
        owner_fixture_text = gold_by_doc[owners[0]][1]
        # source_text phải xuất hiện trong fixture của CHÍNH document đó (không phải bất kỳ)
        assert ann["source_text"] in owner_fixture_text, (
            f"parent_context: source_text của {pid} không có trong fixture {owners[0]}"
        )
        # retrieval_text_expected phải chứa source_text (kế thừa ngữ cảnh cha)
        assert ann["source_text"] in ann["retrieval_text_expected"], (
            f"parent_context: retrieval_text_expected của {pid} thiếu source_text"
        )
        # citation_target không được trống
        assert ann["citation_target"].strip(), f"parent_context: {pid} thiếu citation_target"
