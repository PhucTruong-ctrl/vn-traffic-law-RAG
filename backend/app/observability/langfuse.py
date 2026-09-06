"""Langfuse adapter for the complete query pipeline."""

from __future__ import annotations

from contextlib import suppress

from app.observability.langfuse_client import get_langfuse, trace_legal_query
from app.observability.query_trace import QueryTrace


def emit_query_trace(trace: QueryTrace) -> QueryTrace:
    """Emit a completed QueryTrace, safely no-op when Langfuse is disabled."""
    root = trace_legal_query(trace.query, trace.trace_id, trace.user_id, trace.metadata)
    for span in trace.spans:
        child = root.start_observation(
            as_type="span",
            name=span["name"],
            input=span.get("input"),
            metadata={k: v for k, v in span.items() if k not in {"name", "input", "output"}},
        )
        if span.get("output") is not None:
            child.update(output=span["output"])
        child.end()
    root.update(output=trace.output)
    root.end()
    with suppress(Exception):
        get_langfuse().flush()
    return trace
