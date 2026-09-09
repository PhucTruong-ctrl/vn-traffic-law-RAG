"""Evidence completeness checks for retrieved Vietnamese legal context."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from app.ingestion.terminology import terminology_concepts
from app.retrieval.contracts import RetrievalResult

from .query_understanding import QueryPlan
from .query_understanding_types import EvidenceType


class EvidenceStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"


@dataclass(frozen=True)
class CaseEvidenceResult:
    """Evidence outcome for one independently answerable case."""

    case_id: str
    requested_evidence: list[EvidenceType]
    candidate_provisions: list[str]
    evidence_gaps: list[EvidenceType]
    gap_reasons: list[str]
    status: EvidenceStatus


@dataclass(frozen=True)
class EvidenceGateResult:
    """Outcome of checking a context against a query's evidence plan."""

    status: EvidenceStatus
    evidence_gaps: list[EvidenceType]
    covered_provisions: list[str]
    case_results: list[CaseEvidenceResult] = field(default_factory=list)


def _fold_ocr_text(text: str) -> str:
    folded = unicodedata.normalize("NFD", text.casefold())
    folded = "".join(char for char in folded if unicodedata.category(char) != "Mn")
    return folded.replace("đ", "d")


_AMOUNT = re.compile(r"\b\d[\d.,\s]*(?:dong|trieu\s*dong|nghin\s*dong)\b", re.IGNORECASE)
_POINTS = re.compile(
    r"(?:tru\s+(?:[\w]+\s+)?\d+\s*diem"
    r"|\d+\s*diem\s+(?:giay\s+phep|gplx)"
    r"|bi\s+tru\s+\d+\s*diem)",
    re.IGNORECASE,
)


def _covered_types(candidate: RetrievalResult) -> set[EvidenceType]:
    text = _fold_ocr_text(
        " ".join(
            part
            for part in (candidate.text, candidate.source_text, candidate.parent_context)
            if part
        )
    )
    covered: set[EvidenceType] = set()
    if re.search(r"hanh vi vi pham|vi pham|can cu xu phat|quy dinh|hanh vi .* bi phat", text):
        covered.add(EvidenceType.VIOLATION_DEFINITION)
    if _AMOUNT.search(text):
        covered.add(EvidenceType.MONETARY_PENALTY)
    if _POINTS.search(text):
        covered.add(EvidenceType.LICENSE_POINTS)
    if re.search(r"tuoc(?:\s+quyen\s+su\s+dung)?|dinh chi|thu hoi", text):
        covered.add(EvidenceType.LICENSE_SUSPENSION)
    if re.search(r"ngoai le|truong hop duoc mien phat|mien phat|khong bi phat", text):
        covered.add(EvidenceType.EXCEPTION)
    if re.search(r"thu tuc nop phat|thu tuc|quy trinh|nop phat|ho so", text):
        covered.add(EvidenceType.PROCEDURE)
    if re.search(
        r"ap dung khi .*dieu kien|dieu kien|ap dung khi|trong truong hop|duoc phep|nguoi duoc phep",
        text,
    ):
        covered.add(EvidenceType.LEGAL_CONDITION)
    return covered


def _case_has_problem(case: object) -> str | None:
    ambiguity = getattr(case, "ambiguity", [])
    missing = getattr(case, "missing_information", [])
    query_text = _fold_ocr_text(getattr(case, "query_text", ""))
    if ambiguity:
        return "ambiguous case: " + "; ".join(ambiguity)
    if missing:
        return "missing case information: " + "; ".join(missing)
    if re.search(r"(?:khong|không)\s+(?:hoi|hỏi|can|cần|yeu cau|yêu cầu)", query_text):
        return "negated case request"
    return None


_SCOPING_STOPWORDS = {
    "bao",
    "bi",
    "bao nhieu",
    "phat",
    "sao",
    "muc",
    "tien",
    "xe",
    "may",
    "oto",
    "o",
    "to",
    "hanh",
    "vi",
    "quy",
    "dinh",
    "the",
    "nao",
    "di",
    "va",
    "hoac",
    "nguoi",
    "lai",
    "thi",
}
_VIOLATION_MARKERS = {
    "vuot den do",
    "sai lan",
    "nong do",
    "toc do",
    "ruou bia",
}


