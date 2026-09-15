"""Canonical deterministic Markdown-to-LangChain document ingestion."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from .source import normalize_source_kind

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)(?:\n---\s*\n|\Z)", re.DOTALL)
_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_ARTICLE = re.compile(r"^(?:Điều|ĐIỀU)\s+(\d+)(?:\.\s*(.*))?$")
_CLAUSE = re.compile(r"^(\d+)[.)]\s+(.+)$")
_POINT = re.compile(r"^([a-zđ])[.)]\s+(.+)$", re.IGNORECASE)
_HEADING_METADATA: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("ô tô", ("car",), ("road",)),
    ("xe ô tô", ("car",), ("road",)),
    ("xe mô tô", ("motorcycle",), ("road",)),
    ("xe máy", ("motorcycle",), ("road",)),
    ("xe gắn máy", ("motorcycle",), ("road",)),
    ("xe đạp", ("bicycle",), ("road",)),
    ("xe thô sơ", ("bicycle",), ("road",)),
    ("xe chuyên dùng", ("specialized",), ("road",)),
    ("đường bộ", (), ("road",)),
    ("đường sắt", (), ("rail",)),
)


def _heading_metadata(text: str) -> dict[str, list[str]]:
    lowered = text.casefold()
    categories: list[str] = []
    scopes: list[str] = []
    for phrase, phrase_categories, phrase_scopes in _HEADING_METADATA:
        if phrase in lowered:
            categories.extend(item for item in phrase_categories if item not in categories)
            scopes.extend(item for item in phrase_scopes if item not in scopes)
    return {"vehicle_categories": categories, "context_scope": scopes}


_VEHICLE_CATEGORIES = {
    "car": re.compile(r"\b(?:ô tô|xe ô tô)\b", re.IGNORECASE),
    "motorcycle": re.compile(r"\b(?:mô tô|xe máy|xe gắn máy)\b", re.IGNORECASE),
    "bicycle": re.compile(r"\b(?:xe đạp|xe thô sơ)\b", re.IGNORECASE),
    "specialized": re.compile(r"\b(?:máy kéo|xe máy chuyên dùng)\b", re.IGNORECASE),
}
_CONTEXT_SCOPES = {
    "driver_testing": re.compile(
        r"\b(?:sát hạch|đào tạo lái xe|cấp giấy phép lái xe)\b", re.IGNORECASE
    ),
    "railway_crossing": re.compile(
        r"\b(?:đường ngang|cầu chung|đường sắt|rào chắn)\b", re.IGNORECASE
    ),
    "expressway": re.compile(r"\b(?:đường cao tốc|cao tốc)\b", re.IGNORECASE),
    "road_traffic": re.compile(
        r"\b(?:giao thông đường bộ|an toàn giao thông đường bộ|trên đường bộ)\b",
        re.IGNORECASE,
    ),
}


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
    article_heading: str | None = None
    clause: str | None = None
    point: str | None = None
    provision_text: str | None = None
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
            if article_heading:
                metadata["article_heading"] = article_heading
                metadata.update(_heading_metadata(article_heading))
                metadata["vehicle_categories"] = [
                    category
                    for category, pattern in _VEHICLE_CATEGORIES.items()
                    if pattern.search(article_heading)
                ]
                metadata["context_scope"] = [
                    scope
                    for scope, pattern in _CONTEXT_SCOPES.items()
                    if pattern.search(article_heading)
                ]
            if article is not None:
                family = f"article:{article}"
                if clause is not None:
                    family += f":clause:{clause}"
                metadata["provision_family"] = family
            if clause is not None or point is not None:
                metadata["normalized_action"] = text
            sections.append((text, metadata))
        buffer = []

    index = 0
    while index < len(lines):
        raw_line = lines[index]
        line = raw_line.strip()
        heading = _HEADING.match(line)
        marker = heading.group(2).strip() if heading else line

        # OCR sometimes puts a legal marker's punctuation on the next line.
        # Consume only an unambiguous marker fragment; all provision text is
        # still appended from its original source lines below.
        marker_lines = 1
        if index + 1 < len(lines):
            next_line = lines[index + 1].strip()
            if (
                re.fullmatch(r"\d+", marker) or re.fullmatch(r"[a-zđ]", marker, re.IGNORECASE)
            ) and next_line in {".", ")"}:
                marker = f"{marker}{next_line}"
                marker_lines = 2
            elif re.fullmatch(r"(?:Điều|ĐIỀU)", marker) and re.fullmatch(r"\d+[.)]?", next_line):
                marker = f"{marker} {next_line}"
                marker_lines = 2
        if marker_lines == 1 and index + 2 < len(lines):
            next_line = lines[index + 1].strip()
            following_line = lines[index + 2].strip()
            if (
                (re.fullmatch(r"\d+", marker) or re.fullmatch(r"[a-zđ]", marker, re.IGNORECASE))
                and next_line in {".", ")"}
                and following_line
            ):
                marker = f"{marker}{next_line} {following_line}"
                marker_lines = 3

        article_match = _ARTICLE.match(marker)
        if article_match:
            flush()
            article, clause, point = article_match.group(1), None, None
            article_heading = _clean(article_match.group(2) or "")
            provision_text = None
            if article_match.group(2):
                buffer.append(article_match.group(2))
            index += marker_lines
            continue
        clause_match = _CLAUSE.match(marker)
        if clause_match and article is not None:
            flush()
            clause, point = clause_match.group(1), None
            provision_text = clause_match.group(2)
            buffer.append(provision_text)
            index += marker_lines
            continue
        point_match = _POINT.match(marker)
        if point_match and article is not None and clause is not None:
            flush()
            point = point_match.group(1).lower()
            provision_text = point_match.group(2)
            buffer.append(provision_text)
            index += marker_lines
            continue
        if heading:
            flush()
            index += 1
            continue
        buffer.append(raw_line)
        index += 1
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
    source_kind: str | None = None,
    retrieved_at: str | None = None,
    effective_from: str | None = None,
    effective_to: str | None = None,
    status: str | None = None,
) -> list[Document]:
    source = Path(path)
    raw = source.read_text(encoding="utf-8")
    front, body = parse_front_matter(raw)
    doc_id = _document_id(source, front, document_id)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    effective_type = source_type or front.get("source_type") or "markdown"
    common = {
        "document_id": doc_id,
        "document_name": str(document_name or front.get("document_name") or source.stem),
        "source_file": source.as_posix(),
        "source_url": source_url or front.get("source_url") or "",
        "source_type": effective_type,
        "source_kind": normalize_source_kind(
            source_file=source,
            source_kind=source_kind or front.get("source_kind"),
            source_type=effective_type,
        ),
        "retrieved_at": retrieved_at or front.get("retrieved_at") or "",
    }
    if document_number or front.get("document_number"):
        common["document_number"] = str(document_number or front["document_number"])
    effective_status = str(status or front.get("status") or "")
    if effective_status:
        common["status"] = effective_status
    start = effective_from or front.get("effective_from")
    end = effective_to if effective_to is not None else front.get("effective_to")
    if start and effective_status != "PARTIALLY_EFFECTIVE":
        common["effective_from"] = str(start)
    if end and effective_status != "PARTIALLY_EFFECTIVE":
        common["effective_to"] = str(end)
    result: list[Document] = []
    for number, (text, location) in enumerate(_chunks(body), 1):
        location = dict(location)
        if "article" in location:
            family = f"{doc_id}:article:{location['article']}"
            if "clause" in location:
                family += f":clause:{location['clause']}"
            location["provision_family"] = family
        metadata = {
            **common,
            **location,
            "provision_family": location.get("provision_family", "document"),
            "chunk_id": f"{doc_id}:{number:04d}",
            "content_sha256": digest,
        }
        result.append(Document(page_content=text, metadata=metadata))
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
                document_id=entry.get("document_id"),
                document_number=entry.get("document_number"),
                document_name=entry.get("document_name"),
                source_url=entry.get("source_url"),
                source_type=entry.get("source_type"),
                source_kind=entry.get("source_kind"),
                retrieved_at=entry.get("retrieved_at"),
                effective_from=entry.get("effective_from"),
                effective_to=entry.get("effective_to"),
                status=entry.get("status"),
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


__all__ = ["load_markdown", "load_manifest", "parse_front_matter", "write_jsonl"]
