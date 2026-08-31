from datetime import date
from types import SimpleNamespace

from app.query.query_understanding import QueryIntent, QueryPlan
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.retrieval.current import CurrentRetriever

TODAY = date(2026, 8, 31)


def _plan() -> QueryPlan:
    return QueryPlan(
        intent=QueryIntent.CURRENT,
        effective_date=TODAY,
        comparison_from=None,
        comparison_to=None,
        vehicle_type="xe máy",
        document_number=None,
        article=None,
        clause=None,
        point=None,
        legal_entities=[],
        normalized_query="mức phạt hiện nay",
        required_evidence=[],
        missing_query_information=[],
    )


def _result(
    provision_id: str, effective_from: date, effective_to: date | None
) -> RetrievalResult:
    return RetrievalResult(
        rank=1,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc-1",
        document_version_id="doc-version-1",
        text="Nội dung",
        source_text="Nguồn",
        parent_context=None,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause=None,
        point=None,
        effective_from=effective_from,
        effective_to=effective_to,
        page_number=1,
        retrieval_sources=["dense"],
        fused_score=0.9,
        added_by=None,
        source_id=None,
        depth=0,
    )


class _Retriever:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.query_filter = None
        self.limit = None
        self.query = None

    def search(self, query: str, *, query_filter=None, limit=None) -> CandidateSet:
        self.query = query
        self.query_filter = query_filter
        self.limit = limit
        return CandidateSet(query=query, results=self.results, applied_date=None)


class _TemporalRepository:
    def __init__(self, provision_ids: set[str]) -> None:
        self.provision_ids = provision_ids
        self.date = None

    def valid_provisions(self, query_date: date, *, provision_ids=None):
        self.date = query_date
        return [
            SimpleNamespace(provision_id=value)
            for value in (provision_ids or self.provision_ids)
        ]


def test_retrieve_uses_supplied_date_and_keeps_open_interval() -> None:
    retriever = _Retriever(
        [
            _result("open", TODAY, None),
            _result("future", date(2027, 1, 1), None),
            _result("expired", date(2020, 1, 1), TODAY),
        ]
    )
    repository = _TemporalRepository({"open"})

    candidates = CurrentRetriever(retriever, repository, top_k=8).retrieve(
        _plan(), current_date=TODAY
    )

    assert [result.provision_id for result in candidates.results] == ["open"]
    assert candidates.results[0].rank == 1
    assert candidates.applied_date == TODAY
    assert retriever.query == "mức phạt hiện nay"
    assert retriever.limit == 8
    assert repository.date == TODAY


def test_retrieve_excludes_provision_at_effective_to_boundary() -> None:
    retriever = _Retriever([_result("expired", date(2020, 1, 1), TODAY)])

    candidates = CurrentRetriever(retriever).retrieve(_plan(), current_date=TODAY)

    assert candidates.results == []
    assert candidates.applied_date == TODAY
