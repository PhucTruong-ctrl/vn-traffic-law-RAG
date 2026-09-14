"""Deterministic post-generation grounding verification."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .references import LegalReference, metadata_matches


@dataclass(frozen=True)
class VerificationDecision:
    allowed: bool
    reason: str = "verified"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _identity_complete(citation: dict[str, Any]) -> bool:
    return bool(
        _norm(citation.get("source_id"))
        and _norm(citation.get("document_id"))
        and _norm(citation.get("excerpt"))
    )


def _eligible(doc: Any, effective_date: date | None) -> bool:
    if effective_date is None:
        return True
    metadata = getattr(doc, "metadata", {}) or {}
    for key in ("effective_from", "valid_from", "issued_date", "date"):
        value = metadata.get(key)
        if value:
            try:
                if date.fromisoformat(str(value)[:10]) > effective_date:
                    return False
            except ValueError:
                return False
    for key in ("effective_to", "valid_to", "expiry_date"):
        value = metadata.get(key)
        if value:
            try:
                if date.fromisoformat(str(value)[:10]) < effective_date:
                    return False
            except ValueError:
                return False
    return True


def verify_response(
    question: str,
    route: str,
    analysis: Any,
    references: Iterable[LegalReference],
    effective_date: date | None,
    filtered_documents: Iterable[Any],
    answer: str,
    citations: Iterable[dict[str, Any]],
    claims: Iterable[dict[str, Any]],
) -> VerificationDecision:
    """Return a fail-closed decision for generated grounded output."""
    if route not in {"legal", "law", "traffic"}:
        return VerificationDecision(False, "out_of_scope")
    if not _norm(answer) or not re.search(r"[\wÀ-ỹ]", answer):
        return VerificationDecision(False, "output_integrity")
    if len(re.findall(r"[A-Za-zÀ-ÿ]", answer)) == 0:
        return VerificationDecision(False, "output_integrity")
    docs = list(filtered_documents)
    citation_list = [dict(c) for c in citations]
    claim_list = [dict(c) for c in claims]
    if not citation_list or not all(_identity_complete(c) for c in citation_list):
        return VerificationDecision(False, "citation_identity_incomplete")
    by_source = {_norm((getattr(d, "metadata", {}) or {}).get("chunk_id")): d for d in docs}
    for citation in citation_list:
        source = _norm(citation.get("source_id"))
        doc = by_source.get(source)
        if doc is None:
            return VerificationDecision(False, "citation_not_retrieved")
        text = _norm(getattr(doc, "page_content", ""))
        excerpt = _norm(citation.get("excerpt"))
        if not excerpt or excerpt not in text:
            return VerificationDecision(False, "citation_excerpt_mismatch")
        if not _eligible(doc, effective_date):
            return VerificationDecision(False, "temporal_mismatch")
    refs = list(references)
    for ref in refs:
        if not any(metadata_matches((getattr(d, "metadata", {}) or {}), ref) for d in docs):
            return VerificationDecision(False, "reference_not_covered")
    citation_ids = {_norm(c.get("source_id")) for c in citation_list}
    for claim in claim_list:
        ids = {_norm(i) for i in claim.get("provision_ids", [])}
        if not ids or not ids <= citation_ids:
            return VerificationDecision(False, "claim_citation_mismatch")
    return VerificationDecision(True)


__all__ = ["VerificationDecision", "verify_response"]
