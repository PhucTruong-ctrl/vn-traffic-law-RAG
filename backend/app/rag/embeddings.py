"""OpenRouter dense embeddings through the maintained LangChain integration."""

from __future__ import annotations

from collections.abc import Iterable

from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from app.config import get_embedding_settings


class EmbeddingError(RuntimeError):
    """Raised when the configured embedding provider is unavailable."""


class OpenRouterEmbeddingClient:
    """Small adapter retaining one official OpenAI-compatible embedding client."""

    def __init__(self) -> None:
        settings = get_embedding_settings()
        if settings.dimensions != 768:
            raise ValueError("dense embedding dimension must be 768")
        if not settings.openrouter_api_key:
            raise EmbeddingError("OpenRouter provider is unavailable")
        self.client = OpenAIEmbeddings(
            model=settings.model,
            dimensions=settings.dimensions,
            api_key=SecretStr(settings.openrouter_api_key),
            base_url=settings.openrouter_base_url,
        )

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        try:
            return self.client.embed_documents(list(texts))
        except Exception as exc:
            raise EmbeddingError("OpenRouter embedding provider is unavailable") from exc

    def embed_query(self, text: str) -> list[float]:
        try:
            return self.client.embed_query(text)
        except Exception as exc:
            raise EmbeddingError("OpenRouter embedding provider is unavailable") from exc


__all__ = ["EmbeddingError", "OpenRouterEmbeddingClient"]
