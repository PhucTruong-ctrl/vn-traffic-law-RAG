"""Alembic migration environment for the VNLaw backend.

The schema target is the SQLAlchemy ``Base.metadata`` of the persistence
models (``app.persistence.models``, VNLRAG-37). The database URL is resolved
conventionally, mirroring ``app.config.Settings`` (doc 07 §7.3.3): an explicit
``sqlalchemy.url`` config value (integration tests inject it), then the
``DATABASE_URL`` environment variable, then the repository-root ``.env`` file.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the backend package importable regardless of the invocation cwd
# (one-shot `migrate` service, CI step, test run).
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.persistence.models import Base  # noqa: E402  (VNLRAG-37 contract)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the database URL: config > DATABASE_URL env > repo-root .env."""
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured

    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    env_file = _BACKEND_DIR.parent / ".env"
    if env_file.is_file():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return line.partition("=")[2].strip().strip("'\"")

    raise RuntimeError(
        "DATABASE_URL is not set: export the variable, provide a repository-"
        "root .env file (doc 07 §7.3.3), or set [alembic] sqlalchemy.url."
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL to stdout, no DB connection)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against the resolved database."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
