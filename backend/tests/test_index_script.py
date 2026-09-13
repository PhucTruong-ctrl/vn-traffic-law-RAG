from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "index.py"
_spec = importlib.util.spec_from_file_location("index_script", SCRIPT)
assert _spec and _spec.loader
index_script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(index_script)


@dataclass
class Settings:
    path: Path
    collection: str = "serving"
    url: str = ""
    api_key: str = "secret"
    timeout: int = 3


@dataclass
class Info:
    points_count: int


class FakeClient:
    def __init__(self, points: int):
        self.info = Info(points)
        self.closed = False

    def get_collection(self, collection: str) -> Info:
        return self.info

    def close(self) -> None:
        self.closed = True


class FakeStore:
    def __init__(self, client: FakeClient, collection_name: str):
        self.client = client
        self.collection_name = collection_name
        self.added: list[object] = []

    def add_documents(self, documents: list[object]) -> None:
        self.added.extend(documents)


def _patch_common(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, points: int = 1, url: str = ""
):
    settings = Settings(path=tmp_path / "qdrant", url=url)
    monkeypatch.setattr(index_script, "get_qdrant_settings", lambda: settings)
    monkeypatch.setattr(index_script, "get_embedding_settings", lambda: Settings(path=tmp_path))
    monkeypatch.setattr(index_script, "OpenAIEmbeddings", lambda **kwargs: kwargs)
    monkeypatch.setattr(index_script, "FastEmbedSparse", lambda name: name)
    client = FakeClient(points)
    calls: list[dict[str, object]] = []

    def construct_instance(**kwargs):
        calls.append(kwargs)
        return FakeStore(client, kwargs["collection_name"])

    monkeypatch.setattr(index_script.QdrantVectorStore, "construct_instance", construct_instance)
    return settings, client, calls


def _chunks(tmp_path: Path, count: int = 1) -> Path:
    path = tmp_path / "chunks.jsonl"
    path.write_text("\n".join('{"page_content": "x", "metadata": {}}' for _ in range(count)))
    return path


def test_default_invocation_uses_configured_collection_without_force(monkeypatch, tmp_path):
    settings, client, calls = _patch_common(monkeypatch, tmp_path)
    assert index_script.main(["--chunks", str(_chunks(tmp_path))]) == 0
    assert calls[0]["collection_name"] == settings.collection
    assert calls[0]["force_recreate"] is False
    assert client.closed


def test_force_recreate_requires_explicit_collection(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path)
    with pytest.raises(SystemExit, match="--collection"):
        index_script.main(["--chunks", str(_chunks(tmp_path)), "--force-recreate"])


def test_force_recreate_passes_flag_and_remote_api_key(monkeypatch, tmp_path):
    _, _, calls = _patch_common(monkeypatch, tmp_path, url="https://qdrant.example")
    index_script.main(
        ["--chunks", str(_chunks(tmp_path)), "--collection", "new", "--force-recreate"]
    )
    assert calls[0]["force_recreate"] is True
    assert calls[0]["client_options"] == {
        "url": "https://qdrant.example",
        "timeout": 3,
        "api_key": "secret",
    }


def test_count_mismatch_fails(monkeypatch, tmp_path):
    _patch_common(monkeypatch, tmp_path, points=2)
    with pytest.raises(SystemExit, match="expected 1 points, found 2"):
        index_script.main(["--chunks", str(_chunks(tmp_path))])
