"""Small deterministic evidence and abstention gate."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .references import normalize_reference_value

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
        if _is_valid_identity(_metadata(doc))
        and _matches_content(
            doc,
            required_action_terms=required_action_terms,
            required_vehicle_terms=required_vehicle_terms,
            excluded_contexts=excluded_contexts,
            effective_date=effective_date,
        )
    ]
    if not valid_docs:
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "insufficient_relevant_evidence")
    if required_reference:
        reference = (
            required_reference.as_dict()
            if hasattr(required_reference, "as_dict")
            else required_reference
        )
        if not any(_matches_reference(_metadata(doc), reference) for doc in valid_docs):
            return EvidenceDecision(False, ABSTENTION_MESSAGE, "reference_not_found")
    if required_intents:
        expected = {intent for intent in required_intents if intent}
        covered = {label for doc in valid_docs for label in _intent_labels(_metadata(doc))}
        if expected - covered:
            return EvidenceDecision(False, ABSTENTION_MESSAGE, "insufficient_intents")
    if min_score is not None and not any(_score(doc) >= min_score for doc in valid_docs):
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "score_below_threshold")
    return EvidenceDecision(True)


def _is_valid_identity(metadata: Mapping[str, Any]) -> bool:
    return bool(
        metadata.get("document_id")
        or metadata.get("document_number")
        or metadata.get("document_name")
    )


def _matches_content(
    document: Any,
    *,
    required_action_terms: Iterable[str] | None,
    required_vehicle_terms: Iterable[str] | None,
    excluded_contexts: Iterable[str] | None,
    effective_date: Any | None,
) -> bool:
    text = str(getattr(document, "page_content", "")).casefold()
    if any(term.casefold() not in text for term in (required_action_terms or ())):
        return False
    if required_vehicle_terms and not any(
        term.casefold() in text for term in required_vehicle_terms
    ):
        return False
    if any(term.casefold() in text for term in (excluded_contexts or ())):
        return False
    return effective_date is None or _effective(_metadata(document), effective_date)


def _effective(metadata: Mapping[str, Any], value: Any) -> bool:
    start = metadata.get("effective_from", metadata.get("valid_from"))
    end = metadata.get("effective_to", metadata.get("valid_to"))
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


def _metadata(document: Any) -> Mapping[str, Any]:
    metadata = getattr(document, "metadata", None)
    return metadata if isinstance(metadata, Mapping) else {}


def _score(document: Any) -> float:
    value = _metadata(document).get("score", _metadata(document).get("relevance_score", 0))
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


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
        if actual_normalized != expected_normalized:
            return False
    return True


def _normalize(value: Any) -> str:
    return normalize_reference_value(value)


__all__ = ["ABSTENTION_MESSAGE", "EvidenceDecision", "assess_evidence"]
