"""Unit tests: embedding provider adapters (VNLRAG-41) — no live API needed.

Provider calls are exercised through ``httpx.MockTransport`` fake transports;
the optional live tests at the bottom are skipped unless an API key is present.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from app.config import EmbeddingSettings
from app.retrieval import embedding
from app.retrieval.embedding import (
    ConfigError,
    EmbeddingDimensionError,
    EmbeddingProvider,
    EmbeddingProviderError,
    GeminiEmbeddingAdapter,
    JinaEmbeddingAdapter,
    VersionedEmbeddingCache,
    embedding_cache_key,
    get_embedding_provider,
)

DIMS = 4
BATCH = 2
#: Jina v5 text-nano dims are model-fixed (768); the adapter validates them.
JINA_DIMS = 768


def _settings(**overrides: Any) -> EmbeddingSettings:
    values: dict[str, Any] = {
        "provider": "gemini",
        "model": "gemini-embedding-2",
        "dimensions": DIMS,
        "batch_size": BATCH,
        "max_retries": 2,
        "timeout_seconds": 5.0,
        "gemini_api_key": "test-gemini-key",
        "jina_api_key": "test-jina-key",
    }
    values.update(overrides)
    return EmbeddingSettings(**values)


def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _gemini_handler(
    dims: int, token_per_text: int = 1, vectors: list[list[float]] | None = None
) -> Any:
    """Fake Gemini ``batchEmbedContents`` handler; values mark input order."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        texts = [entry["content"]["parts"][0]["text"] for entry in body["requests"]]
        values = (
            vectors
            if vectors is not None
            else [[float(index)] * dims for index in range(len(texts))]
        )
        return httpx.Response(
            200,
            json={
                "embeddings": [
                    {
                        "values": values[index],
                        "statistics": {"truncated": False, "token_count": token_per_text},
                    }
                    for index in range(len(texts))
                ]
            },
        )

    return handler


