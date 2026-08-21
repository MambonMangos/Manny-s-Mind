"""Database engine and session management."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

import utils.env  # noqa: F401  (load .env before reading DATABASE_URL)
from database.models import Base

logger = logging.getLogger(__name__)

_DB_DIR = Path(__file__).resolve().parent.parent / "data"
_DB_PATH = _DB_DIR / "moneyball.db"


def _database_url_from_secrets() -> str:
    """Read DATABASE_URL from Streamlit secrets ('' when unavailable).

    Streamlit Cloud cannot set environment variables on an already-deployed
    app, but ``secrets.toml`` is editable live via 'Manage app' — so hosted
    deployments configure the database there.
    """
    try:
        from streamlit import secrets

        value = secrets.get("DATABASE_URL")
        return str(value) if value else ""
    except Exception:  # noqa: BLE001 - not running inside Streamlit
        logger.debug("Streamlit secrets unavailable for DATABASE_URL")
        return ""


def _resolve_database_url() -> str:
    """Resolve the database URL.

    Resolution order (matches docs/configuration.md):

        Environment variables (.env / container env) -> Streamlit secrets ->
        default SQLite file
    """
    return (
        os.getenv("DATABASE_URL")
        or _database_url_from_secrets()
        or f"sqlite:///{_DB_PATH}"
    )


def _set_sqlite_pragma(dbapi_conn, connection_record):
    """Enable WAL mode and foreign keys for SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _make_engine(url: str) -> Engine:
    """Create an engine configured for the URL's dialect."""
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url,
        echo=False,
        # check_same_thread is SQLite-specific (Streamlit reruns span
        # threads); other dialects reject unknown connect arguments.
        connect_args={"check_same_thread": False} if is_sqlite else {},
    )
    if is_sqlite:
        event.listen(engine, "connect", _set_sqlite_pragma)
    return engine


# Ensure the default SQLite parent directory exists up front so that any
# connection to the default URL works even before init_db() is called
# (e.g. during tests). Harmless for non-file DATABASE_URL values.
_DB_DIR.mkdir(parents=True, exist_ok=True)

_DATABASE_URL = _resolve_database_url()
_IS_SQLITE = _DATABASE_URL.startswith("sqlite")

engine = _make_engine(_DATABASE_URL)

_session_factory = sessionmaker(bind=engine)

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


def get_session() -> Session:
    """Return a new SQLAlchemy session."""
    return _session_factory()


def init_db() -> None:
    """Create all tables if they do not exist.

    Only runs when DB_ALLOW_CREATE_ALL is enabled (default: true for local
    development). With Alembic-managed schemas, run ``alembic upgrade head``
    instead and set DB_ALLOW_CREATE_ALL=false.
    """
    if _IS_SQLITE:
        _DB_DIR.mkdir(parents=True, exist_ok=True)
    if not _DB_ALLOW_CREATE_ALL:
        logger.warning(
            "DB_ALLOW_CREATE_ALL=false — skipping create_all(); "
            "ensure the schema is applied via `alembic upgrade head`"
        )
        return
    Base.metadata.create_all(bind=engine)
