"""Validate the versioned evaluation gold set and its integrity metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.evaluation.gold_set import GoldCategory, validate_record


def validate_gold_set(path: Path, hash_path: Path | None = None) -> list[str]:
    errors: list[str] = []
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or not records:
        return ["records must be a non-empty list"]
    ids: set[str] = set()
    for index, item in enumerate(records):
        try:
            record = validate_record(item)
            if record.id in ids:
                errors.append(f"record {index}: duplicate id {record.id}")
            ids.add(record.id)
            if record.review_status.value != "APPROVED":
                errors.append(f"record {index}: not approved")
            if "reason_code" not in record.temporal_metadata:
                errors.append(f"record {index}: missing reason_code")
            if record.category is GoldCategory.OUT_OF_SCOPE and record.expected_provision_ids:
                errors.append(f"record {index}: out-of-scope has provisions")
        except Exception as exc:
            errors.append(f"record {index}: {exc}")
    if hash_path is not None:
        metadata = json.loads(hash_path.read_text(encoding="utf-8"))
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if metadata.get("gold_set_hash") != actual:
            errors.append("gold_set_hash mismatch")
        if metadata.get("record_count") != len(records):
            errors.append("record_count mismatch")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_gold_set(
        root / "data/gold-sets/gold-v1/gold.json",
        root / "data/gold-sets/gold-v1/hash.json",
    )
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
