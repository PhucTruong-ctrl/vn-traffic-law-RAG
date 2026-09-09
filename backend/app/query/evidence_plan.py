"""Deterministic evidence requirements for legal query plans."""

from __future__ import annotations

import re
from collections.abc import Iterable

from .query_understanding_types import EvidenceType


def required_evidence_for(
    intent: object,
    question: str,
    legal_entities: Iterable[str] = (),
) -> list[EvidenceType]:
    """Return the smallest evidence set that can answer ``question``."""
    del legal_entities
    intent_value = getattr(intent, "value", intent)
    if str(intent) == "QueryIntent.OUT_OF_SCOPE" or intent_value == "OUT_OF_SCOPE":
        return []

    text = question.casefold()
    required: list[EvidenceType] = []
    asks_exception = bool(
        re.search(
            r"ngoại lệ|không bị phạt|trường hợp miễn|miễn phạt|ngoài trường hợp",
            text,
        )
    )
    asks_procedure = bool(re.search(r"thủ tục|quy trình|cách xử lý|hồ sơ|nộp phạt", text))
    asks_condition = bool(
        re.search(r"điều kiện|khi nào được|áp dụng khi|trong trường hợp", text)
    )
    asks_penalty = bool(
        re.search(
            r"mức phạt|phạt bao nhiêu|tiền phạt|xử phạt|phạt tiền|"
            r"phạt\s+sao|phạt\s+thế\s+nào",
            text,
        )
    )
    asks_points = bool(re.search(r"trừ điểm|bao nhiêu điểm|điểm giấy phép", text))
    asks_suspension = bool(
        re.search(r"tước|thu hồi|đình chỉ|suspend|suspension", text)
    )

    if asks_penalty or asks_suspension:
        required.extend(
            (EvidenceType.VIOLATION_DEFINITION, EvidenceType.MONETARY_PENALTY)
        )
    elif asks_exception or asks_condition:
        required.append(EvidenceType.VIOLATION_DEFINITION)

    if asks_points:
        required.append(EvidenceType.LICENSE_POINTS)
    if asks_suspension:
        required.append(EvidenceType.LICENSE_SUSPENSION)
    if asks_exception:
        required.append(EvidenceType.EXCEPTION)
    if asks_procedure:
        required.append(EvidenceType.PROCEDURE)
    if asks_condition:
        required.append(EvidenceType.LEGAL_CONDITION)

    if not required and asks_points:
        required.append(EvidenceType.LICENSE_POINTS)
    elif not required and intent_value != "SOURCE_SEARCH":
        required.append(EvidenceType.VIOLATION_DEFINITION)
    return required


__all__ = ["EvidenceType", "required_evidence_for"]
