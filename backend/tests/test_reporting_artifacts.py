from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
REPORT = REPO_ROOT / "data" / "evaluation" / "reporting" / "report.json"


def test_report_sources_point_to_persisted_artifacts() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    sources = payload["sources"]

    assert sources[:2] == [
        "backend/data/evaluation/temporal/results.json",
        "backend/data/evaluation/suite-d/results.json",
    ]
    assert all((REPO_ROOT / source).is_file() for source in sources)
