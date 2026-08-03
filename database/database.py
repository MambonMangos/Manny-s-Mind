"""Database engine and session management."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import utils.env  # noqa: F401  (load .env before reading DATABASE_URL)
from database.models import Base

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DB_DIR / "moneyball.db"
_DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DB_PATH}")

# Ensure the default SQLite parent directory exists up front so that any
# connection to the default URL works even before init_db() is called
# (e.g. during tests). Harmless for non-file DATABASE_URL values.
_DB_DIR.mkdir(parents=True, exist_ok=True)

# create_all() is a bootstrap convenience for local development only. In
# environments that manage the schema with Alembic (the production path), set
# DB_ALLOW_CREATE_ALL=false so cold starts cannot silently drift from the
# migration baseline.
_DB_ALLOW_CREATE_ALL = os.getenv("DB_ALLOW_CREATE_ALL", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

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
    """Create all tables if they do not exist.

    Only runs when DB_ALLOW_CREATE_ALL is enabled (default: true for local
    development). With Alembic-managed schemas, run ``alembic upgrade head``
    instead and set DB_ALLOW_CREATE_ALL=false.
    """
    _DB_DIR.mkdir(parents=True, exist_ok=True)
    if not _DB_ALLOW_CREATE_ALL:
        logger.warning(
            "DB_ALLOW_CREATE_ALL=false — skipping create_all(); "
            "ensure the schema is applied via `alembic upgrade head`"
        )
        return
    Base.metadata.create_all(bind=engine)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and foreign keys for SQLite."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
