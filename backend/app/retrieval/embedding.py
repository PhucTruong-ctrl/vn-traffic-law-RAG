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
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict

from app.config import EmbeddingSettings

logger = logging.getLogger(__name__)

__all__ = [
    "ConfigError",
    "EmbeddingDimensionError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "GeminiEmbeddingAdapter",
    "JinaEmbeddingAdapter",
    "LocalE5EmbeddingAdapter",
    "VersionedEmbeddingCache",
    "embedding_cache_key",
    "get_embedding_provider",
    "EmbeddingSelectionManifest",
    "EmbeddingSpaceMismatchError",
    "benchmark_local_embeddings",
    "load_embedding_selection_manifest",
    "write_embedding_selection_manifest",
    "ensure_embedding_space_compatible",
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
        keys = [
            embedding_cache_key(self.name, self._encoder_version, text, mode="query")
            for text in texts
        ]
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


class LocalE5EmbeddingAdapter(EmbeddingProvider):
    """Local E5 encoder, with a deterministic stdlib fallback when unavailable.

    The fallback is intentionally lexical rather than semantic.  It is used
    only when SentenceTransformers cannot be imported (including a broken
    optional torch installation), never downloads a model, and advertises its
    own stable encoder version.
    """

    FALLBACK_PROVIDER = "local-hash"
    FALLBACK_ENCODER_VERSION = "local-hash-v1"

    def __init__(
        self,
        settings: EmbeddingSettings,
        *,
        cache: VersionedEmbeddingCache | None = None,
        encoder_version: str | None = None,
    ) -> None:
        self.name = settings.model
        self.dims = settings.dimensions
        self.batch_size = settings.batch_size
        self._cache = cache
        self._encoder_version = encoder_version
        self.total_tokens = 0
        self.requests = 0
        self.provider = "local-sentence-transformer"
        self.device = "cpu"
        self._model: Any | None = None
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:
            logger.warning(
                "SentenceTransformers unavailable; using deterministic %s fallback: %s",
                self.FALLBACK_PROVIDER,
                exc,
            )
            self.provider = self.FALLBACK_PROVIDER
            self._encoder_version = encoder_version or self.FALLBACK_ENCODER_VERSION
            return
        try:
            import torch

            device: Literal["cpu", "cuda"]
            if settings.local_device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                device = settings.local_device
        except Exception:
            device = "cpu"
        try:
            self.device = device
            self._model = SentenceTransformer(self.name, device=device)
        except Exception as exc:
            logger.warning(
                "SentenceTransformers model unavailable; using deterministic %s fallback: %s",
                self.FALLBACK_PROVIDER,
                exc,
            )
            self.provider = self.FALLBACK_PROVIDER
            self.device = "cpu"
            self._encoder_version = encoder_version or self.FALLBACK_ENCODER_VERSION

    @staticmethod
    def _fallback_vector(text: str, dimensions: int) -> list[float]:
        normalized = " ".join(text.casefold().split())
        features = normalized.split()
        features.extend(
            normalized[index : index + 3] for index in range(max(0, len(normalized) - 2))
        )
        vector = [0.0] * dimensions
        for feature in features or [""]:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=16).digest()
            bucket = int.from_bytes(digest[:8], "big") % dimensions
            sign = 1.0 if digest[8] & 1 else -1.0
            vector[bucket] += sign * (1.0 + digest[9] / 255.0)
        norm = sum(value * value for value in vector) ** 0.5
        return [value / norm for value in vector] if norm else vector

    def _encode(self, texts: list[str], prefix: str) -> list[list[float]]:
        prepared = [text if text.startswith(prefix) else prefix + text for text in texts]
        if self._model is None:
            out = [self._fallback_vector(text, self.dims) for text in prepared]
            self.requests += 1
            return out
        vectors = self._model.encode(
            prepared, batch_size=self.batch_size, convert_to_numpy=True, normalize_embeddings=True
        )
        out = [vector.tolist() if hasattr(vector, "tolist") else list(vector) for vector in vectors]
        if any(len(vector) != self.dims for vector in out):
            raise EmbeddingDimensionError(
                f"{self.name} returned a dimension different from {self.dims}"
            )
        self.requests += 1
        return out

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self._cache is None or self._encoder_version is None:
            return self._encode(texts, "query: ")
        keys = [
            embedding_cache_key(self.name, self._encoder_version, text, mode="query")
            for text in texts
        ]
        vectors: list[list[float] | None] = [self._cache.get(key) for key in keys]
        missing = [index for index, vector in enumerate(vectors) if vector is None]
        if missing:
            fresh = self._encode([texts[index] for index in missing], "query: ")
            for index, vector in zip(missing, fresh, strict=True):
                vectors[index] = vector
                self._cache.set(keys[index], vector)
        return [vector for vector in vectors if vector is not None]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(self._embed_cached(texts[start : start + self.batch_size], "passage: "))
        return out

    def _embed_cached(self, texts: list[str], prefix: str) -> list[list[float]]:
        if self._cache is None or self._encoder_version is None:
            return self._encode(texts, prefix)
        keys = [
            embedding_cache_key(self.name, self._encoder_version, text, mode="passage")
            for text in texts
        ]
        vectors: list[list[float] | None] = [self._cache.get(key) for key in keys]
        missing = [index for index, vector in enumerate(vectors) if vector is None]
        if missing:
            fresh = self._encode([texts[index] for index in missing], prefix)
            for index, vector in zip(missing, fresh, strict=True):
                vectors[index] = vector
                self._cache.set(keys[index], vector)
        return [vector for vector in vectors if vector is not None]


