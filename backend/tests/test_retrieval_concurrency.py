from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from time import sleep
from unittest.mock import patch

from app.rag.retrieval import Retriever


def test_cold_start_creates_store_once_for_concurrent_callers() -> None:
    retriever = Retriever()
    callers = 12
    start = Barrier(callers)
    create_lock = Lock()
    created: list[object] = []
    store = object()

    def create_store() -> object:
        with create_lock:
            created.append(store)
        sleep(0.01)
        retriever._store = store
        return store

    def get_store() -> object:
        start.wait()
        return retriever._store_for_query()

    with (
        patch.object(retriever, "_create_store", side_effect=create_store),
        ThreadPoolExecutor(max_workers=callers) as pool,
    ):
        results = list(pool.map(lambda _: get_store(), range(callers)))

    assert len(created) == 1
    assert all(result is store for result in results)
