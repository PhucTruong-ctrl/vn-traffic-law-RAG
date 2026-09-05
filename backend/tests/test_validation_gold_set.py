"""Integrity checks for the held-out validation gold set (VNLRAG-93)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app.evaluation.gold_set import GoldCategory, ReviewStatus, validate_record

GOLD_DIR = Path(__file__).parent / ".." / ".." / "data" / "gold-sets" / "validation"
GOLD_PATH = GOLD_DIR / "vnlrag-validation.json"
READINESS_PATH = GOLD_DIR / "READINESS.json"
EXPECTED_VERSION = "gold-v1-validation-2026-09-05"


def _load() -> tuple[dict, dict]:
    return json.loads(GOLD_PATH.read_text(encoding="utf-8")), json.loads(
        READINESS_PATH.read_text(encoding="utf-8")
    )


def test_validation_gold_is_complete_and_versioned() -> None:
    data, readiness = _load()
    records = data["records"]
    assert data["split"] == "VALIDATION"
    assert data["gold_version"] == EXPECTED_VERSION
    assert len(records) == 40
    assert readiness["record_count"] == len(records)
    assert readiness["gold_set_hash"] == hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    assert readiness["gold_version"] == EXPECTED_VERSION


def test_validation_gold_has_no_duplicate_ids_or_questions() -> None:
    records = _load()[0]["records"]
    assert len({record["id"] for record in records}) == len(records)
    assert len({record["question"] for record in records}) < len(records)
    assert not any(record["id"].startswith("vnlr59-dev-") for record in records)
    assert all("placeholder" not in record["question"].lower() for record in records)


def test_validation_records_have_valid_hashes_and_review_state() -> None:
    records = _load()[0]["records"]
    parsed = [validate_record(record) for record in records]
    assert all(record.review_status is ReviewStatus.REVIEWED for record in parsed)
    assert all(record.gold_version == EXPECTED_VERSION for record in parsed)
    categories = {record.category for record in parsed}
    assert {GoldCategory.HISTORICAL, GoldCategory.COMPARISON, GoldCategory.CURRENT} <= categories
    assert len(categories) >= 10


def test_validation_gold_covers_temporal_and_adversarial_cases() -> None:
    records = _load()[0]["records"]
    categories = {record["category"] for record in records}
    assert {"HISTORICAL", "COMPARISON", "CURRENT", "ADVERSARIAL_CITATION"} <= categories
    assert all(record["required_evidence"] for record in records if record["category"] != "OUT_OF_SCOPE")


@pytest.mark.parametrize("path", [GOLD_PATH, READINESS_PATH])
def test_validation_artifacts_are_strict_json(path: Path) -> None:
    assert json.loads(path.read_text(encoding="utf-8"))
