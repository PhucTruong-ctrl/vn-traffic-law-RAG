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

SCHEMA_VERSION = "candidate-corpus-v2"
DEFAULT_MANIFESTS = Path("../data/manifests")
DEFAULT_PDF_DIR = Path("../data/corpus/task1-pdfs")
DEFAULT_OUTPUT = Path("../data/candidate-corpus-manifest.json")
SOURCE_ALLOWLIST = "datafiles.chinhphu.vn"
EXPECTED_DOCUMENT_COUNT = 14


def _canonical(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entries(manifests_dir: Path) -> tuple[list[dict[str, Any]], list[str]]:
    entries: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in sorted(manifests_dir.rglob("*.manifest.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        validation = validate_manifest(manifest)
        if validation:
            errors.extend(f"{path}: {error}" for error in validation)
            continue
        source = manifest["source_url"]
        if source.split("/")[2].lower() != SOURCE_ALLOWLIST:
            errors.append(f"{path}: source_not_allowlisted:{source}")
            continue
        entries.append(
            {
                "document_id": manifest["document_id"],
                "manifest_path": path.relative_to(manifests_dir).as_posix(),
                "source_url": source,
                "source_version": manifest["document_number"],
                "file_hash": manifest["file_hash"],
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
        )
    return entries, errors


def build_candidate_corpus(
    manifests_dir: Path,
    pdf_dir: Path = DEFAULT_PDF_DIR,
    *,
    expected_count: int = EXPECTED_DOCUMENT_COUNT,
) -> dict[str, Any]:
    entries, errors = _manifest_entries(manifests_dir)
    by_id: dict[str, dict[str, Any]] = {}
    by_hash: dict[str, str] = {}
    for entry in entries:
        document_id = entry["document_id"]
        file_hash = entry["file_hash"]
        if document_id in by_id:
            errors.append(f"duplicate_document_id:{document_id}")
            continue
        if file_hash in by_hash:
            errors.append(f"duplicate_file_hash:{file_hash}:{by_hash[file_hash]}")
            continue
        pdf_path = pdf_dir / f"{document_id}.pdf"
        if not pdf_path.is_file():
            errors.append(f"missing_pdf:{document_id}:{pdf_path}")
            continue
        actual_hash = _sha256_file(pdf_path)
        if actual_hash != file_hash:
            errors.append(
                f"sha256_mismatch:{document_id}:expected={file_hash}:actual={actual_hash}"
            )
            continue
        entry["local_path"] = pdf_path.as_posix()
        entry["local_sha256"] = actual_hash
        by_id[document_id] = entry
        by_hash[file_hash] = document_id
    selected = sorted(by_id.values(), key=lambda entry: entry["document_id"])
    if len(selected) != expected_count:
        errors.append(f"document_count:{len(selected)}:expected={expected_count}")
    if "nd-168-2024" not in by_id:
        errors.append("required_document_missing:nd-168-2024")
    if errors:
        raise ValueError("candidate corpus validation failed: " + "; ".join(errors))
    artifact = {
        "schema_version": SCHEMA_VERSION,
        "manifest_count": len(selected),
        "snapshot": {
            "document_count": len(selected),
            "identity_key": "document_id+file_hash",
            "source_allowlist": [SOURCE_ALLOWLIST],
            "entries_sha256": _sha256(selected),
        },
        "coverage": {
            "documents": len(selected),
            "review_status_counts": {
                status: sum(entry["coverage"]["review_status"] == status for entry in selected)
                for status in sorted({entry["coverage"]["review_status"] for entry in selected})
            },
            "source_domains": [SOURCE_ALLOWLIST],
        },
        "entries": selected,
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
    if artifact.get("manifest_count") != EXPECTED_DOCUMENT_COUNT:
        errors.append(f"expected {EXPECTED_DOCUMENT_COUNT} documents")
    snapshot = artifact.get("snapshot")
    if not isinstance(snapshot, dict):
        errors.append("missing snapshot metadata")
    elif snapshot.get("source_allowlist") != [SOURCE_ALLOWLIST]:
        errors.append("source allowlist mismatch")
    for entry in entries:
        if entry.get("source_url", "").split("/")[2].lower() != SOURCE_ALLOWLIST:
            errors.append(f"source_not_allowlisted:{entry.get('document_id')}")
        if entry.get("local_sha256") != entry.get("file_hash"):
            errors.append(f"local_sha256 mismatch:{entry.get('document_id')}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifests-dir", type=Path, default=DEFAULT_MANIFESTS)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite immutable artifact: {args.output}")
    artifact = build_candidate_corpus(args.manifests_dir, args.pdf_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(_canonical(artifact))
    print(f"PASS: {args.output} ({artifact['manifest_count']} documents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
