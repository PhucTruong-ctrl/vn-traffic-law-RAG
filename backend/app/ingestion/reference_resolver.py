"""Deterministic extraction and resolution of legal relations.

The resolver deliberately emits unresolved candidates instead of guessing.  It
is persistence-agnostic so ingestion and tests can use the same contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping

PROVISION_RELATIONS = frozenset({"PARENT_OF", "REFERS_TO", "SIBLING_OF", "PENALTY_COMPANION"})
DOCUMENT_RELATIONS = frozenset({"AMENDS", "REPEALS", "SUPERSEDES", "CORRECTS", "GUIDES", "RELATED_TO"})

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
 "AMENDS": re.compile(r"sửa đổi(?:,? bổ sung)?\s+(?:một số\s+)?(?:điều của\s+)?(?P<doc>[^.;,]+)", re.I),
 "REPEALS": re.compile(r"bãi bỏ\s+(?:toàn bộ|một phần)?\s*(?P<doc>[^.;,]+)", re.I),
 "SUPERSEDES": re.compile(r"thay thế\s+(?P<doc>[^.;,]+)", re.I),
 "CORRECTS": re.compile(r"đính chính\s+(?P<doc>[^.;,]+)", re.I),
 "GUIDES": re.compile(r"hướng dẫn\s+(?:thi hành\s+)?(?P<doc>[^.;,]+)", re.I),
 "RELATED_TO": re.compile(r"liên quan đến\s+(?P<doc>[^.;,]+)", re.I),
}
_CITATION = re.compile(r"(?:(?:điểm\s+(?P<point>[a-zđ]))\s+)?(?:(?:khoản|mục)\s+(?P<clause>\d+))?\s*điều\s+(?P<article>\d+)", re.I)

def extract_provision_references(text: str, source_id: str, *, relation_type: str = "REFERS_TO") -> list[ReferenceCandidate]:
    """Extract only explicit citations, normalized to ``article/clause/point`` keys."""
    if relation_type not in PROVISION_RELATIONS:
        raise ValueError(f"invalid provision relation: {relation_type}")
    out = []
    for m in _CITATION.finditer(text):
        key = "/".join(x for x in (m.group("article"), m.group("clause"), m.group("point")) if x)
        out.append(ReferenceCandidate(source_id, relation_type, m.group(0), target_provision_id=key))
    return out

def resolve_candidate(candidate: ReferenceCandidate, provisions: Iterable[object], *, source_version: int | None = None) -> ReferenceCandidate:
    """Bind a candidate to exactly one provision in the source version.

    Provision objects may be ORM rows or simple objects exposing provision_id,
    version, and id. Ambiguous or absent matches remain unresolved and require review.
    """
    rows = [p for p in provisions if getattr(p, "provision_id", None) == candidate.target_provision_id]
    if source_version is not None:
        rows = [p for p in rows if getattr(p, "version", None) == source_version]
    if len(rows) != 1:
        return ReferenceCandidate(**{**candidate.__dict__, "resolution_status": "PENDING_REVIEW", "reason": "AMBIGUOUS_REFERENCE" if rows else "TARGET_NOT_FOUND"})
    row = rows[0]
    return ReferenceCandidate(**{**candidate.__dict__, "target_provision_id": str(getattr(row, "id", candidate.target_provision_id)), "target_version": getattr(row, "version", None), "resolution_status": "RESOLVED"})

def review_item_for(candidate: ReferenceCandidate, *, document_id: str, ingestion_run_id: str) -> dict[str, object]:
    """Return fields matching ReviewItem for unresolved/ambiguous candidates."""
    return {"ingestion_run_id": ingestion_run_id, "document_id": document_id, "target_type": "PROVISION_REFERENCE", "target_id": candidate.source_provision_id, "reason_code": candidate.reason or "UNRESOLVED_REFERENCE", "description": candidate.source_text, "evidence": {"relation_type": candidate.relation_type}}

def extract_document_relations(text: str, source_document_id: str, known_documents: Mapping[str, str]) -> list[DocumentCandidate]:
    out = []
    for relation, pattern in _DOC_PATTERNS.items():
        for m in pattern.finditer(text):
            note = m.group("doc").strip()
            matches = [doc_id for key, doc_id in known_documents.items() if key.lower() in note.lower()]
            target = matches[0] if len(matches) == 1 else None
            out.append(DocumentCandidate(source_document_id, target, relation, note, "RESOLVED" if target else "PENDING_REVIEW"))
    return out

def infer_parent_relations(provisions: Iterable[object]) -> list[ReferenceCandidate]:
    """Derive hierarchy edges only when article/clause/point ancestry is explicit."""
    rows = list(provisions); out = []
    for child in rows:
        parent = next((p for p in rows if getattr(p, "document_version_id", None) == getattr(child, "document_version_id", None) and getattr(p, "article", None) == getattr(child, "article", None) and getattr(p, "clause", None) == getattr(child, "clause", None) and getattr(p, "point", None) is None and getattr(child, "point", None) is not None), None)
        if parent is not None:
            out.append(ReferenceCandidate(str(getattr(parent, "provision_id")), "PARENT_OF", "hierarchy", str(getattr(child, "provision_id")), getattr(child, "version", None), "RESOLVED", extraction_method="hierarchy"))
    return out
