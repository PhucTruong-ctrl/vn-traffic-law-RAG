"""Review thesis evaluation answers interactively or from a review JSONL file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, NoReturn

VALID = {"pass", "fail"}


def fail(message: str) -> NoReturn:
    raise SystemExit(f"error: {message}")


def read_rows(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"cannot read answers: {exc}")
    rows = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"line {number} is invalid JSON: {exc}")
        if not isinstance(value, dict) or not isinstance(value.get("case_id"), str):
            fail(f"line {number} must contain case_id")
        rows.append(value)
    if not rows:
        fail("answer JSONL is empty")
    return rows


def read_reviews(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    reviews = {}
    for row in read_rows(path):
        case_id = row["case_id"]
        if case_id in reviews:
            fail(f"duplicate review for {case_id}")
        decision = row.get("answer_correctness_manual")
        if decision not in VALID:
            fail(f"review for {case_id} must be pass or fail")
        reviews[case_id] = {
            "case_id": case_id,
            "answer_correctness_manual": decision,
            "notes": str(row.get("notes", "")),
        }
    return reviews


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("answers", type=Path, help="evaluation raw JSONL")
    parser.add_argument("--output", type=Path, required=True, help="review JSONL output")
    parser.add_argument(
        "--non-interactive", action="store_true", help="read decisions from --input"
    )
    parser.add_argument(
        "--input", type=Path, help="JSONL containing case_id, answer_correctness_manual, notes"
    )
    args = parser.parse_args()
    rows = read_rows(args.answers)
    existing = read_reviews(args.output)
    supplied = read_reviews(args.input) if args.input else {}
    decisions = dict(existing)
    with args.output.open("a", encoding="utf-8") as output:
        for row in rows:
            case_id = row["case_id"]
            if case_id in decisions:
                continue
            review = supplied.get(case_id)
            if review is None:
                if args.non_interactive:
                    fail(f"missing review for {case_id}")
                print(
                    f"\nCase {case_id} [{row.get('category', '')}]\n"
                    f"Question: {row.get('question', '')}\n"
                    f"Answer: {json.dumps(row.get('prediction'), ensure_ascii=False)}"
                )
                decision = input("Decision (pass/fail): ").strip().casefold()
                if decision not in VALID:
                    fail(f"invalid decision for {case_id}; use pass or fail")
                notes = input("Notes (optional): ").strip()
                review = {"case_id": case_id, "answer_correctness_manual": decision, "notes": notes}
            output.write(json.dumps(review, ensure_ascii=False) + "\n")
            output.flush()
            decisions[case_id] = review
    missing = [row["case_id"] for row in rows if row["case_id"] not in decisions]
    if missing:
        fail(f"incomplete reviews: {', '.join(missing)}")
    print(json.dumps({"output": str(args.output), "reviewed": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
