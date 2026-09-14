"""Validate the versioned evaluation gold set and its integrity metadata."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.evaluation.gold_set import GoldCategory, assign_split, validate_record


def validate_gold_set(
    path: Path,
    hash_path: Path | None = None,
    *,
    corpus_manifest: Path | None = None,
) -> list[str]:
    """Validate the frozen 200-record contract without masking blockers."""
    errors: list[str] = []
    try:
        payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"unable to read gold set: {exc}"]
    records = payload.get("records")
    if not isinstance(records, list):
        return ["records must be a list"]
    if len(records) != 200:
        errors.append(f"record_count must be exactly 200 (got {len(records)})")
    ids: set[str] = set()
    splits = {"DEVELOPMENT": 0, "VALIDATION": 0, "FINAL_TEST": 0}
    categories = {category.value for category in GoldCategory}
    corpus_ids: set[str] = set()
    if corpus_manifest is not None:
        try:
            corpus = json.loads(corpus_manifest.read_text(encoding="utf-8"))
            corpus_ids = {entry["document_id"] for entry in corpus.get("entries", [])}
            if not corpus_ids:
                errors.append("approved corpus manifest has no entries")
            if any(
                entry.get("coverage", {}).get("review_status") != "ACCEPTED"
                for entry in corpus.get("entries", [])
            ):
                errors.append("approved corpus contains non-ACCEPTED entries")
        except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
            errors.append(f"unable to read approved corpus: {exc}")
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
            splits[assign_split(record.id).value] += 1
            if record.category is GoldCategory.OUT_OF_SCOPE:
                if record.expected_provision_ids or record.acceptable_provision_ids:
                    errors.append(f"record {index}: out-of-scope has provisions")
            elif corpus_ids and any(
                provision.split("__", 1)[0] not in corpus_ids
                for provision in record.acceptable_provision_ids
            ):
                errors.append(f"record {index}: references unapproved corpus provision")
        except Exception as exc:
            errors.append(f"record {index}: {exc}")
    if splits != {"DEVELOPMENT": 40, "VALIDATION": 40, "FINAL_TEST": 120}:
        errors.append(f"split counts must be 40/40/120 (got {splits})")
    missing_categories = categories - {
        item.get("category") for item in records if isinstance(item, dict)
    }
    if missing_categories:
        errors.append("missing categories: " + ", ".join(sorted(missing_categories)))
    if hash_path is not None:
        try:
            metadata = json.loads(hash_path.read_text(encoding="utf-8"))
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if metadata.get("gold_set_hash") != actual:
                errors.append("gold_set_hash mismatch")
            if metadata.get("record_count") != len(records):
                errors.append("record_count mismatch")
            if metadata.get("frozen") is not True:
                errors.append("readiness is not FROZEN")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"unable to read hash metadata: {exc}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    errors = validate_gold_set(
        root / "data/gold-sets/gold-v1/gold.json",
        root / "data/gold-sets/gold-v1/hash.json",
        corpus_manifest=root / "data/candidate-corpus-manifest.json",
    )
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
