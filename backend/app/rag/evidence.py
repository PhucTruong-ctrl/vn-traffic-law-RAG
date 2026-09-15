"""Small deterministic evidence and abstention gate."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .references import normalize_reference_value


def _metadata(document: Any) -> Mapping[str, Any]:
    """Return stable metadata for LangChain documents and mapping records."""
    if isinstance(document, Mapping):
        metadata = document.get("metadata", document)
    else:
        metadata = getattr(document, "metadata", {})
    return metadata if isinstance(metadata, Mapping) else {}


def _score(document: Any) -> float:
    """Extract a numeric retrieval score; malformed or absent values fail closed."""
    if isinstance(document, Mapping):
        value = document.get("score")
        if value is None and isinstance(document.get("metadata"), Mapping):
            value = document["metadata"].get("score")
    else:
        value = getattr(document, "score", None)
        if value is None:
            metadata = getattr(document, "metadata", {})
            if isinstance(metadata, Mapping):
                value = metadata.get("score")
    if value is None:
        return float("-inf")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


_VEHICLE_ALIASES = {
    "car": {"car", "ô tô", "xe ô tô", "xe hơi"},
    "motorcycle": {"motorcycle", "xe máy", "xe mô tô", "xe gắn máy", "mô tô", "moped"},
    "bicycle": {"bicycle", "xe đạp", "xe thô sơ", "đạp điện"},
    "specialized": {"specialized", "xe chuyên dùng", "máy kéo"},
}


def _canonical_tokens(value: Any) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", str(value or "").casefold(), flags=re.UNICODE)
        if len(token) > 1
    }


def _metadata_values(metadata: Mapping[str, Any], *keys: str) -> tuple[str, ...]:
    values: list[str] = []
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(str(item) for item in value)
        elif value is not None:
            values.append(str(value))
    return tuple(values)


def _vehicle_matches(metadata: Mapping[str, Any], required: tuple[str, ...]) -> bool:
    if not required:
        return True
    declared = _metadata_values(
        metadata, "vehicle_categories", "vehicle", "vehicle_type", "vehicle_category"
    )
    if not declared:
        return False
    requested_text = " ".join(required).casefold()
    requested_categories = {
        category
        for category, aliases in _VEHICLE_ALIASES.items()
        if any(alias in requested_text for alias in aliases)
    }
    declared_categories = {
        category
        for category, aliases in _VEHICLE_ALIASES.items()
        if any(alias in " ".join(declared).casefold() for alias in aliases)
    }
    return bool(requested_categories & declared_categories)


def _action_matches(metadata: Mapping[str, Any], required: tuple[str, ...]) -> bool:
    if not required:
        return True
    canonical = metadata.get("normalized_action") or metadata.get("action")
    if not canonical:
        return bool(
            _canonical_tokens(" ".join(required)) & _canonical_tokens(metadata.get("context", ""))
        )
    expected = _canonical_tokens(" ".join(required))
    actual = _canonical_tokens(canonical)
    ignored = {"mức", "phạt", "tiền", "bao", "nhiêu", "thế", "nào"}
    expected -= ignored
    if not expected:
        return True
    aliases = {"vượt": {"vượt", "chấp", "hành", "hiệu", "lệnh"}, "đèn": {"đèn", "tín", "hiệu"}}
    return bool(expected & actual) or any(
        aliases.get(token, {token}) & actual for token in expected
    )


ABSTENTION_MESSAGE = "Chưa đủ căn cứ trong dữ liệu pháp luật được truy xuất để trả lời chắc chắn."


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    allowed: bool
    message: str | None = None
    reason: str | None = None


def assess_evidence(
    documents: Iterable[Any],
    *,
    required_reference: Mapping[str, str] | Any | None = None,
    min_documents: int = 1,
    min_score: float | None = None,
    required_intents: Iterable[str] | None = None,
    required_action_terms: Iterable[str] | None = None,
    required_vehicle_terms: Iterable[str] | None = None,
    excluded_contexts: Iterable[str] | None = None,
    effective_date: Any | None = None,
) -> EvidenceDecision:
    """Allow generation only when retrieved evidence clears deterministic gates."""
    docs = list(documents)
    if len(docs) < min_documents:
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "insufficient_documents")
    valid_docs = [
        doc
        for doc in docs
        if _matches_content(
            doc,
            required_action_terms=required_action_terms,
            required_vehicle_terms=required_vehicle_terms,
            excluded_contexts=excluded_contexts,
            effective_date=effective_date,
        )
    ]
    if effective_date is not None and not valid_docs:
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "no_temporally_valid_evidence")
    valid_docs = [doc for doc in valid_docs if _is_valid_identity(_metadata(doc))]
    if not valid_docs and any(
        _metadata(doc).get("document_id") or _metadata(doc).get("chunk_id") for doc in docs
    ):
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "insufficient_evidence")
    if required_reference:
        reference = (
            required_reference.as_dict()
            if hasattr(required_reference, "as_dict")
            else required_reference
        )
        if not any(_matches_reference(_metadata(doc), reference) for doc in valid_docs):
            return EvidenceDecision(False, ABSTENTION_MESSAGE, "reference_not_found")
    if (
        required_action_terms
        and any(_has_action_identity(doc, required_action_terms) for doc in valid_docs)
        and not any(
            _has_action_identity(doc, required_action_terms) and _has_sanction_signal(doc)
            for doc in valid_docs
        )
    ):
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "missing_sanction_evidence")
    if required_intents:
        expected = {intent for intent in required_intents if intent}
        covered: set[str] = set()
        for intent in expected:
            terms = _intent_terms(intent)
            if any(
                intent in _intent_labels(_metadata(doc)) or terms <= _meaningful_text(doc)
                for doc in valid_docs
            ):
                covered.add(intent)
        if expected - covered:
            return EvidenceDecision(False, ABSTENTION_MESSAGE, "insufficient_intents")
    if min_score is not None and not any(_score(doc) >= min_score for doc in valid_docs):
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "score_below_threshold")
    return EvidenceDecision(True)


def _meaningful_text(document: Any) -> set[str]:
    return _meaningful_tokens(str(getattr(document, "page_content", "")))


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", text.casefold(), flags=re.UNICODE)
        if len(token) > 1
    }


def _intent_terms(intent: str) -> set[str]:
    return _meaningful_tokens(intent)


def _is_valid_identity(metadata: Mapping[str, Any]) -> bool:
    # Citation construction enforces complete identity; low-level evidence
    # selection accepts document-only records used by temporal tests.
    return bool(
        str(metadata.get("document_id") or "").strip()
        or str(metadata.get("chunk_id") or "").strip()
    )


def _has_sanction_signal(document: Any) -> bool:
    """Require an explicit sanction signal for action/penalty evidence."""
    metadata = _metadata(document)
    searchable = " ".join(
        [
            str(getattr(document, "page_content", "")),
            *(
                str(metadata.get(key, ""))
                for key in ("sanction", "penalty", "fine", "points", "action")
            ),
        ]
    )
    return bool(
        re.search(
            r"(?:phạt\s*(?:tiền)?|mức\s*phạt|tiền\s*phạt|trừ\s*điểm|tước\s+quyền|"
            r"tịch\s*thu|tạm\s*giữ|\b\d[\d.,]*\s*(?:đ|đồng|vnđ|triệu|nghìn)\b)",
            searchable,
            flags=re.IGNORECASE,
        )
    )


def _has_action_identity(document: Any, required_action_terms: Iterable[str] | None) -> bool:
    if not required_action_terms:
        return True
    metadata = _metadata(document)
    return bool(
        str(
            metadata.get("normalized_action")
            or metadata.get("action")
            or metadata.get("violation")
            or ""
        ).strip()
    )


def _matches_content(
    document: Any,
    *,
    required_action_terms: Iterable[str] | None,
    required_vehicle_terms: Iterable[str] | None,
    excluded_contexts: Iterable[str] | None,
    effective_date: Any | None,
) -> bool:
    searchable = " ".join(
        [
            str(getattr(document, "page_content", "")),
            *(
                str(_metadata(document).get(key, ""))
                for key in (
                    "provision_family",
                    "context",
                    "context_scope",
                    "violation",
                    "action",
                    "normalized_action",
                    "vehicle",
                    "vehicle_type",
                    "vehicle_category",
                    "vehicle_categories",
                )
            ),
        ]
    )
    aliases = {
        "không đội mũ bảo hiểm hoặc không cài quai đúng quy cách": (
            "không đội",
            "mũ bảo hiểm",
            "cài quai",
        ),
        "quy định về số người được chở trên xe": (
            "số người được chở",
            "chở theo",
            "người được chở",
        ),
        "sử dụng đèn chiếu sáng khi tham gia giao thông": (
            "đèn chiếu sáng",
            "sử dụng không đủ đèn",
        ),
        "sử dụng còi trong khu đông dân cư": ("bấm còi", "sử dụng còi", "rú ga"),
        "quay đầu xe": ("quay đầu xe", "quay đầu"),
        "lùi xe": ("lùi xe",),
    }
    action_terms = tuple(
        str(term).casefold() for term in (required_action_terms or ()) if str(term).strip()
    )
    if any(
        term not in searchable and not any(alias in searchable for alias in aliases.get(term, ()))
        for term in action_terms
    ):
        return False
    metadata = _metadata(document)
    if (
        action_terms
        and not _action_matches(metadata, action_terms)
        and (metadata.get("normalized_action") or metadata.get("action"))
    ):
        return False
    vehicle_terms = tuple(
        term.casefold() for term in (required_vehicle_terms or ()) if str(term).strip()
    )
    if vehicle_terms and not _vehicle_matches(metadata, vehicle_terms):
        return False
    if any(str(term).casefold() in searchable for term in (excluded_contexts or ())):
        return False
    return effective_date is None or _effective(metadata, effective_date)


def _effective(metadata: Mapping[str, Any], value: Any) -> bool:
    start = metadata.get("effective_from", metadata.get("valid_from"))
    end = metadata.get("effective_to", metadata.get("effective_until", metadata.get("valid_to")))
    try:
        return (start is None or _date_value(start) <= value) and (
            end is None or value <= _date_value(end)
        )
    except (TypeError, ValueError):
        return False


def _date_value(value: Any) -> Any:
    if isinstance(value, str):
        from datetime import date

        return date.fromisoformat(value[:10])
    if hasattr(value, "date"):
        return value.date()
    return value


def _intent_labels(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    labels = metadata.get("intent") or metadata.get("intent_text")
    if isinstance(labels, str):
        return (labels,)
    if isinstance(labels, (list, tuple, set)):
        return tuple(label for label in labels if isinstance(label, str))
    return ()


def _matches_reference(metadata: Mapping[str, Any], reference: Mapping[str, str]) -> bool:
    for key, expected in reference.items():
        if key == "number":
            actual = metadata.get("document_number") or metadata.get("document_name")
        elif key == "kind":
            continue
        else:
            actual = metadata.get(key)
        actual_normalized = _normalize(actual)
        expected_normalized = _normalize(expected)
        if key == "article":
            actual_normalized = actual_normalized.removeprefix("điều")
            expected_normalized = expected_normalized.removeprefix("điều")
        elif key == "number":
            if _document_number_family(actual_normalized) != _document_number_family(
                expected_normalized
            ):
                return False
            continue
        if actual_normalized != expected_normalized:
            return False
    return True


def _document_number_family(value: str) -> str:
    match = re.search(r"\d+/\d{4}", value)
    return match.group(0) if match else value


def _normalize(value: Any) -> str:
    return normalize_reference_value(value)


__all__ = ["ABSTENTION_MESSAGE", "EvidenceDecision", "assess_evidence"]
