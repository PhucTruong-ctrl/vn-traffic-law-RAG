"""Deterministic post-generation grounding verification."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .generator import is_refusal_answer
from .references import LegalReference


@dataclass(frozen=True, slots=True)
class SanitizedResponse:
    answer: str
    citations: tuple[dict[str, Any], ...]
    claims: tuple[dict[str, Any], ...]
    allowed: bool
    reason: str


def _norm(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _citation_norm(value: Any) -> str:
    normalized = re.sub(r"[—–-]", " ", str(value or "").casefold())
    normalized = re.sub(r"\b(?:nghị định|thông tư|luật)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9à-ỹ]+", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\b(?:nd|tt|nđ|cp)\b", " ", normalized)
    return "".join(normalized.split())


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


_MONEY_RE = re.compile(
    r"(?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?P<unit>triệu|nghìn|nghin|đồng|dong|vnd|đ)?",
    re.IGNORECASE | re.UNICODE,
)


def _money_values(text: str) -> set[int]:
    """Return every dong amount written in the text, in đồng."""
    values: set[int] = set()
    for match in _MONEY_RE.finditer(text):
        raw, unit = match.group("amount"), (match.group("unit") or "").casefold()
        separated = "." in raw or "," in raw
        if not unit and not separated:
            # A bare number is an article, a decree year, or a clause index.
            continue
        digits = int(raw.replace(".", "").replace(",", ""))
        if unit == "triệu":
            digits *= 1_000_000
        elif unit in {"nghìn", "nghin"}:
            digits *= 1_000
        if digits >= 1000:
            values.add(digits)
    return values


def unsupported_amounts(answer: str, documents: Iterable[Any]) -> set[int]:
    """Money amounts stated in the answer that no cited provision states."""
    sources = " ".join(str(getattr(doc, "page_content", "")) for doc in documents)
    supported = _money_values(sources)
    return {value for value in _money_values(answer) if value not in supported}


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


def _dump_guard_failure(answer: str, docs: list[Any]) -> None:
    import json
    import os

    path = os.environ.get("VNLRAG_GUARD_DUMP")
    if not path:
        return
    payload = {
        "answer": answer,
        "unsupported": sorted(unsupported_amounts(answer, docs)),
        "docs": [
            {
                "chunk_id": (getattr(doc, "metadata", {}) or {}).get("chunk_id"),
                "amounts": sorted(_money_values(str(getattr(doc, "page_content", "")))),
                "text": str(getattr(doc, "page_content", "")),
            }
            for doc in docs
        ],
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def sanitize_response(
    question: str,
    route: str,
    analysis: Any,
    references: Iterable[LegalReference],
    effective_date: date | None,
    filtered_documents: Iterable[Any],
    answer: str,
    citations: Iterable[dict[str, Any]],
    claims: Iterable[dict[str, Any]],
) -> SanitizedResponse:
    """Drop unsupported generated evidence while preserving usable output."""
    if route not in {"legal", "law", "traffic"}:
        return SanitizedResponse(answer, (), (), False, "out_of_scope")
    if not _norm(answer) or not re.search(r"[A-Za-zÀ-ỹ]", answer):
        return SanitizedResponse(answer, (), (), False, "output_integrity")
    if is_refusal_answer(answer):
        return SanitizedResponse(answer, (), (), False, "generation_insufficient_evidence")
    docs = list(filtered_documents)
    if not docs:
        return SanitizedResponse(answer, (), (), False, "insufficient_evidence")
    if unsupported_amounts(answer, docs):
        _dump_guard_failure(answer, docs)
        return SanitizedResponse(answer, (), (), False, "unsupported_figures")
    raw_citations = [dict(citation) for citation in citations]
    by_source = {_norm((getattr(doc, "metadata", {}) or {}).get("chunk_id")): doc for doc in docs}
    valid: list[dict[str, Any]] = []
    first_drop_reason: str | None = None
    for citation in raw_citations:
        source = by_source.get(_norm(citation.get("source_id")))
        reason = None
        if not _identity_complete(citation):
            reason = "citation_identity_incomplete"
        elif source is None:
            reason = "citation_not_retrieved"
        elif _citation_norm(citation.get("document_id")) != _citation_norm(
            (getattr(source, "metadata", {}) or {}).get("document_id")
        ):
            reason = "citation_identity_mismatch"
        elif _norm(citation.get("excerpt")) not in _norm(getattr(source, "page_content", "")):
            reason = "citation_excerpt_mismatch"
        elif not _eligible(source, effective_date):
            reason = "temporal_mismatch"
        elif not _supports_request(question, analysis, source):
            reason = "citation_context_mismatch"
        if reason:
            first_drop_reason = first_drop_reason or reason
        elif _norm(citation.get("source_id")) not in {
            _norm(item.get("source_id")) for item in valid
        }:
            valid.append(citation)
    extracted = extract_cited_citations(answer, docs, raw_citations)
    surviving = extracted or valid
    surviving_ids = {_norm(citation.get("source_id")) for citation in surviving}
    surviving_claims: list[dict[str, Any]] = []
    for raw in claims:
        claim = dict(raw)
        ids = {_norm(item) for item in claim.get("provision_ids", [])}
        if ids and ids <= surviving_ids:
            surviving_claims.append(claim)
    reason = "verified" if extracted else (first_drop_reason or "citation_not_retrieved")
    return SanitizedResponse(answer, tuple(surviving), tuple(surviving_claims), True, reason)


def extract_cited_citations(
    answer: str,
    documents: Iterable[Any],
    citations: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract answer citation markers and return first matching citations."""
    docs = {
        _norm((getattr(document, "metadata", {}) or {}).get("chunk_id")): document
        for document in documents
    }
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    markers = re.findall(
        r"\[([^\]]+)\]|\b(Điều\s+\S+(?:\s+Khoản\s+\S+)?(?:\s+Điểm\s+\S+)?(?:\s+[^\[\].,;]+)?)",
        answer,
        re.I,
    )
    for bracketed, plain in markers:
        marker = bracketed or plain
        fields = {
            "article": re.search(r"Điều\s+([\w.-]+)", marker, re.I),
            "clause": re.search(r"Khoản\s+([\w.-]+)", marker, re.I),
            "point": re.search(r"Điểm\s+([\w.-]+)", marker, re.I),
        }
        source_match = re.search(
            r"\b(?:doc[-\s_]?\w+|(?:nghị định|thông tư|luật)\s+[^,\]—]+)", marker, re.I
        )
        source_text = source_match.group(0) if source_match else marker
        for citation in citations:
            source_id = _norm(citation.get("source_id"))
            if source_id in seen or source_id not in docs:
                continue
            metadata = getattr(docs[source_id], "metadata", {}) or {}
            if any(
                match and _norm(citation.get(key)) != _norm(match.group(1))
                for key, match in ((key, fields[key]) for key in ("article", "clause", "point"))
            ):
                continue
            document_values = [
                citation.get("document_id"),
                citation.get("document_number"),
                citation.get("document_name"),
                citation.get("document_title"),
                metadata.get("document_id"),
                metadata.get("document_number"),
                metadata.get("document_name"),
            ]
            if not any(
                _citation_norm(source_text) in _citation_norm(value)
                or _citation_norm(value) in _citation_norm(source_text)
                for value in document_values
                if value
            ):
                continue
            results.append(dict(citation))
            seen.add(source_id)
            break
    return results


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


__all__ = ["SanitizedResponse", "extract_cited_citations", "sanitize_response"]
