"""Behavior tests for the standalone search API."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api import search as search_api
from app.main import app


def _result(rank: int, number: str = "12/2024") -> SimpleNamespace:
    return SimpleNamespace(
        rank=rank,
        provision_id=f"p-{rank}",
        provision_version=1,
        document_id="d-1",
        document_version_id="dv-1",
        text="text",
        source_text="snippet",
        document_number=number,
        article="Điều 1",
        clause=None,
        point=None,
        effective_from=date(2024, 1, 1),
        effective_to=None,
        page_number=rank,
        retrieval_sources=["dense"],
        source_id="src",
        parent_context=None,
    )


def test_search_validates_request_and_rejects_unknown_mode() -> None:
    client = TestClient(app)
    assert client.post("/api/v1/search", json={"query": ""}).status_code == 422
    assert client.post("/api/v1/search", json={"query": "x", "mode": "other"}).status_code == 422
    assert client.post("/api/v1/search", json={"query": "x", "top_k": 101}).status_code == 422


@pytest.mark.parametrize("mode", ["hybrid", "dense", "sparse"])
def test_search_response_fields_filters_mode_and_pagination(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    seen: dict[str, object] = {}

    class Retriever:
        def retrieve(self, query: str, **kwargs: object) -> SimpleNamespace:
            seen.update(mode=mode, query=query, kwargs=kwargs)
            return SimpleNamespace(results=[_result(1), _result(2, "99/2024"), _result(3)])

        def search(self, query: str, **kwargs: object) -> SimpleNamespace:
            seen.update(mode=mode, query=query, kwargs=kwargs)
            return SimpleNamespace(results=[_result(1), _result(2, "99/2024"), _result(3)])

    monkeypatch.setattr(search_api, "_build_retriever", lambda selected: Retriever())
    response = TestClient(app).post(
        "/api/v1/search",
        json={
            "query": "tax",
            "mode": mode,
            "document_type": "12",
            "page": 2,
            "page_size": 1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["page"] == 2 and payload["page_size"] == 1
    assert payload["results"][0]["provision_id"] == "p-3"
    assert {
        "rank",
        "provision_id",
        "interval",
        "hierarchy",
        "provenance",
        "snippet",
    } <= payload["results"][0].keys()
    assert len(payload["trace_id"]) == 32
    assert seen["query"] == "tax"
