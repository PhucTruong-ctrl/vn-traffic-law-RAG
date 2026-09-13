from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep


def test_store_for_query_creates_store_once_under_concurrency(monkeypatch) -> None:
    from app.rag import retrieval

    retriever = retrieval.Retriever()
    store = object()
    calls = 0
    calls_lock = Lock()

    def create_store():
        nonlocal calls
        with calls_lock:
            calls += 1
        sleep(0.01)
        retriever._store = store
        return store

    monkeypatch.setattr(retriever, "_create_store", create_store)

    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _: retriever._store_for_query(), range(8)))

    assert stores == [store] * 8
    assert calls == 1
