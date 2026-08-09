"""Application configuration.

Settings are loaded from the real environment first, then from the repository
root ``.env`` file (``env_file``), matching doc 07 §7.3.3. Langfuse credentials
are read exclusively through pydantic-settings from the environment — never
hardcoded or logged.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached until cleared)."""
    return Settings()
