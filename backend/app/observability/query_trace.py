"""Durable, provider-neutral query trace model."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class QueryTrace:
    """In-memory representation of one complete legal-query pipeline."""

    query: str
    trace_id: str = field(default_factory=lambda: uuid4().hex)
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    spans: list[dict[str, Any]] = field(default_factory=list)
    output: Any = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    def add_span(self, name: str, *, input: Any = None, output: Any = None, **metadata: Any) -> dict[str, Any]:
        span = {"name": name, "input": input, "output": output, **metadata}
        self.spans.append(span)
        return span

    def finish(self, output: Any = None) -> QueryTrace:
        self.output = output
        self.ended_at = datetime.now(timezone.utc)
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "user_id": self.user_id,
            "metadata": dict(self.metadata),
            "spans": [dict(span) for span in self.spans],
            "output": self.output,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }


class QueryTraceStore:
    """Small process-local persistence boundary; replaceable by a repository."""

    def __init__(self) -> None:
        self._traces: dict[str, QueryTrace] = {}

    def save(self, trace: QueryTrace) -> QueryTrace:
        self._traces[trace.trace_id] = trace
        return trace

    def get(self, trace_id: str) -> QueryTrace | None:
        return self._traces.get(trace_id)

    def all(self) -> list[QueryTrace]:
        return list(self._traces.values())
