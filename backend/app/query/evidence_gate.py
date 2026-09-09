"""Evidence completeness checks for retrieved Vietnamese legal context."""

from __future__ import annotations

import re
import unicodedata
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


def _fold_ocr_text(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return folded.replace("đ", "d")


_AMOUNT = re.compile(r"\b\d[\d.,\s]*(?:dong|trieu\s*dong|nghin\s*dong)\b", re.IGNORECASE)
_POINTS = re.compile(r"tru\s+(?:[\wd]+\s+)?\d+\s*diem|\d+\s*diem\s+(?:giay phep|gplx)")


def _covered_types(candidate: RetrievalResult) -> set[EvidenceType]:
    text = _fold_ocr_text(
        " ".join(
            part
            for part in (candidate.text, candidate.source_text, candidate.parent_context)
            if part
        )
    )
    covered: set[EvidenceType] = set()

    if re.search(r"(?:hanh vi|vi pham|vi).{0,100}(?:bi phat|bi xu ly|xu phat|phat tien)", text):
        covered.add(EvidenceType.VIOLATION_DEFINITION)
    if _AMOUNT.search(text) and re.search(r"phat|xu phat", text):
        covered.add(EvidenceType.MONETARY_PENALTY)
    if _POINTS.search(text) or re.search(r"tru.{0,30}diem\s+(?:giay phep|gplx)", text):
        covered.add(EvidenceType.LICENSE_POINTS)
    if re.search(
        r"tuoc\s+(?:quyen\s+su\s+dung\s+)?(?:giay phep lai xe|gplx)"
        r"|thu hoi\s+(?:giay phep lai xe|gplx)"
        r"|dinh chi\s+(?:giay phep lai xe|gplx)",
        text,
    ):
        covered.add(EvidenceType.LICENSE_SUSPENSION)
    if re.search(
        r"khong\s+(?:bi\s+)?phat|truong hop\s+(?:duoc\s+)?mien|ngoai le|khong ap dung",
        text,
    ):
        covered.add(EvidenceType.EXCEPTION)
    if re.search(r"nop phat|trinh tu|thu tuc|ho so|cach xu ly", text):
        covered.add(EvidenceType.PROCEDURE)
    if re.search(r"dieu kien|ap dung khi|trong truong hop|khi dap ung|duoc phep", text):
        covered.add(EvidenceType.LEGAL_CONDITION)
    return covered


class EvidenceCompletenessGate:
    """Determine whether retrieved provisions cover every required evidence type."""

    def evaluate(
        self, plan: QueryPlan, context: Sequence[RetrievalResult]
    ) -> EvidenceGateResult:
        covered_provisions: list[str] = []
        provision_types: dict[str, set[EvidenceType]] = {}
        for candidate in context:
            if getattr(candidate, "review_status", "ACCEPTED") != "ACCEPTED":
                continue
            types = _covered_types(candidate)
            provision_types.setdefault(candidate.provision_id, set()).update(types)
            if types and candidate.provision_id not in covered_provisions:
                covered_provisions.append(candidate.provision_id)

        covered_types = set().union(*provision_types.values()) if provision_types else set()
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
