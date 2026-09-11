"""Evaluate local retrieval against JSON or JSONL question records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.rag.retrieval import Retriever  # noqa: E402


def _records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        payload = json.loads(text)
        if isinstance(payload, list):
            values = payload
        elif isinstance(payload, dict) and isinstance(payload.get("questions"), list):
            values = payload["questions"]
        else:
            values = [payload]
    else:
        values = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [value for value in values if isinstance(value, dict)]


def _value(item: Any, name: str) -> Any:
    if isinstance(item, dict):
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and name in metadata:
            return metadata[name]
        return item.get(name)
    return getattr(item, name, None)


def _matches(item: Any, record: dict[str, Any]) -> bool:
    expected_document = record.get("expected_document")
    expected_article = record.get("expected_article")
    document = _value(item, "document_name") or _value(item, "document")
    article = _value(item, "article")
    doc_match = (
        expected_document is None
        or str(expected_document).casefold() in str(document or "").casefold()
    )
    article_match = expected_article is None or str(expected_article) == str(article)
    return doc_match and article_match


def run(questions_path: Path, chunks_path: Path, top_k: int = 8) -> None:
    retriever = Retriever(chunks_path=chunks_path)
    records = _records(questions_path)
    hits = citation_matches = 0
    for record in records:
        question = str(record.get("question", ""))
        results = retriever.search(question, k=top_k)
        hit = any(_matches(item, record) for item in results)
        citation_match = any(_matches(item, record) for item in results)
        hits += int(hit)
        citation_matches += int(citation_match)
    total = len(records)
    denominator = total or 1
    print(f"QUESTIONS: {total}")
    print(f"HIT@{top_k}: {hits}/{total} ({hits / denominator:.1%})")
    print(f"CITATION MATCHES: {citation_matches}/{total} ({citation_matches / denominator:.1%})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path, help="JSON or JSONL question file")
    parser.add_argument("--chunks", type=Path, default=ROOT / "data/processed/chunks.jsonl")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    run(args.questions, args.chunks, args.top_k)


if __name__ == "__main__":
    main()
