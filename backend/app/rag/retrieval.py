"""Dependency-light persistent lexical retrieval for rescue deployments."""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_REFERENCE_RE = re.compile(
    r"(?:(?:khoản\s+(?P<clause>\d+)\s+)?điều\s+(?P<article>\d+)"
    r"(?:\s+(?:của\s+)?(?P<kind>nghị\s+định|thông\s+tư)\s*(?:số\s+)?"
    r"(?P<number>\d+(?:/\d{4})?(?:/[a-zđ0-9-]+)?))?)",
    re.IGNORECASE,
)


def _tokens(value: object) -> list[str]:
    text = unicodedata.normalize("NFC", str(value or "")).casefold()
    return _TOKEN_RE.findall(text)


def _text(chunk: Mapping[str, Any]) -> str:
    return " ".join(
        str(chunk.get(key, ""))
        for key in ("text", "content", "retrieval_text", "source_text", "heading")
    )


def _norm_doc(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def _metadata_matches(chunk: Mapping[str, Any], filters: Mapping[str, object] | None) -> bool:
    if not filters:
        return True
    metadata = chunk.get("metadata")
    values = metadata if isinstance(metadata, Mapping) else chunk
    for key, expected in filters.items():
        actual = values.get(key)
        if isinstance(expected, (list, tuple, set, frozenset)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


class Retriever:
    """Persistent local index with deterministic BM25-like lexical ranking."""

    def __init__(
        self,
        chunks_path: str | os.PathLike[str] | None = None,
        index_path: str | os.PathLike[str] | None = None,
    ) -> None:
        chunks_path_value: str | os.PathLike[str] = chunks_path or os.getenv(
            "RESCUE_CHUNKS", "data/processed/chunks.jsonl"
        )
        index_path_value: str | os.PathLike[str] = index_path or os.getenv(
            "RESCUE_INDEX_PATH", "data/processed/index"
        )
        self.chunks_path = Path(chunks_path_value)
        self.index_path = Path(index_path_value)
        self._chunks: list[dict[str, Any]] = []
        self._tf: list[Counter[str]] = []
        self._df: Counter[str] = Counter()
        self._avgdl = 0.0
        self._load()

    def _load(self) -> None:
        index_file = self.index_path / "chunks.json"
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            data = None
        if not isinstance(data, list):
            if not self.chunks_path.exists():
                return
            data = []
            with self.chunks_path.open(encoding="utf-8") as handle:
                for line in handle:
                    if line.strip():
                        data.append(json.loads(line))
        self._chunks = [dict(item) for item in data if isinstance(item, Mapping)]
        self._tf = [Counter(_tokens(_text(chunk))) for chunk in self._chunks]
        for tf in self._tf:
            self._df.update(tf.keys())
        self._avgdl = sum(sum(tf.values()) for tf in self._tf) / len(self._tf) if self._tf else 0.0

    def search(
        self,
        question: str,
        k: int = 8,
        metadata: Mapping[str, object] | None = None,
        filters: Mapping[str, object] | None = None,
    ) -> list[dict[str, Any]]:
        """Return up to ``k`` matching chunks; metadata/filters are exact field filters."""
        if k <= 0:
            return []
        query_tokens = _tokens(question)
        query = Counter(query_tokens)
        reference = _REFERENCE_RE.search(question)
        ref_article = reference.group("article") if reference else None
        ref_clause = reference.group("clause") if reference else None
        ref_doc = (
            _norm_doc(reference.group("number"))
            if reference and reference.group("number")
            else None
        )
        wanted = metadata or filters
        scored: list[tuple[float, str, int, dict[str, Any]]] = []
        n = len(self._chunks)
        for pos, (chunk, tf) in enumerate(zip(self._chunks, self._tf, strict=True)):
            if not _metadata_matches(chunk, wanted):
                continue
            score = 0.0
            dl = sum(tf.values()) or 1
            for token in query:
                if token not in tf:
                    continue
                idf = math.log(1.0 + (n - self._df[token] + 0.5) / (self._df[token] + 0.5))
                score += idf * (
                    tf[token] * 2.2 / (tf[token] + 1.2 * (0.25 + 0.75 * dl / (self._avgdl or dl)))
                )
            if reference:
                metadata_values = chunk.get("metadata")
                article_value = (
                    metadata_values.get("article")
                    if isinstance(metadata_values, Mapping)
                    else chunk.get("article")
                )
                blob = (
                    " ".join(
                        str(chunk.get(key, ""))
                        for key in (
                            "article",
                            "parent_context",
                            "text",
                            "content",
                            "retrieval_text",
                            "source_text",
                            "document_number",
                        )
                    )
                    + f" {article_value or ''}"
                )
                article_match = re.search(r"(?:điều\s+)?(\d+)", str(article_value or ""), re.I)
                article_ok = bool(
                    ref_article
                    and (
                        article_match
                        and article_match.group(1) == ref_article
                        or re.search(rf"điều\s*{re.escape(ref_article)}\b", blob, re.I)
                    )
                )
                doc_value = (
                    chunk.get("document_number")
                    or (chunk.get("metadata") or {}).get("document_number")
                    if isinstance(chunk.get("metadata"), Mapping)
                    else chunk.get("document_number")
                )
                doc_ok = bool(ref_doc and _norm_doc(doc_value) == ref_doc) or bool(
                    ref_doc and _norm_doc(blob).find(ref_doc) >= 0
                )
                if article_ok:
                    score += 100.0
                    if ref_clause and re.search(
                        rf"(?:khoản\s*){re.escape(ref_clause)}\b", blob, re.I
                    ):
                        score += 20.0
                if doc_ok:
                    score += 50.0
            if score > 0:
                chunk_id = str(chunk.get("chunk_id", chunk.get("id", pos)))
                scored.append((score, chunk_id, pos, chunk))
        scored.sort(key=lambda item: (-item[0], item[1], item[2]))
        return [item[3] for item in scored[:k]]

    def persist(self, chunks: Iterable[Mapping[str, Any]]) -> int:
        """Write chunks and rebuild the local index."""
        records = [dict(chunk) for chunk in chunks]
        self.index_path.mkdir(parents=True, exist_ok=True)
        (self.index_path / "chunks.json").write_text(
            json.dumps(records, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        self._chunks = records
        self._tf = [Counter(_tokens(_text(chunk))) for chunk in records]
        self._df = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        self._avgdl = sum(sum(tf.values()) for tf in self._tf) / len(self._tf) if self._tf else 0.0
        return len(records)

    def build(self, chunks: Iterable[Mapping[str, Any]] | None = None) -> int:
        """Load JSONL chunks and rebuild the in-memory index.

        When ``chunks`` is omitted, the configured JSONL source is used.  The
        method intentionally does not write the source file; ``persist`` is
        available when callers need a durable derived index.
        """
        if chunks is None:
            if not self.chunks_path.exists():
                self._chunks = []
            else:
                chunks = (
                    json.loads(line)
                    for line in self.chunks_path.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
        records = [dict(chunk) for chunk in chunks or ()]
        self._chunks = records
        self._tf = [Counter(_tokens(_text(chunk))) for chunk in records]
        self._df = Counter()
        for tf in self._tf:
            self._df.update(tf.keys())
        self._avgdl = sum(sum(tf.values()) for tf in self._tf) / len(self._tf) if self._tf else 0.0
        return len(records)

    def save(self) -> int:
        """Persist the currently loaded chunks as the derived local index."""
        return self.persist(self._chunks)


__all__ = ["Retriever"]
