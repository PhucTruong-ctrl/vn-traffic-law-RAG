"""Freeze and validate the deterministic candidate corpus manifest.

The freeze is metadata-only: source PDFs stay external, while the committed
artifact records every manifest's provenance, digest, licence, and coverage.
"""
from __future__ import annotations


import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.validate_manifest import validate_manifest

SCHEMA_VERSION = "candidate-corpus-v1"
DEFAULT_MANIFESTS = Path("../data/manifests")
DEFAULT_OUTPUT = Path("../data/candidate-corpus-manifest.json")


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")

def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def build_candidate_corpus(manifests_dir: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(manifests_dir.rglob("*.manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validation = validate_manifest(manifest)
        if validation:
            errors.extend(f"{path}: {error}" for error in validation)
        document_id = manifest.get("document_id")
        if not isinstance(document_id, str):
            errors.append(f"{path}: missing document_id")
            continue
        entry = {
            "document_id": document_id,
            "manifest_path": path.relative_to(manifests_dir).as_posix(),
            "source_url": manifest.get("source_url"),
            "source_version": manifest.get("document_number"),
            "file_hash": manifest.get("file_hash"),
            "license": manifest.get("license", "unknown"),
            "coverage": {
                "status": manifest.get("status"),
                "review_status": manifest.get("review_status"),
                "effective_from": manifest.get("effective_from"),
                "effective_to": manifest.get("effective_to"),
                "expected_points": manifest.get("expected_points", 0),
                "expected_tables": manifest.get("expected_tables", 0),
            },
        }
        entries.append(entry)
    ids = [entry["document_id"] for entry in entries]
    hashes = [entry["file_hash"] for entry in entries]
    if len(ids) != len(set(ids)):
        errors.append("duplicate document_id")
    if len(hashes) != len(set(hashes)):
        errors.append("duplicate file_hash")
    if errors:
        raise ValueError("candidate corpus validation failed: " + "; ".join(errors))
    entries.sort(key=lambda entry: entry["document_id"])
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "manifest_count": len(entries),
        "coverage": {
            "documents": len(entries),
            "review_status_counts": {
                status: sum(
                    entry["coverage"]["review_status"] == status for entry in entries
                )
                for status in sorted(
                    {entry["coverage"]["review_status"] for entry in entries}
                )
            },
            "source_domains": sorted({e["source_url"].split("/")[2] for e in entries}),
        },
        "entries": entries,
    }
    artifact["artifact_sha256"] = _sha256(artifact)
    return artifact


def validate_frozen_corpus(artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if artifact.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    entries = artifact.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]
    if artifact.get("manifest_count") != len(entries):
        errors.append("manifest_count does not match entries")
    ids = [entry.get("document_id") for entry in entries]
    hashes = [entry.get("file_hash") for entry in entries]
    if len(ids) != len(set(ids)):
        errors.append("duplicate document_id")
    if len(hashes) != len(set(hashes)):
        errors.append("duplicate file_hash")
    recorded = artifact.get("artifact_sha256")
    if isinstance(recorded, str):
        payload = dict(artifact)
        payload.pop("artifact_sha256", None)
        if recorded != _sha256(payload):
            errors.append("artifact_sha256 mismatch")
    else:
        errors.append("missing artifact_sha256")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifests-dir", type=Path, default=DEFAULT_MANIFESTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite immutable artifact: {args.output}")
    artifact = build_candidate_corpus(args.manifests_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(artifact))
    print(f"PASS: {args.output} ({artifact['manifest_count']} documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
