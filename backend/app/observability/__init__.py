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
    "HealthCheck",
    "Metrics",
    "NoOpLangfuse",
    "build_prompt",
    "get_langfuse",
    "metrics",
    "readiness",
    "trace_legal_query",
]

from app.observability.health import HealthCheck, Metrics, metrics, readiness
