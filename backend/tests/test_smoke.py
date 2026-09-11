import logging
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.legal import api as legal_api
from app.legal import corpus
from app.main import app


def test_active_routes_are_registered() -> None:
    paths = set(app.openapi()["paths"])
    assert {
        "/api/v1/chat",
        "/api/v1/health",
        "/api/v1/auth/register",
        "/api/v1/auth/login",
        "/api/v1/auth/me",
        "/api/v1/chats",
        "/api/v1/legal-documents",
        "/api/v1/legal-search",
    } <= paths
    assert not any(path.startswith("/api/v1/documents") for path in paths)


def test_default_corpus_paths_resolve_from_repository_root(monkeypatch) -> None:
    monkeypatch.chdir(Path(__file__).resolve().parents[2] / "backend")
    monkeypatch.delenv("LEGAL_MANIFEST", raising=False)
    monkeypatch.delenv("LEGAL_CHUNKS", raising=False)

    checkout_root = Path(__file__).resolve().parents[2]
    assert checkout_root == corpus._ROOT
    assert checkout_root / "data" / "sources" / "manifest.json" == corpus._MANIFEST
    assert checkout_root / "data" / "corpus" / "mds" == corpus._LOCAL_DIR
    assert checkout_root / "data" / "processed" / "chunks.jsonl" == corpus._PROCESSED
    assert corpus._PROCESSED.is_file()
    loaded = corpus.chunks()
    assert loaded
    assert all(chunk.text.strip() for chunk in loaded)


def test_health_live() -> None:
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_reports_dependency_failure(monkeypatch) -> None:
    monkeypatch.setattr(main, "_supabase_ready", lambda: False)
    monkeypatch.setattr(main, "_qdrant_ready", lambda: True)
    response = TestClient(app).get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "supabase": False, "qdrant": True}


def test_qdrant_readiness_returns_false_when_settings_raise(monkeypatch) -> None:
    def raise_settings_error():
        raise RuntimeError("invalid qdrant settings")

    monkeypatch.setattr(main, "get_qdrant_settings", raise_settings_error)

    assert main._qdrant_ready() is False


def test_qdrant_readiness_closes_created_client(monkeypatch) -> None:
    class Settings:
        url = "http://qdrant"
        timeout = 2
        collection = "legal"

    class Client:
        closed = False

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_collection(self, collection):
            assert collection == Settings.collection

        def close(self):
            self.closed = True

    client = Client()
    monkeypatch.setattr(main, "get_qdrant_settings", lambda: Settings())
    monkeypatch.setattr(main, "QdrantClient", lambda **kwargs: client)

    assert main._qdrant_ready() is True
    assert client.closed is True


def test_trace_id_propagates_and_completion_log_is_structured(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = TestClient(app).get(
            "/api/v1/health/live", headers={"X-Trace-ID": "incoming-trace"}
        )
    assert response.headers["X-Trace-ID"] == "incoming-trace"
    record = next(record for record in caplog.records if record.message == "request completed")
    assert record.trace_id == "incoming-trace"
    assert record.method == "GET"
    assert record.path == "/api/v1/health/live"
    assert record.status == 200
    assert record.duration_ms >= 0
    assert response.json() == {"status": "ok"}


@dataclass
class Chunk:
    text: str
    metadata: dict


def test_markdown_document_detail_exposes_content_and_source_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        legal_api,
        "chunks",
        lambda: [
            Chunk(
                text="Điều 1. Nội dung quy định.",
                metadata={
                    "chunk_id": "c-1",
                    "document_id": "nd100",
                    "document_name": "Nghị định 100",
                    "source_file": "nd100.md",
                    "source_type": "markdown",
                    "source_kind": "markdown",
                },
            )
        ],
    )

    response = TestClient(app).get("/api/v1/legal-documents/nd100")

    assert response.status_code == 200
    assert response.json()["content"] == "Điều 1. Nội dung quy định."
    assert response.json()["source"]["source_kind"] == "markdown"
    assert response.json()["source"]["pdf_url"] is None


def test_pdf_document_detail_exposes_source_contract_without_file_read(monkeypatch) -> None:
    monkeypatch.setattr(
        legal_api,
        "chunks",
        lambda: [
            Chunk(
                text="PDF provision",
                metadata={
                    "chunk_id": "pdf-1",
                    "document_id": "pdf-law",
                    "document_name": "PDF law",
                    "source_file": "/missing/not-read.pdf",
                    "source_type": "pdf",
                    "source_url": "https://example.test/law.pdf",
                },
            )
        ],
    )

    response = TestClient(app).get("/api/v1/legal-documents/pdf-law")

    assert response.status_code == 200
    assert response.json()["content"] is None
    assert response.json()["source"]["source_kind"] == "pdf"
    assert response.json()["source"]["pdf_url"] == "https://example.test/law.pdf"
    response = TestClient(app).get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
