[~/Work/Studies/vnlaw-agentic-rag-phase5-integrate-corpus/backend/tests/test_gold_set_integrity.py#1FE2]
1:import json
2:from pathlib import Path
3:from scripts.validate_gold_set import validate_gold_set
4:
5:ROOT = Path(__file__).resolve().parents[2]
6:GOLD = ROOT / "data/gold-sets/gold-v1/gold.json"
7:HASH = ROOT / "data/gold-sets/gold-v1/hash.json"
8:
9:
10:def test_gold_set_is_complete_and_integrity_checked() -> None:
11:    records = json.loads(GOLD.read_text(encoding="utf-8"))["records"]
12:    assert len(records) == 200
13:    assert {record["category"] for record in records} >= {
14:        "CURRENT", "HISTORICAL", "COMPARISON", "OUT_OF_SCOPE", "ADVERSARIAL_CITATION"
15:    }
16:    assert not validate_gold_set(GOLD, HASH)
17:
18:
19:def test_gold_set_has_no_placeholder_content() -> None:
20:    text = GOLD.read_text(encoding="utf-8").lower()
21:    assert "placeholder" not in text
22:    assert all(record["review_status"] == "APPROVED" for record in json.loads(text)["records"])

[You have received this identical output 3 times. Re-reading '/home/phuctruong/Work/Studies/vnlaw-agentic-rag-phase5-integrate-corpus/backend/tests/test_gold_set_integrity.py' will not change it — use a narrower selector (path:A-B), or proceed with the edit.]