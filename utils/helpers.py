"""Shared utility helpers."""

from __future__ import annotations

from database.database import get_session, init_db
from services.data_loader import DataLoader, is_data_stale


def ensure_data_loaded() -> None:
    """Ensure the database is initialised and populated with fresh data.

    Fetches from the FPL API if the database is empty or stale (>1 hour old).
    """
    init_db()

    if is_data_stale():
        session = get_session()
        try:
            loader = DataLoader()
            loader.load(session)
        finally:
            session.close()
