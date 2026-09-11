"""Run a dependency-light local retrieval and answer smoke check."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))

from app.rag.retrieval import Retriever  # noqa: E402
from app.rag.service import RescueService  # noqa: E402

QUESTIONS = (
    "Người điều khiển xe máy phải đội mũ bảo hiểm như thế nào?",
    "Mức phạt khi vượt đèn đỏ đối với ô tô là bao nhiêu?",
    "Điều kiện cấp giấy phép lái xe hạng B là gì?",
)


def _field(item: Any, name: str, default: str = "-") -> Any:
    if isinstance(item, dict):
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and name in metadata:
            return metadata[name]
        return item.get(name, default)
    return getattr(item, name, default)


def run(chunks_path: Path, top_k: int = 8) -> None:
    retriever = Retriever(chunks_path=chunks_path)
    service = RescueService(retriever)
    for question in QUESTIONS:
        started = time.perf_counter()
        results = retriever.search(question, k=top_k)
        payload = service.answer(question, chunks=results, top_k=top_k)
        elapsed_ms = (time.perf_counter() - started) * 1000
        print(f"QUESTION: {question}")
        print("TOP RETRIEVAL:")
        for rank, item in enumerate(results, 1):
            print(
                f"  {rank}. document={_field(item, 'document_name', _field(item, 'document'))} "
                f"article={_field(item, 'article')} clause={_field(item, 'clause')} "
                f"page={_field(item, 'page', _field(item, 'page_number'))} "
                f"score={_field(item, 'score', '-')}"
            )
        print(f"ANSWER: {payload.get('answer', '')}")
        print("CITATIONS:")
        for citation in payload.get("citations", []):
            print(
                "  document="
                f"{citation.get('document', '-')} article={citation.get('article', '-')} "
                f"clause={citation.get('clause', '-')} page={citation.get('page', '-')}"
            )
        print(f"LATENCY: {elapsed_ms:.2f} ms")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--chunks",
        type=Path,
        default=ROOT / "data/processed/chunks.jsonl",
        help="JSONL corpus path (default: data/processed/chunks.jsonl)",
    )
    parser.add_argument("--top-k", type=int, default=8, help="number of retrieval results")
    args = parser.parse_args()
    run(args.chunks, args.top_k)


if __name__ == "__main__":
    main()
