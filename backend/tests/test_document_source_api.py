from types import SimpleNamespace

import pytest
from fastapi.responses import JSONResponse, Response

from app.api import documents


class _Session:
    def __init__(self, document):
        self.document = document

    def scalar(self, _statement):
        return self.document


class _Storage:
    def __init__(self, data: bytes | None = None):
        self.data = data
        self.put_calls = []

    def get(self, _bucket, _key):
        if self.data is None:
            raise FileNotFoundError
        return self.data

    def put(self, bucket, key, data, **kwargs):
        self.put_calls.append((bucket, key, data, kwargs))


def _document(**overrides):
    values = {
        "document_id": "nd-168-2024",
        "file_hash": "7bb11b939d162499ab404aa41a940cce05dbf071d9cbae7a8898b00d4b4a48bd",
        "source_url": "https://datafiles.chinhphu.vn/example.pdf",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_document_source_returns_cached_pdf(monkeypatch):
    storage = _Storage(b"%PDF-cached")
    monkeypatch.setattr(documents, "get_object_storage", lambda: storage)
    response = documents.get_document_source("nd-168-2024", _Session(_document()))
    assert isinstance(response, Response)
    assert response.media_type == "application/pdf"
    assert response.body == b"%PDF-cached"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_document_source_reports_missing_official_pdf(monkeypatch):
    storage = _Storage()
    monkeypatch.setattr(documents, "get_object_storage", lambda: storage)
    response = documents.get_document_source("missing", _Session(None))
    assert isinstance(response, JSONResponse)
    assert response.status_code == 404
    assert b"NOT_FOUND" in response.body


def test_document_source_rejects_untrusted_download_host(monkeypatch):
    storage = _Storage()
    monkeypatch.setattr(documents, "get_object_storage", lambda: storage)
    response = documents.get_document_source(
        "nd-168-2024",
        _Session(_document(source_url="https://example.com/document.pdf")),
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 502
    assert b"SOURCE_PDF_UNAVAILABLE" in response.body
    assert storage.put_calls == []


@pytest.mark.parametrize(
    "source_url",
    [
        "https://datafiles.chinhphu.vn/example.pdf?download=1",
        "https://user:pass@datafiles.chinhphu.vn/example.pdf",
        "https://datafiles.chinhphu.vn:444/example.pdf",
        "https://datafiles.chinhphu.vn",
    ],
)
def test_document_source_rejects_malicious_or_noncanonical_url(monkeypatch, source_url):
    storage = _Storage()
    monkeypatch.setattr(documents, "get_object_storage", lambda: storage)
    response = documents.get_document_source(
        "nd-168-2024",
        _Session(_document(source_url=source_url)),
    )
    assert isinstance(response, JSONResponse)
    assert response.status_code == 502
    assert storage.put_calls == []
