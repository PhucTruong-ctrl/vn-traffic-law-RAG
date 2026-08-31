"""Deterministic evidence requirements for legal query plans."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .query_understanding_types import EvidenceType


def required_evidence_for(
    intent: object, question: str, legal_entities: Iterable[str] = ()
) -> list[EvidenceType]:
    """Return the smallest evidence set that can answer ``question``."""
    if (
        str(intent) == "QueryIntent.OUT_OF_SCOPE"
        or getattr(intent, "value", intent) == "OUT_OF_SCOPE"
    ):
        return []
    text = question.casefold()
    entities = {entity.casefold() for entity in legal_entities}
    required: list[EvidenceType] = []
    asks_exception = bool(
        re.search(r"ngoại lệ|không bị phạt|trường hợp miễn|miễn phạt|ngoài trường hợp", text)
    )
    asks_procedure = bool(re.search(r"thủ tục|quy trình|cách xử lý|hồ sơ|nộp phạt", text))
    asks_condition = bool(re.search(r"điều kiện|khi nào được|áp dụng khi|trong trường hợp", text))
    asks_penalty = bool(re.search(r"mức phạt|phạt bao nhiêu|tiền phạt|xử phạt|phạt tiền", text))
    asks_points = bool(
        re.search(r"trừ điểm|bao nhiêu điểm|điểm giấy phép", text)
    ) or "giấy phép lái xe" in entities
    asks_suspension = bool(re.search(r"tước|thu hồi|đình chỉ|suspend|suspension", text))

    if asks_procedure:
        required.append(EvidenceType.PROCEDURE)
    elif asks_exception:
        required.extend((EvidenceType.VIOLATION_DEFINITION, EvidenceType.EXCEPTION))
    elif asks_condition:
        required.extend((EvidenceType.VIOLATION_DEFINITION, EvidenceType.LEGAL_CONDITION))
    elif asks_penalty:
        required.extend((EvidenceType.VIOLATION_DEFINITION, EvidenceType.MONETARY_PENALTY))
        if asks_points:
            required.append(EvidenceType.LICENSE_POINTS)
        if asks_suspension:
            required.append(EvidenceType.LICENSE_SUSPENSION)
    elif asks_points:
        required.append(EvidenceType.LICENSE_POINTS)
    elif asks_suspension:
        required.extend((EvidenceType.VIOLATION_DEFINITION, EvidenceType.LICENSE_SUSPENSION))
    elif intent is not None:
        required.append(EvidenceType.VIOLATION_DEFINITION)
    return required


__all__ = ["EvidenceType", "required_evidence_for"]
