"""Read-only Markdown and LangChain-compatible JSONL corpus access."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.ingestion.markdown import load_manifest
from app.ingestion.source import normalized_metadata

_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _ROOT / "data" / "sources" / "manifest.json"
_LOCAL_DIR = _ROOT / "data" / "corpus" / "mds"
_PROCESSED = _ROOT / "data" / "processed" / "chunks.jsonl"
_STOPWORDS = frozenset(
    [
        "a",
        "cái",
        "các",
        "có",
        "cho",
        "của",
        "được",
        "để",
        "điều",
        "đó",
        "trong",
        "là",
        "này",
        "những",
        "và",
        "với",
        "từ",
        "về",
        "khi",
        "không",
        "theo",
        "trên",
        "tại",
        "một",
        "số",
    ]
)


_KNOWN = {
    "document_id",
    "doc_id",
    "document_name",
    "source_file",
    "source_url",
    "pdf_url",
    "source_kind",
    "source_type",
    "retrieved_at",
    "content_sha256",
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
    selected = value
    if selected is None:
        env_name = "LEGAL_MANIFEST" if default == _MANIFEST else "LEGAL_CHUNKS"
        selected = os.getenv(env_name)
    if selected is None:
        return default
    path = Path(selected)
    return path if path.is_absolute() else _ROOT / path


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
        raw_metadata = row.get("metadata")
        metadata_source = raw_metadata if isinstance(raw_metadata, dict) else row
        metadata = {
            str(k): v
            for k, v in metadata_source.items()
            if k in _KNOWN and k not in {"text", "page_content", "metadata"}
        }
        if "document_id" not in metadata and metadata.get("doc_id"):
            metadata["document_id"] = metadata["doc_id"]
        if "chunk_id" not in metadata and metadata.get("id"):
            metadata["chunk_id"] = metadata["id"]
        chunks.append(Chunk(text=text.strip(), metadata=normalized_metadata(metadata)))
    return chunks


def chunks(
    *, manifest: str | Path | None = None, processed: str | Path | None = None
) -> list[Chunk]:
    selected = _read_processed(_path(processed, _PROCESSED))
    if selected:
        return selected
    manifest_path = _path(manifest, _MANIFEST)
    docs = load_manifest(manifest_path, local_dir=_LOCAL_DIR)
    return [
        Chunk(text=d.page_content, metadata=normalized_metadata(dict(d.metadata))) for d in docs
    ]


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
            value is None or (md.get(key) is not None and str(md[key]) == value)
            for key, value in (
                ("document_id", document_id),
                ("article", article),
                ("clause", clause),
                ("point", point),
            )
        )

    return [item for item in items if matches(item)]


def _tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[^\W\d_]+|\d+", value.casefold())
        if len(token) > 1 and token not in _STOPWORDS
    ]


def search_chunks(items: list[Chunk], query: str, **filters: str | None) -> list[tuple[Chunk, int]]:
    terms = _tokens(query)
    query_phrase = " ".join(terms)
    filtered = filter_chunks(items, **filters)
    scored = []
    for item in filtered:
        tokens = _tokens(item.text)
        token_set = set(tokens)
        overlap = sum(token in token_set for token in terms)
        score = overlap * 10
        if query_phrase and query_phrase in " ".join(tokens):
            score += len(terms) * 10
        if score:
            scored.append((item, score))
    return sorted(scored, key=lambda pair: (-pair[1], str(pair[0].metadata.get("chunk_id", ""))))
