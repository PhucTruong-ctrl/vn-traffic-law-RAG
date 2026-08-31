from datetime import date
from types import SimpleNamespace

import pytest

from app.query.query_understanding import QueryPlan
from app.query.query_understanding_types import EvidenceType, QueryIntent
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.retrieval.historical import HistoricalRetriever

QUERY_DATE = date(2024, 6, 1)


def _plan(*, missing: list[str] | None = None) -> QueryPlan:
    return QueryPlan(
        intent=QueryIntent.HISTORICAL,
        effective_date=QUERY_DATE,
        comparison_from=None,
        comparison_to=None,
        vehicle_type=None,
        document_number=None,
        article=None,
        clause=None,
        point=None,
        legal_entities=[],
        normalized_query="mức phạt",
        required_evidence=[EvidenceType.MONETARY_PENALTY],
        missing_query_information=missing or [],
    )


def _result(provision_id: str) -> RetrievalResult:
    return RetrievalResult(
        rank=1,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc-1",
        document_version_id="version-1",
        text="Nội dung",
        source_text="Nội dung",
        parent_context=None,
        document_number="168/2024/NĐ-CP",
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


class FakeRetriever:
    def __init__(self, results: list[RetrievalResult]) -> None:
        self.results = results
        self.query_filter = None

    def search(self, query: str, *, query_filter=None, limit=None) -> CandidateSet:
        self.query_filter = query_filter
        return CandidateSet(query=query, results=self.results, applied_date=None)


class FakeTemporalRepository:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows
        self.arguments = None

    def valid_provisions(self, d: date, *, provision_ids: list[str]) -> list[object]:
        self.arguments = (d, provision_ids)
        return self.rows


def test_rejects_missing_or_ambiguous_date() -> None:
    retriever = FakeRetriever([])
    temporal = FakeTemporalRepository([])
    historical = HistoricalRetriever(retriever, temporal)

    with pytest.raises(ValueError, match="unambiguous"):
        historical.retrieve(_plan(missing=["query_date"]), query_date=None)


def test_excludes_future_provisions_using_authoritative_rows() -> None:
    retriever = FakeRetriever([_result("future"), _result("valid")])
    temporal = FakeTemporalRepository(
        [
            SimpleNamespace(
                provision_id="future",
                review_status="ACCEPTED",
                effective_from=date(2025, 1, 1),
                effective_to=None,
            ),
            SimpleNamespace(
                provision_id="valid",
                review_status="ACCEPTED",
                effective_from=date(2020, 1, 1),
                effective_to=None,
            ),
        ]
    )

    result = HistoricalRetriever(retriever, temporal).retrieve(_plan(), query_date=QUERY_DATE)

    assert [item.provision_id for item in result.results] == ["valid"]
    assert result.applied_date == QUERY_DATE
    assert temporal.arguments == (QUERY_DATE, ["future", "valid"])


def test_applied_date_and_temporal_filter_are_forwarded() -> None:
    retriever = FakeRetriever([_result("valid")])
    temporal = FakeTemporalRepository(
        [SimpleNamespace(provision_id="valid", review_status="ACCEPTED")]
    )

    result = HistoricalRetriever(retriever, temporal).retrieve(_plan(), query_date=QUERY_DATE)

    assert result.applied_date == QUERY_DATE
    assert retriever.query_filter is not None
