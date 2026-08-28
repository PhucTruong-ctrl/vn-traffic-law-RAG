from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from app.ingestion.actors import quality_gate as quality_gate_module
from app.ingestion.actors import resolve_temporal as temporal_actor
from app.ingestion.actors.resolve_temporal import resolve_temporal_actor


class _Session:
    def __init__(self) -> None:
        self.committed = False
        self.closed = False

    def scalars(self, _statement):
        return SimpleNamespace(all=lambda: [])

    def scalar(self, _statement):
        return None

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def test_actor_resolves_persisted_provisions_without_manifest_provisions(monkeypatch) -> None:
    run = SimpleNamespace(
        id="run-id",
        document_id="doc-id",
        manifest_json={"effective_from": "2024-01-01", "review_status": "ACCEPTED"},
    )
    version = SimpleNamespace(id="version-id", effective_from=date(2024, 1, 1))
    row = SimpleNamespace(
        provision_id="article-1",
        version=1,
        effective_from=None,
        effective_to=None,
        review_status="PENDING",
    )
    session = _Session()
    quality_gate_send = Mock()

    monkeypatch.setattr(temporal_actor, "new_session", lambda: session)
    monkeypatch.setattr(temporal_actor, "load_run", lambda _session, _job_id: run)
    monkeypatch.setattr(quality_gate_module.quality_gate_actor, "send", quality_gate_send)
    monkeypatch.setattr(temporal_actor, "stage_done", lambda _run, _stage: False)
    monkeypatch.setattr(temporal_actor, "latest_document_version", lambda _session, _document_id: version)
    monkeypatch.setattr(temporal_actor, "list_provisions", lambda _session, _version_id: [row])


    resolve_temporal_actor(job_id="job-id")

    assert row.effective_from == date(2024, 1, 1)
    assert row.effective_to is None
    assert row.review_status == "ACCEPTED"
    assert session.committed is True
    quality_gate_send.assert_called_once_with("job-id")
