"""Small OpenRouter embedding client using only Python standard library."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class EmbeddingError(RuntimeError):
    """Raised when the embedding request cannot be completed or validated."""


class OpenRouterEmbeddingClient:
    """Batch embedding client for OpenRouter's OpenAI-compatible endpoint."""

    endpoint = "https://openrouter.ai/api/v1/embeddings"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        timeout: float | None = None,
        batch_size: int | None = None,
        endpoint: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY", "")
        self.model = model or os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
        self.dimensions = dimensions or int(os.getenv("EMBEDDING_DIMENSIONS", "768"))
        self.timeout = timeout or float(os.getenv("EMBEDDING_TIMEOUT", "60"))
        self.batch_size = batch_size or int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
        self.endpoint = endpoint or os.getenv("OPENROUTER_EMBEDDINGS_URL", self.endpoint)
        if self.dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed one request-sized sequence, preserving response order."""
        values = [str(text) for text in texts]
        if not values:
            return []
        if not self.api_key:
            raise EmbeddingError("OPENROUTER_API_KEY is required for OpenRouter embeddings")
        body = {
            "input": values,
            "model": self.model,
            "dimensions": self.dimensions,
            "encoding_format": "float",
        }
        request = Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise EmbeddingError(f"OpenRouter embeddings HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise EmbeddingError(f"OpenRouter embeddings request failed: {exc}") from exc

        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list) or len(items) != len(values):
            raise EmbeddingError("OpenRouter response must contain one embedding per input")
        try:
            ordered = sorted(items, key=lambda item: int(item["index"]))
            vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingError("OpenRouter response contains invalid embedding data") from exc
        if any(len(vector) != self.dimensions for vector in vectors):
            raise EmbeddingError(
                "OpenRouter returned an embedding with unexpected dimension; "
                f"expected {self.dimensions}"
            )
        return vectors

    def embed_batch(self, texts: Iterable[str]) -> list[list[float]]:
        """Embed arbitrary input in bounded batches, preserving input order."""
        values = [str(text) for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(values), self.batch_size):
            vectors.extend(self.embed(values[start : start + self.batch_size]))
        return vectors

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        """Compatibility spelling for callers that use a text-oriented API."""
        return self.embed_batch(texts)


__all__ = ["EmbeddingError", "OpenRouterEmbeddingClient"]
