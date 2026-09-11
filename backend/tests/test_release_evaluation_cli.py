from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_release_evaluation import load_frozen_gold


def test_load_frozen_gold_fails_closed_when_readiness_not_frozen(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({"records": []}), encoding="utf-8")
    readiness = tmp_path / "READINESS.json"
    readiness.write_text(
        json.dumps({"frozen": False, "freeze_status": "BLOCKED"}), encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="not frozen"):
        load_frozen_gold(gold, readiness)


def test_load_frozen_gold_requires_exact_count(tmp_path: Path) -> None:
    gold = tmp_path / "gold.json"
    gold.write_text(json.dumps({"records": []}), encoding="utf-8")
    readiness = tmp_path / "READINESS.json"
    readiness.write_text(json.dumps({"frozen": True, "freeze_status": "FROZEN"}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="exactly 200"):
        load_frozen_gold(gold, readiness)
