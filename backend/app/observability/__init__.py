"""Observability: Langfuse tracing and release-pinned prompt fallback loading."""

from app.observability.langfuse_client import (
    FallbackPrompt,
    NoOpLangfuse,
    build_prompt,
    get_langfuse,
    trace_legal_query,
)

__all__ = [
    "FallbackPrompt",
    "NoOpLangfuse",
    "build_prompt",
    "get_langfuse",
    "trace_legal_query",
]
