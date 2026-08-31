"""Jina reranking adapter for retrieved legal provisions."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from app.config import get_retrieval_settings
from app.retrieval.contracts import RetrievalResult


class JinaRerankerClient(Protocol):
    """Small boundary matching the Jina SDK's rerank operation."""

    def rerank(
        self,
        *,
        model: str,
        query: str,
        documents: Sequence[str],
        top_n: int,
    ) -> Any: ...


@dataclass(frozen=True)
class RerankFailure:
    """Explicit provider failure retained for workflow observability."""

    error: Exception


class Reranker:
    """Rerank candidates while making provider failure non-destructive."""

    def __init__(
        self,
        client: JinaRerankerClient,
        *,
        model: str | None = None,
        final_top_k: int | None = None,
        buffer: int | None = None,
    ) -> None:
        settings = get_retrieval_settings()
        self._client = client
        self._model = model or settings.reranker_model
        self._final_top_k = final_top_k if final_top_k is not None else settings.final_top_k
        self._buffer = buffer if buffer is not None else settings.reranker_buffer
        self._cache: dict[str, dict[str, float]] = {}
        self.last_failure: RerankFailure | None = None

    @property
    def model(self) -> str:
        return self._model

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalResult],
        top_n: int | None = None,
    ) -> list[RetrievalResult]:
        """Return provider-ranked candidates, or the original order on failure."""
        original = list(candidates)
        self.last_failure = None
        if not original:
            return []

        limit = min(
            len(original),
            max(1, top_n if top_n is not None else self._final_top_k + self._buffer),
            self._final_top_k + self._buffer,
        )
        key = self._cache_key(query, original)
        try:
            scores_by_provision = self._cache.get(key)
            if scores_by_provision is None:
                response = self._client.rerank(
                    model=self._model,
                    query=query,
                    documents=[candidate.text for candidate in original],
                    top_n=limit,
                )
                ranked = self._parse_response(response, len(original), limit)
                scores_by_provision = {
                    original[index].provision_id: score for index, score in ranked
                }
                self._cache[key] = scores_by_provision
            ordered = sorted(
                enumerate(original),
                key=lambda item: (
                    -scores_by_provision.get(item[1].provision_id, float("-inf")),
                    item[0],
                ),
            )
            return [
                candidate.model_copy(
                    update={
                        "rank": rank,
                        "fused_score": scores_by_provision.get(candidate.provision_id),
                    }
                )
                for rank, (_, candidate) in enumerate(ordered, 1)
            ]
        except Exception as error:
            self.last_failure = RerankFailure(error)
            return [candidate.model_copy() for candidate in original]

    def _cache_key(self, query: str, candidates: Sequence[RetrievalResult]) -> str:
        provision_ids = "\x1f".join(sorted(candidate.provision_id for candidate in candidates))
        material = f"{query}\x1f{provision_ids}\x1f{self._model}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_response(
        response: Any, candidate_count: int, limit: int
    ) -> list[tuple[int, float]]:
        items = response.get("data", response) if isinstance(response, Mapping) else response
        if not isinstance(items, (list, tuple)) and hasattr(items, "results"):
            items = items.results
        parsed: list[tuple[int, float]] = []
        for item in items:
            index = item.get("index") if isinstance(item, Mapping) else item.index
            score = (
                item.get("relevance_score")
                if isinstance(item, Mapping)
                else getattr(item, "relevance_score", getattr(item, "score", None))
            )
            if not isinstance(index, int) or not 0 <= index < candidate_count:
                raise ValueError("Jina returned an invalid candidate index")
            if not isinstance(score, (int, float)):
                raise ValueError("Jina returned an invalid relevance score")
            parsed.append((index, float(score)))
        if len(parsed) > limit or len({index for index, _ in parsed}) != len(parsed):
            raise ValueError("Jina returned invalid reranking results")
        return parsed


__all__ = ["JinaRerankerClient", "RerankFailure", "Reranker"]
