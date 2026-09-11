"""Deterministic ingestion of authorized local Markdown legal sources."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .pdf import LegalChunk, PageRecord, split_legal_pages

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)(?:\n---\s*\n|\Z)", re.DOTALL)
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


def _scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    """Parse simple ``key: value`` front matter without a YAML dependency."""
    match = _FRONT_MATTER.match(text.replace("\r\n", "\n").replace("\r", "\n"))
    if not match:
        return {}, text
    metadata: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if _KEY.fullmatch(key):
            metadata[key] = _scalar(value)
    return metadata, text[match.end() :]


def _clean(value: str) -> str:
    return re.sub(r"[ \t]+", " ", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _document_id(path: Path, metadata: Mapping[str, Any], declared: str | None) -> str:
    value = declared or metadata.get("document_id")
    return str(value) if value else path.stem


def load_markdown(
    path: str | Path,
    *,
    document_id: str | None = None,
    source_url: str | None = None,
    source_type: str = "markdown",
    retrieved_at: str | None = None,
) -> list[dict[str, Any]]:
    """Load one local Markdown file into splitter-compatible legal chunk mappings."""
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    front, body = parse_front_matter(raw)
    doc_id = _document_id(source, front, document_id)
    url = source_url or front.get("source_url")
    retrieved = retrieved_at or front.get("retrieved_at")
    if not retrieved:
        retrieved = datetime.fromtimestamp(source.stat().st_mtime, UTC).isoformat()
    source_file = source.as_posix()
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    page = PageRecord(doc_id, str(front.get("document_name", source.stem)), 1, body, source_file)
    chunks = split_legal_pages([page])
    if not chunks and _clean(body):
        chunks = [
            LegalChunk(
                digest[:24],
                _clean(body),
                doc_id,
                page.document_name,
                1,
                None,
                None,
                None,
                source_file,
            )
        ]
    result: list[dict[str, Any]] = []
    for chunk in chunks:
        item = asdict(chunk)
        item.update(
            {
                "source_url": url,
                "source_type": source_type,
                "document_id": doc_id,
                "retrieved_at": str(retrieved),
            }
        )
        result.append(item)
    return result


def load_manifest(
    manifest: str | Path = "data/sources/manifest.json", *, local_dir: str | Path
) -> list[dict[str, Any]]:
    """Load only manifest-listed files beneath the explicitly supplied local directory."""
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    entries = data.get("documents", data) if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise ValueError("manifest must contain a documents list")
    root = Path(local_dir).resolve()
    loaded: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("file"):
            raise ValueError("manifest document entries require file")
        candidate = (root / str(entry["file"])).resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError(f"manifest file escapes local directory: {entry['file']}")
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        loaded.extend(
            load_markdown(
                candidate, document_id=entry.get("document_id"), source_url=entry.get("source_url")
            )
        )
    return loaded


def write_jsonl(chunks: Iterable[Mapping[str, Any]], output: str | Path) -> int:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(dict(chunk), ensure_ascii=False, sort_keys=True) + "\n")
            count += 1
    return count


__all__ = ["load_markdown", "load_manifest", "parse_front_matter", "write_jsonl"]
