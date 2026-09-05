import json
from pathlib import Path

from scripts.validate_gold_set import validate_gold_set

ROOT = Path(__file__).resolve().parents[2]
GOLD = ROOT / "data/gold-sets/gold-v1/gold.json"
HASH = ROOT / "data/gold-sets/gold-v1/hash.json"


def test_gold_set_is_complete_and_integrity_checked() -> None:
    records = json.loads(GOLD.read_text(encoding="utf-8"))["records"]
    assert len(records) == 200
    assert {record["category"] for record in records} >= {
        "CURRENT",
        "HISTORICAL",
        "COMPARISON",
        "OUT_OF_SCOPE",
        "ADVERSARIAL_CITATION",
    }
    assert not validate_gold_set(GOLD, HASH)


def test_gold_set_has_no_placeholder_content() -> None:
    text = GOLD.read_text(encoding="utf-8").lower()
    assert "placeholder" not in text
    assert all(
        record["review_status"].upper() == "APPROVED"
        for record in json.loads(text)["records"]
    )
