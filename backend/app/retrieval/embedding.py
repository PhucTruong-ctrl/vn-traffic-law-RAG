"""Embedding provider adapters (VNLRAG-41).

Dense-embedding adapters for the Suite B candidates (doc 04 §4.8, ADR-013):

- :class:`GeminiEmbeddingAdapter` — Gemini Embedding 2 via the Gemini REST
  ``batchEmbedContents`` endpoint. The model's default output dimension is
  3072; the adapter always *requests* the configured dimension (Suite B test
  config: 768) through ``outputDimensionality`` and verifies the response.
- :class:`JinaEmbeddingAdapter` — Jina Embeddings v5 via the Jina
  ``/v1/embeddings`` REST endpoint: ``jina-embeddings-v5-text-nano`` is 768
  dims and ``jina-embeddings-v5-text-small`` is 1024 dims (doc 04 §4.8.2).

**No permanent model choice is claimed here.** The factory selects the adapter
purely from configuration (``EMBEDDING_PROVIDER``/``EMBEDDING_MODEL``); Suite B
(E1-E3) decides the production model from benchmark evidence, never beforehand
(doc 00 §7, ADR-013). Changing the production model requires a collection
rebuild + alias switch (doc 03 §3.11.7) — two embedding spaces are never mixed.

Both adapters share the same HTTP plumbing: bounded retries with exponential
backoff on 429/5xx (max ``max_retries`` retries, ``Retry-After`` respected),
no unbounded loops, and per-call token usage logged and accumulated for cost
tracking. API keys are read from configuration only (``GEMINI_API_KEY`` /
``JINA_API_KEY``); a missing key raises :class:`ConfigError` at call time.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from app.config import EmbeddingSettings

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigError",
    "EmbeddingDimensionError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "GeminiEmbeddingAdapter",
    "JinaEmbeddingAdapter",
    "VersionedEmbeddingCache",
    "embedding_cache_key",
    "get_embedding_provider",
]

#: Default REST base URLs (proxy/deployment overrides are not needed this phase).
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
JINA_API_BASE_URL = "https://api.jina.ai"

#: Backoff base: delays are ``base * 2 ** (attempt - 1)`` — 1s, 2s, 4s for the
#: default 3 retries (bounded, no unbounded loops).
BACKOFF_BASE_SECONDS = 1.0

#: Cap on a server-provided ``Retry-After`` so a stale or hostile header can
#: never stall a job; retries stay bounded in count AND wall-clock time.
MAX_RETRY_AFTER_SECONDS = 120.0

#: Module-level sleep hook so tests can fast-forward backoff without touching
#: the global ``time`` module.
_sleep: Callable[[float], None] = time.sleep


class ConfigError(RuntimeError):
    """Invalid embedding configuration: missing API key or unsupported provider."""


class EmbeddingProviderError(RuntimeError):
    """The provider API failed (hard 4xx, or after bounded retries)."""


class EmbeddingDimensionError(ValueError):
    """A provider returned a vector whose dimension differs from the configured one."""


class EmbeddingProvider(ABC):
    """Contract every dense-embedding provider adapter implements.

    Attributes:
        name: Provider model identifier (as sent to the API).
        dims: Configured output dimension; :meth:`embed` raises
            :class:`EmbeddingDimensionError` if the provider returns anything else.
        batch_size: Chunk size used by :meth:`embed_batch`.
        total_tokens: Cumulative provider-reported token usage (cost tracking).
        requests: Cumulative count of successful provider round-trips.
    """

    name: str
    dims: int
    batch_size: int
    total_tokens: int
    requests: int

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` in ONE provider round-trip.

        ``len(texts)`` must not exceed the provider's per-request limit; use
        :meth:`embed_batch` for arbitrary input sizes.

        Raises:
            ConfigError: required API key is missing.
            EmbeddingProviderError: provider error after bounded retries, or hard 4xx.
            EmbeddingDimensionError: any returned vector has a wrong dimension.
        """

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` in batches of :attr:`batch_size`, preserving input order."""


class _HttpEmbeddingAdapter(EmbeddingProvider):
    """Shared HTTP/retry/cost/cache plumbing for the REST embedding adapters.

    Concrete adapters implement :meth:`_embed_uncached` (one provider
    round-trip); everything else — batching, versioned caching, bounded retry
    with backoff, dimension verification, cost accounting — lives here.
    """

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        api_key: str,
        key_env_name: str,
        base_url: str,
        client: httpx.Client | None = None,
        cache: VersionedEmbeddingCache | None = None,
        encoder_version: str | None = None,
    ) -> None:
        self.name = settings.model
        self.dims = settings.dimensions
        self.batch_size = settings.batch_size
        self._api_key = api_key
        self._key_env_name = key_env_name
        self._base_url = base_url.rstrip("/")
        self._max_retries = settings.max_retries
        self._client = (
            client if client is not None else httpx.Client(timeout=settings.timeout_seconds)
        )
        self._cache = cache
        self._encoder_version = encoder_version
        self.total_tokens = 0
        self.requests = 0

    # -- Public contract ------------------------------------------------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One provider round-trip, served from the versioned cache when enabled."""
        if not texts:
            return []
        if self._cache is None or self._encoder_version is None:
            return self._embed_uncached(texts)
        keys = [embedding_cache_key(self.name, self._encoder_version, text) for text in texts]
        vectors: list[list[float] | None] = [self._cache.get(key) for key in keys]
        missing = [index for index, vector in enumerate(vectors) if vector is None]
        if missing:
            fresh = self._embed_uncached([texts[index] for index in missing])
            for index, vector in zip(missing, fresh, strict=True):
                vectors[index] = vector
                self._cache.set(keys[index], vector)
        return [vector for vector in vectors if vector is not None]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` in chunks of :attr:`batch_size`, concatenated in order."""
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(self.embed(texts[start : start + self.batch_size]))
        return out

    # -- Subclass hook ---------------------------------------------------------

    @abstractmethod
    def _embed_uncached(self, texts: list[str]) -> list[list[float]]:
        """One provider round-trip, bypassing the cache; updates cost counters."""

    # -- HTTP retry plumbing (bounded, doc 05 §R13) ---------------------------

    def _post_with_retry(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """POST with bounded retries on 429/5xx/transport errors.

        Up to ``max_retries`` retries with exponential backoff; a
        ``Retry-After`` header overrides the backoff delay (capped at
        ``MAX_RETRY_AFTER_SECONDS``). Non-retryable errors raise immediately.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                response = self._client.post(url, params=params, headers=headers, json=json_body)
            except httpx.TransportError as exc:
                if attempt > self._max_retries:
                    raise EmbeddingProviderError(
                        f"{self.name} request failed after {attempt - 1} retries: {exc}"
                    ) from exc
                delay = self._backoff_delay(attempt, None)
                logger.warning(
                    "embedding transport error (attempt %d/%d): %s; retrying in %.1fs",
                    attempt,
                    self._max_retries + 1,
                    exc,
                    delay,
                )
                _sleep(delay)
                continue
            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt > self._max_retries:
                    raise EmbeddingProviderError(
                        f"{self.name} HTTP {response.status_code} after {attempt - 1} retries: "
                        f"{self._error_detail(response)}"
                    ) from None
                delay = self._backoff_delay(attempt, self._retry_after_seconds(response))
                logger.warning(
                    "embedding HTTP %d (attempt %d/%d); retrying in %.1fs",
                    response.status_code,
                    attempt,
                    self._max_retries + 1,
                    delay,
                )
                _sleep(delay)
                continue
            if response.is_error:
                raise EmbeddingProviderError(
                    f"{self.name} HTTP {response.status_code}: {self._error_detail(response)}"
                ) from None
            return response

    def _backoff_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return retry_after
        return BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))

    @staticmethod
    def _retry_after_seconds(response: httpx.Response) -> float | None:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            seconds = float(raw)
        except ValueError:
            logger.debug("ignoring non-numeric Retry-After header %r", raw)
            return None
        capped = min(max(0.0, seconds), MAX_RETRY_AFTER_SECONDS)
        if capped != seconds:
            logger.warning("capping Retry-After %ss to %ss", seconds, MAX_RETRY_AFTER_SECONDS)
        return capped

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            for key in ("message", "detail"):
                message = payload.get(key)
                if isinstance(message, str) and message:
                    return message
            error = payload.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
        text = response.text.strip()
        return (text[:200] + "…") if len(text) > 200 else (text or f"HTTP {response.status_code}")

    # -- Response validation and cost accounting -------------------------------

    def _verified(self, vectors: Sequence[Any], expected_count: int) -> list[list[float]]:
        """Type- and dimension-check provider vectors; raise on any mismatch."""
        if len(vectors) != expected_count:
            raise EmbeddingProviderError(
                f"{self.name} returned {len(vectors)} vectors for {expected_count} texts"
            )
        out: list[list[float]] = []
        for index, vector in enumerate(vectors):
            if not isinstance(vector, (list, tuple)):
                raise EmbeddingProviderError(
                    f"{self.name} returned a non-list vector at index {index}"
                )
            try:
                floats = [float(value) for value in vector]
            except (TypeError, ValueError) as exc:
                raise EmbeddingProviderError(
                    f"{self.name} returned a non-numeric vector at index {index}"
                ) from exc
            if len(floats) != self.dims:
                raise EmbeddingDimensionError(
                    f"{self.name} returned {len(floats)} dims at index {index}, "
                    f"expected {self.dims} (EMBEDDING_DIMENSIONS)"
                )
            out.append(floats)
        return out

    def _account(self, tokens: int) -> None:
        self.total_tokens += tokens
        self.requests += 1
        logger.info(
            "embedding usage: provider=%s model=%s tokens=%d total_tokens=%d requests=%d",
            type(self).__name__,
            self.name,
            tokens,
            self.total_tokens,
            self.requests,
        )

    def _require_api_key(self) -> None:
        if not self._api_key:
            raise ConfigError(
                f"{self.name} requires {self._key_env_name} (or "
                f"EMBEDDING_{self._key_env_name}); set it in the environment or "
                f".env (doc 07 §7.3.3)"
            )


