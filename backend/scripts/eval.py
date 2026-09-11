"""Evaluate real Qdrant HYBRID retrieval against question records."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from langchain_openai import OpenAIEmbeddings  # noqa: E402
from langchain_qdrant import FastEmbedSparse, QdrantVectorStore, RetrievalMode  # noqa: E402

from app.config import get_embedding_settings, get_qdrant_settings  # noqa: E402


def _records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    values = (
        json.loads(text)
        if path.suffix.lower() == ".json"
        else [json.loads(line) for line in text.splitlines() if line.strip()]
    )
    if isinstance(values, dict):
        values = values.get("questions", [values])
    return [item for item in values if isinstance(item, dict)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", type=Path)
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()
    settings, qdrant = get_embedding_settings(), get_qdrant_settings()
    if not settings.openrouter_api_key:
        raise SystemExit("evaluation requires OPENROUTER_API_KEY")
    try:
        store = QdrantVectorStore.from_existing_collection(
            collection_name=qdrant.collection,
            embedding=OpenAIEmbeddings(
                model=settings.model,
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_base_url,
            ),
            sparse_embedding=FastEmbedSparse("Qdrant/bm25"),
            retrieval_mode=RetrievalMode.HYBRID,
            url=qdrant.url,
            api_key=qdrant.api_key or None,
        )
        records = _records(args.questions)
        hits = 0
        for record in records:
            docs = store.similarity_search(record.get("question", ""), k=args.top_k)
            expected = str(record.get("expected_document", "")).casefold()
            hits += int(
                not expected
                or any(
                    expected in str(doc.metadata.get("document_id", "")).casefold()
                    for doc in docs
                )
            )
        print(
            f"QUESTIONS: {len(records)}\n"
            f"HIT@{args.top_k}: {hits}/{len(records)} "
            f"({hits / (len(records) or 1):.1%})"
        )
    except Exception as exc:
        raise SystemExit(f"evaluation failed: {exc}") from exc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
