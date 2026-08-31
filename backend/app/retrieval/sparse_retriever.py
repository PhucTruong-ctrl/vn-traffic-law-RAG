"""Sparse retrieval over the active legal-provision Qdrant collection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qdrant_client import QdrantClient, models

from app.retrieval.contracts import CandidateSet, result_from_payload
from app.retrieval.qdrant_store import PROVISION_ALIAS, SPARSE_VECTOR_NAME
from app.retrieval.sparse import SparseEncoder, sparse_vector_dict


class SparseRetriever:
    """Retrieve accepted provisions using the indexed sparse vector."""

    def __init__(
        self,
        client: QdrantClient,
        encoder: SparseEncoder,
        *,
        collection: str = PROVISION_ALIAS,
        top_k: int = 30,
    ) -> None:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        self._client = client
        self._encoder = encoder
        self._collection = collection
        self._top_k = top_k

    def search(
        self,
        query: str,
        *,
        query_filter: models.Filter | None = None,
        limit: int | None = None,
    ) -> CandidateSet:
        """Search ``query`` and preserve Qdrant scores in shared results."""
        requested_limit = self._top_k if limit is None else limit
        if requested_limit < 1:
            raise ValueError("limit must be at least 1")

        weights = self._encoder.encode(query)
        if not weights:
            return CandidateSet(query=query, results=[], applied_date=None)

        encoded = sparse_vector_dict(weights)
        response = self._client.query_points(
            collection_name=self._collection,
            query=models.SparseVector(**encoded),
            using=SPARSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=requested_limit,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        results = [
            result_from_payload(
                _payload(point),
                rank=rank,
                score=getattr(point, "score", None),
                source="sparse",
            )
            for rank, point in enumerate(points, start=1)
        ]
        return CandidateSet(query=query, results=results, applied_date=None)


def _payload(point: Any) -> Mapping[str, object]:
    payload = getattr(point, "payload", None)
    if not isinstance(payload, Mapping):
        raise ValueError("sparse retrieval point is missing its payload")
    return payload


__all__ = ["SparseRetriever"]
