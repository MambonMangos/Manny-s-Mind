"""Alembic migration environment.

Wired to the project's SQLAlchemy models and to the same DATABASE_URL
configuration used by the application (see database/database.py). The URL
can be overridden with the DATABASE_URL environment variable, which is the
recommended way to target a specific environment (local / staging / prod).
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import utils.env  # noqa: F401  (load .env before reading DATABASE_URL)
from alembic import context
from database.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override the configured URL with DATABASE_URL when present. This keeps
# migrations and the application pointing at the same database.
if not config.get_main_option("sqlalchemy.url") or os.getenv("DATABASE_URL"):
    config.set_main_option(
        "sqlalchemy.url",
        os.getenv("DATABASE_URL") or config.get_main_option("sqlalchemy.url"),
    )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL without a live DBAPI connection — useful for reviewing the SQL
    a migration would produce.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
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


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
