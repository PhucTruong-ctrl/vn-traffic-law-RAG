"""PostgreSQL session factory for the HTTP API layer (VNLRAG-135).

The database URL follows the repo convention (``alembic/env.py``, doc 07
§7.3.3): the ``DATABASE_URL`` environment variable first, then the
repository-root ``.env`` file. No connection is opened at import time — the
engine is created lazily on first use and cached.

The session factory is request-scoped: ``get_db`` yields one
:class:`sqlalchemy.orm.Session` per request and closes it afterwards. Write
paths commit explicitly (the repositories only flush; the caller owns the
transaction, per the persistence layer convention).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_DIR.parent


def _resolve_database_url() -> str:
    """Resolve DATABASE_URL: environment variable, then the repo-root .env."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env_file = _REPO_ROOT / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return line.partition("=")[2].strip().strip("'\"")
    raise RuntimeError(
        "DATABASE_URL is not set: export the variable or provide a repo-root "
        ".env file (doc 07 §7.3.3)"
    )


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine (created lazily, cached)."""
    return create_engine(_resolve_database_url(), pool_pre_ping=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed on exit."""
    session = sessionmaker(bind=get_engine(), expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
