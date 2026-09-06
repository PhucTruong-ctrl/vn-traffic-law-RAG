from __future__ import annotations

from collections.abc import Sequence

from app.evaluation.ragflow_adapter import map_citation, map_citations
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


def test_ragflow_citation_mapping_accepts_canonical_fields_and_case_normalization() -> None:
    canonical_ids = {"nd-168-2024:article:5", "nd-168-2024:clause:2"}

    assert map_citation({"canonical_provision_id": "nd-168-2024:article:5"}, canonical_ids) == "nd-168-2024:article:5"
    assert map_citation({"provision_id": "ND-168-2024:ARTICLE:5"}, canonical_ids) == "nd-168-2024:article:5"
    assert map_citation({"id": "nd-168-2024:clause:2"}, canonical_ids) == "nd-168-2024:clause:2"


def test_ragflow_mapping_counts_unmappable_citations_in_accuracy() -> None:
    result = map_citations(
        [
            {"id": "nd-168-2024:article:5"},
            {"id": "nd-168-2024:article:999"},
            {"text": "Điều 5"},
        ],
        {"nd-168-2024:article:5"},
    )

    assert result == {"mapped": ["nd-168-2024:article:5"], "unmappable": 2, "mapping_accuracy": 1 / 3}


def test_ragflow_mapping_does_not_guess_from_text_or_partial_ids() -> None:
    canonical_ids = {"nd-168-2024:article:5"}

    assert map_citation({"id": "nd-168-2024:article:5-extra"}, canonical_ids) is None
    assert map_citation({"text": "Điều 5"}, canonical_ids) is None
