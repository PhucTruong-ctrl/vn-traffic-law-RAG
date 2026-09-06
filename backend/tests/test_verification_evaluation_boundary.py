from datetime import date
from types import SimpleNamespace

from app.evaluation.ragas_adapter import evaluate_ragas
from app.verification.l2_citation import L2CitationVerifier
from app.verification.workflow import LegalVerificationBoundary


def _record(pid="p1"):
    return SimpleNamespace(
        provision_id=pid,
        review_status="ACCEPTED",
        text="Mức phạt tiền áp dụng.",
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


def test_legal_boundary_runs_gates_and_accepts_grounded_answer():
    record = _record()
    draft = SimpleNamespace(
        claims=[SimpleNamespace(claim="Mức phạt tiền", provision_ids=["p1"], numbers=[])]
    )
    result = LegalVerificationBoundary(L2CitationVerifier([record])).verify(
        draft, [record], query_date=date(2025, 1, 1)
    )
    assert result.passed
    assert result.checked_provision_ids == ("p1",)


def test_ragas_never_scores_unverified_records():
    result = evaluate_ragas(
        [{"verification_status": "ABSTAIN"}], evaluator=lambda _: {"faithfulness": 1.0}
    )
    assert result.status == "na"
    assert result.metrics["faithfulness"].value is None


def test_ragas_missing_evaluator_is_na_not_zero():
    result = evaluate_ragas([{"verification_status": "VALID"}])
    assert result.metrics["answer_relevancy"].value is None
    assert result.metrics["answer_relevancy"].status == "na"
