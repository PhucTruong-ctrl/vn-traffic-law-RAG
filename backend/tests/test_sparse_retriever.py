"""Focused tests for sparse retrieval Qdrant wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from qdrant_client import models

from app.retrieval.sparse import SparseEncoder, tokenize_vietnamese
from app.retrieval.sparse_retriever import SparseRetriever


_PAYLOAD = {
    "review_status": "ACCEPTED",
    "provision_id": "nd-168-2024__dieu-7__diem-d",
    "provision_version": 1,
    "document_id": "nd-168-2024",
    "document_version_id": "version-1",
    "text": "Mức phạt đối với xe đạp.",
    "source_text": "d) Mức phạt đối với xe đạp.",
    "parent_context": None,
    "document_number": "168/2024/NĐ-CP",
    "article": "7",
    "clause": None,
    "point": "d",
    "effective_from": "2024-01-01",
    "effective_to": None,
    "page_number": 1,
}


@dataclass
class _Point:
    payload: dict[str, object]
    score: float


class _Encoder:
    version = "test"

    def __init__(self, weights: dict[int, float] | None = None) -> None:
        self.weights = weights if weights is not None else {2: 0.75, 7: 0.25}
        self.queries: list[str] = []

    def encode(self, text: str) -> dict[int, float]:
        self.queries.append(text)
        return self.weights

    def encode_batch(self, texts: list[str]) -> list[dict[int, float]]:
        return [self.encode(text) for text in texts]

    def fit(self, documents: list[str]) -> None:
        del documents


class _Client:
    def __init__(self, points: list[_Point]) -> None:
        self.points = points
        self.calls: list[dict[str, Any]] = []

    def query_points(self, **kwargs: Any) -> list[_Point]:
        self.calls.append(kwargs)
        return self.points


def test_sparse_search_uses_named_vector_filter_limit_and_preserves_scores() -> None:
    encoder = _Encoder()
    client = _Client([_Point(_PAYLOAD, 0.8125)])
    query_filter = models.Filter(must=[])

    candidates = SparseRetriever(client, encoder, collection="test", top_k=9).search(
        "xe đạp bị phạt",
        query_filter=query_filter,
    )

    assert encoder.queries == ["xe đạp bị phạt"]
    call = client.calls[0]
    assert call["collection_name"] == "test"
    assert call["using"] == "sparse"
    assert call["limit"] == 9
    assert call["query_filter"] is query_filter
    assert call["with_payload"] is True
    assert call["query"].indices == [2, 7]
    assert call["query"].values == [0.75, 0.25]
    assert candidates.query == "xe đạp bị phạt"
    assert candidates.results[0].fused_score == pytest.approx(0.8125)
    assert candidates.results[0].retrieval_sources == ["sparse"]


def test_sparse_search_limit_overrides_default() -> None:
    client = _Client([_Point(_PAYLOAD, 1.0)])
    SparseRetriever(client, _Encoder(), top_k=30).search("phạt", limit=4)
    assert client.calls[0]["limit"] == 4


def test_empty_sparse_query_does_not_call_qdrant() -> None:
    encoder = _Encoder(weights={})
    client = _Client([])

    result = SparseRetriever(client, encoder).search("unseen")

    assert result.results == []
    assert client.calls == []


def test_sparse_provider_errors_are_not_silenced() -> None:
    class FailingEncoder(_Encoder):
        def encode(self, text: str) -> dict[int, float]:
            raise RuntimeError(f"provider failed for {text}")

    with pytest.raises(RuntimeError, match="provider failed"):
        SparseRetriever(_Client([]), FailingEncoder()).search("xe đạp")


def test_tokenizer_preserves_diacritics_and_d_distinction() -> None:
    assert tokenize_vietnamese("Điểm đ: xe đạp, đường bộ") == [
        "điểm",
        "đ",
        "xe",
        "đạp",
        "đường",
        "bộ",
    ]


def test_invalid_top_k_and_limit_are_rejected() -> None:
    with pytest.raises(ValueError, match="top_k"):
        SparseRetriever(_Client([]), _Encoder(), top_k=0)
    with pytest.raises(ValueError, match="limit"):
        SparseRetriever(_Client([]), _Encoder()).search("phạt", limit=0)