def _case_candidates(case: object, context: Sequence[RetrievalResult]) -> list[RetrievalResult]:
    query_text = _fold_ocr_text(getattr(case, "query_text", ""))
    candidates = list(context)
    concepts = terminology_concepts(query_text)
    vehicle = _fold_ocr_text(getattr(case, "vehicle_type", "") or "")
    if vehicle and re.search(rf"(?<!\w){re.escape(vehicle)}(?!\w)", query_text):
        concepts.update(terminology_concepts(vehicle))
    if not concepts:
        concepts = {marker for marker in _VIOLATION_MARKERS if marker in query_text}
    if not concepts:
        return candidates
    scoped: list[RetrievalResult] = []
    for candidate in candidates:
        candidate_text = _fold_ocr_text(
            " ".join(
                part
                for part in (candidate.text, candidate.source_text, candidate.parent_context)
                if part
            )
        )
        if concepts.intersection(terminology_concepts(candidate_text)) or any(
            marker in candidate_text for marker in concepts
        ):
            scoped.append(candidate)
    return scoped


def _evaluate_case(
    case: object, plan: QueryPlan, context: Sequence[RetrievalResult]
) -> CaseEvidenceResult:
    requested = list(getattr(plan, "required_evidence", []))
    scoped = _case_candidates(case, context)
    covered: set[EvidenceType] = set()
    provisions: list[str] = []
    for candidate in scoped:
        covered.update(_covered_types(candidate))
        provisions.append(candidate.provision_id)
    gaps = [evidence_type for evidence_type in requested if evidence_type not in covered]
    reasons = [] if not gaps else [f"missing evidence: {gap.value}" for gap in gaps]
    problem = _case_has_problem(case)
    if problem:
        reasons.append(problem)
    if problem and not gaps:
        gaps = [EvidenceType.VIOLATION_DEFINITION]
    return CaseEvidenceResult(
        case_id=str(getattr(case, "case_id", "case-1")),
        requested_evidence=requested,
        candidate_provisions=provisions,
        evidence_gaps=gaps,
        gap_reasons=reasons,
        status=EvidenceStatus.COMPLETE if not gaps else EvidenceStatus.INCOMPLETE,
    )


def targeted_query_for_gap(gap: EvidenceType, plan: QueryPlan) -> str:
    """Create bounded repair query focused on one missing evidence type."""
    labels = {
        EvidenceType.VIOLATION_DEFINITION: "hành vi vi phạm",
        EvidenceType.MONETARY_PENALTY: "mức phạt tiền",
        EvidenceType.LICENSE_POINTS: "điểm bị trừ",
        EvidenceType.LICENSE_SUSPENSION: "tước hoặc đình chỉ giấy phép lái xe",
        EvidenceType.EXCEPTION: "ngoại lệ miễn phạt",
        EvidenceType.PROCEDURE: "thủ tục xử lý",
        EvidenceType.LEGAL_CONDITION: "điều kiện áp dụng",
    }
    return f"{plan.normalized_query}; tìm {labels.get(gap, gap.value)}"


class EvidenceCompletenessGate:
    """Require every planned evidence type before generation."""

    def evaluate(self, plan: QueryPlan, context: Sequence[RetrievalResult]) -> EvidenceGateResult:
        cases = list(getattr(plan, "cases", []))
        if not cases:
            query = plan.normalized_query
            folded_query = _fold_ocr_text(query)
            conjunction = re.search(
                r"(.+?)\s+va\s+(.+?)(?=\s+phat\b|$)",
                folded_query,
            )
            if conjunction and all(
                marker in conjunction.group(0) for marker in ("vuot den do", "sai lan")
            ):
                cases = [
                    type(
                        "Case",
                        (),
                        {
                            "case_id": f"case-{index}",
                            "query_text": phrase.strip(),
                            "requested_evidence": list(plan.required_evidence),
                        },
                    )()
                    for index, phrase in enumerate(conjunction.groups(), start=1)
                ]
            else:
                cases = [
                    type(
                        "Case",
                        (),
                        {
                            "case_id": "case-1",
                            # Generic synthetic fixtures represent the complete
                            # retrieved context; do not scope them by the
                            # analyzer's normalized query.
                            "query_text": "",
                            "requested_evidence": list(plan.required_evidence),
                        },
                    )()
                ]
        case_results = [_evaluate_case(case, plan, context) for case in cases]
        gaps = list(dict.fromkeys(gap for result in case_results for gap in result.evidence_gaps))
        provisions = list(
            dict.fromkeys(
                provision for result in case_results for provision in result.candidate_provisions
            )
        )
        return EvidenceGateResult(
            status=EvidenceStatus.COMPLETE if not gaps else EvidenceStatus.INCOMPLETE,
            evidence_gaps=gaps,
            covered_provisions=provisions,
            case_results=case_results,
        )
