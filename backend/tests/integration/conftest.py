"""PostgreSQL-backed fixtures for the VNLRAG-38 migration integration tests.

These tests run against a real PostgreSQL server only — SQLite is disallowed
for integration conclusions (doc 04 §4.12.3, doc 06 §6.2.2). Every session
creates a dedicated scratch database (``<main-db>_test``) so migrations never
touch the application database; the scratch database is dropped on teardown.
Tests that exercise their own upgrade/downgrade cycle get a separate per-test
scratch database.

The database URL is resolved with the same convention as ``alembic/env.py``:
an explicit ``sqlalchemy.url`` config value (not used here), then the
``DATABASE_URL`` environment variable, then the repository-root ``.env`` file
(doc 07 §7.3.3).

Nothing here connects to a database at import time, so the default CI unit job
(``pytest tests/ -m "not integration"``, doc 07 §7.11.1) never touches
PostgreSQL: all database work happens inside fixtures of integration-marked
tests.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

# Postgres identifiers created by these fixtures; keep them simple and safe.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _resolve_base_url() -> str:
    """Resolve DATABASE_URL: environment variable, then repo-root .env."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return _require_postgres(url)
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return _require_postgres(line.partition("=")[2].strip().strip("'\""))
    raise RuntimeError(
        "integration tests need a reachable PostgreSQL: set DATABASE_URL "
        "(postgresql+psycopg://...) in the environment or in the repo-root "
        ".env file (doc 07 §7.3.3)"
    )


def _require_postgres(url: str) -> str:
    """Reject non-PostgreSQL URLs: SQLite is disallowed for integration tests."""
    if make_url(url).get_backend_name() != "postgresql":
        raise RuntimeError(
            "PostgreSQL integration tests require a postgresql+psycopg:// "
            "DATABASE_URL (SQLite is disallowed, doc 04 §4.12.3 / doc 06 §6.2.2)"
        )
    return url


def _with_database(url: str, database: str) -> str:
    """Return ``url`` with the database name replaced by ``database``."""
    return make_url(url).set(database=database).render_as_string(hide_password=False)


def _scratch_name(base_url: str, suffix: str) -> str:
    name = make_url(base_url).database
    if not name or not _IDENTIFIER_RE.fullmatch(name):
        raise RuntimeError(f"DATABASE_URL must name a plain-identifier database, got: {name!r}")
    scratch = f"{name}_{suffix}"
    if not _IDENTIFIER_RE.fullmatch(scratch):
        raise RuntimeError(f"scratch database name is not a safe identifier: {scratch!r}")
    return scratch


def _create_scratch_database(base_url: str, scratch_name: str) -> None:
    """Create a scratch database (drops any pre-existing one with the name)."""
    admin = create_engine(_with_database(base_url, "postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{scratch_name}"'))
    finally:
        admin.dispose()


def _drop_scratch_database(base_url: str, scratch_name: str) -> None:
    admin = create_engine(_with_database(base_url, "postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)'))
    finally:
        admin.dispose()


def _alembic_config(database_url: str) -> AlembicConfig:
    """Alembic config pinned to absolute paths and the given database URL."""
    cfg = AlembicConfig(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(BACKEND_DIR))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


@pytest.fixture(scope="session")
def migration_db_url() -> Iterator[str]:
    """Session-scoped scratch database URL; dropped after the session."""
    base_url = _resolve_base_url()
    scratch = _scratch_name(base_url, "test")
    _create_scratch_database(base_url, scratch)
    yield _with_database(base_url, scratch)
    _drop_scratch_database(base_url, scratch)


@pytest.fixture(scope="session")
def alembic_config(migration_db_url: str) -> AlembicConfig:
    """Alembic config pointed at the session scratch database."""
    return _alembic_config(migration_db_url)


@pytest.fixture(scope="session")
def upgraded_engine(alembic_config: AlembicConfig) -> Iterator[Engine]:
    """Engine against the session scratch database, migrated to ``head``."""
    command.upgrade(alembic_config, "head")
    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url"))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def cycle_db_url() -> Iterator[str]:
    """Per-test scratch database for upgrade/downgrade round-trip tests."""
    base_url = _resolve_base_url()
    scratch = _scratch_name(base_url, f"cycle{uuid.uuid4().hex[:6]}")
    _create_scratch_database(base_url, scratch)
    yield _with_database(base_url, scratch)
    _drop_scratch_database(base_url, scratch)


@contextmanager
def clean_transaction(engine: Engine) -> Iterator[Connection]:
    """A connection with a transaction that is always rolled back.

    The caller may use ``conn.begin_nested()`` (savepoints) around statements
    expected to raise, so one failed statement does not abort the rest of the
    transaction; the outer transaction is rolled back on exit, leaving the
    scratch database empty between tests.
    """
    conn = engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


def sqlstate(exc: Exception) -> str | None:
    """PostgreSQL SQLSTATE from a SQLAlchemy DBAPI exception, if available."""
    orig = getattr(exc, "orig", None)
    return getattr(orig, "sqlstate", None)