class GeminiEmbeddingAdapter(_HttpEmbeddingAdapter):
    """Gemini Embedding 2 via the Gemini REST ``batchEmbedContents`` endpoint.

    The model's default output dimension is 3072; this adapter always requests
    the configured dimension (Suite B test config: 768, doc 04 §4.8.2) via
    ``outputDimensionality`` and verifies the response dimension. The API key
    comes from ``GEMINI_API_KEY`` (config), never hardcoded; a missing key
    raises :class:`ConfigError` at call time.
    """

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        client: httpx.Client | None = None,
        cache: VersionedEmbeddingCache | None = None,
        encoder_version: str | None = None,
    ) -> None:
        super().__init__(
            settings,
            api_key=settings.gemini_api_key,
            key_env_name="GEMINI_API_KEY",
            base_url=GEMINI_API_BASE_URL,
            client=client,
            cache=cache,
            encoder_version=encoder_version,
        )

    def _embed_uncached(self, texts: list[str]) -> list[list[float]]:
        self._require_api_key()
        url = f"{self._base_url}/v1beta/models/{quote(self.name)}:batchEmbedContents"
        body = {
            "requests": [
                {
                    "model": f"models/{self.name}",
                    "content": {"parts": [{"text": text}]},
                    "outputDimensionality": self.dims,
                }
                for text in texts
            ]
        }
        response = self._post_with_retry(url, params={"key": self._api_key}, json_body=body)
        data = response.json()
        embeddings = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(embeddings, list):
            raise EmbeddingProviderError(f"{self.name} response missing 'embeddings' list")
        tokens = 0
        vectors: list[Any] = []
        for entry in embeddings:
            if not isinstance(entry, dict):
                raise EmbeddingProviderError(f"{self.name} returned a non-object embedding entry")
            vectors.append(entry.get("values"))
            statistics = entry.get("statistics")
            if isinstance(statistics, dict):
                tokens += int(statistics.get("token_count") or statistics.get("tokenCount") or 0)
        usage = data.get("usageMetadata") if isinstance(data, dict) else None
        if isinstance(usage, dict):
            tokens = int(usage.get("totalTokenCount") or usage.get("promptTokenCount") or tokens)
        self._account(tokens)
        return self._verified(vectors, len(texts))


