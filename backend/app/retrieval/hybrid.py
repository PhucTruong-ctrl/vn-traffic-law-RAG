"""Hybrid dense+sparse retrieval with exact-reference promotion."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from qdrant_client import QdrantClient, models

from app.config import RetrievalSettings, get_retrieval_settings
from app.retrieval.contracts import CandidateSet, RetrievalResult, result_from_payload
from app.retrieval.exact_lookup import ExactLookup
from app.retrieval.filters import build_temporal_filter
from app.retrieval.qdrant_store import DENSE_VECTOR_NAME, PROVISION_ALIAS, SPARSE_VECTOR_NAME
from app.retrieval.embedding import EmbeddingProvider
from app.retrieval.sparse import SparseEncoder, sparse_vector_dict


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]],
    *,
    k: int = 60,
    weights: Sequence[float] | None = None,
) -> list[tuple[str, float]]:
    """Fuse ranked IDs using weighted reciprocal rank fusion."""
    if k < 1:
        raise ValueError("k must be at least 1")
    if weights is not None and len(weights) != len(rankings):
        raise ValueError("weights must match rankings")
    scores: dict[str, float] = {}
    for channel, ranking in enumerate(rankings):
        weight = 1.0 if weights is None else weights[channel]
        for rank, provision_id in enumerate(ranking, start=1):
            scores[provision_id] = scores.get(provision_id, 0.0) + weight / (k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))


class HybridRetriever:
    """Retrieve via Qdrant's dense/sparse prefetch and RRF fusion."""

    def __init__(
        self,
        client: QdrantClient,
        embedder: EmbeddingProvider,
        encoder: SparseEncoder,
        exact_lookup: ExactLookup | None = None,
        *,
        collection: str = PROVISION_ALIAS,
        settings: RetrievalSettings | None = None,
    ) -> None:
        self._client = client
        self._embedder = embedder
        self._encoder = encoder
        self._exact_lookup = exact_lookup
        self._collection = collection
        self._settings = settings or get_retrieval_settings()

    def retrieve(
        self,
        query: str,
        *,
        query_date: date,
        vehicle_type: str | None = None,
        exact_reference: Mapping[str, str | None] | None = None,
    ) -> CandidateSet:
        """Return fused candidates, retaining exact matches outside Qdrant fusion."""
        dense_vector = self._embedder.embed([query])[0]
        sparse_weights = self._encoder.encode(query)
        query_filter = (
            build_temporal_filter(query_date, vehicle_type=vehicle_type)
            if self._settings.temporal_filter_enabled
            else None
        )
        prefetch: list[models.Prefetch] = [
            models.Prefetch(
                query=dense_vector,
                using=DENSE_VECTOR_NAME,
                limit=self._settings.dense_prefetch,
                filter=query_filter,
            )
        ]
        if sparse_weights:
            prefetch.append(
                models.Prefetch(
                    query=models.SparseVector(**sparse_vector_dict(sparse_weights)),
                    using=SPARSE_VECTOR_NAME,
                    limit=self._settings.sparse_prefetch,
                    filter=query_filter,
                )
            )
        response = self._client.query_points(
            collection_name=self._collection,
            prefetch=prefetch,
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=self._settings.fusion_limit,
            with_payload=True,
        )
        points = getattr(response, "points", response)
        results = [
            result_from_payload(
                _payload(point),
                rank=rank,
                score=getattr(point, "score", None),
                source="hybrid",
            ).model_copy(update={"retrieval_sources": ["dense", "sparse"]})
            for rank, point in enumerate(points, start=1)
        ]
        exact = self._exact_candidates(exact_reference, query_date, vehicle_type)
        exact_ids = {result.provision_id for result in exact}
        merged = _merge_exact(results, exact)
        # Exact candidates are intentionally promoted after fusion, never dropped.
        merged.sort(key=lambda result: (result.provision_id not in exact_ids, result.rank, result.provision_id))
        merged = [result.model_copy(update={"rank": rank}) for rank, result in enumerate(merged, start=1)]
        exact_results = [result for result in merged if result.provision_id in exact_ids]
        merged = exact_results + [
            result for result in merged if result.provision_id not in exact_ids
        ][: self._settings.final_top_k]
        merged = [result.model_copy(update={"rank": rank}) for rank, result in enumerate(merged, start=1)]
        return CandidateSet(query=query, results=merged, applied_date=query_date)

    def _exact_candidates(
        self,
        reference: Mapping[str, str | None] | None,
        query_date: date,
        vehicle_type: str | None,
    ) -> list[RetrievalResult]:
        if not reference or self._exact_lookup is None or not self._settings.exact_lookup_enabled:
            return []
        document_number = reference.get("document_number")
        if not document_number:
            return []
        candidates = self._exact_lookup.lookup(
            document_number=document_number,
            article=reference.get("article"),
            clause=reference.get("clause"),
            point=reference.get("point"),
            query_date=query_date,
            vehicle_type=vehicle_type,
        )
        return candidates.results


def _payload(point: Any) -> Mapping[str, object]:
    payload = getattr(point, "payload", None)
    if not isinstance(payload, Mapping):
        raise ValueError("hybrid retrieval point is missing a payload")
    return payload


def _merge_exact(results: Sequence[RetrievalResult], exact: Sequence[RetrievalResult]) -> list[RetrievalResult]:
    by_id = {result.provision_id: result for result in results}
    for result in exact:
        current = by_id.get(result.provision_id)
        if current is None:
            by_id[result.provision_id] = result.model_copy(update={"retrieval_sources": [*result.retrieval_sources, "exact"]})
        else:
            sources = list(dict.fromkeys([*current.retrieval_sources, *result.retrieval_sources, "exact"]))
            by_id[result.provision_id] = current.model_copy(update={"retrieval_sources": sources})
    return list(by_id.values())


__all__ = ["HybridRetriever", "reciprocal_rank_fusion"]
