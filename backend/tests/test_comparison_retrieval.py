from datetime import date

from app.query.query_understanding import QueryIntent, QueryPlan
from app.retrieval.comparison import ComparisonRetriever
from app.retrieval.contracts import CandidateSet, RetrievalResult

BEFORE = date(2024, 1, 1)
AFTER = date(2025, 1, 1)


def _plan() -> QueryPlan:
    return QueryPlan(
        intent=QueryIntent.COMPARISON,
        effective_date=None,
        comparison_from=BEFORE,
        comparison_to=AFTER,
        vehicle_type=None,
        document_number=None,
        article=None,
        clause=None,
        point=None,
        legal_entities=[],
        normalized_query="quy định trước và sau",
        required_evidence=[],
        missing_query_information=[],
    )


def _result(provision_id: str, document_number: str) -> RetrievalResult:
    return RetrievalResult(
        rank=1,
        provision_id=provision_id,
        provision_version=1,
        document_id=document_number,
        document_version_id=f"version-{provision_id}",
        text=f"Nội dung {provision_id}",
        source_text=f"Nguồn {provision_id}",
        parent_context=None,
        document_number=document_number,
        article="7",
        clause=None,
        point=None,
        effective_from=date(2020, 1, 1),
        effective_to=None,
        page_number=1,
        retrieval_sources=["dense"],
        fused_score=0.9,
        added_by=None,
        source_id=None,
        depth=0,
    )


class _Historical:
    def __init__(self, candidates: CandidateSet) -> None:
        self.candidates = candidates
        self.dates: list[date] = []

    def retrieve(self, plan: QueryPlan, *, query_date: date) -> CandidateSet:
        self.dates.append(query_date)
        return self.candidates


class _Current:
    def __init__(self, candidates: CandidateSet) -> None:
        self.candidates = candidates
        self.dates: list[date] = []

    def retrieve(self, plan: QueryPlan, *, current_date: date) -> CandidateSet:
        self.dates.append(current_date)
        return self.candidates


def test_same_date_keeps_two_independent_documents_and_side_dates() -> None:
    before = CandidateSet(
        query="before", results=[_result("old", "NĐ-1")], applied_date=BEFORE
    )
    after = CandidateSet(
        query="after", results=[_result("new", "NĐ-2")], applied_date=BEFORE
    )
    historical = _Historical(before)
    current = _Current(after)

    result = ComparisonRetriever(historical, current).compare(
        _plan(), date_from=BEFORE, date_to=BEFORE
    )

    assert historical.dates == [BEFORE]
    assert current.dates == [BEFORE]
    assert result.before.results[0].provision_id == "old"
    assert result.after.results[0].provision_id == "new"
    assert result.before_applied_date == BEFORE
    assert result.after_applied_date == BEFORE


def test_amendment_keeps_before_and_after_citation_lists_separate() -> None:
    before = CandidateSet(
        query="quy định", results=[_result("original", "NĐ-1")], applied_date=BEFORE
    )
    after = CandidateSet(
        query="quy định", results=[_result("amended", "NĐ-2")], applied_date=AFTER
    )
    result = ComparisonRetriever(_Historical(before), _Current(after)).compare(
        _plan(), date_from=BEFORE, date_to=AFTER
    )

    assert result.before.applied_date == BEFORE
    assert result.after.applied_date == AFTER
    assert [item.provision_id for item in result.before.results] == ["original"]
    assert [item.provision_id for item in result.after.results] == ["amended"]
    assert result.before.results is not result.after.results
