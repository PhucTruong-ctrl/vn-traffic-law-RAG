"""Configuration for the OpenRouter and local Qdrant RAG pipeline."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[2]


class _Env(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    openrouter_api_key: str = Field(default="", validation_alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", validation_alias="OPENROUTER_BASE_URL"
    )


class EmbeddingSettings(_Env):
    model: str = Field(default="text-embedding-3-small", validation_alias="EMBEDDING_MODEL")
    dimensions: int = Field(default=768, validation_alias="EMBEDDING_DIMENSIONS")


class GenerationSettings(_Env):
    model: str = Field(
        default="deepseek/deepseek-v4-flash-0731", validation_alias="GENERATION_MODEL"
    )


class SupabaseSettings(_Env):
    url: str = Field(default="", validation_alias="SUPABASE_URL")
    anon_key: str = Field(default="", validation_alias="SUPABASE_ANON_KEY")
    service_role_key: str = Field(default="", validation_alias="SUPABASE_SERVICE_ROLE_KEY")

    def model_post_init(self, __context: object) -> None:
        self.url = self.url.rstrip("/")


@lru_cache(maxsize=1)
def get_supabase_settings() -> SupabaseSettings:
    return SupabaseSettings()


class QdrantSettings(_Env):
    path: Path = Field(
        default_factory=lambda: _ROOT / "data/processed/qdrant", validation_alias="QDRANT_PATH"
    )
    collection: str = Field(default="traffic_law", validation_alias="QDRANT_COLLECTION")
    url: str = Field(default="", validation_alias="QDRANT_URL")
    timeout: int | None = Field(default=2, validation_alias="QDRANT_TIMEOUT")

    def model_post_init(self, __context: object) -> None:
        path = self.path.expanduser()
        if not path.is_absolute():
            path = _ROOT / path
        self.path = path.resolve()
        self.url = self.url.rstrip("/")


@lru_cache(maxsize=1)
def get_generation_settings() -> GenerationSettings:
    return GenerationSettings()


@lru_cache(maxsize=1)
def get_embedding_settings() -> EmbeddingSettings:
    return EmbeddingSettings()


@lru_cache(maxsize=1)
def get_qdrant_settings() -> QdrantSettings:
    return QdrantSettings()


__all__ = [
    "EmbeddingSettings",
    "GenerationSettings",
    "QdrantSettings",
    "SupabaseSettings",
    "get_embedding_settings",
    "get_generation_settings",
    "get_qdrant_settings",
    "get_supabase_settings",
]
