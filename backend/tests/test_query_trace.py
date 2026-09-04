from __future__ import annotations

from datetime import datetime

import app.observability.langfuse_client as langfuse_client
from app.observability.langfuse import emit_query_trace
from app.observability.query_trace import QueryTrace, QueryTraceStore


def test_query_trace_records_ordered_spans_and_serializes_metadata() -> None:
    trace = QueryTrace("query", user_id="u1", metadata={"request_id": "r1"})
    retrieve = trace.add_span("retrieve", input={"query": "query"}, output={"hits": 2}, latency_ms=12)
    answer = trace.add_span("answer", output={"text": "ok"})
    trace.finish({"answer": "ok"})

    payload = trace.as_dict()
    assert [span["name"] for span in payload["spans"]] == ["retrieve", "answer"]
    assert retrieve["latency_ms"] == 12
    assert payload["metadata"] == {"request_id": "r1"}
    assert payload["output"] == {"answer": "ok"}
    assert datetime.fromisoformat(payload["started_at"]).tzinfo is not None
    assert datetime.fromisoformat(payload["ended_at"]).tzinfo is not None


def test_query_trace_store_replaces_same_trace_id_and_lists_traces() -> None:
    store = QueryTraceStore()
    first = QueryTrace("first", trace_id="shared")
    replacement = QueryTrace("replacement", trace_id="shared")

    assert store.save(first) is first
    assert store.save(replacement) is replacement
    assert store.get("shared") is replacement
    assert store.get("missing") is None
    assert store.all() == [replacement]


def test_emit_query_trace_is_safe_when_langfuse_disabled(monkeypatch) -> None:
    monkeypatch.setattr(langfuse_client, "_client", None)
    monkeypatch.setattr(langfuse_client, "get_settings", lambda: type("Settings", (), {"langfuse_enabled": False, "prompt_source": "LANGFUSE"})())
    trace = QueryTrace("query")
    trace.add_span("retrieve", input={"q": "query"}, output={"hits": 1})
    trace.finish({"answer": "ok"})

    assert emit_query_trace(trace) is trace
    assert isinstance(langfuse_client.get_langfuse(), langfuse_client.NoOpLangfuse)
    assert langfuse_client.get_langfuse().flush() is None
