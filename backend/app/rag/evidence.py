"""Small deterministic evidence and abstention gate."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

ABSTENTION_MESSAGE = "Chưa đủ căn cứ trong dữ liệu pháp luật được truy xuất để trả lời chắc chắn."


@dataclass(frozen=True, slots=True)
class EvidenceDecision:
    allowed: bool
    message: str | None = None
    reason: str | None = None


def assess_evidence(
    documents: Iterable[Any],
    *,
    required_reference: Mapping[str, str] | None = None,
    min_documents: int = 1,
    min_score: float | None = None,
) -> EvidenceDecision:
    """Allow generation only when retrieved evidence clears deterministic gates."""
    docs = list(documents)
    if len(docs) < min_documents:
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "insufficient_documents")
    if required_reference and not any(
        _matches_reference(_metadata(doc), required_reference) for doc in docs
    ):
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "reference_not_found")
    if min_score is not None and not any(_score(doc) >= min_score for doc in docs):
        return EvidenceDecision(False, ABSTENTION_MESSAGE, "score_below_threshold")
    return EvidenceDecision(True)


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
        else:
            actual = metadata.get(key)
        if _normalize(actual) != _normalize(expected):
            return False
    return True


def _normalize(value: Any) -> str:
    return "".join(str(value or "").casefold().split())


__all__ = ["ABSTENTION_MESSAGE", "EvidenceDecision", "assess_evidence"]
