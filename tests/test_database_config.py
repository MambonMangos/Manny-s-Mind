"""Tests for database URL resolution and dialect-aware engine setup."""

from __future__ import annotations

import pytest
from sqlalchemy import event, text

import database.database as db
from database.database import (
    _make_engine,
    _resolve_database_url,
    _set_sqlite_pragma,
)

# ---------------------------------------------------------------------------
# URL resolution: env > Streamlit secrets > default SQLite path
# ---------------------------------------------------------------------------


def test_env_var_wins(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///tmp/env.db")
    monkeypatch.setattr(db, "_database_url_from_secrets", lambda: "postgresql://s")
    assert _resolve_database_url() == "sqlite:///tmp/env.db"


def test_secrets_used_when_env_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "_database_url_from_secrets", lambda: "postgresql://s")
    assert _resolve_database_url() == "postgresql://s"


def test_defaults_to_local_sqlite(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(db, "_database_url_from_secrets", lambda: "")
    url = _resolve_database_url()
    assert url.startswith("sqlite:///")
    assert url.endswith("moneyball.db")


# ---------------------------------------------------------------------------
# Dialect-aware engine construction
# ---------------------------------------------------------------------------


def test_sqlite_engine_registers_pragma_listener():
    engine = _make_engine("sqlite://")
    assert event.contains(engine, "connect", _set_sqlite_pragma)


def test_sqlite_engine_enforces_foreign_keys():
    engine = _make_engine("sqlite://")
    with engine.connect() as conn:
        value = conn.execute(text("PRAGMA foreign_keys")).scalar()
    assert value == 1


def test_postgres_engine_has_no_sqlite_specifics():
    pytest.importorskip("psycopg2")
    engine = _make_engine(
        "postgresql+psycopg2://user:password@localhost:5432/moneyball"
    )
    assert engine.dialect.name == "postgresql"
    assert not event.contains(engine, "connect", _set_sqlite_pragma)
