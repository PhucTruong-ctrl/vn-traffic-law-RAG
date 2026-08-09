import json
from pathlib import Path

import jsonschema
import pytest
from jsonschema import Draft7Validator, FormatChecker
from jsonschema.validators import extend

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "templates" / "legal-provision.schema.json"
SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

EXPECTED_FIELDS = {
    "provision_id",
    "document_version_id",
    "chapter",
    "section",
    "article",
    "clause",
    "point",
    "heading",
    "source_text",
    "retrieval_text",
    "parent_context",
    "effective_from",
    "effective_to",
    "status",
    "page_number",
    "bbox",
    "source_element_ids",
    "content_hash",
    "version",
    "review_status",
}


def _effective_interval(validator, _keyword, instance, _schema):
    """Custom keyword `x-effective-interval`: effective_to > effective_from (docs/00 §8.3).

    JSON Schema draft-07 cannot compare two sibling properties, so the ordering
    rule is enforced via a custom keyword; the DB layer adds the same CHECK.
    """
    if not validator.is_type(instance, "object"):
        return
    effective_from = instance.get("effective_from")
    effective_to = instance.get("effective_to")
    if (
        isinstance(effective_from, str)
        and isinstance(effective_to, str)
        and effective_to <= effective_from
    ):
        yield jsonschema.ValidationError(
            f"effective_to ({effective_to}) must be greater than effective_from ({effective_from})"
        )


VALIDATOR = extend(Draft7Validator, {"x-effective-interval": _effective_interval})


def _validate(instance: dict) -> list[jsonschema.ValidationError]:
    return list(VALIDATOR(SCHEMA, format_checker=FormatChecker()).iter_errors(instance))


def _messages(errors: list[jsonschema.ValidationError]) -> list[str]:
    return [error.message for error in errors]


def make_provision(**overrides: object) -> dict:
    provision = {
        "provision_id": "nd-168-2024__dieu-7__khoan-4__diem-b",
        "document_version_id": "ver-nd-168-2024-1",
        "chapter": "Chương I",
        "section": "Mục 1",
        "article": "Điều 7",
        "clause": "Khoản 4",
        "point": "Điểm b)",
        "heading": "Xử phạt người điều khiển xe ô tô",
        "source_text": "b) Dàn hàng ngang từ 03 xe trở lên",
        "retrieval_text": "Khoản 4. Phạt tiền từ ... đến ...: b) Dàn hàng ngang từ 03 xe trở lên",
        "parent_context": "Khoản 4. Xử phạt các hành vi vi phạm",
        "effective_from": "2025-01-01",
        "effective_to": None,
        "status": "EFFECTIVE",
        "page_number": 12,
        "bbox": {
            "left": 50.0,
            "top": 100.0,
            "right": 300.0,
            "bottom": 120.0,
            "page_height": 842.0,
            "page_width": 595.0,
        },
        "source_element_ids": ["elem-123"],
        "content_hash": "a" * 64,
        "version": 1,
        "review_status": "ACCEPTED",
    }
    provision.update(overrides)
    return provision


def test_valid_full_provision_passes() -> None:
    assert _validate(make_provision()) == []


def test_schema_requires_exactly_the_20_fields() -> None:
    assert set(SCHEMA["required"]) == EXPECTED_FIELDS
    assert len(SCHEMA["required"]) == 20


@pytest.mark.parametrize("field", sorted(EXPECTED_FIELDS))
def test_each_of_the_20_fields_is_required(field: str) -> None:
    instance = make_provision()
    del instance[field]
    errors = _validate(instance)
    assert errors
    assert any(f"'{field}' is a required property" in message for message in _messages(errors))


@pytest.mark.parametrize(
    "provision_id",
    [
        "nd-168-2024__dieu-7__khoan-4__diem-b",
        "nd-168-2024__dieu-7__khoan-4__diem-d",
        "nd-168-2024__dieu-7__khoan-4__diem-đ",
        "nd-168-2024__dieu-7__khoan-4__diem-e",  # đầy đủ bảng chữ cái tiếng Việt (docs/03:1041)
        "nd-168-2024__dieu-7",
        "nd-168-2024__dieu-7__khoan-4",
        "nd-168-2024__phu-luc-1",
        "nd-168-2024__phu-luc-1__bang-2",
        "nd-168-2024__dieu-7__bang-2",
        "nd-168-2024__dieu-7__khoan-chuyen-tiep",
        "nd-168-2024__chuyen-tiep-1",
        "nd-168-2024__tieu-de-1",
    ],
)
def test_valid_provision_ids_pass(provision_id: str) -> None:
    assert _validate(make_provision(provision_id=provision_id)) == []


def test_diem_d_and_diem_d_da_are_distinct_valid_ids() -> None:
    """Điểm d) -> diem-d và Điểm đ) -> diem-đ: hai ID hợp lệ khác nhau (docs/03:1041, 1050)."""
    id_d = "nd-168-2024__dieu-7__khoan-4__diem-d"
    id_d_da = "nd-168-2024__dieu-7__khoan-4__diem-đ"
    assert id_d != id_d_da
    assert _validate(make_provision(provision_id=id_d)) == []
    assert _validate(make_provision(provision_id=id_d_da)) == []


