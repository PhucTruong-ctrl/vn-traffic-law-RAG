"""Unit tests: review CLI + review item repository (VNLRAG-155).

No PostgreSQL required: argument parsing and decision mapping are pure
functions; the repository is exercised through a duck-typed fake session
(same convention as ``tests/test_corpus_qa.py``), and CLI handlers are
tested with ``_connect`` monkeypatched.  The real-PostgreSQL flow lives in
``tests/integration/test_review_decision_flow.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC

import pytest

from app.persistence.models import ReviewItem
from app.persistence.repositories.review_items import (
    DECISION_TO_STATUS,
    ReviewItemNotFoundError,
    ReviewItemRepository,
)
from scripts import review_item as cli


class _FakeSession:
    """Duck-typed Session capturing add/flush/scalar(s)/commit for unit testing."""

    def __init__(self) -> None:
        self.added: object | None = None
        self.flushed = False
        self.committed = False
        self.closed = False
        self.statement: object | None = None
        self.scalar_result: object | None = None
        self.scalars_result: list[ReviewItem] = []

    def add(self, obj: object) -> None:
        self.added = obj

    def flush(self) -> None:
        self.flushed = True

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True

    def scalar(self, statement: object) -> object | None:
        self.statement = statement
        return self.scalar_result

    def scalars(self, statement: object) -> list[ReviewItem]:
        self.statement = statement
        return self.scalars_result


def _row(**overrides: object) -> ReviewItem:
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "ingestion_run_id": uuid.uuid4(),
        "document_id": "doc-1",
        "target_type": "PROVISION",
        "target_id": "nd-168-2024__dieu-7",
        "reason_code": "LOW_OCR_COVERAGE",
        "description": "OCR coverage 0.42 below the 0.8 threshold",
        "evidence": {"text_extraction_rate": 0.42},
        "status": "PENDING",
    }
    fields.update(overrides)
    return ReviewItem(**fields)  # type: ignore[arg-type]


def _fake_repo_session(scalar_result: object | None = None) -> _FakeSession:
    session = _FakeSession()
    session.scalar_result = scalar_result
    return session


# ── argument parsing (pure, no DB) ─────────────────────────────────────────


def test_parser_list_defaults() -> None:
    args = cli.build_parser().parse_args(["list"])
    assert args.command == "list"
    assert args.status is None
    assert callable(args.func)


def test_parser_list_status() -> None:
    args = cli.build_parser().parse_args(["list", "--status", "PENDING"])
    assert args.status == "PENDING"


def test_parser_list_rejects_unknown_status() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["list", "--status", "NOPE"])


def test_parser_show_parses_uuid() -> None:
    item_id = uuid.uuid4()
    args = cli.build_parser().parse_args(["show", str(item_id)])
    assert args.command == "show"
    assert args.item_id == item_id


def test_parser_accept() -> None:
    item_id = uuid.uuid4()
    args = cli.build_parser().parse_args(["accept", str(item_id), "--reviewer", "linh"])
    assert args.command == "accept"
    assert args.item_id == item_id
    assert args.reviewer == "linh"
    assert "reason" not in vars(args)


def test_parser_needs_review_and_reject_take_reason() -> None:
    item_id = uuid.uuid4()
    for command in ("needs-review", "reject"):
        args = cli.build_parser().parse_args(
            [command, str(item_id), "--reviewer", "linh", "--reason", "check source"]
        )
        assert args.command == command
        assert args.reviewer == "linh"
        assert args.reason == "check source"


def test_parser_rejects_malformed_uuid() -> None:
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["show", "not-a-uuid"])


# ── decision mapping (pure) ─────────────────────────────────────────────────


def test_decision_to_status_mapping() -> None:
    # NEEDS_REVIEW is a routing decision, not a DB status: it maps back to
    # PENDING because the CHECK allows only PENDING/ACCEPTED/REJECTED/DROPPED.
    assert DECISION_TO_STATUS == {
        "ACCEPTED": "ACCEPTED",
        "NEEDS_REVIEW": "PENDING",
        "REJECTED": "REJECTED",
        "DROPPED": "DROPPED",
    }


def test_default_reviewer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEWER", "linh")
    assert cli._default_reviewer() == "linh"
    monkeypatch.delenv("REVIEWER")
    assert cli._default_reviewer() == "cli"


# ── repository (fake session) ──────────────────────────────────────────────


def test_create_defaults_to_pending() -> None:
    session = _FakeSession()
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]
    row = repository.create(
        ingestion_run_id=uuid.uuid4(),
        document_id="doc-1",
        target_type="PROVISION",
        target_id="nd-168-2024__dieu-7",
        reason_code="LOW_OCR_COVERAGE",
        description="OCR coverage 0.42",
        evidence={"text_extraction_rate": 0.42},
    )

    assert isinstance(row, ReviewItem)
    # status PENDING is applied by the ORM/server default at flush time; the
    # fake session cannot run flush defaults, so it is asserted against real
    # PostgreSQL in tests/integration/test_review_decision_flow.py.
    assert row.status is None
    assert row.reviewer is None
    assert row.reviewed_at is None
    assert row.evidence == {"text_extraction_rate": 0.42}
    assert session.added is row
    assert session.flushed is True


def test_get_returns_row() -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    assert repository.get(row.id) is row
    sql = str(session.statement)
    assert "review_items" in sql
    assert "WHERE review_items.id" in sql


def test_list_builds_status_filter_and_limit() -> None:
    session = _FakeSession()
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    repository.list(status="PENDING")
    sql = str(session.statement)
    assert "review_items" in sql
    assert "WHERE review_items.status" in sql
    assert "LIMIT" in sql

    repository.list()
    sql_all = str(session.statement)
    assert "WHERE" not in sql_all


def test_list_returns_rows() -> None:
    rows = [_row(), _row()]
    session = _FakeSession()
    session.scalars_result = rows
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    assert repository.list() == rows


def test_record_decision_accept_sets_reviewer_and_reviewed_at() -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    updated = repository.record_decision(row.id, "ACCEPTED", reviewer="linh")

    assert updated is row
    assert row.status == "ACCEPTED"
    assert row.reviewer == "linh"
    assert row.reviewed_at is not None
    assert row.reviewed_at.tzinfo is UTC
    assert session.flushed is True


def test_record_decision_needs_review_keeps_pending() -> None:
    row = _row(description="original description")
    session = _fake_repo_session(scalar_result=row)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    updated = repository.record_decision(
        row.id, "NEEDS_REVIEW", reviewer="linh", reason="verify against official source"
    )

    assert updated.status == "PENDING"
    assert updated.reviewer == "linh"
    assert updated.reviewed_at is not None
    # Reason is appended for audit; the item stays in the review queue.
    assert updated.description == "original description\nverify against official source"


@pytest.mark.parametrize("decision", ["REJECTED", "DROPPED"])
def test_record_decision_rejected_and_dropped(decision: str) -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    updated = repository.record_decision(row.id, decision, reviewer="linh")  # type: ignore[arg-type]

    # REJECTED/DROPPED -> dropped, never indexed (boundary enforced in VNLRAG-44).
    assert updated.status == decision
    assert updated.reviewer == "linh"
    assert updated.reviewed_at is not None


def test_record_decision_reason_without_description() -> None:
    row = _row(description=None)
    session = _fake_repo_session(scalar_result=row)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    updated = repository.record_decision(row.id, "REJECTED", reviewer="linh", reason="duplicate")

    assert updated.description == "duplicate"


def test_record_decision_unknown_decision_raises() -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="invalid review decision"):
        repository.record_decision(row.id, "MAYBE", reviewer="linh")  # type: ignore[arg-type]


def test_record_decision_missing_item_raises() -> None:
    session = _fake_repo_session(scalar_result=None)
    repository = ReviewItemRepository(session)  # type: ignore[arg-type]

    with pytest.raises(ReviewItemNotFoundError, match="not found"):
        repository.record_decision(uuid.uuid4(), "ACCEPTED", reviewer="linh")


# ── CLI handlers (monkeypatched session) ───────────────────────────────────


def test_main_show_missing_item_returns_1(capsys: pytest.CaptureFixture[str]) -> None:
    session = _fake_repo_session(scalar_result=None)

    def fake_connect() -> _FakeSession:
        return session

    cli._connect = fake_connect  # type: ignore[assignment]

    code = cli.main(["show", str(uuid.uuid4())])

    assert code == 1
    assert "not found" in capsys.readouterr().err


def test_main_accept_records_decision(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)

    monkeypatch.setattr(cli, "_connect", lambda: session)

    code = cli.main(["accept", str(row.id), "--reviewer", "linh"])

    assert code == 0
    assert session.committed is True
    assert session.closed is True
    assert row.status == "ACCEPTED"
    assert row.reviewer == "linh"
    assert row.reviewed_at is not None
    out = capsys.readouterr().out
    assert "ACCEPTED" in out
    assert "linh" in out


def test_main_accept_reviewer_from_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    monkeypatch.setattr(cli, "_connect", lambda: session)
    monkeypatch.setenv("REVIEWER", "env-reviewer")

    code = cli.main(["accept", str(row.id)])

    assert code == 0
    assert row.reviewer == "env-reviewer"
    assert "env-reviewer" in capsys.readouterr().out


def test_main_reject_records_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    monkeypatch.setattr(cli, "_connect", lambda: session)

    code = cli.main(["reject", str(row.id), "--reviewer", "linh", "--reason", "duplicate"])

    assert code == 0
    assert row.status == "REJECTED"
    assert row.reviewer == "linh"
    assert row.description.endswith("duplicate")


def test_main_needs_review_keeps_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row()
    session = _fake_repo_session(scalar_result=row)
    monkeypatch.setattr(cli, "_connect", lambda: session)

    code = cli.main(["needs-review", str(row.id), "--reviewer", "linh", "--reason", "check"])

    assert code == 0
    assert row.status == "PENDING"
    assert row.reviewer == "linh"
    assert row.reviewed_at is not None


def test_main_list_prints_rows(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_row(), _row(status="ACCEPTED", reviewer="linh")]
    session = _FakeSession()
    session.scalars_result = rows
    monkeypatch.setattr(cli, "_connect", lambda: session)

    code = cli.main(["list"])

    assert code == 0
    out = capsys.readouterr().out
    assert "STATUS" in out
    assert "PENDING" in out
    assert "ACCEPTED" in out
    assert "LOW_OCR_COVERAGE" in out


def test_main_list_empty(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    session = _FakeSession()
    monkeypatch.setattr(cli, "_connect", lambda: session)

    code = cli.main(["list", "--status", "PENDING"])

    assert code == 0
    assert "No review items." in capsys.readouterr().out
