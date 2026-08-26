"""Langfuse client factory with graceful no-op degradation.

Langfuse sits off the correctness path (doc 00 §4.11, doc 03 §3.27): when
``LANGFUSE_ENABLED=false`` every entry point returns a no-op stub so the
application never fails, blocks, or performs network calls for observability.

The ``langfuse`` SDK is imported lazily, only when a real client is built —
after settings have been loaded from the environment (instrumentation best
practice) and never at all when observability is disabled.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml  # type: ignore[import-untyped]

from app.config import get_settings

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse._client.span import LangfuseObservationWrapper

_REPO_ROOT = Path(__file__).resolve().parents[3]

_client: Langfuse | NoOpLangfuse | None = None


@dataclass(frozen=True)
class FallbackPrompt:
    """A release-pinned prompt loaded from ``FALLBACK_PROMPTS_DIR``."""

    name: str
    version: str
    template: str
    prompt_hash: str
    source: str = "RELEASE_FALLBACK"


class NoOpLangfuse:
    """No-op stand-in used when observability is disabled.

    Mirrors the small Langfuse v4 SDK surface used by the application; every
    method is a safe no-op so callers need no ``langfuse_enabled`` branches.
    """

    def start_observation(self, **kwargs: Any) -> NoOpLangfuse:
        return self

    def start_as_current_observation(self, **kwargs: Any) -> NoOpLangfuse:
        return self

    def update(self, **kwargs: Any) -> NoOpLangfuse:
        return self

    def end(self, **kwargs: Any) -> NoOpLangfuse:
        return self

    def flush(self) -> None:
        return None

    def shutdown(self) -> None:
        return None

    def get_prompt(self, **kwargs: Any) -> None:
        return None

    def __enter__(self) -> NoOpLangfuse:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None


def get_langfuse() -> Langfuse | NoOpLangfuse:
    """Return the process-wide client, building it lazily on first use.

    Returns a no-op stub when ``settings.langfuse_enabled`` is false. Tests may
    reset the cached client via ``app.observability.langfuse_client._client``.
    """
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def _build_client() -> Langfuse | NoOpLangfuse:
    settings = get_settings()
    if not settings.langfuse_enabled:
        return NoOpLangfuse()
    # Deferred import: the SDK is only ever loaded after settings are
    # available, and never when observability is disabled.
    from langfuse import Langfuse

    return Langfuse(
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )


def trace_legal_query(
    query: str,
    trace_id: str,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> LangfuseObservationWrapper | NoOpLangfuse:
    """Start a ``legal_query`` trace and return its root observation.

    The langfuse v4 SDK dropped ``start_trace()``; a trace is created as the
    root observation via ``start_observation(..., trace_context=...)``. The
    returned object (root span, or no-op client when disabled) accepts nested
    ``start_observation`` calls so callers can build the doc 03 §3.27.2 span
    hierarchy uniformly.
    """
    client = get_langfuse()
    settings = get_settings()
    if not settings.langfuse_enabled:
        return cast(NoOpLangfuse, client)
    return cast(
        LangfuseObservationWrapper,
        client.start_observation(
            name="legal_query",
            trace_context={"trace_id": trace_id},
            input={"query": query},
            metadata={
                **(metadata or {}),
                "user_id": user_id,
                "prompt_source": settings.prompt_source,
            },
        ),
    )


def build_prompt(name: str, fallback_path: str | Path) -> FallbackPrompt:
    """Load a release-pinned prompt from the fallback prompts directory.

    W1 scope: this is a local fallback-file loader only. The full
    ``LANGFUSE -> CACHE -> RELEASE_FALLBACK`` resolver (``client.get_prompt``,
    cache, source selection) is implemented by the prompt-management ticket
    (doc 03 §3.27.3).

    ``fallback_path`` is used as-is when absolute, otherwise resolved against
    ``settings.fallback_prompts_dir``. The YAML must define ``name``,
    ``version``, ``template`` and a ``hash`` equal to the SHA-256 of the
    template (doc 07 §7.3.6); a missing or mismatched declared hash is
    rejected so a mutated prompt is never silently served.
    """
    path = Path(fallback_path)
    if not path.is_absolute():
        path = Path(get_settings().fallback_prompts_dir) / path
    with path.open("r", encoding="utf-8") as handle:
        data: Any = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"invalid fallback prompt {path}: expected a YAML mapping")
    template = str(data.get("template") or "")
    if not template:
        raise ValueError(f"fallback prompt {path} has an empty template")
    prompt_hash = hashlib.sha256(template.encode("utf-8")).hexdigest()
    declared_hash = str(data.get("hash") or "").strip()
    if not declared_hash:
        raise ValueError(f"fallback prompt {path} has no declared 'hash' (doc 07 §7.3.6)")
    if declared_hash != prompt_hash:
        raise ValueError(
            f"fallback prompt {path}: declared hash {declared_hash[:12]}… "
            f"does not match template SHA-256 {prompt_hash[:12]}…"
        )
    return FallbackPrompt(
        name=str(data.get("name") or name),
        version=str(data.get("version") or ""),
        template=template,
        prompt_hash=prompt_hash,
    )