def _jina_handler(dims: int, total_tokens: int = 5) -> Any:
    """Fake Jina ``/v1/embeddings`` handler; values mark input order."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        texts = body["input"]
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "data": [
                    {"object": "embedding", "index": index, "embedding": [float(index)] * dims}
                    for index in range(len(texts))
                ],
                "usage": {"total_tokens": total_tokens, "prompt_tokens": total_tokens},
            },
        )

    return handler


# ---------------------------------------------------------------------------
# Adapter contract
# ---------------------------------------------------------------------------


def test_gemini_adapter_contract_returns_dims_sized_vectors() -> None:
    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(_gemini_handler(DIMS)))
    assert adapter.name == "gemini-embedding-2"
    assert adapter.dims == DIMS
    assert adapter.batch_size == BATCH
    assert isinstance(adapter, EmbeddingProvider)

    vectors = adapter.embed(["một", "hai", "ba"])
    assert len(vectors) == 3
    assert all(len(vector) == DIMS for vector in vectors)
    # Values mark input order: index 0/1/2.
    assert vectors[1] == [1.0] * DIMS


def test_gemini_embed_batch_preserves_order_and_chunks() -> None:
    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(_gemini_handler(DIMS)))
    texts = ["a", "b", "c", "d", "e"]
    vectors = adapter.embed_batch(texts)
    assert len(vectors) == 5
    # Chunk sizes were 2/2/1, so per-chunk values are [0,1], [0,1], [0].
    assert vectors == [[0.0] * DIMS, [1.0] * DIMS, [0.0] * DIMS, [1.0] * DIMS, [0.0] * DIMS]
    assert adapter.requests == 3


def test_embed_batch_empty_input_no_requests() -> None:
    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(_gemini_handler(DIMS)))
    assert adapter.embed_batch([]) == []
    assert adapter.embed([]) == []
    assert adapter.requests == 0
    assert adapter.total_tokens == 0


def test_jina_adapter_contract_returns_dims_sized_vectors() -> None:
    settings = _settings(
        provider="jina", model="jina-embeddings-v5-text-nano", dimensions=JINA_DIMS
    )
    adapter = JinaEmbeddingAdapter(settings, client=_client(_jina_handler(JINA_DIMS)))
    assert adapter.name == "jina-embeddings-v5-text-nano"
    assert adapter.dims == JINA_DIMS

    vectors = adapter.embed_batch(["x", "y", "z"])
    assert [len(vector) for vector in vectors] == [JINA_DIMS] * 3
    # Values mark each request's input index (restarting at 0 per request), so
    # the concatenated marker stream proves batch order is preserved: 0,1 | 0.
    assert [vector[0] for vector in vectors] == [0.0, 1.0, 0.0]


def test_embed_raises_on_wrong_dimension() -> None:
    handler = _gemini_handler(DIMS, vectors=[[1.0] * (DIMS + 1)])
    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(handler))
    with pytest.raises(EmbeddingDimensionError, match="expected 4"):
        adapter.embed(["x"])


def test_embed_raises_on_vector_count_mismatch() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"embeddings": [{"values": [1.0] * DIMS}]},  # 1 vector for 2 texts
        )

    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(handler))
    with pytest.raises(EmbeddingProviderError, match="1 vectors for 2 texts"):
        adapter.embed(["x", "y"])


# ---------------------------------------------------------------------------
# Retry / backoff (bounded)
# ---------------------------------------------------------------------------


def test_retry_on_429_respects_retry_after_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) <= 2:
            return httpx.Response(
                429, headers={"Retry-After": "5"}, json={"error": {"message": "rate limited"}}
            )
        return httpx.Response(
            200, json={"embeddings": [{"values": [0.0] * DIMS, "statistics": {"token_count": 2}}]}
        )

    monkeypatch.setattr(embedding, "_sleep", sleeps.append)
    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(handler))
    vectors = adapter.embed(["x"])
    assert len(vectors) == 1
    assert len(attempts) == 3  # 1 attempt + 2 retries
    assert sleeps == [5.0, 5.0]  # Retry-After respected over backoff
    assert adapter.requests == 1  # only the successful call is billed


def test_retry_backoff_bounded_on_persistent_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(503, json={"error": {"message": "unavailable"}})

    monkeypatch.setattr(embedding, "_sleep", sleeps.append)
    adapter = GeminiEmbeddingAdapter(_settings(max_retries=2), client=_client(handler))
    with pytest.raises(EmbeddingProviderError, match="after 2 retries"):
        adapter.embed(["x"])
    assert len(attempts) == 3  # 1 attempt + 2 retries — no unbounded loop
    assert sleeps == [1.0, 2.0]  # exponential backoff: base * 2 ** (attempt - 1)


def test_retry_after_capped_to_max(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "99999"})
        return httpx.Response(200, json={"embeddings": [{"values": [0.0] * DIMS}]})

    monkeypatch.setattr(embedding, "_sleep", sleeps.append)
    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(handler))
    adapter.embed(["x"])
    assert sleeps == [embedding.MAX_RETRY_AFTER_SECONDS]


def test_transport_error_retried_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(embedding, "_sleep", lambda _: None)
    adapter = GeminiEmbeddingAdapter(_settings(max_retries=2), client=_client(handler))
    with pytest.raises(EmbeddingProviderError, match="connection refused"):
        adapter.embed(["x"])
    assert len(attempts) == 3


def test_hard_4xx_raises_immediately_without_retry() -> None:
    attempts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(401, json={"error": {"message": "API key not valid"}})

    adapter = GeminiEmbeddingAdapter(_settings(), client=_client(handler))
    with pytest.raises(EmbeddingProviderError, match="API key not valid"):
        adapter.embed(["x"])
    assert len(attempts) == 1


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------


def test_gemini_cost_tracking_accumulates_tokens() -> None:
    adapter = GeminiEmbeddingAdapter(
        _settings(), client=_client(_gemini_handler(DIMS, token_per_text=7))
    )
    adapter.embed(["a", "b"])
    assert adapter.total_tokens == 14
    assert adapter.requests == 1
    adapter.embed(["c"])
    assert adapter.total_tokens == 21
    assert adapter.requests == 2


def test_jina_cost_tracking_uses_usage_total_tokens() -> None:
    adapter = JinaEmbeddingAdapter(
        _settings(provider="jina", model="jina-embeddings-v5-text-nano", dimensions=JINA_DIMS),
        client=_client(_jina_handler(JINA_DIMS, total_tokens=5)),
    )
    adapter.embed(["a", "b"])
    assert adapter.total_tokens == 5
    assert adapter.requests == 1


# ---------------------------------------------------------------------------
# Versioned cache
# ---------------------------------------------------------------------------


def test_cache_key_versioning() -> None:
    key = embedding_cache_key("gemini-embedding-2", "v1", "điều 1")
    assert embedding_cache_key("gemini-embedding-2", "v1", "điều 1") == key  # deterministic
    assert embedding_cache_key("gemini-embedding-2", "v2", "điều 1") != key  # version
    assert embedding_cache_key("gemini-embedding-2", "v1", "điều 2") != key  # text
    assert embedding_cache_key("jina-embeddings-v5-text-nano", "v1", "điều 1") != key  # model


def test_cache_lru_eviction() -> None:
    cache = VersionedEmbeddingCache(max_size=2)
    cache.set("a", [1.0])
    cache.set("b", [2.0])
    cache.set("c", [3.0])
    assert len(cache) == 2
    assert cache.get("a") is None  # oldest evicted
    assert cache.get("b") == [2.0]
    assert cache.get("c") == [3.0]


def test_cache_get_refreshes_lru_position() -> None:
    cache = VersionedEmbeddingCache(max_size=2)
    cache.set("a", [1.0])
    cache.set("b", [2.0])
    assert cache.get("a") == [1.0]  # a becomes most-recent
    cache.set("c", [3.0])  # evicts b, keeps a
    assert cache.get("a") == [1.0]
    assert cache.get("b") is None
    assert cache.get("c") == [3.0]


def test_cache_rejects_nonpositive_max_size() -> None:
    with pytest.raises(ValueError, match=">= 1"):
        VersionedEmbeddingCache(max_size=0)


def test_adapter_cache_reuses_vectors_for_same_version() -> None:
    attempts: list[int] = []
    handler = _gemini_handler(DIMS)
    wrapped = _client(handler)
    original_post = wrapped.post

    def counting_post(*args: Any, **kwargs: Any) -> Any:
        attempts.append(1)
        return original_post(*args, **kwargs)

    wrapped.post = counting_post  # type: ignore[method-assign]
    cache = VersionedEmbeddingCache()
    adapter = GeminiEmbeddingAdapter(_settings(), client=wrapped, cache=cache, encoder_version="v1")
    first = adapter.embed(["a", "b"])
    second = adapter.embed(["a", "b"])
    assert first == second
    assert len(attempts) == 1  # second call fully served from cache
    assert len(cache) == 2


def test_adapter_cache_version_change_reembeds() -> None:
    attempts: list[int] = []
    cache = VersionedEmbeddingCache()

    def make_adapter(version: str) -> GeminiEmbeddingAdapter:
        handler = _gemini_handler(DIMS)
        wrapped = _client(handler)
        original_post = wrapped.post

        def counting_post(*args: Any, **kwargs: Any) -> Any:
            attempts.append(1)
            return original_post(*args, **kwargs)

        wrapped.post = counting_post  # type: ignore[method-assign]
        return GeminiEmbeddingAdapter(
            _settings(), client=wrapped, cache=cache, encoder_version=version
        )

    v1 = make_adapter("v1")
    v2 = make_adapter("v2")
    assert v1.embed(["a"]) == v2.embed(["a"])  # same text, same vector value
    assert len(attempts) == 2  # version change invalidates the cache entry


# ---------------------------------------------------------------------------
# Factory and config
# ---------------------------------------------------------------------------


def test_factory_selects_gemini_from_config() -> None:
    provider = get_embedding_provider(_settings(provider="gemini"))
    assert isinstance(provider, GeminiEmbeddingAdapter)
    assert provider.name == "gemini-embedding-2"
    assert provider.dims == DIMS
    assert provider.batch_size == BATCH


def test_factory_selects_jina_from_config() -> None:
    settings = _settings(
        provider="jina", model="jina-embeddings-v5-text-nano", dimensions=JINA_DIMS
    )
    provider = get_embedding_provider(settings)
    assert isinstance(provider, JinaEmbeddingAdapter)
    assert provider.name == "jina-embeddings-v5-text-nano"
    assert provider.dims == JINA_DIMS


def test_factory_wires_versioned_cache() -> None:
    cache = VersionedEmbeddingCache(max_size=8)
    provider = get_embedding_provider(_settings(), cache=cache, encoder_version="v1")
    assert provider._cache is cache  # noqa: SLF001 — factory wiring contract
    assert provider._encoder_version == "v1"  # noqa: SLF001


def test_missing_gemini_api_key_raises_config_error_at_call_time() -> None:
    adapter = GeminiEmbeddingAdapter(
        _settings(gemini_api_key=""), client=_client(_gemini_handler(DIMS))
    )
    with pytest.raises(ConfigError, match="GEMINI_API_KEY"):
        adapter.embed(["x"])
    assert adapter.requests == 0


def test_missing_jina_api_key_raises_config_error_at_call_time() -> None:
    settings = _settings(
        provider="jina",
        model="jina-embeddings-v5-text-nano",
        dimensions=JINA_DIMS,
        jina_api_key="",
    )
    adapter = JinaEmbeddingAdapter(settings, client=_client(_jina_handler(JINA_DIMS)))
    with pytest.raises(ConfigError, match="JINA_API_KEY"):
        adapter.embed(["x"])


def test_jina_known_model_dimension_mismatch_raises_config_error() -> None:
    settings = _settings(provider="jina", model="jina-embeddings-v5-text-nano", dimensions=512)
    with pytest.raises(ConfigError, match="768 dims"):
        JinaEmbeddingAdapter(settings)


def test_module_exports() -> None:
    for name in (
        "ConfigError",
        "EmbeddingDimensionError",
        "EmbeddingProvider",
        "EmbeddingProviderError",
        "GeminiEmbeddingAdapter",
        "JinaEmbeddingAdapter",
        "VersionedEmbeddingCache",
        "embedding_cache_key",
        "get_embedding_provider",
    ):
        assert hasattr(embedding, name), name


# ---------------------------------------------------------------------------
# Optional live provider calls (guarded: skipped without an API key)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_live_gemini_embedding_roundtrip() -> None:
    settings = EmbeddingSettings(
        provider="gemini", model="gemini-embedding-2", dimensions=768, batch_size=2
    )
    if not settings.gemini_api_key:
        pytest.skip("GEMINI_API_KEY not set; skipping live Gemini call")
    adapter = GeminiEmbeddingAdapter(settings)
    texts = ["Điều 1. Phạm vi điều chỉnh", "Khoản 2 Điều 5 Nghị định 168/2024/NĐ-CP"]
    vectors = adapter.embed_batch(texts)
    assert len(vectors) == len(texts)
    assert all(len(vector) == settings.dimensions for vector in vectors)
    assert adapter.requests == 1
    assert adapter.total_tokens > 0


@pytest.mark.integration
def test_live_jina_embedding_roundtrip() -> None:
    settings = EmbeddingSettings(
        provider="jina", model="jina-embeddings-v5-text-nano", dimensions=768, batch_size=2
    )
    if not settings.jina_api_key:
        pytest.skip("JINA_API_KEY not set; skipping live Jina call")
    adapter = JinaEmbeddingAdapter(settings)
    texts = ["Điều 1. Phạm vi điều chỉnh", "Khoản 2 Điều 5 Nghị định 168/2024/NĐ-CP"]
    vectors = adapter.embed_batch(texts)
    assert len(vectors) == len(texts)
    assert all(len(vector) == settings.dimensions for vector in vectors)
    assert adapter.requests == 1
