"""Build the persistent local retrieval index from processed JSONL chunks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.rag.retrieval import Retriever

DEFAULT_CHUNKS_PATH = Path("data/processed/chunks.jsonl")
DEFAULT_INDEX_PATH = Path("data/processed/index")


def _read_chunks(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"processed chunks file not found: {path}")
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path} at line {line_number}") from exc
        if not isinstance(record, Mapping):
            raise ValueError(f"chunk at {path}:{line_number} must be a JSON object")
        records.append(dict(record))
    return records


def load_markdown_chunks(
    markdown_dir: str | Path,
    *,
    chunks_path: str | Path = DEFAULT_CHUNKS_PATH,
) -> list[dict[str, Any]]:
    """Combine the existing JSONL corpus with explicitly supplied local Markdown.

    Markdown files are read in lexical relative-path order and never fetched.
    Each file is one deterministic chunk; optional front matter can provide
    ``document_id``, ``source_type`` and ``source_url``.
    """
    directory = Path(markdown_dir)
    if not directory.is_dir():
        raise NotADirectoryError(f"Markdown directory not found: {directory}")
    records = _read_chunks(Path(chunks_path)) if Path(chunks_path).exists() else []
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        fields: dict[str, str] = {}
        if text.startswith("---\n"):
            _, _, remainder = text.partition("\n")
            header, separator, body = remainder.partition("\n---")
            if separator:
                text = body.lstrip("\n")
                for line in header.splitlines():
                    key, sep, value = line.partition(":")
                    if sep and key.strip() in {"document_id", "source_type", "source_url"}:
                        fields[key.strip()] = value.strip().strip("\"'")
        relative = path.relative_to(directory).as_posix()
        document_id = fields.get("document_id") or path.stem
        source_url = fields.get("source_url") or f"local://{relative}"
        source_type = fields.get("source_type") or "markdown"
        chunk_id = hashlib.sha256(
            "\0".join((document_id, source_url, relative, text)).encode("utf-8")
        ).hexdigest()[:24]
        records.append(
            {
                "id": chunk_id,
                "text": text,
                "document_id": document_id,
                "document_name": path.stem,
                "page": 1,
                "chunk_index": 0,
                "source_url": source_url,
                "source_type": source_type,
                "metadata": {
                    "document_id": document_id,
                    "source_url": source_url,
                    "source_type": source_type,
                },
            }
        )
    return records


def build_index(
    chunks_path: str | Path = DEFAULT_CHUNKS_PATH,
    index_path: str | Path = DEFAULT_INDEX_PATH,
    *,
    chunks: Iterable[Mapping[str, Any]] | None = None,
) -> int:
    """Persist a deterministic lexical index and return the chunk count.

    The default path reads the repository's processed JSONL corpus. Passing
    ``chunks`` keeps callers and smoke checks independent of external providers.
    """
    source = Path(chunks_path)
    records = [dict(item) for item in chunks] if chunks is not None else _read_chunks(source)
    retriever = Retriever(chunks_path=source, index_path=Path(index_path))
    return retriever.persist(records)


def index_corpus(
    chunks_path: str | Path = DEFAULT_CHUNKS_PATH,
    index_path: str | Path = DEFAULT_INDEX_PATH,
) -> int:
    """Build the derived index from a processed corpus JSONL file."""
    return build_index(chunks_path, index_path)


__all__ = [
    "DEFAULT_CHUNKS_PATH",
    "DEFAULT_INDEX_PATH",
    "build_index",
    "index_corpus",
    "load_markdown_chunks",
]
