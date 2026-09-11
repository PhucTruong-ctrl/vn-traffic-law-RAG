"""Build the dependency-light retrieval index from chunks JSONL."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.rag.retrieval import Retriever  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index chunks JSONL for local lexical retrieval.")
    parser.add_argument(
        "chunks",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[2] / "data" / "processed" / "chunks.jsonl",
        help="Input chunks.jsonl path",
    )
    parser.add_argument(
        "--index-path",
        type=Path,
        default=Path("backend/data/qdrant"),
        help="Persistent index directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.chunks.exists():
        raise SystemExit(f"chunks file not found: {args.chunks}")
    records = [json.loads(line) for line in args.chunks.open(encoding="utf-8") if line.strip()]
    count = Retriever(args.chunks, args.index_path).persist(records)
    print(f"indexed {count} chunks at {args.index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
