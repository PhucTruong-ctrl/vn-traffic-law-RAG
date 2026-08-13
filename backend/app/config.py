"""Application configuration.

Settings are loaded from the real environment first, then from the repository
root ``.env`` file (``env_file``), matching doc 07 §7.3.3. Langfuse credentials
are read exclusively through pydantic-settings from the environment — never
hardcoded or logged.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

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


class SparseSettings(BaseSettings):
    """Sparse-encoder configuration (doc 03 §3.11.2).

    Read from ``SPARSE_*`` environment variables, then the repo-root ``.env``
    file (doc 07 §7.3.3). ``encoder_version`` is the id recorded in every
    indexed point's ``sparse_encoder_version`` payload key; changing the
    encoder means a collection rebuild + alias switch, never mixing two sparse
    spaces in one collection. ``tokenizer`` names the tokenizer the
    ``BM25SparseEncoder`` implements (only ``"unicode-word"`` exists today;
    Suite C tokenizer verification may add variants).
    """

    model_config = SettingsConfigDict(
        env_prefix="SPARSE_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    encoder_version: str = "bm25-v1"
    tokenizer: str = "unicode-word"


#: Canonical object-storage buckets (doc 03 §3.12.1, FR-08). Kept in sync with
#: ``app.storage.BUCKETS`` (pinned by tests/test_object_storage.py) and the
#: docker-compose ``MINIO_BUCKETS`` bootstrap list.
_DEFAULT_OBJECT_STORAGE_BUCKETS = (
    "source-pdfs",
    "parser-outputs",
    "page-images",
    "ingestion-artifacts",
    "review-artifacts",
    "evaluation-artifacts",
)


class ObjectStorageSettings(BaseSettings):
    """S3-compatible object storage configuration (doc 03 §3.12, doc 04 §4.15).

    Read from ``MINIO_*`` environment variables, then the repo-root ``.env``
    file (doc 07 §7.3.3): ``MINIO_ENDPOINT``, ``MINIO_USE_SSL``,
    ``MINIO_BUCKETS`` (comma-separated list). Credentials accept the MinIO
    server spellings ``MINIO_ROOT_USER`` / ``MINIO_ROOT_PASSWORD`` (used by
    docker-compose), the S3 SDK spellings ``MINIO_ACCESS_KEY`` /
    ``MINIO_SECRET_KEY``, and the repository's ``MINIO_ACCESS`` /
    ``MINIO_SECRET`` forms (see the ``AliasChoices`` on ``access_key`` /
    ``secret_key``). ``endpoint`` is ``host[:port]`` with no scheme; a scheme
    is tolerated and stripped by :class:`app.storage.S3ObjectStorage`.
    """

    model_config = SettingsConfigDict(
        env_prefix="MINIO_",
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    endpoint: str = "localhost:9000"
    access_key: str = Field(
        default="",
        validation_alias=AliasChoices("MINIO_ROOT_USER", "MINIO_ACCESS_KEY", "MINIO_ACCESS"),
    )
    secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("MINIO_ROOT_PASSWORD", "MINIO_SECRET_KEY", "MINIO_SECRET"),
    )
    use_ssl: bool = False
    buckets: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: list(_DEFAULT_OBJECT_STORAGE_BUCKETS)
    )

    @field_validator("buckets", mode="before")
    @classmethod
    def _parse_buckets(cls, value: object) -> object:
        """Accept the docker-compose/bootstrap form ``MINIO_BUCKETS=a,b,c``."""
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value


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


@lru_cache(maxsize=1)
def get_sparse_settings() -> SparseSettings:
    """Return the process-wide sparse settings singleton (cached until cleared)."""
    return SparseSettings()


@lru_cache(maxsize=1)
def get_object_storage_settings() -> ObjectStorageSettings:
    """Return the process-wide object-storage settings singleton (cached until cleared)."""
    return ObjectStorageSettings()
