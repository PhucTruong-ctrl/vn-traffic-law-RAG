"""Grade thesis evaluation answers into runner-compatible review artifacts."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from openai import OpenAI

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_generation_settings  # noqa: E402

JUDGE_MODEL = "openai/gpt-4o-mini"
REVIEW_KEYS = (
    "case_id",
    "answer_correctness_manual",
    "faithfulness",
    "completeness",
    "citation_support",
    "notes",
    "judge",
    "evidence",
    "human_override",
    "coverage_status",
)
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "accuracy": {"type": "number", "enum": [0, 0.5, 1]},
        "faithfulness": {"type": "number", "minimum": 0, "maximum": 1},
        "completeness": {"type": "number", "minimum": 0, "maximum": 1},
        "citation_support": {"type": "number", "minimum": 0, "maximum": 1},
        "notes": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "accuracy",
        "faithfulness",
        "completeness",
        "citation_support",
        "notes",
        "evidence",
    ],
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _coordinates(row: dict[str, Any], cases: dict[str, dict[str, Any]]) -> list[str]:
    gold = cases.get(str(row.get("case_id")), row)
    values: list[str] = []
    for key in ("expected_provision_ids", "expected_coordinates", "expected_refs"):
        item = gold.get(key)
        if isinstance(item, list):
            values.extend(str(x) for x in item)
        elif isinstance(item, str):
            values.append(item)
    answer_key = gold.get("answer_key")
    if isinstance(answer_key, dict):
        for key in ("provision_ids", "coordinates", "expected_provision_ids"):
            item = answer_key.get(key)
            if isinstance(item, list):
                values.extend(str(x) for x in item)
    return list(dict.fromkeys(values))


def _citation_ids(row: dict[str, Any]) -> list[str]:
    citations = (row.get("prediction") or {}).get("citations", [])
    out = []
    for citation in citations:
        if isinstance(citation, str):
            out.append(citation)
        elif isinstance(citation, dict):
            out.extend(
                str(citation[k]) for k in ("provision_id", "coordinate", "id") if citation.get(k)
            )
    return out


def assemble_prompt(row: dict[str, Any], expected: list[str], deterministic: dict[str, Any]) -> str:
    prediction = row.get("prediction") or {}
    return json.dumps(
        {
            "rubric": (
                "Score accuracy 0/0.5/1; faithfulness, completeness, citation_support 0..1. "
                "Refusal cases have null semantic scores."
            ),
            "case": {
                "case_id": row.get("case_id"),
                "category": row.get("category"),
                "question": row.get("question"),
            },
            "answer": prediction.get("answer", ""),
            "status": prediction.get("status"),
            "citations": prediction.get("citations", []),
            "expected_coordinates": expected,
            "deterministic_checks": deterministic,
            "instruction": (
                "Return strict JSON matching the supplied schema; quote citation excerpts used."
            ),
        },
        ensure_ascii=False,
        indent=2,
    )


def deterministic_checks(row: dict[str, Any], expected: list[str]) -> dict[str, Any]:
    cited = _citation_ids(row)
    answer = str((row.get("prediction") or {}).get("answer", ""))
    overlap = [
        coord
        for coord in expected
        if coord in answer or any(part in answer for part in coord.split("__"))
    ]
    return {
        "expected_coordinates": expected,
        "cited_coordinates": cited,
        "coordinates_present": bool(set(cited) & set(expected)),
        "answer_coordinate_overlap": overlap,
    }


def parse_judge_response(raw: str) -> dict[str, Any]:
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("judge response is not an object")
    for key in SCHEMA["required"]:
        if key not in data:
            raise ValueError(f"missing {key}")
    if data["accuracy"] not in (0, 0.5, 1):
        raise ValueError("invalid accuracy")
    for key in ("faithfulness", "completeness", "citation_support"):
        if not isinstance(data[key], (int, float)) or not 0 <= data[key] <= 1:
            raise ValueError(f"invalid {key}")
    if not isinstance(data["notes"], str) or not isinstance(data["evidence"], list):
        raise ValueError("invalid notes/evidence")
    return data


def _is_refusal(row: dict[str, Any]) -> bool:
    category = str(row.get("category", ""))
    gold = row.get("expected_abstain")
    return bool(gold) or category == "insufficient_evidence"


def _is_out_of_corpus(row: dict[str, Any]) -> bool:
    return str(row.get("category", "")) == "out_of_scope" or bool(row.get("out_of_corpus"))


def grade_row(
    row: dict[str, Any],
    cases: dict[str, dict[str, Any]],
    judge: Callable[[str], str] | None,
    retries: int = 1,
) -> dict[str, Any]:
    expected = _coordinates(row, cases)
    checks = deterministic_checks(row, expected)
    refusal = _is_refusal(row)
    prediction = row.get("prediction") or {}
    abstained = (
        str(prediction.get("status", "")).lower() in {"abstain", "refused", "refusal"}
        or "không có" in str(prediction.get("answer", "")).lower()
    )
    if refusal:
        correct = 1 if abstained else 0
        return {
            "case_id": row.get("case_id"),
            "answer_correctness_manual": correct,
            "faithfulness": None,
            "completeness": None,
            "citation_support": None,
            "notes": "Expected abstention; "
            + ("sensible refusal" if abstained else "answered instead of refusing"),
            "judge": "deterministic",
            "evidence": [],
            "human_override": "",
            "coverage_status": "out_of_corpus" if _is_out_of_corpus(row) else "abstention",
        }
    prompt = assemble_prompt(row, expected, checks)
    if not judge:
        raise RuntimeError("judge required")
    raw = ""
    for _attempt in range(retries + 1):
        try:
            parsed = parse_judge_response(judge(prompt))
            return {
                "case_id": row.get("case_id"),
                "answer_correctness_manual": parsed["accuracy"],
                "faithfulness": parsed["faithfulness"],
                "completeness": parsed["completeness"],
                "citation_support": parsed["citation_support"],
                "notes": parsed["notes"],
                "judge": JUDGE_MODEL,
                "evidence": parsed["evidence"],
                "human_override": "",
                "coverage_status": "out_of_corpus" if _is_out_of_corpus(row) else "corpus",
            }
        except Exception as exc:
            raw = f"{type(exc).__name__}: {exc}"
    return {
        "case_id": row.get("case_id"),
        "answer_correctness_manual": None,
        "faithfulness": None,
        "completeness": None,
        "citation_support": None,
        "notes": f"judge_error: {raw}",
        "judge": JUDGE_MODEL,
        "evidence": [],
        "human_override": "",
        "coverage_status": "out_of_corpus" if _is_out_of_corpus(row) else "corpus",
    }


def write_outputs(prefix: Path, reviews: list[dict[str, Any]]) -> None:
    with prefix.with_suffix(".reviews.jsonl").open("w", encoding="utf-8") as f:
        for row in reviews:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    with prefix.with_suffix(".reviews.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_KEYS)
        writer.writeheader()
        for row in reviews:
            writer.writerow(
                {
                    k: json.dumps(row[k], ensure_ascii=False)
                    if isinstance(row[k], (list, dict))
                    else row[k]
                    for k in REVIEW_KEYS
                }
            )
    categories: dict[str, list[float]] = {}
    for row in reviews:
        if row["coverage_status"] == "out_of_corpus":
            continue
        category = str(row.get("category", "unknown"))
        score = row["answer_correctness_manual"]
        if isinstance(score, (int, float)):
            categories.setdefault(category, []).append(float(score))
    lines = [
        "# Thesis answer review summary",
        "",
        "| Category | Mean accuracy | Cases |",
        "|---|---:|---:|",
    ]
    for category, scores in sorted(categories.items()):
        lines.append(f"| {category} | {sum(scores) / len(scores):.3f} | {len(scores)} |")
    lines += ["", "## Cases scoring below 1", ""]
    for row in reviews:
        if (
            isinstance(row["answer_correctness_manual"], (int, float))
            and row["answer_correctness_manual"] < 1
        ):
            lines.append(f"- {row['case_id']}: {row['notes']}")
    out_cases = [r["case_id"] for r in reviews if r["coverage_status"] == "out_of_corpus"]
    lines += ["", "## Out of corpus", "", ", ".join(map(str, out_cases)) or "None"]
    prefix.with_suffix(".review-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    parser.add_argument("--cases", type=Path, default=Path("data/evaluation/thesis-gold-40.json"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--only-case")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    rows = load_jsonl(args.run)
    if args.only_case:
        rows = [r for r in rows if str(r.get("case_id")) == args.only_case]
    if args.limit is not None:
        rows = rows[: args.limit]
    gold_data = json.loads(args.cases.read_text(encoding="utf-8")) if args.cases.exists() else []
    if isinstance(gold_data, dict):
        gold_data = gold_data.get("cases", [])
    cases = {str(r.get("id", r.get("case_id"))): r for r in gold_data if isinstance(r, dict)}
    prompts = [
        assemble_prompt(r, _coordinates(r, cases), deterministic_checks(r, _coordinates(r, cases)))
        for r in rows
    ]
    if args.dry_run:
        for i, prompt in enumerate(prompts, 1):
            print(f"--- prompt {i}/{len(prompts)} ---\n{prompt}")
        print(f"total_cases={len(rows)}")
        return 0
    settings = get_generation_settings()
    client = OpenAI(
        api_key=settings.openrouter_api_key, base_url=settings.openrouter_base_url, max_retries=0
    )

    def call(prompt: str) -> str:
        response = client.chat.completions.create(
            model=getattr(settings, "model", JUDGE_MODEL),
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "thesis_grade", "strict": True, "schema": SCHEMA},
            },
        )
        return response.choices[0].message.content or ""

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(grade_row, r, cases, call) for r in rows]
        reviews = [f.result() for f in as_completed(futures)]
    reviews.sort(key=lambda r: str(r["case_id"]))
    for review, source in zip(
        reviews, sorted(rows, key=lambda r: str(r.get("case_id"))), strict=True
    ):
        review["category"] = source.get("category", "unknown")
    output = args.output_dir or args.run.parent
    output.mkdir(parents=True, exist_ok=True)
    write_outputs(output / args.run.stem, reviews)
    return 0


if __name__ == "__main__":
    sys.exit(main())
