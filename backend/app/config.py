"""Application configuration.

Settings are loaded from the real environment first, then from the repository
root ``.env`` file (``env_file``), matching doc 07 §7.3.3. Langfuse credentials
are read exclusively through pydantic-settings from the environment — never
hardcoded or logged.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"

PromptSource = Literal["LANGFUSE", "CACHE", "RELEASE_FALLBACK"]


class Settings(BaseSettings):
    """Runtime configuration for the VNLaw backend."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core application
    app_env: str = "development"
    log_level: str = "INFO"
    timezone: str = "UTC"

    # Langfuse observability (off the correctness path, doc 00 §4.11)
    langfuse_enabled: bool = True
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # Prompt management — W1 scope: local fallback loader + trace skeleton
    # only. The full LANGFUSE -> CACHE -> RELEASE_FALLBACK resolver
    # (client.get_prompt, cache, source selection) ships with the
    # prompt-management ticket (doc 03 §3.27.3).
    prompt_source: PromptSource = "LANGFUSE"
    fallback_prompts_dir: str = "/app/prompts/fallback"
    fallback_prompt_version_query_analyzer: str = ""
    fallback_prompt_version_query_rewriter: str = ""
    fallback_prompt_version_hyde: str = ""
    fallback_prompt_version_generator: str = ""
    fallback_prompt_version_claim_verifier: str = ""

    # Ingestion
    max_ingestion_workers: int = 1


class QdrantSettings(BaseSettings):
    """Qdrant retrieval-index connection and collection naming (doc 03 §3.11).

    Read from ``QDRANT_*`` environment variables, then the repo-root ``.env``
    file (doc 07 §7.3.3). ``url`` defaults to localhost for local development;
    the docker-compose ``vnlaw-qdrant`` service is reachable via
    ``QDRANT_URL=http://qdrant:6333`` in the compose environment.
    """

    model_config = SettingsConfigDict(
        env_prefix="QDRANT_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    url: str = "http://localhost:6333"
    api_key: str = ""
    collection_alias: str = "legal_provisions_active"
    collection_prefix: str = "legal_provisions"


class EmbeddingSettings(BaseSettings):
    """Dense embedding provider configuration (doc 03 §3.11, doc 04 §4.8, doc 07 §7.3.3).

    Read from ``EMBEDDING_*`` environment variables, then the repo-root ``.env``
    file (doc 07 §7.3.3): ``EMBEDDING_PROVIDER``, ``EMBEDDING_MODEL``,
    ``EMBEDDING_DIMENSIONS``, ``EMBEDDING_BATCH_SIZE``. Provider API keys are
    read from the bare ``GEMINI_API_KEY`` / ``JINA_API_KEY`` variables (doc 07
    §7.3.3); the prefixed spellings are accepted as fallbacks.

    The embedding model is deliberately NOT pinned permanently: Suite B (E1-E3)
    benchmarks decide the production model from evidence (ADR-013). This config
    only selects what :func:`app.retrieval.embedding.get_embedding_provider`
    instantiates; model IDs live here, never hardcoded in domain logic.
    """

    model_config = SettingsConfigDict(
        env_prefix="EMBEDDING_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    provider: Literal["gemini", "jina"] = "gemini"
    model: str = "gemini-embedding-2"
    #: Suite B test dimension (E1/E2: 768, E3 text-small: 1024). Gemini's model
    #: default is 3072; the adapter requests this value via ``outputDimensionality``.
    dimensions: int = 768
    batch_size: int = 32
    max_retries: int = 3
    timeout_seconds: float = 60.0
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "EMBEDDING_GEMINI_API_KEY"),
    )
    jina_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("JINA_API_KEY", "EMBEDDING_JINA_API_KEY"),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached until cleared)."""
    return Settings()


@lru_cache(maxsize=1)
def get_qdrant_settings() -> QdrantSettings:
    """Return the process-wide Qdrant settings singleton (cached until cleared)."""
    return QdrantSettings()


@lru_cache(maxsize=1)
def get_embedding_settings() -> EmbeddingSettings:
    """Return the process-wide embedding settings singleton (cached until cleared)."""
    return EmbeddingSettings()
