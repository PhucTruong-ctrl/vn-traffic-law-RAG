from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from app.config import RetrievalSettings
from app.retrieval.contracts import CandidateSet, RetrievalResult
from app.retrieval.hybrid import HybridRetriever, _merge_exact, reciprocal_rank_fusion

_PAYLOAD = {
    "provision_id": "p-1",
    "provision_version": 1,
    "document_id": "doc-1",
    "document_version_id": "version-1",
    "document_number": "168/2024/NĐ-CP",
    "article": "7",
    "clause": None,
    "point": "đ",
    "text": "Nội dung",
    "source_text": "Gốc",
    "parent_context": None,
    "effective_from": "2025-01-01",
    "effective_to": None,
    "page_number": 1,
    "review_status": "ACCEPTED",
}


@dataclass
class Point:
    payload: dict[str, object]
    score: float


def test_rrf_is_weighted_and_deterministic() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=1, weights=[2.0, 1.0])
    assert fused[0][0] == "b"
    assert fused[0][1] == pytest.approx(7 / 6)
    assert fused[1:] == [("a", 1.0), ("c", 1 / 3)]


def test_retrieve_uses_prefetch_rrf_and_retains_exact() -> None:
    class Client:
        def __init__(self) -> None:
            self.kwargs = None

        def query_points(self, **kwargs: object) -> object:
            self.kwargs = kwargs
            return SimpleNamespace(points=[Point(_PAYLOAD, 0.5)])

    class Embedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2]]

    class Encoder:
        def encode(self, text: str) -> dict[int, float]:
            return {1: 1.0}

    exact_result = RetrievalResult(
        rank=1,
        provision_id="exact",
        provision_version=1,
        document_id="doc-1",
        document_version_id="version-1",
        text="exact",
        source_text="exact",
        parent_context=None,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause=None,
        point="đ",
        effective_from=date(2025, 1, 1),
        effective_to=None,
        page_number=1,
        retrieval_sources=["exact"],
        fused_score=None,
        added_by=None,
        source_id=None,
        depth=0,
    )

    class Exact:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] | None = None

        def lookup(self, **kwargs: object) -> CandidateSet:
            self.kwargs = kwargs
            return CandidateSet(query="ref", results=[exact_result], applied_date=date(2025, 1, 1))

    class Temporal:
        def valid_provisions(self, query_date: date, *, provision_ids: set[str]):
            return [SimpleNamespace(provision_id="p-1")]

    client = Client()
    exact = Exact()
    result = HybridRetriever(
        client,
        Embedder(),
        Encoder(),
        exact,
        temporal_repository=Temporal(),
        settings=RetrievalSettings(final_top_k=1),
    ).retrieve(
        "phạt",
        query_date=date(2025, 1, 1),
        exact_reference={"document_number": "168/2024/NĐ-CP", "article": "7", "point": "đ"},
    )
    assert [item.provision_id for item in result.results] == ["exact", "p-1"]
    assert result.results[1].retrieval_sources == ["hybrid"]
    assert client.kwargs["query"].rrf.k == 60
    assert client.kwargs["query"].rrf.weights == [1.0, 1.0]
    assert len(client.kwargs["prefetch"]) == 2
    assert client.kwargs["prefetch"][0].limit == 30
    assert client.kwargs["limit"] == 20
    assert exact.kwargs is not None
    assert exact.kwargs["derived_provision_ids"] == {"p-1"}


def test_retrieve_uses_valid_dense_request_when_sparse_encoding_is_empty() -> None:
    class Client:
        def __init__(self) -> None:
            self.kwargs = None

        def query_points(self, **kwargs: object) -> object:
            self.kwargs = kwargs
            return SimpleNamespace(points=[Point(_PAYLOAD, 0.5)])

    class Embedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2]]

    class EmptyEncoder:
        def encode(self, text: str) -> dict[int, float]:
            return {}

    client = Client()
    result = HybridRetriever(client, Embedder(), EmptyEncoder()).retrieve(
        "phạt", query_date=date(2025, 1, 1)
    )

    assert result.results[0].retrieval_sources == ["hybrid"]
    assert client.kwargs is not None
    assert len(client.kwargs["prefetch"]) == 1
    assert client.kwargs["prefetch"][0].using == "dense"
    assert client.kwargs["query"].rrf.weights == [1.0]



def test_retrieve_preserves_explicit_payload_retrieval_sources() -> None:
    class Client:
        def query_points(self, **kwargs: object) -> object:
            return SimpleNamespace(
                points=[
                    Point({**_PAYLOAD, "retrieval_sources": ["dense"]}, 0.5)
                ]
            )

    class Embedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2]]

    class Encoder:
        def encode(self, text: str) -> dict[int, float]:
            return {}

    result = HybridRetriever(Client(), Embedder(), Encoder()).retrieve(
        "phạt", query_date=date(2025, 1, 1)
    )

    assert result.results[0].retrieval_sources == ["dense"]

def test_retrieve_post_checks_qdrant_ids_against_authoritative_temporal_rows() -> None:
    stale_payload = {**_PAYLOAD, "provision_id": "stale"}

    class Client:
        def query_points(self, **kwargs: object) -> object:
            return SimpleNamespace(
                points=[Point(_PAYLOAD, 0.5), Point(stale_payload, 0.4)]
            )

    class Embedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1, 0.2]]

    class Encoder:
        def encode(self, text: str) -> dict[int, float]:
            return {}

    class Temporal:
        def __init__(self) -> None:
            self.ids = None

        def valid_provisions(self, query_date: date, *, provision_ids: set[str]):
            self.ids = provision_ids
            return [SimpleNamespace(provision_id="p-1")]

    temporal = Temporal()
    result = HybridRetriever(
        Client(), Embedder(), Encoder(), temporal_repository=temporal
    ).retrieve("phạt", query_date=date(2025, 1, 1))

    assert [item.provision_id for item in result.results] == ["p-1"]
    assert temporal.ids == {"p-1", "stale"}

def test_merge_exact_uses_canonical_fields_and_only_merges_sources() -> None:
    derived = RetrievalResult(
        rank=1,
        provision_id="p-1",
        provision_version=1,
        document_id="stale-doc",
        document_version_id="stale-version",
        text="stale text",
        source_text="stale source",
        parent_context="stale parent",
        document_number="stale-document",
        article="stale article",
        clause="stale clause",
        point="d",
        effective_from=date(2020, 1, 1),
        effective_to=date(2021, 1, 1),
        page_number=99,
        retrieval_sources=["dense", "sparse"],
        fused_score=0.8,
        added_by=None,
        source_id="stale-source",
        depth=0,
    )
    canonical = derived.model_copy(
        update={
            "document_id": "canonical-doc",
            "document_version_id": "canonical-version",
            "text": "canonical text",
            "source_text": "canonical source",
            "parent_context": None,
            "document_number": "168/2024/NĐ-CP",
            "article": "7",
            "clause": None,
            "point": "đ",
            "effective_from": date(2025, 1, 1),
            "effective_to": None,
            "page_number": 3,
            "retrieval_sources": ["exact"],
            "fused_score": None,
            "source_id": "canonical-source",
        }
    )

    merged = _merge_exact([derived], [canonical])

    assert merged == [
        canonical.model_copy(update={"retrieval_sources": ["dense", "sparse", "exact"]})
    ]

