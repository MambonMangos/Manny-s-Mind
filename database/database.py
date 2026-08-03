"""Database engine and session management."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import utils.env  # noqa: F401  (load .env before reading DATABASE_URL)
from database.models import Base

_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DB_DIR / "moneyball.db"
_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH}")

engine = create_engine(
    _DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

_session_factory = sessionmaker(bind=engine)


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    return _session_factory()


def init_db() -> None:
    """Create all tables if they do not exist."""
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and foreign keys for SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
