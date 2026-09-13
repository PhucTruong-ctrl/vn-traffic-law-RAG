"""Build deterministic LangChain legal documents from the canonical local corpus."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.ingestion.markdown import load_manifest, write_jsonl  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=_ROOT / "data/sources/manifest.json")
    parser.add_argument("--local-dir", type=Path, default=_ROOT / "data/corpus/mds")
    parser.add_argument("--output", type=Path, default=_ROOT / "data/processed/chunks.jsonl")
    args = parser.parse_args(argv)
    try:
        documents = load_manifest(args.manifest, local_dir=args.local_dir)
        count = write_jsonl(documents, args.output)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"source ingestion failed: {exc}") from exc
    print(f"wrote {count} legal chunks to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
