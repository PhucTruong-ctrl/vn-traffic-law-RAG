"""Dense-vector retrieval over the active Qdrant provision collection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from qdrant_client import QdrantClient, models

from app.retrieval.contracts import CandidateSet, result_from_payload
from app.retrieval.embedding import EmbeddingProvider
from app.retrieval.qdrant_store import DENSE_VECTOR_NAME, PROVISION_ALIAS


class DenseRetriever:
    """Retrieve accepted legal provisions using the named dense vector."""

    def __init__(
        self,
        client: QdrantClient,
        embedder: EmbeddingProvider,
        *,
        collection: str = PROVISION_ALIAS,
        top_k: int = 30,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._collection = collection
        self._top_k = top_k

    def search(
        self,
        query: str,
        *,
        query_filter: models.Filter | None = None,
        limit: int | None = None,
    ) -> CandidateSet:
        """Embed ``query`` and map Qdrant hits into the shared result contract."""
        vector = self._embedder.embed([query])[0]
        response = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            using=DENSE_VECTOR_NAME,
            query_filter=query_filter,
            limit=self._top_k if limit is None else limit,
            with_payload=True,
        )

        results = [
            result_from_payload(
                _payload_for(point),
                rank=rank,
                score=getattr(point, "score", None),
                source="dense",
            )
            for rank, point in enumerate(response.points, start=1)
        ]
        return CandidateSet(query=query, results=results, applied_date=None)


def _payload_for(point: Any) -> Mapping[str, object]:
    payload = getattr(point, "payload", None)
    if not isinstance(payload, Mapping):
        raise ValueError("dense retrieval point is missing a payload")
    return payload


__all__ = ["DenseRetriever"]