class JinaEmbeddingAdapter(_HttpEmbeddingAdapter):
    """Jina Embeddings v5 via the Jina ``/v1/embeddings`` REST endpoint.

    Model dimension is fixed by the model: ``jina-embeddings-v5-text-nano`` is
    768 dims and ``jina-embeddings-v5-text-small`` is 1024 dims (doc 04 §4.8).
    A configured dimension contradicting a known model raises
    :class:`ConfigError` at construction; unknown models are verified at embed
    time instead. The API key comes from ``JINA_API_KEY`` (config).
    """

    KNOWN_DIMS: dict[str, int] = {
        "jina-embeddings-v5-text-nano": 768,
        "jina-embeddings-v5-text-small": 1024,
    }

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        client: httpx.Client | None = None,
        cache: VersionedEmbeddingCache | None = None,
        encoder_version: str | None = None,
    ) -> None:
        expected = self.KNOWN_DIMS.get(settings.model)
        if expected is not None and expected != settings.dimensions:
            raise ConfigError(
                f"{settings.model} is {expected} dims, but EMBEDDING_DIMENSIONS is "
                f"{settings.dimensions}; align the configuration (doc 04 §4.8.2)"
            )
        super().__init__(
            settings,
            api_key=settings.jina_api_key,
            key_env_name="JINA_API_KEY",
            base_url=JINA_API_BASE_URL,
            client=client,
            cache=cache,
            encoder_version=encoder_version,
        )

    def _embed_uncached(self, texts: list[str]) -> list[list[float]]:
        self._require_api_key()
        url = f"{self._base_url}/v1/embeddings"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        body = {"model": self.name, "input": texts}
        response = self._post_with_retry(url, headers=headers, json_body=body)
        data = response.json()
        items = data.get("data") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise EmbeddingProviderError(f"{self.name} response missing 'data' list")
        # Preserve request order (contract doc 06 §6.2.2.5): sort by the
        # provider-reported index instead of trusting response order.
        ordered = sorted(
            items,
            key=lambda item: item.get("index", 0) if isinstance(item, dict) else 0,
        )
        vectors = [item.get("embedding") if isinstance(item, dict) else None for item in ordered]
        usage = data.get("usage") if isinstance(data, dict) else None
        tokens = int(usage.get("total_tokens") or 0) if isinstance(usage, dict) else 0
        self._account(tokens)
        return self._verified(vectors, len(texts))