class EmbeddingSelectionManifest(BaseModel):
    """Deterministic metadata for the dense+sparse vector space in a rebuild."""

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    revision: str
    dimensions: int
    prefix: str
    device: str
    throughput_texts_per_second: float
    quality: dict[str, float | None]
    artifact_hash: str
    sparse_vocabulary_version: str
    manifest_version: str = "embedding-selection-v1"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    def space_key(self) -> tuple[str, str, str, int, str, str]:
        return (self.provider, self.model, self.revision, self.dimensions, self.prefix, self.device)


class EmbeddingSpaceMismatchError(ValueError):
    """Raised when vectors/metadata do not describe one immutable space."""


def _artifact_hash(records: Sequence[object]) -> str:
    payload = json.dumps(
        list(records), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def benchmark_local_embeddings(
    records: Sequence[Mapping[str, object]],
    *,
    candidates: Sequence[str] = ("intfloat/multilingual-e5-small",),
    sparse_vocabulary_version: str = "bm25-v1",
    device: str = "cpu",
    max_candidates: int = 3,
    max_records: int = 40,
    provider_factory: Callable[[EmbeddingSettings], EmbeddingProvider] | None = None,
) -> list[EmbeddingSelectionManifest]:
    """Benchmark only bounded local candidates already available to SentenceTransformers.

    Candidates are intentionally explicit: discovery never downloads models.  A
    candidate is usable only when its local adapter can be instantiated.
    """
    if max_candidates < 1 or max_records < 1:
        raise ValueError("benchmark bounds must be positive")
    selected = sorted(set(candidates))[:max_candidates]
    sample = list(records)[:max_records]
    texts = [str(row.get("text", row.get("query", ""))) for row in sample]
    artifact_hash = _artifact_hash(sample)
    output: list[EmbeddingSelectionManifest] = []
    for model in selected:
        settings = EmbeddingSettings(
            provider="local",
            model=model,
            dimensions=768,
            local_device=cast(Literal["auto", "cpu", "cuda"], device),
        )
        try:
            provider = (provider_factory or get_embedding_provider)(settings)
            provider_name = getattr(provider, "provider", None)
            if provider_name != "local-sentence-transformer":
                logger.warning(
                    "skipping %s benchmark candidate: provider %r is not SentenceTransformer E5",
                    model,
                    provider_name,
                )
                continue
            started = time.perf_counter()
            vectors = provider.embed_batch(texts)
            elapsed = max(time.perf_counter() - started, 1e-9)
        except (ConfigError, EmbeddingProviderError, EmbeddingDimensionError, OSError):
            continue
        if not vectors:
            continue
        model_obj = getattr(provider, "_model", None)
        model_config = getattr(model_obj, "config", None)
        if not isinstance(model_config, Mapping):
            continue
        actual_model = str(model_config.get("_name_or_path", "")).strip()
        actual_revision = str(
            model_config.get("_commit_hash", model_config.get("revision", ""))
        ).strip()
        if not actual_model or not actual_revision:
            logger.warning("skipping %s benchmark candidate: missing provider metadata", model)
            continue
        quality_records = [
            {
                "id": str(row.get("id", index)),
                "retrieved": row.get("retrieved", []),
                "relevant": row.get("relevant", []),
            }
            for index, row in enumerate(sample)
            if "retrieved" in row or "relevant" in row
        ]
        quality: dict[str, float | None] = {}
        if quality_records:
            from app.evaluation.metrics.retrieval import evaluate_retrieval

            reports = evaluate_retrieval(quality_records)
            quality = {name: report.value for name, report in reports.items()}
        output.append(
            EmbeddingSelectionManifest(
                provider=str(provider_name),
                model=actual_model,
                revision=actual_revision,
                dimensions=len(vectors[0]),
                prefix="passage: ",
                device=str(getattr(provider, "device", device)),
                throughput_texts_per_second=len(texts) / elapsed,
                quality=quality,
                artifact_hash=artifact_hash,
                sparse_vocabulary_version=sparse_vocabulary_version,
            )
        )
    return sorted(
        output,
        key=lambda item: (
            -(item.quality.get("mrr@10") or -1.0),
            -item.throughput_texts_per_second,
            item.model,
        ),
    )


def write_embedding_selection_manifest(path: Path, manifest: EmbeddingSelectionManifest) -> str:
    payload = json.dumps(manifest.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_embedding_selection_manifest(path: Path) -> EmbeddingSelectionManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    return EmbeddingSelectionManifest(**data)


def ensure_embedding_space_compatible(
    selected: EmbeddingSelectionManifest,
    existing: EmbeddingSelectionManifest | None,
    *,
    rebuild: bool = False,
) -> None:
    if existing is not None and selected.space_key() != existing.space_key() and not rebuild:
        raise EmbeddingSpaceMismatchError(
            "embedding model/revision/dimensions/prefix/device changed; rebuild required"
        )


def embedding_cache_key(
    model: str, encoder_version: str, text: str, *, mode: str = "default"
) -> str:
    """Deterministic cache key including the embedding input mode.

    Query and passage prefixes produce different vector-space inputs and must
    never share a cache entry.
    """
    material = "\x00".join((model, encoder_version, mode, text))
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
    if config.provider == "local":
        return LocalE5EmbeddingAdapter(config, cache=cache, encoder_version=encoder_version)
    raise ConfigError(f"unsupported embedding provider: {config.provider!r}")
