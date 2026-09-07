from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_evaluation_artifacts import audit_report


def test_audit_preserves_incomplete_source_statuses(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text(
        json.dumps({"status": "NOT_RUN", "reason": "dependency unavailable"}), encoding="utf-8"
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"status": "PARTIAL", "sources": ["metrics.json"]}),
        encoding="utf-8",
    )

    result = audit_report(tmp_path, report)

    assert result["status"] == "PARTIAL"
    assert result["reported_status"] == "PARTIAL"
    assert result["incomplete_statuses"] == ["NOT_RUN"]
    assert result["sources"]["metrics.json"]["statuses"] == ["NOT_RUN"]


def test_audit_blocks_missing_source_without_claiming_completion(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"status": "COMPLETED", "sources": ["missing.json"]}),
        encoding="utf-8",
    )

    result = audit_report(tmp_path, report)

    assert result["status"] == "BLOCKED"
    assert result["reported_status"] == "COMPLETED"
    assert result["errors"] == ["missing source: missing.json"]


def test_audit_accepts_complete_sources(tmp_path: Path) -> None:
    (tmp_path / "metrics.json").write_text(
        json.dumps({"status": "COMPLETED", "value": 1}), encoding="utf-8"
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"status": "COMPLETED", "sources": ["metrics.json"]}),
        encoding="utf-8",
    )

    result = audit_report(tmp_path, report)

    assert result["status"] == "COMPLETED"
    assert result["reported_status"] == "COMPLETED"
    assert result["incomplete_statuses"] == []
