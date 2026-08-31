from datetime import date
from types import SimpleNamespace

from app.retrieval.contracts import RetrievalResult
from app.retrieval.reranker import Reranker


def candidate(provision_id: str, rank: int) -> RetrievalResult:
    return RetrievalResult(
        rank=rank,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc",
        document_version_id="version",
        text=f"text {provision_id}",
        source_text=f"source {provision_id}",
        parent_context=None,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause=None,
        point=None,
        effective_from=date(2025, 1, 1),
        effective_to=None,
        page_number=1,
        retrieval_sources=["dense"],
        fused_score=None,
        added_by=None,
        source_id=None,
        depth=0,
    )


def test_success_reranks_and_caps_provider_request() -> None:
    class Client:
        def __init__(self) -> None:
            self.calls = 0
            self.top_n = None

        def rerank(self, **kwargs: object) -> list[object]:
            self.calls += 1
            self.top_n = kwargs["top_n"]
            return [
                SimpleNamespace(index=1, relevance_score=0.9),
                SimpleNamespace(index=0, relevance_score=0.2),
            ]

    client = Client()
    results = Reranker(client, final_top_k=1, buffer=1).rerank(
        "query", [candidate("p1", 1), candidate("p2", 2), candidate("p3", 3)]
    )
    assert client.top_n == 2
    assert [result.provision_id for result in results] == ["p2", "p1", "p3"]
    assert [result.rank for result in results] == [1, 2, 3]


def test_failure_returns_original_order_and_signal() -> None:
    class Client:
        def rerank(self, **kwargs: object) -> object:
            raise RuntimeError("unavailable")

    original = [candidate("p1", 1), candidate("p2", 2)]
    reranker = Reranker(Client())
    results = reranker.rerank("query", original)
    assert [result.provision_id for result in results] == ["p1", "p2"]
    assert reranker.last_failure is not None
    assert str(reranker.last_failure.error) == "unavailable"


def test_successful_response_is_cached() -> None:
    class Client:
        calls = 0

        def rerank(self, **kwargs: object) -> list[object]:
            self.calls += 1
            return [SimpleNamespace(index=0, relevance_score=1.0)]

    client = Client()
    reranker = Reranker(client)
    items = [candidate("p1", 1)]
    reranker.rerank("query", items)
    reranker.rerank("query", list(reversed(items)))
    assert client.calls == 1
