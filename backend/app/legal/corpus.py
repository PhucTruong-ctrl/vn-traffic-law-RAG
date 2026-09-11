"""Read-only Markdown and LangChain-compatible JSONL corpus access."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ingestion.markdown import load_manifest

_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _ROOT / "data" / "sources" / "manifest.json"
_LOCAL_DIR = _ROOT / "data" / "corpus" / "mds"
_PROCESSED = _ROOT / "data" / "processed" / "markdown-chunks.jsonl"
_KNOWN = {
    "document_id",
    "doc_id",
    "document_name",
    "source_file",
    "source_url",
    "source_type",
    "retrieved_at",
    "chunk_id",
    "id",
    "article",
    "clause",
    "point",
    "text",
    "page_content",
    "page",
}


@dataclass(frozen=True)
class Chunk:
    text: str
    metadata: dict[str, Any]


def _path(value: str | Path | None, default: Path) -> Path:
    if value is not None:
        return Path(value)
    env_name = "LEGAL_MANIFEST" if default == _MANIFEST else "LEGAL_CHUNKS"
    env_value = os.getenv(env_name)
    return Path(env_value) if env_value is not None else default


def _read_processed(path: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    if not path.is_file():
        return chunks
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        text = row.get("text") or row.get("page_content")
        if not isinstance(text, str) or not text.strip():
            continue
        metadata = {
            str(k): v for k, v in row.items() if k in _KNOWN and k not in {"text", "page_content"}
        }
        if "document_id" not in metadata and metadata.get("doc_id"):
            metadata["document_id"] = metadata["doc_id"]
        if "chunk_id" not in metadata and metadata.get("id"):
            metadata["chunk_id"] = metadata["id"]
        chunks.append(Chunk(text=text.strip(), metadata=metadata))
    return chunks


def chunks(
    *, manifest: str | Path | None = None, processed: str | Path | None = None
) -> list[Chunk]:
    selected = _read_processed(_path(processed, _PROCESSED))
    if selected:
        return selected
    manifest_path = _path(manifest, _MANIFEST)
    docs = load_manifest(manifest_path, local_dir=_LOCAL_DIR)
    return [Chunk(text=d.page_content, metadata=dict(d.metadata)) for d in docs]


def _value(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return None if value is None else str(value)


def filter_chunks(
    items: list[Chunk],
    *,
    document_id: str | None = None,
    article: str | None = None,
    clause: str | None = None,
    point: str | None = None,
) -> list[Chunk]:
    def matches(item: Chunk) -> bool:
        md = item.metadata
        return all(
            value is None or _value(md, key) == value
            for key, value in (
                ("document_id", document_id),
                ("article", article),
                ("clause", clause),
                ("point", point),
            )
        )

    return [item for item in items if matches(item)]


def search_chunks(items: list[Chunk], query: str, **filters: str | None) -> list[tuple[Chunk, int]]:
    terms = re.findall(r"\w+", query.casefold())
    filtered = filter_chunks(items, **filters)
    scored = []
    for item in filtered:
        haystack = item.text.casefold()
        score = sum(haystack.count(term) for term in terms)
        if score:
            scored.append((item, score))
    return sorted(scored, key=lambda pair: (-pair[1], str(pair[0].metadata.get("chunk_id", ""))))
