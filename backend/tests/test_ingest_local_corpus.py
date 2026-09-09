"""Focused behavioral tests for the local corpus ingestion CLI."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.persistence.models import ProvisionProvenance
from scripts import ingest_local_corpus as cli


def _parsed(parser: str = "pdfplumber") -> SimpleNamespace:
    return SimpleNamespace(
        pages=[object()],
        parser=parser,
        parsed_document_id="parse-1",
        document_id="doc-1",
        parser_version="test",
        ir_schema_version="document-ir-v2",
        source_object_key="doc-1.pdf",
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )


def _pdf(tmp_path: Path, name: str = "doc-1", data: bytes = b"pdf") -> Path:
    path = tmp_path / f"{name}.pdf"
    path.write_bytes(data)
    return path


def _manifest(path: Path, *, review_status: str = "ACCEPTED", file_hash: str | None = None) -> dict:
    return {
        "document_id": path.stem,
        "review_status": review_status,
        "file_hash": (
            file_hash if file_hash is not None else hashlib.sha256(path.read_bytes()).hexdigest()
        ),
    }


def _install_manifest(monkeypatch: pytest.MonkeyPatch, manifest: dict, tmp_path: Path) -> None:
    manifest_path = tmp_path / f"{manifest['document_id']}.manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(cli, "MANIFESTS", tmp_path)


def test_ingest_reports_every_requested_document_and_explicit_failure(
    monkeypatch, tmp_path: Path
) -> None:
    good = _pdf(tmp_path, "good")
    bad = _pdf(tmp_path, "bad")
    _install_manifest(monkeypatch, _manifest(good), tmp_path)
    (tmp_path / "bad.manifest.json").write_text(json.dumps(_manifest(bad)), encoding="utf-8")

    def parse(path: Path, *, ocr_adapter=None):
        if path.stem == "good":
            return _parsed()
        raise RuntimeError("parser down")

    monkeypatch.setattr(cli, "_parse", parse)
    monkeypatch.setattr(
        cli,
        "extract_legal_provisions",
        lambda _ir: [SimpleNamespace(provision_id="doc-1__dieu-1")],
    )
    monkeypatch.setattr(cli, "enrich_provision", lambda item: item)

    result = cli.ingest([good, bad], dry_run=True)

    assert result["expected_documents"] == 2
    assert {row["document_id"] for row in result["documents"]} == {"good"}
    assert {row["document_id"] for row in result["failures"]} == {"bad"}
    assert "parser down" in result["failures"][0]["error"]


def test_ingest_fails_document_when_no_legal_provisions_are_extracted(
    monkeypatch, tmp_path: Path
) -> None:
    path = _pdf(tmp_path)
    _install_manifest(monkeypatch, _manifest(path), tmp_path)
    monkeypatch.setattr(cli, "_parse", lambda _path, *, ocr_adapter=None: _parsed())
    monkeypatch.setattr(cli, "extract_legal_provisions", lambda _ir: [])
    result = cli.ingest([path], dry_run=True)
    assert result["failures"][0]["document_id"] == path.stem
    assert "no legal provisions extracted" in result["failures"][0]["error"]


def test_main_returns_nonzero_and_prints_failure(
    monkeypatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for index in range(13):
        name = "bad" if index == 1 else f"good-{index}"
        path = _pdf(tmp_path, name)
        (tmp_path / f"{name}.manifest.json").write_text(
            json.dumps(_manifest(path)), encoding="utf-8"
        )
    monkeypatch.setattr(cli, "CORPUS", tmp_path)
    monkeypatch.setattr(
        cli,
        "DEFAULT_DOCUMENTS",
        tuple(f"good-{i}" if i != 1 else "bad" for i in range(13)),
    )
    monkeypatch.setattr(
        cli,
        "ingest",
        lambda paths, *, dry_run, batch_size=32: {
            "documents": [],
            "failures": [{"document_id": "bad", "error": "boom"}],
            "dry_run": dry_run,
            "expected_documents": len(paths),
        },
    )

    # The CLI emits the complete report and makes a failed document observable.
    code = cli.main([])
    out = capsys.readouterr().out
    assert code != 0
    assert '"bad"' in out
    assert '"boom"' in out


def test_manifest_review_gate_and_hash_are_enforced(monkeypatch, tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    monkeypatch.setattr(cli, "MANIFESTS", tmp_path)
    (tmp_path / "doc-1.manifest.json").write_text(
        json.dumps(_manifest(path, review_status="PENDING")), encoding="utf-8"
    )
    pending = cli.ingest([path], dry_run=True)
    assert pending["failures"][0]["document_id"] == "doc-1"
    assert "ACCEPTED" in pending["failures"][0]["error"]

    (tmp_path / "doc-1.manifest.json").write_text(
        json.dumps(_manifest(path, file_hash="0" * 64)), encoding="utf-8"
    )
    mismatch = cli.ingest([path], dry_run=True)
    assert "hash mismatch" in mismatch["failures"][0]["error"]


def test_searchable_parser_then_ocr_fallback(monkeypatch, tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    _install_manifest(monkeypatch, _manifest(path), tmp_path)
    calls: list[str] = []

    def parse_searchable(_path):
        calls.append("pdf")
        raise cli.SearchableTextRequiredError("no text")

    def parse_ocr_subprocess(_path, _checkpoint):
        calls.append("ocr")
        return _parsed("hybrid_ocr")

    monkeypatch.setattr(cli, "_parse_searchable", parse_searchable)
    monkeypatch.setattr(cli, "_parse_scanned_in_worker", parse_ocr_subprocess)
    result = cli._parse(path)
    assert result.parser == "hybrid_ocr"
    assert calls == ["pdf", "ocr"]


def test_scanned_pdf_renderer_uses_checked_pdftoppm(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        (tmp_path / "page-2.png").write_bytes(b"2")
        (tmp_path / "page-1.png").write_bytes(b"1")

    monkeypatch.setattr(subprocess, "run", run)
    result = cli._render_scanned_pdf(tmp_path / "scan.pdf", tmp_path)
    assert result == [(1, tmp_path / "page-1.png"), (2, tmp_path / "page-2.png")]
    assert calls[0][0][:4] == ["pdftoppm", "-png", "-r", "144"]
    assert calls[0][1]["check"] is True


def test_dry_run_does_not_touch_persistence_boundaries(monkeypatch, tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    _install_manifest(monkeypatch, _manifest(path), tmp_path)
    monkeypatch.setattr(cli, "_parse", lambda _path, *, ocr_adapter=None: _parsed())
    touched = []
    monkeypatch.setattr(
        cli, "_persist", lambda *_args, **_kwargs: touched.append("db"), raising=False
    )
    monkeypatch.setattr(
        cli, "QdrantClient", lambda *_args, **_kwargs: touched.append("qdrant"), raising=False
    )

    result = cli.ingest([path], dry_run=True)

    assert result["dry_run"] is True
    assert touched == []


def test_repeat_ingestion_is_idempotent_at_persistence_boundary(
    monkeypatch, tmp_path: Path
) -> None:
    path = _pdf(tmp_path)
    _install_manifest(monkeypatch, _manifest(path), tmp_path)
    monkeypatch.setattr(cli, "_parse", lambda _path, *, ocr_adapter=None: _parsed())
    monkeypatch.setattr(
        cli,
        "extract_legal_provisions",
        lambda _ir: [SimpleNamespace(provision_id="doc-1__dieu-1")],
    )
    monkeypatch.setattr(cli, "enrich_provision", lambda item: item)
    monkeypatch.setattr(cli, "get_engine", lambda: object())
    monkeypatch.setattr(
        cli,
        "_persist",
        lambda *args, **kwargs: {"document_id": "doc-1"},
    )
    monkeypatch.setattr(cli, "index_accepted_provisions", lambda *args, **kwargs: None)
    monkeypatch.setattr(cli, "ensure_qdrant_collection", lambda: object())

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

    monkeypatch.setattr(cli, "sessionmaker", lambda **_: lambda: Session())
    first = cli.ingest([path], dry_run=False)
    second = cli.ingest([path], dry_run=False)

    assert first == second
    assert first["documents"][0]["document_id"] == "doc-1"


def test_scanned_documents_use_fresh_ocr_workers(monkeypatch, tmp_path):
    paths = [_pdf(tmp_path, f"scan-{i}") for i in range(2)]
    for path in paths:
        _install_manifest(monkeypatch, _manifest(path), tmp_path)
    calls = []

    def parse(path: Path):
        calls.append(path.name)
        return _parsed("hybrid_ocr")

    monkeypatch.setattr(cli, "_parse", parse)
    monkeypatch.setattr(
        cli, "extract_legal_provisions", lambda _ir: [SimpleNamespace(provision_id="x")]
    )
    monkeypatch.setattr(cli, "enrich_provision", lambda item: item)
    monkeypatch.setattr(cli, "_prepare_document", lambda *args: {})
    result = cli.ingest(paths, dry_run=True)
    assert not result["failures"]
    assert calls == ["scan-0.pdf", "scan-1.pdf"]


def test_ocr_worker_roundtrips_parsed_document(monkeypatch, tmp_path):
    output = tmp_path / "worker.json"
    parsed = cli.ParsedDocument(
        pages=[],
        parser="hybrid_ocr",
        parsed_document_id="parse-1",
        document_id="doc-1",
        parser_version="test",
        ir_schema_version="document-ir-v2",
        source_object_key="doc-1.pdf",
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )

    class OCR:
        def __init__(self, **kwargs):
            assert kwargs["device"] == "gpu:0"

        def parse_document(self, *_args, **kwargs):
            return parsed

    monkeypatch.setattr(cli, "_render_scanned_pdf", lambda *_args: [(1, tmp_path / "page.png")])
    import app.ingestion.adapters.hybrid_ocr_adapter as hybrid_ocr_adapter

    monkeypatch.setattr(hybrid_ocr_adapter, "HybridOCRAdapter", OCR)
    cli._run_ocr_worker(_pdf(tmp_path), output, tmp_path / "checkpoint")
    assert cli.ParsedDocument.model_validate_json(output.read_text()).parser == "hybrid_ocr"


def test_ocr_worker_failure_includes_child_stderr(monkeypatch, tmp_path):
    class Completed:
        returncode = 2
        stderr = "GPU init failed"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: Completed())
    with pytest.raises(RuntimeError, match="GPU init failed"):
        cli._parse_scanned_in_worker(_pdf(tmp_path), tmp_path / "checkpoint")


def test_dry_run_runs_same_preparation_as_persist(monkeypatch, tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    _install_manifest(monkeypatch, _manifest(path), tmp_path)
    monkeypatch.setattr(cli, "_parse", lambda _path, *, ocr_adapter=None: _parsed())
    monkeypatch.setattr(cli, "extract_legal_provisions", lambda _ir: [])
    result = cli.ingest([path], dry_run=True)
    assert result["failures"] and "no legal provisions extracted" in result["failures"][0]["error"]


def test_prepare_document_rejects_group_b_failures(monkeypatch, tmp_path: Path) -> None:
    path = _pdf(tmp_path)
    manifest = _manifest(path)
    ir = _parsed()
    ir.pages = []
    monkeypatch.setattr(cli, "evaluate_group_a", lambda _ir: SimpleNamespace(verdict="passed"))
    monkeypatch.setattr(
        cli,
        "evaluate_group_b",
        lambda _rows: SimpleNamespace(passed=False, model_dump=lambda **_: {"misses": 1}),
    )
    with pytest.raises(RuntimeError, match="Group B quality gate failed"):
        cli._prepare_document(path, manifest, ir, [SimpleNamespace()])


def test_persist_provenance_lookup_accepts_all_key_conditions(tmp_path: Path, monkeypatch) -> None:
    """The recovered provenance query must pass conditions as separate arguments."""
    key = (
        ProvisionProvenance.provision_version_row_id == 1,
        ProvisionProvenance.source_document_version_id == 2,
        ProvisionProvenance.source_element_id == "p1",
        ProvisionProvenance.role == "operative",
    )
    statement = cli.select(ProvisionProvenance).where(*key)
    assert "provision_version_row_id" in str(statement)
    assert "source_document_version_id" in str(statement)
