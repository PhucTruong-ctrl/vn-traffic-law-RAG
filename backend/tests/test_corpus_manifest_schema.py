"""Tests for the corpus document manifest JSON Schema.

Covers the validation rules from docs/06-test-evaluation.md §6.2.1.1:
required fields, ISO date format, URL format, valid document id, enum
membership, effective interval, extra="forbid", and SHA-256 file hash.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from scripts.validate_manifest import validate_manifest

TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
SCHEMA = json.loads((TEMPLATES_DIR / "corpus-manifest.schema.json").read_text(encoding="utf-8"))
EXAMPLE = json.loads((TEMPLATES_DIR / "corpus-manifest.example.json").read_text(encoding="utf-8"))

VALID_HASH = "9e387c099aa9af454e7082513011d8fe35c811693edfaf763d5494a6aa02ab99"


def base_manifest() -> dict:
    """A valid PENDING manifest (reviewed_by/reviewed_at intentionally absent)."""
    return {
        "document_id": "nd-168-2024",
        "source_url": "https://vbpl.vn/TW/Pages/vbpq-van-ban-goc.aspx?ItemID=168-2024-NDCP",
        "downloaded_at": "2026-08-01T09:05:00+07:00",
        "file_hash": VALID_HASH,
        "document_number": "168/2024/NĐ-CP",
        "document_type": "DECREE",
        "issuer": "Chính phủ",
        "issued_date": "2024-12-26",
        "effective_from": "2025-01-01",
        "effective_to": "2026-12-31",
        "status": "EFFECTIVE",
        "relation_notes": "",
        "review_status": "PENDING",
    }


def test_schema_is_valid_draft07() -> None:
    jsonschema.Draft7Validator.check_schema(SCHEMA)


def test_example_manifest_is_valid() -> None:
    assert validate_manifest(EXAMPLE) == []


def test_valid_pending_manifest_without_review_fields() -> None:
    assert validate_manifest(base_manifest()) == []


@pytest.mark.parametrize("field", SCHEMA["required"])
def test_missing_required_field_fails(field: str) -> None:
    manifest = base_manifest()
    del manifest[field]
    errors = validate_manifest(manifest)
    assert errors, f"expected failure when required field '{field}' is missing"


@pytest.mark.parametrize("review_status", ["ACCEPTED", "REJECTED"])
def test_review_fields_required_for_accepted_or_rejected(review_status: str) -> None:
    manifest = base_manifest()
    manifest["review_status"] = review_status
    errors = validate_manifest(manifest)
    assert errors, f"expected failure when '{review_status}' lacks reviewed_by/reviewed_at"


@pytest.mark.parametrize("review_status", ["PENDING", "DROPPED"])
def test_review_fields_not_required_for_pending_or_dropped(review_status: str) -> None:
    manifest = base_manifest()
    manifest["review_status"] = review_status
    assert validate_manifest(manifest) == []


def test_invalid_review_status_fails() -> None:
    manifest = base_manifest()
    manifest["review_status"] = "REVIEWED"
    assert validate_manifest(manifest)


@pytest.mark.parametrize(
    ("effective_from", "effective_to"),
    [
        ("2026-12-31", "2026-12-31"),  # equal -> invalid
        ("2026-06-01", "2026-05-01"),  # reversed -> invalid (doc 06 example)
    ],
)
def test_invalid_effective_interval_fails(effective_from: str, effective_to: str) -> None:
    manifest = base_manifest()
    manifest["effective_from"] = effective_from
    manifest["effective_to"] = effective_to
    errors = validate_manifest(manifest)
    assert errors, "expected failure for invalid effective interval"


def test_valid_effective_interval_passes() -> None:
    manifest = base_manifest()
    manifest["effective_from"] = "2026-05-01"
    manifest["effective_to"] = "2026-06-01"
    assert validate_manifest(manifest) == []


def test_valid_null_effective_to_current_document_passes() -> None:
    """A currently EFFECTIVE, ACCEPTED document may have effective_to = null (docs/03 §3.10.4)."""
    manifest = base_manifest()
    manifest["review_status"] = "ACCEPTED"
    manifest["reviewed_by"] = "reviewer-01"
    manifest["reviewed_at"] = "2026-08-02T10:30:00+07:00"
    manifest["effective_from"] = "2025-01-01"
    manifest["effective_to"] = None
    manifest["status"] = "EFFECTIVE"
    assert validate_manifest(manifest) == []


def test_valid_null_temporal_pending_document_passes() -> None:
    """A PENDING document with unknown effectiveness may have both dates null (docs/03 §3.15.6)."""
    manifest = base_manifest()
    manifest["review_status"] = "PENDING"
    manifest["effective_from"] = None
    manifest["effective_to"] = None
    assert validate_manifest(manifest) == []


def test_accepted_manifest_requires_effective_from() -> None:
    """An ACCEPTED manifest must have a determinate effective start (docs/03 §3.10.4)."""
    manifest = base_manifest()
    manifest["review_status"] = "ACCEPTED"
    manifest["reviewed_by"] = "reviewer-01"
    manifest["reviewed_at"] = "2026-08-02T10:30:00+07:00"
    manifest["effective_from"] = None
    errors = validate_manifest(manifest)
    assert errors, "expected failure when ACCEPTED manifest has effective_from = null"


def test_unknown_extra_field_fails() -> None:
    manifest = base_manifest()
    manifest["batch"] = "batch-01"
    assert validate_manifest(manifest)


@pytest.mark.parametrize(
    "file_hash",
    [
        "not-a-hash",
        "9e387c099aa9af454e7082513011d8fe35c811693edfaf763d5494a6aa02ab9",  # 63 chars
        "9e387c099aa9af454e7082513011d8fe35c811693edfaf763d5494a6aa02ab999",  # 65 chars
        "9E387C099AA9AF454E7082513011D8FE35C811693EDFAF763D5494A6AA02AB99",  # uppercase
        "zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz",  # 64 non-hex
    ],
)
def test_invalid_file_hash_fails(file_hash: str) -> None:
    manifest = base_manifest()
    manifest["file_hash"] = file_hash
    assert validate_manifest(manifest)


def test_invalid_document_id_fails() -> None:
    manifest = base_manifest()
    manifest["document_id"] = "Invalid_ID"
    assert validate_manifest(manifest)


def test_invalid_document_type_fails() -> None:
    manifest = base_manifest()
    manifest["document_type"] = "ORDINANCE"
    assert validate_manifest(manifest)


def test_invalid_status_fails() -> None:
    manifest = base_manifest()
    manifest["status"] = "REPEALED"
    assert validate_manifest(manifest)


def test_invalid_source_url_fails() -> None:
    manifest = base_manifest()
    manifest["source_url"] = "not a url"
    assert validate_manifest(manifest)


def test_invalid_date_format_fails() -> None:
    manifest = base_manifest()
    manifest["issued_date"] = "26/12/2024"
    assert validate_manifest(manifest)
