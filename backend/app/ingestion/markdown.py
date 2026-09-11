"""Canonical deterministic Markdown-to-LangChain document ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)(?:\n---\s*\n|\Z)", re.DOTALL)
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ARTICLE = re.compile(r"^(?:Điều|ĐIỀU)\s+(\d+)(?:\.\s*(.*))?$")
_CLAUSE = re.compile(r"^(\d+)[.)]\s+(.+)$")
_POINT = re.compile(r"^([a-zđ])[.)]\s+(.+)$", re.IGNORECASE)


def _scalar(value: str) -> Any:
    value = value.strip()
    if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    match = _FRONT_MATTER.match(normalized)
    if not match:
        return {}, normalized
    metadata: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if _KEY.fullmatch(key):
            metadata[key] = _scalar(value)
    return metadata, normalized[match.end() :]


def _clean(text: str) -> str:
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n")).strip()


def _document_id(path: Path, metadata: Mapping[str, Any], declared: str | None) -> str:
    return str(declared or metadata.get("document_id") or path.stem)


def _chunks(body: str) -> list[tuple[str, dict[str, Any]]]:
    lines = body.splitlines()
    sections: list[tuple[str, dict[str, Any]]] = []
    article: str | None = None
    clause: str | None = None
    point: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal buffer
        text = _clean("\n".join(buffer))
        if text:
            metadata: dict[str, Any] = {}
            if article is not None:
                metadata["article"] = article
            if clause is not None:
                metadata["clause"] = clause
            if point is not None:
                metadata["point"] = point
            sections.append((text, metadata))
        buffer = []

    for raw_line in lines:
        line = raw_line.strip()
        heading = _HEADING.match(line)
        marker = heading.group(2).strip() if heading else line
        article_match = _ARTICLE.match(marker)
        if article_match:
            flush()
            article, clause, point = article_match.group(1), None, None
            title = article_match.group(2)
            if title:
                buffer.append(title)
            continue
        clause_match = _CLAUSE.match(marker)
        if clause_match and article is not None:
            flush()
            clause, point = clause_match.group(1), None
            buffer.append(clause_match.group(2))
            continue
        point_match = _POINT.match(marker)
        if point_match and article is not None and clause is not None:
            flush()
            point = point_match.group(1).lower()
            buffer.append(point_match.group(2))
            continue
        if heading:
            flush()
            continue
        buffer.append(raw_line)
    flush()
    return sections


def load_markdown(
    path: str | Path,
    *,
    document_id: str | None = None,
    document_number: str | None = None,
    document_name: str | None = None,
    source_url: str | None = None,
    source_type: str | None = None,
    retrieved_at: str | None = None,
) -> list[Document]:
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    front, body = parse_front_matter(raw)
    doc_id = _document_id(source, front, document_id)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    common = {
        "document_id": doc_id,
        "document_name": str(document_name or front.get("document_name") or source.stem),
        "source_file": source.as_posix(),
        "source_url": source_url or front.get("source_url") or "",
        "source_type": source_type or front.get("source_type") or "markdown",
        "retrieved_at": retrieved_at or front.get("retrieved_at") or "",
    }
    if document_number or front.get("document_number"):
        common["document_number"] = str(document_number or front["document_number"])
    result: list[Document] = []
    for number, (text, location) in enumerate(_chunks(body), 1):
        metadata = {
            **common,
            **location,
            "chunk_id": f"{doc_id}:{number:04d}",
            "content_sha256": digest,
        }
        result.append(Document(page_content=text, metadata=metadata))
    if not result and _clean(body):
        result.append(
            Document(
                page_content=_clean(body),
                metadata={**common, "chunk_id": f"{doc_id}:0001", "content_sha256": digest},
            )
        )
    return result


def load_manifest(
    manifest: str | Path = "data/sources/manifest.json",
    *,
    local_dir: str | Path = "data/corpus/mds",
) -> list[Document]:
    payload = json.loads(Path(manifest).read_text(encoding="utf-8"))
    entries = payload.get("documents", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("manifest must contain a documents list")
    root = Path(local_dir).resolve()
    loaded: list[Document] = []
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("file"):
            raise ValueError("manifest document entries require file")
        candidate = (root / str(entry["file"])).resolve()
        if root not in candidate.parents or candidate.suffix.lower() != ".md":
            raise ValueError(
                f"manifest file must be Markdown beneath local directory: {entry['file']}"
            )
        if not candidate.is_file():
            raise FileNotFoundError(candidate)
        loaded.extend(
            load_markdown(
                candidate,
                document_number=entry.get("document_number"),
                document_name=entry.get("document_name"),
                document_id=entry.get("document_id"),
                source_url=entry.get("source_url"),
                source_type=entry.get("source_type"),
            )
        )
    return loaded


def write_jsonl(documents: Iterable[Document], output: str | Path) -> int:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with destination.open("w", encoding="utf-8") as handle:
        for document in documents:
            handle.write(
                json.dumps(
                    {"page_content": document.page_content, "metadata": dict(document.metadata)},
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            count += 1
    return count


__all__ = ["Document", "load_markdown", "load_manifest", "parse_front_matter", "write_jsonl"]
