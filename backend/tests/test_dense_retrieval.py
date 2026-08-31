from types import SimpleNamespace

import pytest
from qdrant_client import models

from app.retrieval.contracts import CandidateSet
from app.retrieval.dense import DenseRetriever
from app.retrieval.embedding import EmbeddingProviderError


@pytest.fixture
def payload() -> dict[str, object]:
    return {
        "provision_id": "p-1",
        "provision_version": 1,
        "document_id": "doc-1",
        "document_version_id": "version-1",
        "document_number": "168/2024/NĐ-CP",
        "article": "7",
        "clause": None,
        "point": "đ",
        "text": "Nội dung tìm kiếm",
        "source_text": "Nội dung gốc",
        "parent_context": None,
        "effective_from": "2025-01-01",
        "effective_to": None,
        "page_number": 4,
        "review_status": "ACCEPTED",
    }


def test_search_embeds_query_and_maps_hits(payload: dict[str, object]) -> None:
    class Embedder:
        def __init__(self) -> None:
            self.queries: list[list[str]] = []

        def embed(self, texts: list[str]) -> list[list[float]]:
            self.queries.append(texts)
            return [[0.1, 0.2]]

    class Client:
        def __init__(self) -> None:
            self.kwargs: dict[str, object] = {}

        def query_points(self, **kwargs: object) -> object:
            self.kwargs = kwargs
            return SimpleNamespace(points=[SimpleNamespace(payload=payload, score=0.9)])

    embedder = Embedder()
    client = Client()
    query_filter = models.Filter()
    candidates = DenseRetriever(client, embedder, top_k=30).search(
        "mức phạt", query_filter=query_filter
    )

    assert isinstance(candidates, CandidateSet)
    assert embedder.queries == [["mức phạt"]]
    assert candidates.query == "mức phạt"
    assert candidates.results[0].provision_id == "p-1"
    assert candidates.results[0].retrieval_sources == ["dense"]
    assert client.kwargs == {
        "collection_name": "legal_provisions_active",
        "query": [0.1, 0.2],
        "using": "dense",
        "query_filter": query_filter,
        "limit": 30,
        "with_payload": True,
    }


def test_search_honors_custom_collection_and_limit(payload: dict[str, object]) -> None:
    class Embedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0]]

    class Client:
        def query_points(self, **kwargs: object) -> object:
            assert kwargs["collection_name"] == "provision_test"
            assert kwargs["limit"] == 2
            assert kwargs["query_filter"] is None
            return SimpleNamespace(points=[])

    candidates = DenseRetriever(Client(), Embedder(), collection="provision_test", top_k=30).search(
        "query", limit=2
    )
    assert candidates.results == []


def test_provider_error_propagates() -> None:
    error = EmbeddingProviderError("provider unavailable")

    class Embedder:
        def embed(self, texts: list[str]) -> list[list[float]]:
            raise error

    class Client:
        def query_points(self, **kwargs: object) -> object:
            pytest.fail("Qdrant must not be queried when embedding fails")

    with pytest.raises(EmbeddingProviderError) as raised:
        DenseRetriever(Client(), Embedder()).search("query")
    assert raised.value is error
