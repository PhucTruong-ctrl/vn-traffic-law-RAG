"""Recursively extract PDFs into deterministic legal JSONL chunks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
_CORPUS = _REPO_ROOT / "data" / "corpus" / "pdfs"
_OUTPUT = _REPO_ROOT / "data" / "processed" / "chunks.jsonl"
_CHECKPOINT_ROOT = _REPO_ROOT / "data" / "processed" / "ingest-checkpoints"
_PAGE_CACHE = _REPO_ROOT / "data" / "processed" / "page-cache"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.ingestion import LegalChunk, extract_pages, split_legal_pages, write_jsonl  # noqa: E402


def _source_key(pdf: Path) -> str:
    return hashlib.sha256(pdf.read_bytes()).hexdigest()


def _checkpoint_path(pdf: Path, checkpoint_dir: Path) -> Path:
    return checkpoint_dir / f"{_source_key(pdf)}.jsonl"


def _load_checkpoint(path: Path) -> list[LegalChunk] | None:
    if not path.is_file():
        return None
    try:
        return [
            LegalChunk(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines()
        ]
    except (OSError, TypeError, ValueError):
        return None


def _write_checkpoint(path: Path, chunks: list[LegalChunk]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        for chunk in chunks:
            handle.write(json.dumps(asdict(chunk), ensure_ascii=False, sort_keys=True) + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_output(chunks: list[LegalChunk], output: Path) -> int:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    count = write_jsonl(chunks, temporary)
    os.replace(temporary, output)
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=_CORPUS,
        help="directory containing PDFs (searched recursively)",
    )
    parser.add_argument("--output", type=Path, default=_OUTPUT, help="destination JSONL path")
    args = parser.parse_args(argv)
    pdfs = sorted(
        (path for path in args.pdf_dir.rglob("*.pdf") if path.is_file()),
        key=lambda path: path.relative_to(args.pdf_dir).as_posix(),
    )
    if not pdfs:
        parser.error(f"no PDF files found under {args.pdf_dir}")
    checkpoint_dir = args.output.parent / f"{args.output.stem}.checkpoints"
    chunks: list[LegalChunk] = []
    for index, pdf in enumerate(pdfs, 1):
        checkpoint = _checkpoint_path(pdf, checkpoint_dir)
        cached = _load_checkpoint(checkpoint)
        if cached is not None:
            file_chunks = cached
            print(f"[{index}/{len(pdfs)}] cache hit {pdf}")
        else:
            print(f"[{index}/{len(pdfs)}] extracting {pdf}")
            file_chunks = split_legal_pages(extract_pages(pdf, cache_dir=_PAGE_CACHE))
            _write_checkpoint(checkpoint, file_chunks)
        chunks.extend(file_chunks)
        _write_output(chunks, args.output)
    print(f"wrote {len(chunks)} chunks from {len(pdfs)} PDFs to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
