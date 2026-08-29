from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

from app.ingestion.actors import quality_gate as quality_gate_module
from app.ingestion.actors import resolve_temporal as temporal_actor
from app.ingestion.actors.resolve_temporal import resolve_temporal_actor
from app.ingestion.temporal_resolver import ResolutionResult, ResolvedVersion


class _Session:
    def __init__(self) -> None:
        self.committed = False
        self.closed = False
        self.added = []

    def scalars(self, _statement):
        return SimpleNamespace(all=lambda: [])

    def scalar(self, _statement):
        return None

    def add(self, item) -> None:
        self.added.append(item)

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def test_actor_translates_dated_accepted_amendment_relation(monkeypatch) -> None:
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
        document_version_id="version-id",
    )
    relation = SimpleNamespace(
        relation_type="AMENDS",
        effective_from=date(2025, 1, 1),
        review_status="ACCEPTED",
        resolution_status="RESOLVED",
        confidence=1.0,
        source_document_id="doc-id",
        source_note="amendment",
    )

    class RelationSession(_Session):
        def __init__(self):
            super().__init__()
            self.scalar_calls = 0

        def scalars(self, _statement):
            self.scalar_calls += 1
            return SimpleNamespace(all=lambda: [] if self.scalar_calls == 1 else [relation])

    session = RelationSession()
    captured = {}
    quality_gate_send = Mock()
    result = ResolutionResult((ResolvedVersion("article-1", 1, date(2024, 1, 1), None),), ())
    monkeypatch.setattr(temporal_actor, "new_session", lambda: session)
    monkeypatch.setattr(temporal_actor, "load_run", lambda *_: run)
    monkeypatch.setattr(temporal_actor, "stage_done", lambda *_: False)
    monkeypatch.setattr(temporal_actor, "latest_document_version", lambda *_: version)
    monkeypatch.setattr(temporal_actor, "list_provisions", lambda *_: [row])
    monkeypatch.setattr(quality_gate_module.quality_gate_actor, "send", quality_gate_send)
    monkeypatch.setattr(temporal_actor, "stage_done", lambda *_: False)
    monkeypatch.setattr(temporal_actor, "latest_document_version", lambda *_: version)
    monkeypatch.setattr(temporal_actor, "list_provisions", lambda *_: [row])
    monkeypatch.setattr(
        temporal_actor,
        "resolve_temporal",
        lambda _manifest, events: (captured.setdefault("events", events), result)[1],
    )
    resolve_temporal_actor(job_id="job-id")

    assert captured["events"][0]["event_type"] == "AMENDED"
    assert captured["events"][0]["event_date"] == date(2025, 1, 1)


def test_actor_halts_for_missing_successor_content(monkeypatch) -> None:
    run = SimpleNamespace(
        id="run-id",
        document_id="doc-id",
        manifest_json={
            "effective_from": "2024-01-01",
            "review_status": "ACCEPTED",
            "provisions": [{"provision_id": "article-1", "version": 1}],
            "effect_events": [
                {
                    "event_type": "AMENDED",
                    "event_date": "2024-02-01",
                    "affected_provision_versions": [{"provision_id": "article-1"}],
                    "review_status": "ACCEPTED",
                }
            ],
        },
    )
    version = SimpleNamespace(id="version-id", effective_from=date(2024, 1, 1))
    row = SimpleNamespace(
        provision_id="article-1",
        version=1,
        effective_from=None,
        effective_to=None,
        review_status="PENDING",
        document_version_id="version-id",
    )
    session = _Session()
    quality_gate_send = Mock()

    monkeypatch.setattr(temporal_actor, "new_session", lambda: session)
    monkeypatch.setattr(temporal_actor, "load_run", lambda _session, _job_id: run)
    monkeypatch.setattr(quality_gate_module.quality_gate_actor, "send", quality_gate_send)
    monkeypatch.setattr(temporal_actor, "stage_done", lambda _run, _stage: False)
    monkeypatch.setattr(
        temporal_actor,
        "latest_document_version",
        lambda _session, _document_id: version,
    )
    monkeypatch.setattr(temporal_actor, "list_provisions", lambda _session, _version_id: [row])

    resolve_temporal_actor(job_id="job-id")

    assert run.status == "PENDING_REVIEW"
    assert run.current_stage == "RESOLVING_TEMPORAL"
    assert run.error["code"] == "TEMPORAL_REVIEW"
    assert quality_gate_send.called is False
    assert len(session.added) == 1
    assert session.added[0].reason_code == "MISSING_SUCCESSOR_CONTENT"


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
    monkeypatch.setattr(
        temporal_actor,
        "latest_document_version",
        lambda _session, _document_id: version,
    )
    monkeypatch.setattr(temporal_actor, "list_provisions", lambda _session, _version_id: [row])

    resolve_temporal_actor(job_id="job-id")

    assert row.effective_from == date(2024, 1, 1)
    assert row.effective_to is None
    assert row.review_status == "ACCEPTED"
    assert session.committed is True
    quality_gate_send.assert_called_once_with("job-id")
