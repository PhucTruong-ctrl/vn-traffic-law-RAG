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


def _action_norm(value: Any) -> str:
    return re.sub(r"[^\w]+", " ", str(value or "").casefold(), flags=re.UNICODE).strip()


def _values(metadata: dict[str, Any], *keys: str) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return tuple(values)


_VEHICLE_ALIASES = {
    "car": {"car", "ô tô", "xe ô tô", "xe hơi"},
    "motorcycle": {"motorcycle", "xe máy", "xe mô tô", "xe gắn máy", "mô tô"},
    "bicycle": {"bicycle", "xe đạp", "xe thô sơ", "đạp điện"},
    "specialized": {"specialized", "xe chuyên dùng", "máy kéo"},
}


def _requested_vehicles(question: str, analysis: Any) -> set[str]:
    explicit = set(getattr(analysis, "vehicle_types", ()) or ())
    if explicit:
        return explicit
    lowered = _norm(question)
    result = set()
    for category, aliases in _VEHICLE_ALIASES.items():
        if any(alias in lowered for alias in aliases if len(alias) > 2):
            result.add(category)
    return result


def _metadata_vehicles(metadata: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for value in _values(
        metadata, "vehicle_categories", "vehicle", "vehicle_type", "vehicle_category"
    ):
        normalized = _norm(value)
        for category, aliases in _VEHICLE_ALIASES.items():
            if normalized == category or any(alias in normalized for alias in aliases):
                result.add(category)
    return result


def _action_matches(question: str, analysis: Any, metadata: dict[str, Any], text: str) -> bool:
    declared = (
        metadata.get("normalized_action") or metadata.get("action") or metadata.get("violation")
    )
    if not declared:
        return True
    canonical = _action_norm(declared)
    intents = getattr(analysis, "intents", ()) if analysis is not None else ()
    expected = (
        " ".join(
            str(getattr(intent, "text", intent))
            for intent in intents
            if getattr(intent, "kind", "legal") == "legal"
        )
        or question
    )
    expected_tokens = _meaningful_tokens(expected) - {
        "mức",
        "phạt",
        "tiền",
        "trừ",
        "điểm",
        "tước",
        "quyền",
        "sử",
        "dụng",
        "xử",
        "lý",
        "tạm",
        "giữ",
        "phương",
        "tiện",
        "bao",
        "nhiêu",
        "thế",
        "nào",
    }
    if not expected_tokens:
        return True
    actual_tokens = _meaningful_tokens(canonical)
    aliases = {
        "vượt": {"vượt", "không", "chấp", "hành", "hiệu", "lệnh"},
        "đèn": {"đèn", "tín", "hiệu"},
        "đỏ": {"đỏ"},
        "điện": {"điện", "thoại"},
        "thoại": {"điện", "thoại"},
    }
    relevant = {token for token in expected_tokens if token in actual_tokens or token in aliases}
    return bool(relevant) and any(aliases.get(token, {token}) & actual_tokens for token in relevant)


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
    normalized_answer = _norm(answer)
    if not normalized_answer or not re.search(r"[\wÀ-ỹ]", answer):
        return VerificationDecision(False, "output_integrity")
    if len(re.findall(r"[A-Za-zÀ-ÿ]", answer)) == 0:
        return VerificationDecision(False, "output_integrity")
    if any(
        phrase in normalized_answer
        for phrase in (
            "chưa đủ căn cứ",
            "chưa đủ thông tin",
            "không đủ căn cứ",
            "chưa có đủ thông tin",
            "không có đủ căn cứ",
            "không đủ bằng chứng",
        )
    ):
        return VerificationDecision(False, "generation_insufficient_evidence")
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
        metadata = getattr(doc, "metadata", {}) or {}
        if _norm(citation.get("document_id")) != _norm(metadata.get("document_id")):
            return VerificationDecision(False, "citation_identity_mismatch")
        text = _norm(getattr(doc, "page_content", ""))
        excerpt = _norm(citation.get("excerpt"))
        if not excerpt or excerpt not in text:
            return VerificationDecision(False, "citation_excerpt_mismatch")
        if not _eligible(doc, effective_date):
            return VerificationDecision(False, "temporal_mismatch")
        if not _supports_request(question, analysis, doc):
            return VerificationDecision(False, "citation_context_mismatch")
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


def _supports_request(question: str, analysis: Any, document: Any) -> bool:
    metadata = getattr(document, "metadata", {}) or {}
    requested = _requested_vehicles(question, analysis)
    declared = _metadata_vehicles(metadata)
    if requested and declared and not requested.intersection(declared):
        return False
    if (
        requested
        and any(
            metadata.get(key)
            for key in ("vehicle_categories", "vehicle", "vehicle_type", "vehicle_category")
        )
        and not declared
    ):
        return False
    return _action_matches(question, analysis, metadata, str(getattr(document, "page_content", "")))


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
        if len(token) > 2 and token not in {"bao", "bị", "có", "đối", "với", "thế", "nào"}
    }


__all__ = ["VerificationDecision", "verify_response"]
