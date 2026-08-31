"""Evidence completeness checks for retrieved Vietnamese legal context."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from app.retrieval.contracts import RetrievalResult

from .query_understanding import QueryPlan
from .query_understanding_types import EvidenceType


class EvidenceStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class EvidenceGateResult:
    """Outcome of checking a context against a query's evidence plan."""

    status: EvidenceStatus
    evidence_gaps: list[EvidenceType]
    covered_provisions: list[str]


_AMOUNT = re.compile(
    r"\b\d[\d.,\s]*(?:đồng|triệu\s*đồng|nghìn\s*đồng)\b", re.IGNORECASE
)
_POINTS = re.compile(r"trừ\s+(?:[\wđ]+\s+)?\d+\s*điểm|\d+\s*điểm\s+(?:giấy phép|gplx)")


def _covered_types(candidate: RetrievalResult) -> set[EvidenceType]:
    text = " ".join(
        part
        for part in (candidate.text, candidate.source_text, candidate.parent_context)
        if part
    ).casefold()
    covered: set[EvidenceType] = set()

    # A definition needs the provision's violation/punishment language, not a
    # bare heading or an unrelated mention of the offence.
    if re.search(r"(?:hành vi|vi phạm).{0,100}(?:bị phạt|bị xử lý|xử phạt)", text):
        covered.add(EvidenceType.VIOLATION_DEFINITION)
    if _AMOUNT.search(text) and re.search(r"phạt|xử phạt", text):
        covered.add(EvidenceType.MONETARY_PENALTY)
    if _POINTS.search(text) or re.search(r"trừ.{0,30}điểm\s+(?:giấy phép|gplx)", text):
        covered.add(EvidenceType.LICENSE_POINTS)
    if re.search(
        r"tước\s+(?:quyền\s+sử\s+dụng\s+)?(?:giấy phép lái xe|gplx)"
        r"|thu hồi\s+(?:giấy phép lái xe|gplx)"
        r"|đình chỉ\s+(?:giấy phép lái xe|gplx)",
        text,
    ):
        covered.add(EvidenceType.LICENSE_SUSPENSION)
    if re.search(r"không\s+(?:bị\s+)?phạt|trường hợp\s+(?:được\s+)?miễn|ngoại lệ|không áp dụng", text):
        covered.add(EvidenceType.EXCEPTION)
    if re.search(r"nộp phạt|trình tự|thủ tục|hồ sơ|cách xử lý", text):
        covered.add(EvidenceType.PROCEDURE)
    if re.search(r"điều kiện|áp dụng khi|trong trường hợp|khi đáp ứng", text):
        covered.add(EvidenceType.LEGAL_CONDITION)
    return covered


class EvidenceCompletenessGate:
    """Determine whether retrieved provisions cover every required evidence type."""

    def evaluate(
        self, plan: QueryPlan, context: Sequence[RetrievalResult]
    ) -> EvidenceGateResult:
        covered_provisions: list[str] = []
        covered_types: set[EvidenceType] = set()
        for candidate in context:
            types = _covered_types(candidate)
            covered_types.update(types)
            if types and candidate.provision_id not in covered_provisions:
                covered_provisions.append(candidate.provision_id)

        gaps = [evidence for evidence in plan.required_evidence if evidence not in covered_types]
        return EvidenceGateResult(
            status=EvidenceStatus.INCOMPLETE if gaps else EvidenceStatus.COMPLETE,
            evidence_gaps=gaps,
            covered_provisions=covered_provisions,
        )


_TARGETED_TERMS = {
    EvidenceType.VIOLATION_DEFINITION: "hành vi vi phạm và căn cứ xử phạt",
    EvidenceType.MONETARY_PENALTY: "mức phạt tiền (số tiền và đơn vị đồng)",
    EvidenceType.LICENSE_POINTS: "số điểm bị trừ trên giấy phép lái xe",
    EvidenceType.LICENSE_SUSPENSION: "tước hoặc đình chỉ giấy phép lái xe",
    EvidenceType.EXCEPTION: "trường hợp ngoại lệ hoặc được miễn phạt",
    EvidenceType.PROCEDURE: "thủ tục, trình tự và hồ sơ thực hiện",
    EvidenceType.LEGAL_CONDITION: "điều kiện và trường hợp áp dụng",
}


def targeted_query_for_gap(gap: EvidenceType, plan: QueryPlan) -> str:
    """Build a bounded retrieval query focused on one missing evidence type."""

    return f"{plan.normalized_query} {_TARGETED_TERMS[gap]}"


__all__ = [
    "EvidenceCompletenessGate",
    "EvidenceGateResult",
    "EvidenceStatus",
    "targeted_query_for_gap",
]
