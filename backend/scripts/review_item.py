"""Minimal review CLI for ingestion quality-gate review items (VNLRAG-155).

Usage (from backend/):

    uv run python scripts/review_item.py list
    uv run python scripts/review_item.py list --status PENDING
    uv run python scripts/review_item.py show <item_id>
    uv run python scripts/review_item.py accept <item_id> --reviewer linh
    uv run python scripts/review_item.py needs-review <item_id> --reason "check source"
    uv run python scripts/review_item.py reject <item_id> --reviewer linh --reason "duplicate"

The reviewer defaults to the REVIEWER environment variable, then ``cli``.
Every decision persists reviewer + reviewed_at via ``ReviewItemRepository``
and is committed immediately.  The CLI only records decisions — the indexing
boundary (ACCEPTED -> indexable, otherwise not) is enforced by the ingestion
pipeline (VNLRAG-44).

The database URL follows the repo convention (alembic/env.py, doc 07 §7.3.3):
the ``DATABASE_URL`` environment variable, then the repository-root ``.env``
file.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.persistence.models import ReviewItem  # noqa: E402  (sys.path bootstrap above)
from app.persistence.repositories.review_items import (  # noqa: E402
    DECISION_TO_STATUS,
    ReviewItemNotFoundError,
    ReviewItemRepository,
)

#: ``--status`` choices mirror the routing decisions (doc 03 §3.4.2); note
#: NEEDS_REVIEW is a decision, not a stored status — ``_status_filter`` maps
#: it back to PENDING before querying (see repository module).
_STATUS_CHOICES = ("PENDING", "ACCEPTED", "NEEDS_REVIEW", "REJECTED", "DROPPED")


def _status_filter(choice: str | None) -> str | None:
    """Translate a CLI ``--status`` choice to a stored ``review_items.status``.

    The DB CHECK constraint allows only PENDING/ACCEPTED/REJECTED/DROPPED
    (models.py ``_REVIEW_STATUS_VALUES``); NEEDS_REVIEW is a routing decision
    that leaves the row PENDING, so the choice maps back to PENDING — i.e.
    ``list --status NEEDS_REVIEW`` shows the pending review queue.  Other
    choices are already stored statuses and pass through unchanged.  Matching
    ``DECISION_TO_STATUS``, keys are uppercase and comparison is
    case-insensitive.
    """
    if choice is None:
        return None
    normalized = choice.upper()
    return DECISION_TO_STATUS.get(normalized, normalized)


def _default_reviewer() -> str:
    """Reviewer name: $REVIEWER environment variable, then ``cli``."""
    return os.environ.get("REVIEWER") or "cli"


def _resolve_database_url() -> str:
    """DATABASE_URL environment variable, then the repository-root .env."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = _BACKEND_DIR.parent / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return line.partition("=")[2].strip().strip("'\"")
    raise RuntimeError(
        "DATABASE_URL is not set: export the variable or provide a "
        "repository-root .env file (doc 07 §7.3.3)"
    )


def _connect() -> Session:
    """A new session on the configured database (caller commits/closes)."""
    return Session(create_engine(_resolve_database_url()))


@contextmanager
def _session() -> Iterator[Session]:
    session = _connect()
    try:
        yield session
    finally:
        session.close()


def _item_fields(row: ReviewItem) -> dict[str, str | None]:
    """Plain-field snapshot of a review item.

    Safe to read right after ``session.commit()`` while the session is still
    open (commit expires ORM attributes); the returned dict stays usable
    after the session closes.
    """
    return {
        "id": str(row.id),
        "document_id": row.document_id,
        "target": f"{row.target_type} {row.target_id}",
        "reason_code": row.reason_code,
        "status": row.status,
        "reviewer": row.reviewer,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "description": row.description,
    }