def embedding_cache_key(model: str, encoder_version: str, text: str) -> str:
    """Deterministic cache key: sha256 of model + encoder version + text.

    Versioned so a model or encoder change never reuses vectors across runs
    (doc 08 §8.5.2): the key differs when any of the three inputs differs, and
    identical inputs always map to the same key (deterministic reproduction).
    """
    material = "\x00".join((model, encoder_version, text))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class VersionedEmbeddingCache:
    """Bounded in-memory embedding cache keyed by :func:`embedding_cache_key`.

    LRU eviction at ``max_size`` entries; deliberately persistence-free (a
    rebuild embeds cold or from a future on-disk cache). Deterministic
    reproduction: identical ``(model, encoder_version, text)`` triplets yield
    identical vectors. Stored vectors are treated as immutable by convention;
    :meth:`get` returns the stored object, not a copy.
    """

    def __init__(self, max_size: int = 10_000) -> None:
        if max_size < 1:
            raise ValueError("max_size must be >= 1")
        self.max_size = max_size
        self._entries: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> list[float] | None:
        with self._lock:
            vector = self._entries.get(key)
            if vector is not None:
                self._entries.move_to_end(key)
            return vector

    def set(self, key: str, vector: list[float]) -> None:
        with self._lock:
            self._entries[key] = vector
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_size:
                self._entries.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


def get_embedding_provider(
    config: EmbeddingSettings,
    *,
    cache: VersionedEmbeddingCache | None = None,
    encoder_version: str | None = None,
) -> EmbeddingProvider:
    """Instantiate the embedding provider selected by ``config`` (VNLRAG-41).

    Selection is configuration-only; no model is permanently chosen here —
    Suite B (E1-E3) benchmarks decide the production model from evidence,
    never beforehand (doc 00 §7, ADR-013).

    ``cache``/``encoder_version`` enable the versioned embedding cache: vectors
    are reused only for the exact ``(model, encoder_version, text)`` triple
    (doc 08 §8.5.2), so a rebuild with the same model+version re-embeds nothing
    and a model/encoder change never reads stale vectors.
    """
    if config.provider == "gemini":
        return GeminiEmbeddingAdapter(config, cache=cache, encoder_version=encoder_version)
    if config.provider == "jina":
        return JinaEmbeddingAdapter(config, cache=cache, encoder_version=encoder_version)
    raise ConfigError(f"unsupported embedding provider: {config.provider!r}")
