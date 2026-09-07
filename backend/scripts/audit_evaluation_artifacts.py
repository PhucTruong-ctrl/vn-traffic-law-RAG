"""Audit persisted evaluation artifacts without changing their verdicts.

This is an acceptance runner, not an evaluator: it checks that report sources
exist and preserves the source-level ``NOT_RUN``, ``NA``, and ``PARTIAL``
states instead of turning unavailable prerequisites into fabricated results.

Usage (from the repository root)::

    uv run python -m scripts.audit_evaluation_artifacts
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

_INCOMPLETE = {"NOT_RUN", "NA", "PARTIAL", "SKIPPED", "BLOCKED"}


def _status(value: object) -> str | None:
    if isinstance(value, str):
        normalized = value.strip().upper()
        return normalized or None
    return None


def _walk_statuses(value: object) -> set[str]:
    statuses: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.casefold() == "status":
                status = _status(item)
                if status is not None:
                    statuses.add(status)
            statuses.update(_walk_statuses(item))
    elif isinstance(value, list):
        for item in value:
            statuses.update(_walk_statuses(item))
    return statuses


def _load_source(root: Path, source: str) -> tuple[set[str], list[str]]:
    path = root / source
    if not path.is_file():
        return set(), [f"missing source: {source}"]
    try:
        if path.suffix.casefold() == ".json":
            statuses = _walk_statuses(json.loads(path.read_text(encoding="utf-8")))
        elif path.suffix.casefold() == ".csv":
            with path.open(newline="", encoding="utf-8") as handle:
                rows = csv.DictReader(handle)
                statuses = {
                    normalized
                    for row in rows
                    for normalized in [_status(row.get("status"))]
                    if normalized is not None
                }
        else:
            return set(), [f"unsupported source format: {source}"]
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        return set(), [f"unreadable source {source}: {type(exc).__name__}"]
    return statuses, []


def audit_report(root: Path, report_path: Path | None = None) -> dict[str, Any]:
    report = report_path or root / "data/evaluation/reporting/report.json"
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {"status": "BLOCKED", "errors": [f"unreadable report: {type(exc).__name__}"]}
    sources = payload.get("sources")
    if not isinstance(sources, list) or not all(isinstance(source, str) for source in sources):
        return {"status": "BLOCKED", "errors": ["report sources must be a list of paths"]}
    source_results: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    statuses: set[str] = set()
    for source in sources:
        source_statuses, source_errors = _load_source(root, source)
        source_results[source] = {"statuses": sorted(source_statuses), "errors": source_errors}
        statuses.update(source_statuses)
        errors.extend(source_errors)
    incomplete = sorted(statuses & _INCOMPLETE)
    overall = "BLOCKED" if errors else "PARTIAL" if incomplete else "COMPLETED"
    return {
        "status": overall,
        "reported_status": _status(payload.get("status")),
        "incomplete_statuses": incomplete,
        "sources": source_results,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit persisted evaluation artifacts")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    result = audit_report(args.root, args.report)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if result["status"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
