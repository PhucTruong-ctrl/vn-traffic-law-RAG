# ruff: noqa: E501, E702, UP035, B009
"""Deterministic extraction and resolution of legal relations.

The resolver deliberately emits unresolved candidates instead of guessing.  It
is persistence-agnostic so ingestion and tests can use the same contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

PROVISION_RELATIONS = frozenset({"PARENT_OF", "REFERS_TO", "SIBLING_OF", "PENALTY_COMPANION"})
DOCUMENT_RELATIONS = frozenset(
    {"AMENDS", "REPEALS", "SUPERSEDES", "CORRECTS", "GUIDES", "RELATED_TO"}
)


@dataclass(frozen=True)
class ReferenceCandidate:
    source_provision_id: str
    relation_type: str
    source_text: str
    target_provision_id: str | None = None
    target_version: int | None = None
    resolution_status: str = "UNRESOLVED"
    review_status: str = "PENDING"
    extraction_method: str = "explicit"
    confidence: float | None = None
    reason: str | None = None
    target_document_id: str | None = None


@dataclass(frozen=True)
class DocumentCandidate:
    source_document_id: str
    target_document_id: str | None
    relation_type: str
    source_note: str
    resolution_status: str = "RESOLVED"
    review_status: str = "PENDING"


# Explicit Vietnamese legal wording; no relation is inferred from mere proximity.
_DOC_PATTERNS = {
    "AMENDS": re.compile(
        r"sửa đổi(?:,? bổ sung)?\s+(?:một số\s+)?(?:điều của\s+)?(?P<doc>[^.;,]+)", re.I
    ),
    "REPEALS": re.compile(r"bãi bỏ\s+(?:toàn bộ|một phần)?\s*(?P<doc>[^.;,]+)", re.I),
    "SUPERSEDES": re.compile(r"thay thế\s+(?P<doc>[^.;,]+)", re.I),
    "CORRECTS": re.compile(r"đính chính\s+(?P<doc>[^.;,]+)", re.I),
    "GUIDES": re.compile(r"hướng dẫn\s+(?:thi hành\s+)?(?P<doc>[^.;,]+)", re.I),
    "RELATED_TO": re.compile(r"liên quan đến\s+(?P<doc>[^.;,]+)", re.I),
}
_DOCUMENT = r"(?P<document>(?P<kind>luật|bộ luật|nghị định|thông tư|quyết định|nghị quyết|pháp lệnh)\s+(?:số\s+)?(?P<number>\d+)(?:/(?P<year>\d{4}))?(?:/(?P<suffix>[a-zđ-]+[a-zđ0-9-]*))?)"
_CITATION = re.compile(
    rf"(?:(?:điểm\s+(?P<point>[a-zđ]))\s+)?"
    rf"(?:(?:khoản|mục)\s+(?P<clause>\d+))?\s*điều\s+(?P<article>\d+)"
    rf"(?:\s+{_DOCUMENT})?",
    re.I,
)

_DOCUMENT_SLUG_PREFIX = {
    "luật": "luat",
    "bộ luật": "luat",
    "nghị định": "nd",
    "thông tư": "tt",
    "quyết định": "qd",
    "nghị quyết": "nq",
    "pháp lệnh": "pl",
}


def _target_document_id(match: re.Match[str]) -> str | None:
    if match.group("document") is None:
        return None
    kind = " ".join(match.group("kind").split()).casefold()
    slug = _DOCUMENT_SLUG_PREFIX[kind]
    number = match.group("number")
    year = match.group("year")
    suffix = match.group("suffix")
    normalized_suffix = suffix.casefold() if suffix else None
    # NĐ-CP and issuer-qualified authority suffixes identify the issuing
    # authority, not a distinct canonical document.
    authority_prefix = {
        "luat": "luat",
        "nd": "nd",
        "tt": "tt",
        "qd": "qd",
        "nq": "nq",
        "pl": "pl",
    }[slug]
    if (
        normalized_suffix == "nđ-cp"
        or normalized_suffix
        and re.fullmatch(
            rf"{re.escape(authority_prefix)}-[a-zđ0-9]+(?:-[a-zđ0-9]+)*",
            normalized_suffix,
        )
    ):
        normalized_suffix = None
    return (
        f"{slug}-{number}"
        + (f"-{year}" if year else "")
        + (f"-{normalized_suffix}" if normalized_suffix else "")
    )


def _field(row: object, key: str, default: object = None) -> object:
    return row.get(key, default) if isinstance(row, Mapping) else getattr(row, key, default)


def _contains(interval_start: object, interval_end: object, point: object) -> bool:
    if point is None:
        return False
    try:
        return (interval_start is None or interval_start <= point) and (
            interval_end is None or point < interval_end
        )
    except TypeError:
        return False


def extract_provision_references(
    text: str, source_id: str, *, relation_type: str = "REFERS_TO"
) -> list[ReferenceCandidate]:
    """Extract explicit citations, retaining any named target document."""
    if relation_type not in PROVISION_RELATIONS:
        raise ValueError(f"invalid provision relation: {relation_type}")
    out = []
    for m in _CITATION.finditer(text):
        key = "/".join(x for x in (m.group("article"), m.group("clause"), m.group("point")) if x)
        out.append(
            ReferenceCandidate(
                source_id,
                relation_type,
                m.group(0),
                target_provision_id=key,
                target_document_id=_target_document_id(m),
            )
        )
    return out


def resolve_candidate(
    candidate: ReferenceCandidate,
    provisions: Iterable[object],
    *,
    source_version: int | None = None,
) -> ReferenceCandidate:
    """Bind a citation to one canonical provision, including JSON mappings."""
    rows_all = list(provisions)

    def matches(row: object) -> bool:
        pid = str(_field(row, "provision_id", ""))
        if candidate.target_document_id and not (
            pid == candidate.target_document_id
            or pid.startswith(f"{candidate.target_document_id}__")
        ):
            return False
        target = candidate.target_provision_id or ""
        parts = target.split("/")
        hierarchy = [f"dieu-{parts[0]}"]
        if len(parts) > 1:
            hierarchy.append(f"khoan-{parts[1]}")
        if len(parts) > 2:
            hierarchy.append(f"diem-{parts[2]}")
        if pid == target:
            return True
        return len(pid.split("__")) > 1 and pid.split("__")[1:] == hierarchy

    rows = [p for p in rows_all if matches(p)]
    if candidate.target_document_id is None and source_version is not None:
        rows = [p for p in rows if _field(p, "version") == source_version]
    elif candidate.target_document_id:
        source = next(
            (p for p in rows_all if _field(p, "provision_id") == candidate.source_provision_id),
            None,
        )
        source_start = _field(source, "effective_from")
        applicable = [
            p
            for p in rows
            if _contains(_field(p, "effective_from"), _field(p, "effective_to"), source_start)
        ]
        if applicable:
            rows = applicable
        elif source_version is not None and len(rows) > 1:
            rows = [p for p in rows if _field(p, "version") == source_version]

    if len(rows) != 1:
        reason = "AMBIGUOUS_REFERENCE" if len(rows) > 1 else "TARGET_NOT_FOUND"
        return ReferenceCandidate(
            **{**candidate.__dict__, "resolution_status": "PENDING_REVIEW", "reason": reason}
        )
    row = rows[0]
    resolution_status = (
        "PENDING_REVIEW" if candidate.relation_type == "PENALTY_COMPANION" else "RESOLVED"
    )
    return ReferenceCandidate(
        **{
            **candidate.__dict__,
            "target_provision_id": str(
                _field(row, "id", _field(row, "provision_id", candidate.target_provision_id))
            ),
            "target_version": _field(row, "version"),
            "resolution_status": resolution_status,
        }
    )


def review_item_for(
    candidate: ReferenceCandidate, *, document_id: str, ingestion_run_id: str
) -> dict[str, object]:
    """Return fields matching ReviewItem for unresolved/ambiguous candidates."""
    return {
        "ingestion_run_id": ingestion_run_id,
        "document_id": document_id,
        "target_type": "PROVISION_REFERENCE",
        "target_id": candidate.source_provision_id,
        "reason_code": candidate.reason or "UNRESOLVED_REFERENCE",
        "description": candidate.source_text,
        "evidence": {"relation_type": candidate.relation_type},
    }


_PENALTY = re.compile(
    rf"(?:mức phạt|hình phạt|phạt tiền)[^.;]*(?:quy định tại|theo)\s+"
    rf"(?P<citation>(?:điểm\s+[a-zđ]\s+)?(?:khoản\s+\d+\s+)?điều\s+\d+(?:\s+{_DOCUMENT})?)",
    re.I,
)


def infer_penalty_companions(text: str, source_id: str) -> list[ReferenceCandidate]:
    """Infer companions only from an explicit penalty-to-provision citation."""
    out = []
    for m in _PENALTY.finditer(text):
        citation = _CITATION.search(m.group("citation"))
        if citation:
            target = "/".join(
                value
                for value in (
                    citation.group("article"),
                    citation.group("clause"),
                    citation.group("point"),
                )
                if value
            )
            out.append(
                ReferenceCandidate(
                    source_id,
                    "PENALTY_COMPANION",
                    m.group(0),
                    target_provision_id=target,
                    target_document_id=_target_document_id(citation),
                    extraction_method="explicit_penalty",
                )
            )
    return out


def resolve_references(
    text: str, source_id: str, provisions: Iterable[object], *, source_version: int | None = None
) -> list[ReferenceCandidate]:
    candidates = extract_provision_references(text, source_id)
    candidates.extend(infer_penalty_companions(text, source_id))
    return [resolve_candidate(c, provisions, source_version=source_version) for c in candidates]


def extract_document_relations(
    text: str, source_document_id: str, known_documents: Mapping[str, str]
) -> list[DocumentCandidate]:
    out = []
    for relation, pattern in _DOC_PATTERNS.items():
        for m in pattern.finditer(text):
            note = m.group("doc").strip()
            matches = [
                doc_id for key, doc_id in known_documents.items() if key.lower() in note.lower()
            ]
            target = matches[0] if len(matches) == 1 else None
            out.append(
                DocumentCandidate(
                    source_document_id,
                    target,
                    relation,
                    note,
                    "RESOLVED" if target else "PENDING_REVIEW",
                )
            )
    return out


_MANIFEST_RELATION = re.compile(
    r"\b(?P<relation>AMENDS|REPEALS|SUPERSEDES|CORRECTS|GUIDES|RELATED_TO)\b"
    r"(?:\s+(?:với|with|to|document))?\s+(?P<document>[a-z0-9-]+)",
    re.I,
)


def extract_manifest_relations(
    relation_notes: object,
    source_document_id: str,
    known_documents: Mapping[str, str],
) -> list[DocumentCandidate]:
    """Read reviewer-authored relation edges from manifest notes."""
    if not isinstance(relation_notes, str):
        return []
    out = []
    for match in _MANIFEST_RELATION.finditer(relation_notes):
        relation = match.group("relation").upper()
        token = match.group("document").casefold()
        target = next(
            (doc_id for key, doc_id in known_documents.items() if key.casefold() == token),
            None,
        )
        out.append(
            DocumentCandidate(
                source_document_id,
                target,
                relation,
                match.group(0),
                "RESOLVED" if target else "PENDING_REVIEW",
            )
        )
    return out


def infer_parent_relations(provisions: Iterable[object]) -> list[ReferenceCandidate]:
    """Derive parent and sibling edges from explicit provision hierarchy fields."""
    rows = list(provisions)
    out: list[ReferenceCandidate] = []
    by_level: dict[tuple[object, ...], list[object]] = {}
    clauses_by_key: dict[tuple[object, ...], list[object]] = {}

    def field(row: object, name: str) -> object:
        return row.get(name) if isinstance(row, Mapping) else getattr(row, name, None)

    def version(row: object) -> int | None:
        value = field(row, "version")
        return value if isinstance(value, int) else None

    def key(row: object) -> tuple[object, ...] | None:
        document = field(row, "document_version_id")
        kind = field(row, "node_kind")
        article = field(row, "article")
        clause = field(row, "clause")
        point = field(row, "point")
        if kind == "ARTICLE" and article is not None:
            return (document, "ARTICLE", article)
        if kind == "CLAUSE" and article is not None and clause is not None:
            return (document, "CLAUSE", article)
        if kind == "POINT" and article is not None and clause is not None and point is not None:
            return (document, "POINT", article, clause)
        return None

    for row in rows:
        row_key = key(row)
        if row_key is not None:
            by_level.setdefault(row_key, []).append(row)
        if field(row, "node_kind") == "CLAUSE":
            document = field(row, "document_version_id")
            article = field(row, "article")
            clause = field(row, "clause")
            if article is not None and clause is not None:
                clauses_by_key.setdefault((document, article, clause), []).append(row)

    for _row_key, siblings in by_level.items():
        for index, source in enumerate(siblings):
            source_id = str(field(source, "provision_id"))
            for target in siblings[index + 1 :]:
                out.append(
                    ReferenceCandidate(
                        source_id,
                        "SIBLING_OF",
                        "hierarchy",
                        str(field(target, "provision_id")),
                        version(target),
                        "RESOLVED",
                        extraction_method="hierarchy",
                    )
                )

    for child in rows:
        kind = field(child, "node_kind")
        document = field(child, "document_version_id")
        article = field(child, "article")
        clause = field(child, "clause")
        parent_key = (
            (document, article, clause)
            if kind == "POINT" and clause is not None
            else (document, "ARTICLE", article)
            if kind == "CLAUSE"
            else None
        )
        if parent_key is None:
            continue
        parent = (
            next(iter(clauses_by_key.get((document, article, clause), [])), None)
            if kind == "POINT"
            else next(iter(by_level.get(parent_key, [])), None)
        )
        if parent is not None:
            out.append(
                ReferenceCandidate(
                    str(field(parent, "provision_id")),
                    "PARENT_OF",
                    "hierarchy",
                    str(field(child, "provision_id")),
                    version(child),
                    "RESOLVED",
                    extraction_method="hierarchy",
                )
            )
    return out
