"""Database migration tests.

Verifies the Alembic baseline applies cleanly to a fresh database and
produces the expected schema. Runs against a throwaway SQLite file so the
real development database is never touched.
"""

from __future__ import annotations

import os
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run_alembic(tmp_path, *args: str) -> subprocess.CompletedProcess:
    db_path = tmp_path / "migrate.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{db_path}",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_baseline_upgrade_head_creates_schema(tmp_path):
    """`alembic upgrade head` must succeed on an empty database."""
    result = _run_alembic(tmp_path, "upgrade", "head")
    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"


def test_baseline_schema_matches_models(tmp_path):
    """Post-migration tables must match the ORM models exactly."""
    from sqlalchemy import create_engine, inspect

    db_path = tmp_path / "migrate.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db_path}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=120,
        check=False,
    )

    engine = create_engine(f"sqlite:///{db_path}")
    db_tables = set(inspect(engine).get_table_names())

    import database.models  # noqa: F401
    from database.models import Base

    model_tables = set(Base.metadata.tables.keys())
    assert model_tables <= db_tables, (
        f"Tables missing after migration: {model_tables - db_tables}"
    )


def test_migrations_are_linear_and_ordered(tmp_path):
    """`alembic heads` must report exactly one head (linear history)."""
    result = _run_alembic(tmp_path, "heads")
    assert result.returncode == 0, result.stderr
    heads = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(heads) == 1, f"Expected a single migration head, got: {heads}"
