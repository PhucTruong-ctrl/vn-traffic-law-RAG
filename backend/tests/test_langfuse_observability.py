"""Tests for the Langfuse observability setup (VNLRAG-121).

Unit tests must never require developer credentials: the no-op path, prompt
fallback loading and settings defaults are exercised with fake/missing
credentials. The single integration test (real .env keys present) is skipped
unless the repo-root ``.env`` actually carries Langfuse keys.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import get_settings
from app.observability import langfuse_client
from app.observability.langfuse_client import build_prompt, get_langfuse
from app.observability.skeleton import run_legal_query_trace

REPO_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_DIR = REPO_ROOT / "prompts" / "fallback"
FALLBACK_FILES = [
    "query-analyzer.yaml",
    "query-rewriter.yaml",
    "hyde.yaml",
    "generator.yaml",
    "claim-verifier.yaml",
]


def _has_real_langfuse_keys() -> bool:
    settings = get_settings()
    return bool(
        settings.langfuse_public_key.startswith("pk-lf-")
        and settings.langfuse_secret_key.startswith("sk-lf-")
    )


@pytest.fixture()
def disabled_langfuse(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force LANGFUSE_ENABLED=false and reset cached settings/client."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    get_settings.cache_clear()
    langfuse_client._client = None
    yield
    get_settings.cache_clear()
    langfuse_client._client = None


def test_settings_defaults_without_credentials() -> None:
    """Settings defaults hold even when no real keys are present (no .env needed)."""
    settings = get_settings()
    assert settings.app_env
    assert settings.prompt_source in {"LANGFUSE", "CACHE", "RELEASE_FALLBACK"}
    assert settings.fallback_prompts_dir
    assert settings.max_ingestion_workers == 1


@pytest.mark.skipif(
    not _has_real_langfuse_keys(),
    reason="requires repo-root .env with real Langfuse keys (integration)",
)
def test_settings_load_real_keys_from_env() -> None:
    """Integration-only: real .env keys are picked up from the environment."""
    settings = get_settings()
    assert settings.langfuse_enabled is True
    assert settings.langfuse_public_key.startswith("pk-lf-")
    assert settings.langfuse_secret_key.startswith("sk-lf-")
    assert settings.langfuse_host


def test_disabled_langfuse_returns_noop_stub(disabled_langfuse: None) -> None:
    assert isinstance(get_langfuse(), langfuse_client.NoOpLangfuse)


def test_disabled_run_legal_query_trace_completes_offline(disabled_langfuse: None) -> None:
    """Full trace run succeeds and never loads the langfuse SDK (no network)."""
    trace_id = run_legal_query_trace("mức phạt vượt đèn đỏ năm 2024?")
    assert trace_id
    assert isinstance(langfuse_client._client, langfuse_client.NoOpLangfuse)
    assert "langfuse" not in sys.modules


@pytest.mark.parametrize("filename", FALLBACK_FILES)
def test_build_prompt_returns_content(filename: str) -> None:
    prompt = build_prompt(
        name=filename.removesuffix(".yaml"),
        fallback_path=FALLBACK_DIR / filename,
    )
    assert prompt.name
    assert prompt.version
    assert prompt.template.strip()
    assert prompt.prompt_hash
    assert prompt.source == "RELEASE_FALLBACK"


def test_build_prompt_resolves_relative_to_fallback_prompts_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FALLBACK_PROMPTS_DIR", str(FALLBACK_DIR))
    get_settings.cache_clear()
    try:
        prompt = build_prompt(name="legal-query-analyzer-v1", fallback_path="query-analyzer.yaml")
        assert "Câu hỏi: {{query}}" in prompt.template
    finally:
        get_settings.cache_clear()


def test_build_prompt_rejects_mismatched_declared_hash(tmp_path: Path) -> None:
    """Declared 'hash' must equal SHA-256(template); mismatch is rejected (doc 07 §7.3.6)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        'name: legal-generator-v1\nversion: "1"\n'
        'hash: "0000000000000000000000000000000000000000000000000000000000000000"\n'
        "template: |\n  Nội dung prompt mẫu\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="does not match template SHA-256"):
        build_prompt(name="legal-generator-v1", fallback_path=bad)


def test_build_prompt_rejects_missing_declared_hash(tmp_path: Path) -> None:
    """Fallback prompts must declare a hash (doc 07 §7.3.6)."""
    missing = tmp_path / "missing.yaml"
    missing.write_text(
        'name: legal-generator-v1\nversion: "1"\ntemplate: |\n  Nội dung prompt mẫu\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="no declared 'hash'"):
        build_prompt(name="legal-generator-v1", fallback_path=missing)
