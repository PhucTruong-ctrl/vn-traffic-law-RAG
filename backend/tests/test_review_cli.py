"""Behavioral tests for review CLI contract helpers."""

from __future__ import annotations

from argparse import Namespace
from uuid import uuid4

import pytest

from scripts import review_item


def test_status_filter_maps_decision_to_persisted_status() -> None:
    assert review_item._status_filter("NEEDS_REVIEW") == "PENDING"
    assert review_item._status_filter("ACCEPTED") == "ACCEPTED"
    assert review_item._status_filter("REJECTED") == "REJECTED"


def test_default_reviewer_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REVIEWER", "review-bot")
    assert review_item._default_reviewer() == "review-bot"


def test_decision_handler_commits_and_prints(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    item_id = uuid4()
    row = Namespace(
        id=item_id,
        document_id="doc-1",
        target_type="PROVISION",
        target_id="p-1",
        reason_code="LOW_OCR_COVERAGE",
        status="ACCEPTED",
        reviewer="review-bot",
        reviewed_at=None,
        description="approved",
    )

    class Repo:
        def __init__(self, session):
            pass

        def record_decision(self, *args):
            assert args[0] == item_id
            assert args[1] == "ACCEPTED"
            assert args[2] == "review-bot"
            return row

    class Session:
        def commit(self):
            pass

    monkeypatch.setattr(review_item, "_session", lambda: _context(Session()))
    monkeypatch.setattr(review_item, "ReviewItemRepository", Repo)
    assert review_item._decision_handler("ACCEPTED")(Namespace(item_id=item_id, reviewer=None)) == 0
    output = capsys.readouterr().out
    assert "status:       ACCEPTED" in output
    assert "reviewer:     review-bot" in output


def _context(value):
    class Context:
        def __enter__(self):
            return value

        def __exit__(self, *args):
            return False

    return Context()
