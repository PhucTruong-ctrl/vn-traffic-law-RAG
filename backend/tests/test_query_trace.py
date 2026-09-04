from app.observability.query_trace import QueryTrace, QueryTraceStore


def test_query_trace_persists_pipeline_and_round_trips() -> None:
    trace = QueryTrace("query", user_id="u1")
    trace.add_span("retrieve", output={"hits": 2})
    trace.finish({"answer": "ok"})
    store = QueryTraceStore()
    store.save(trace)
    assert store.get(trace.trace_id) is trace
    assert trace.as_dict()["spans"][0]["output"] == {"hits": 2}
    assert trace.ended_at is not None
