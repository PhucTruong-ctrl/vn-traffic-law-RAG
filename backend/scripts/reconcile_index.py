"""CLI for PostgreSQL-Qdrant index reconciliation (VNLRAG-45).

Usage (from backend/):

    uv run python scripts/reconcile_index.py check
    uv run python scripts/reconcile_index.py check --collection legal_provisions_v1
    uv run python scripts/reconcile_index.py repair --dry-run
    uv run python scripts/reconcile_index.py repair
    uv run python scripts/reconcile_index.py rebuild --dry-run
    uv run python scripts/reconcile_index.py rebuild --collection legal_provisions_v3

Subcommands:

- ``check`` — compare PostgreSQL (ACCEPTED provisions) with the Qdrant index
  and print the report; NO repair. Exits 1 when divergence exists (missing /
  stale / extra), 0 when the index is clean — CI-friendly.
- ``repair`` — compare, then fix: re-index missing and stale points from
  PostgreSQL (PostgreSQL wins; stale points are never deleted) and drop extra
  points that no longer exist in PostgreSQL.
- ``rebuild`` — full collection replacement (doc 03 §3.11.7): build a new
  versioned collection (``--collection``, else ``legal_provisions_v{n+1}``)
  from ALL accepted provisions, then switch ``legal_provisions_active`` to it.
  The previous collection is RETAINED for the rollback/grace period; deleting
  it is the caller's policy.

``--dry-run`` performs the comparison but never mutates Qdrant. Every run is
recorded as an immutable JSON manifest under ``data/evaluation/reconcile/``
(``--out-dir`` overrides). Connection settings follow the repo convention
(doc 07 §7.3.3): ``DATABASE_URL`` / ``QDRANT_URL`` from the environment, then
the repository-root ``.env`` file.

``repair`` and ``rebuild`` index real points, so they resolve the configured
dense embedding provider (``EMBEDDING_*`` settings) and the SHARED
persisted-vocabulary sparse encoder (``load_or_fit_sparse_encoder`` from the
ingestion index actor, VNLRAG-133) fitted on the ACCEPTED provisions'
``retrieval_text`` — every point shares one token vocabulary with stable
sparse dimensions. A missing embedding API key or a missing shared encoder
module fails the run loudly instead of writing divergent vector-less points.
``rebuild`` refuses an existing ``--collection`` name (prior points would
survive) and never switches the alias when the indexing pass is incomplete
(partial rebuild = error).
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.config import get_qdrant_settings  # noqa: E402  (sys.path bootstrap above)
from app.retrieval import reconcile  # noqa: E402

if TYPE_CHECKING:  # pragma: no cover  (annotations only)
    from qdrant_client import QdrantClient

    from app.retrieval.embedding import EmbeddingProvider
    from app.retrieval.sparse import SparseEncoder


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


def _qdrant_client() -> QdrantClient:
    """Qdrant client from ``QdrantSettings`` (``QDRANT_URL`` env / .env)."""
    from qdrant_client import QdrantClient

    settings = get_qdrant_settings()
    return QdrantClient(
        url=settings.url,
        api_key=settings.api_key or None,
        timeout=30,
    )


def _load_or_fit_sparse_encoder(corpus_texts: list[str]) -> SparseEncoder:
    """Lazily import the shared persisted-vocabulary sparse encoder (VNLRAG-133).

    ``load_or_fit_sparse_encoder`` (``app.ingestion.actors.index``) loads the
    persisted corpus vocabulary or fits + persists it on first use, so every
    indexed point — from ingestion actors and from this CLI — shares one token
    vocabulary and therefore stable sparse dimensions (doc 03 §3.11.2). An
    unfitted encoder would assign text-local token ids per provision and
    produce inconsistent sparse dimensions across repaired/rebuild points.

    Imported lazily (same pattern as the ``index_provision_units`` wiring):
    the module is developed in parallel (VNLRAG-133) and may not exist yet —
    repair/rebuild then fail with a clear error instead of silently writing a
    divergent sparse space.
    """
    try:
        from app.ingestion.actors.index import load_or_fit_sparse_encoder
    except ImportError as exc:
        raise RuntimeError(
            "app.ingestion.actors.index.load_or_fit_sparse_encoder is not available "
            "(VNLRAG-133 not merged); repair/rebuild need the shared fitted sparse "
            "encoder so all points share one vocabulary"
        ) from exc
    return cast(SparseEncoder, load_or_fit_sparse_encoder(corpus_texts))


def _resolve_encoders(corpus_texts: list[str]) -> tuple[EmbeddingProvider | None, SparseEncoder]:
    """Configured dense embedding provider + shared fitted BM25 sparse encoder.

    The embedding provider is built from the ``EMBEDDING_*`` settings
    (``get_embedding_provider``); a missing provider API key surfaces as a
    ``ConfigError`` at the first embed — fail-fast inside the indexing pass,
    so a repair/rebuild can never silently write vector-less points into a
    vector collection. The sparse encoder is the shared persisted-vocabulary
    encoder fitted/loaded on ``corpus_texts`` (the ACCEPTED provisions'
    ``retrieval_text``) via :func:`_load_or_fit_sparse_encoder`.
    """
    from app.config import get_embedding_settings
    from app.retrieval.embedding import get_embedding_provider

    return (
        get_embedding_provider(get_embedding_settings()),
        _load_or_fit_sparse_encoder(corpus_texts),
    )


def _print_report(report: reconcile.ReconciliationReport) -> None:
    repaired = report.repaired
    print(
        f"total_pg={report.total_pg} total_qdrant={report.total_qdrant} "
        f"missing={len(report.missing)} stale={len(report.stale)} extra={len(report.extra)}"
    )
    if report.missing:
        print("missing:")
        for point_id in report.missing:
            print(f"  {point_id}")
    if report.stale:
        print("stale:")
        for point_id in report.stale:
            print(f"  {point_id}")
    if report.extra:
        print("extra:")
        for point_id in report.extra:
            print(f"  {point_id}")
    print(
        "repaired: "
        f"missing_reindexed={repaired.missing_reindexed} "
        f"stale_reindexed={repaired.stale_reindexed} "
        f"extra_dropped={repaired.extra_dropped}"
    )


def _run(
    args: argparse.Namespace,
) -> tuple[int, reconcile.ReconciliationReport | None, str | None]:
    """Execute the selected subcommand; returns (exit code, report, old collection).

    ``index_provision_units`` is resolved lazily inside the reconcile module
    (only when a repair/rebuild actually executes), so ``check`` and
    ``--dry-run`` work before VNLRAG-44's indexing module exists.
    """
    client = _qdrant_client()
    try:
        with _session() as session:
            if args.command in ("check", "repair"):
                if args.command == "repair" and args.collection is None and not args.dry_run:
                    # Bootstrap the derived index when the live collection /
                    # alias does not exist yet (idempotent; check and dry-run
                    # never create anything).
                    from app.retrieval.qdrant_store import ensure_qdrant_collection

                    ensure_qdrant_collection(client)
                embedder, sparse_encoder = (
                    _resolve_encoders(reconcile.accepted_retrieval_texts(session))
                    if args.command == "repair"
                    else (None, None)
                )
                report = reconcile.reconcile_index(
                    client,
                    session=session,
                    embedder=embedder,
                    sparse_encoder=sparse_encoder,
                    collection=args.collection,
                    batch_size=args.batch_size,
                    dry_run=args.dry_run or args.command == "check",
                )
                return (1 if report.diverged else 0), report, None
            # rebuild
            embedder, sparse_encoder = _resolve_encoders(
                reconcile.accepted_retrieval_texts(session)
            )
            old = reconcile.rebuild_index(
                client,
                session=session,
                embedder=embedder,
                sparse_encoder=sparse_encoder,
                collection_name=args.collection,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
            )
            return 0, None, old
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _print_rebuild_result(old_collection: str | None, dry_run: bool) -> None:
    if dry_run:
        print("rebuild: dry-run — no collection created, no alias switch")
        return
    if old_collection is None:
        print("rebuild: alias already pointed at the new collection (no-op)")
        return
    print(f"rebuild: alias switched; previous collection retained: {old_collection}")
    print(
        "  note: the previous collection is kept for the grace period (doc 03 "
        "§3.11.7); deleting it is the operator's policy after verification"
    )


def build_parser() -> argparse.ArgumentParser:
    """Argument parser (exposed for tests)."""
    parser = argparse.ArgumentParser(
        prog="reconcile_index",
        description="Compare and repair the Qdrant provision index against PostgreSQL "
        "(PostgreSQL is authoritative, doc 00 §8.6).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("check", "compare and print the report; no repair (exit 1 on divergence)"),
        ("repair", "compare and repair: re-index missing/stale, drop extra"),
        ("rebuild", "full collection replacement + alias switch (doc 03 §3.11.7)"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument(
            "--dry-run",
            action="store_true",
            help="compare only; never mutate Qdrant",
        )
        sub.add_argument(
            "--collection",
            default=None,
            help="check/repair: collection to compare (default: live alias target). "
            "rebuild: NEW collection name (default: next legal_provisions_v{n+1})",
        )
        sub.add_argument(
            "--batch-size",
            type=int,
            default=32,
            help="index_provision_units embedding batch size (default: 32)",
        )
        sub.add_argument(
            "--out-dir",
            type=Path,
            default=None,
            help="run-manifest directory (default: data/evaluation/reconcile/)",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    run_id = reconcile.make_run_id()
    started_at = datetime.now(UTC)
    manifest_config: dict[str, object] = {
        "command": args.command,
        "dry_run": args.dry_run,
        "collection": args.collection,
        "batch_size": args.batch_size,
    }
    try:
        exit_code, report, old_collection = _run(args)
    except Exception as exc:
        print(f"reconcile_index: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if report is not None:
        _print_report(report)
    else:
        _print_rebuild_result(old_collection, args.dry_run)
        # Rebuild produces no point-level report; record the retained old
        # collection so the manifest still tells the full story.
        report = reconcile.ReconciliationReport(repaired=reconcile.RepairCounts())
        manifest_config["rebuild"] = {"old_collection": old_collection}

    finished_at = datetime.now(UTC)
    try:
        path = reconcile.write_run_manifest(
            report,
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            out_dir=args.out_dir,
            config=manifest_config,
        )
    except Exception as exc:
        print(f"reconcile_index: failed to write run manifest: {exc}", file=sys.stderr)
        return 1
    print(f"run_id={run_id} status=COMPLETED manifest={path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
