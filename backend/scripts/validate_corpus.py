"""Validate parsed corpus coverage and structural metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from app.ingestion.markdown import _ARTICLE, _CLAUSE, _POINT
except ImportError:
    _ARTICLE = re.compile(r"^(?:Điều|ĐIỀU)\s+(\d+)(?:\.\s*(.*))?$")
    _CLAUSE = re.compile(r"^(\d+)[.)]\s+(.+)$")
    _POINT = re.compile(r"^([a-zđ])[.)]\s+(.+)$", re.IGNORECASE)


def _number(value: Any, prefix: str) -> str | None:
    text = str(value or "").strip()
    match = re.search(rf"{prefix}\s*(\d+)", text, re.IGNORECASE)
    if match:
        return match.group(1)
    return text if text.isdigit() else None


def coordinate(metadata: dict[str, Any]) -> str | None:
    """Return the local canonical coordinate for a chunk."""
    document = str(metadata.get("document_id") or "").strip()
    article = _number(metadata.get("article"), "Điều")
    clause = _number(metadata.get("clause"), "Khoản")
    point = str(metadata.get("point") or "").strip()
    point_match = re.search(r"(?:Điểm\s*)?([a-zđ])", point, re.IGNORECASE)
    if not document or article is None:
        return None
    result = f"{document}__dieu-{article}"
    if clause is not None:
        result += f"__khoan-{clause}"
        if point_match:
            result += f"__diem-{point_match.group(1).lower()}"
    return result


def _marker_sets(corpus: Path) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {
            "articles": set(),
            "clauses": set(),
            "points": set(),
            "coordinates": {"articles": set(), "clauses": set(), "points": set()},
        }
    )
    for path in sorted(corpus.glob("*.md")):
        document = path.stem
        article = clause = None
        for raw in path.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines():
            line = raw.strip()
            am = _ARTICLE.match(line)
            cm = _CLAUSE.match(line)
            pm = _POINT.match(line)
            if am:
                article, clause = am.group(1), None
                found[document]["articles"].add(article)
                found[document]["coordinates"]["articles"].add(f"{document}__dieu-{article}")
            elif cm and article:
                clause = cm.group(1)
                found[document]["clauses"].add(f"{article}/{clause}")
                found[document]["coordinates"]["clauses"].add(
                    f"{document}__dieu-{article}__khoan-{clause}"
                )
            elif pm and article and clause:
                point = pm.group(1).lower()
                found[document]["points"].add(f"{article}/{clause}/{point}")
                found[document]["coordinates"]["points"].add(
                    f"{document}__dieu-{article}__khoan-{clause}__diem-{point}"
                )
    return {
        doc: {
            key: (
                sorted(value) if key != "coordinates" else {k: sorted(v) for k, v in value.items()}
            )
            for key, value in groups.items()
        }
        for doc, groups in sorted(found.items())
    }


def validate(chunks_path: Path, corpus: Path, *, stats_only: bool = False) -> dict[str, Any]:
    chunks: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    by_id: dict[str, list[int]] = defaultdict(list)
    by_doc_article: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    files_seen: set[str] = set()
    for line_no, line in enumerate(chunks_path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            anomalies.append({"kind": "invalid_json", "line": line_no, "evidence": str(exc)})
            continue
        metadata = item.get("metadata") if isinstance(item, dict) else None
        metadata = metadata if isinstance(metadata, dict) else {}
        content = item.get("page_content", "") if isinstance(item, dict) else ""
        chunk_id = str(metadata.get("chunk_id") or f"line:{line_no}")
        document = str(metadata.get("document_id") or "").strip()
        article = str(metadata.get("article") or "").strip()
        clause = str(metadata.get("clause") or "").strip()
        point = str(metadata.get("point") or "").strip()
        source = str(metadata.get("source_file") or "")
        files_seen.add(Path(source).stem if source else "")
        row = {"line": line_no, "chunk_id": chunk_id, "file": source}
        chunks.append({"metadata": metadata, "page_content": content, "line": line_no})
        by_id[chunk_id].append(line_no)
        if not document:
            anomalies.append({"kind": "missing_document_id", **row})
        if not article:
            anomalies.append({"kind": "missing_article", **row})
        if not str(content).strip():
            anomalies.append({"kind": "empty_page_content", **row})
        if clause and not article:
            anomalies.append({"kind": "clause_without_article", **row})
        if point and not clause:
            anomalies.append({"kind": "point_without_clause", **row})
        if document and article:
            by_doc_article[(document, article)][str(content)] += 1
    for chunk_id, lines in sorted(by_id.items()):
        if len(lines) > 1:
            anomalies.append({"kind": "duplicate_chunk_id", "chunk_id": chunk_id, "lines": lines})
    for (document, article), contents in sorted(by_doc_article.items()):
        for content, count in contents.items():
            if count > 1:
                anomalies.append(
                    {
                        "kind": "duplicate_page_content",
                        "document_id": document,
                        "article": article,
                        "count": count,
                        "page_content": content[:120],
                    }
                )

    stats: dict[str, dict[str, Any]] = {}
    doc_chunks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for chunk in chunks:
        doc = str(chunk["metadata"].get("document_id") or "<missing>")
        doc_chunks[doc].append(chunk)
    for doc, rows in sorted(doc_chunks.items()):
        stats[doc] = {
            "chunks": len(rows),
            "articles": sorted(
                {str(r["metadata"].get("article")) for r in rows if r["metadata"].get("article")}
            ),
            "clauses": sorted(
                {str(r["metadata"].get("clause")) for r in rows if r["metadata"].get("clause")}
            ),
            "points": sorted(
                {str(r["metadata"].get("point")) for r in rows if r["metadata"].get("point")}
            ),
        }
    totals = {
        "chunks": len(chunks),
        "documents": len(stats),
        "articles": sum(len(v["articles"]) for v in stats.values()),
        "clauses": sum(len(v["clauses"]) for v in stats.values()),
        "points": sum(len(v["points"]) for v in stats.values()),
    }
    marker_data = _marker_sets(corpus) if not stats_only else {}
    parser_gaps: list[str] = []
    index_coordinates = {"articles": set(), "clauses": set(), "points": set()}
    for chunk in chunks:
        metadata = chunk["metadata"]
        doc = str(metadata.get("document_id") or "")
        article = _number(metadata.get("article"), "Điều")
        clause = _number(metadata.get("clause"), "Khoản")
        point = str(metadata.get("point") or "").strip()
        pm = re.search(r"(?:Điểm\s*)?([a-zđ])", point, re.IGNORECASE)
        if doc and article:
            index_coordinates["articles"].add(f"{doc}__dieu-{article}")
            if clause:
                index_coordinates["clauses"].add(f"{doc}__dieu-{article}__khoan-{clause}")
                if pm:
                    index_coordinates["points"].add(
                        f"{doc}__dieu-{article}__khoan-{clause}__diem-{pm.group(1).lower()}"
                    )
    if not stats_only:
        for _doc, groups in marker_data.items():
            for kind in ("articles", "clauses", "points"):
                for marker in groups["coordinates"][kind]:
                    if marker not in index_coordinates[kind]:
                        parser_gaps.append(marker)
                        anomalies.append({"kind": "parser_gap", "coordinate": marker})
    corpus_docs = set(marker_data)
    chunk_docs = {doc for doc in doc_chunks if doc != "<missing>"}
    if not stats_only:
        for doc in sorted(corpus_docs - chunk_docs):
            anomalies.append({"kind": "document_missing_from_chunks", "document_id": doc})
        for doc in sorted(chunk_docs - corpus_docs):
            anomalies.append({"kind": "document_missing_from_corpus", "document_id": doc})
    return {
        "stats": stats,
        "totals": totals,
        "anomalies": anomalies,
        "anomaly_counts": dict(sorted(Counter(a["kind"] for a in anomalies).items())),
        "markdown_markers": marker_data,
        "index_coordinates": {k: sorted(v) for k, v in index_coordinates.items()},
        "parser_gaps": sorted(parser_gaps),
    }


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, default=root / "data/processed/chunks.jsonl")
    parser.add_argument("--corpus", type=Path, default=root / "data/corpus/mds")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--fail-on-anomaly", action="store_true")
    parser.add_argument("--stats-only", action="store_true")
    args = parser.parse_args()
    report = validate(args.chunks, args.corpus, stats_only=args.stats_only)
    print("Corpus validation")
    print("Totals:", report["totals"])
    print("Anomaly counts:", report["anomaly_counts"])
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 1 if args.fail_on_anomaly and report["anomalies"] else 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