def _print_fields(fields: dict[str, str | None]) -> None:
    """Human-readable block for one review item."""
    print(f"id:           {fields['id']}")
    print(f"document_id:  {fields['document_id']}")
    print(f"target:       {fields['target']}")
    print(f"reason_code:  {fields['reason_code']}")
    print(f"status:       {fields['status']}")
    print(f"reviewer:     {fields['reviewer'] or '-'}")
    print(f"reviewed_at:  {fields['reviewed_at'] or '-'}")
    if fields["description"]:
        print(f"description:  {fields['description']}")


def _cmd_list(args: argparse.Namespace) -> int:
    status = _status_filter(args.status)
    with _session() as session:
        rows = [row for row in ReviewItemRepository(session).list(status=status)]
    if not rows:
        print("No review items.")
        return 0
    print(f"{'STATUS':<12} {'ID':<36} {'DOCUMENT_ID':<24} {'TARGET':<44} REASON_CODE")
    for row in rows:
        print(
            f"{row.status:<12} {str(row.id):<36} {row.document_id:<24} "
            f"{row.target_type}/{row.target_id:<40} {row.reason_code}"
        )
    return 0


def _cmd_show(args: argparse.Namespace) -> int:
    with _session() as session:
        row = ReviewItemRepository(session).get(args.item_id)
        if row is None:
            raise ReviewItemNotFoundError(f"review item {args.item_id} not found")
        fields = _item_fields(row)
    _print_fields(fields)
    return 0


def _decision_handler(
    decision: str, note: str | None = None
) -> Callable[[argparse.Namespace], int]:
    """Handler factory: record ``decision``, commit, print the updated row."""

    def handler(args: argparse.Namespace) -> int:
        reviewer = args.reviewer or _default_reviewer()
        with _session() as session:
            row = ReviewItemRepository(session).record_decision(
                args.item_id, decision, reviewer, getattr(args, "reason", None)
            )
            session.commit()
            fields = _item_fields(row)
        if note:
            print(note.format(item_id=fields["id"]))
        _print_fields(fields)
        return 0

    return handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review_item",
        description="Review quality-gate review items (VNLRAG-155).",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p_list = sub.add_parser("list", help="list review items (all statuses by default)")
    p_list.add_argument(
        "--status",
        choices=_STATUS_CHOICES,
        help="only items with this status (NEEDS_REVIEW maps to the stored PENDING status)",
    )
    p_list.set_defaults(func=_cmd_list)

    p_show = sub.add_parser("show", help="show one review item")
    p_show.add_argument("item_id", type=UUID, help="review item id (uuid)")
    p_show.set_defaults(func=_cmd_show)

    p_accept = sub.add_parser("accept", help="record the ACCEPTED decision (indexable)")
    p_accept.add_argument("item_id", type=UUID, help="review item id (uuid)")
    p_accept.add_argument("--reviewer", help="reviewer name (default: $REVIEWER, then 'cli')")
    p_accept.set_defaults(func=_decision_handler("ACCEPTED"))

    p_needs = sub.add_parser(
        "needs-review", help="record the NEEDS_REVIEW decision (keeps PENDING)"
    )
    p_needs.add_argument("item_id", type=UUID, help="review item id (uuid)")
    p_needs.add_argument("--reviewer", help="reviewer name (default: $REVIEWER, then 'cli')")
    p_needs.add_argument("--reason", help="decision note appended to the item description")
    p_needs.set_defaults(
        func=_decision_handler(
            "NEEDS_REVIEW",
            note="Recorded NEEDS_REVIEW for {item_id} (status remains PENDING in the DB).",
        )
    )

    p_reject = sub.add_parser("reject", help="record the REJECTED decision (never indexed)")
    p_reject.add_argument("item_id", type=UUID, help="review item id (uuid)")
    p_reject.add_argument("--reviewer", help="reviewer name (default: $REVIEWER, then 'cli')")
    p_reject.add_argument("--reason", help="decision note appended to the item description")
    p_reject.set_defaults(func=_decision_handler("REJECTED"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ReviewItemNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
