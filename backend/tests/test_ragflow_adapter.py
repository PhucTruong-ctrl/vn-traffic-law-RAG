from __future__ import annotations

from collections.abc import Sequence

from app.ingestion.adapters.ragflow_adapter import RAGFlowIngestionPort, RAGFlowRetrievalPort
from app.ingestion.retrieval_units import RetrievalUnit
from app.retrieval.contracts import CandidateSet


class FakeIngest:
    def ingest(self, units: Sequence[RetrievalUnit]) -> int:
        return len(units)


class FakeSearch:
    def search(self, query: str, *, limit: int = 10) -> CandidateSet:
        return CandidateSet(query=query, results=[], applied_date=None)


def test_ragflow_ports_are_provider_neutral() -> None:
    assert isinstance(FakeIngest(), RAGFlowIngestionPort)
    assert isinstance(FakeSearch(), RAGFlowRetrievalPort)
    assert FakeSearch().search("Điều 5").query == "Điều 5"