@pytest.mark.parametrize(
    "provision_id",
    [
        "ND-168-2024__dieu-7__khoan-4__diem-b",  # uppercase
        "nd-168-2024__dieu-7__khoan-4__diem b",  # space
        "nd-168-2024__dieu-7__khoan-4__diem-b!",  # bad char
        "nd-168-2024__dieu-7__khoan-4__diem-",  # missing point letter
        "nd-168__dieu-7__khoan-4__diem-b",  # missing year segment
        "nd-168-2024_dieu-7__khoan-4__diem-b",  # single underscore separator
    ],
)
def test_invalid_provision_id_fails(provision_id: str) -> None:
    errors = _validate(make_provision(provision_id=provision_id))
    assert errors
    assert any("does not match" in message for message in _messages(errors))


@pytest.mark.parametrize("review_status", ["PENDING", "REJECTED", "DROPPED"])
def test_non_accepted_review_status_is_structurally_valid(review_status: str) -> None:
    # review_status: cổng gate corpus, độc lập với status (docs/00:398); non-ACCEPTED vẫn hợp lệ.
    assert _validate(make_provision(review_status=review_status)) == []


def test_extra_field_fails() -> None:
    errors = _validate(make_provision(extra_field="nope"))
    assert errors
    assert any("Additional properties are not allowed" in message for message in _messages(errors))


def test_effective_interval_invalid_fails() -> None:
    errors = _validate(make_provision(effective_from="2025-01-01", effective_to="2024-12-31"))
    assert errors
    assert any("greater than effective_from" in message for message in _messages(errors))


def test_effective_dates_must_be_iso_dates_when_both_present() -> None:
    errors = _validate(make_provision(effective_from="01/01/2025", effective_to="2026-01-01"))
    assert errors
    assert any("is not a 'date'" in message for message in _messages(errors))


def test_malformed_single_sided_effective_from_fails() -> None:
    """effective_from malformed, effective_to null: per-field date format enforced."""
    errors = _validate(make_provision(effective_from="not-a-date", effective_to=None))
    assert errors
    assert any("not-a-date" in message for message in _messages(errors))


def test_malformed_single_sided_effective_to_fails() -> None:
    """effective_to malformed + effective_from valid: date format must be enforced per-field."""
    errors = _validate(make_provision(effective_from="2025-01-01", effective_to="31/12/2026"))
    assert errors
    assert any("is not a 'date'" in message for message in _messages(errors))


def test_null_effective_dates_pass() -> None:
    """PENDING provision with unknown effectiveness: both dates null valid (docs/03:1272)."""
    assert (
        _validate(make_provision(effective_from=None, effective_to=None, review_status="PENDING"))
        == []
    )


@pytest.mark.parametrize(
    "bbox",
    [
        {},  # empty geometry
        {"left": 50.0, "top": 100.0, "right": 300.0},  # missing bottom
        {"left": 50.0, "top": 100.0},  # missing right + bottom
        {"left": "50"},  # non-number
    ],
)
def test_partial_or_malformed_bbox_fails(bbox: object) -> None:
    """Canonical BoundingBox requires left/top/right/bottom; page dims optional."""
    errors = _validate(make_provision(bbox=bbox))
    assert errors


def test_null_bbox_passes() -> None:
    assert _validate(make_provision(bbox=None)) == []


@pytest.mark.parametrize(
    "provision_id",
    [
        "nd-168-2024__khoan-4__dieu-7",  # reversed hierarchy order
        "nd-168-2024__dieu-7__khoan-4__diem-b__dieu-8",  # duplicate article after point
        "nd-168-2024__diem-b",  # point without article/clause path
        "nd-168-2024__phu-luc-1__dieu-7",  # article under appendix (invalid mix)
        "nd-168-2024__dieu-7__khoan-4__bang-2",  # bang under clause (invalid)
        "nd-168-2024__dieu-7__diem-b",  # diem directly under dieu (no khoan)
    ],
)
def test_invalid_hierarchical_provision_id_fails(provision_id: str) -> None:
    """ID grammar must reject unordered/duplicated/mixed hierarchy (oracle finding 1)."""
    errors = _validate(make_provision(provision_id=provision_id))
    assert errors
    assert any("does not match" in message for message in _messages(errors))


def test_node_kind_enum_validates() -> None:
    assert _validate(make_provision(node_kind="ARTICLE")) == []
    assert _validate(make_provision(node_kind="APPENDIX")) == []
    errors = _validate(make_provision(node_kind="UNKNOWN_KIND"))
    assert errors
    assert any("UNKNOWN_KIND" in message for message in _messages(errors))


def test_node_kind_defaults_to_article() -> None:
    """node_kind absent -> default ARTICLE (docs/03:1260); explicit enum valid."""
    assert _validate(make_provision()) == []  # no node_kind key present
    assert _validate(make_provision(node_kind="ARTICLE")) == []
