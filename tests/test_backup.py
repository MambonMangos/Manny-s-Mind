"""Tests for the WAL-consistent database backup script."""

from __future__ import annotations

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.backup_db import backup_database


def _seed_db(path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO t (name) VALUES ('hello')")
        conn.commit()
    finally:
        conn.close()


def test_backup_creates_consistent_copy(tmp_path):
    db = tmp_path / "moneyball.db"
    _seed_db(db)

    dest = backup_database(db, tmp_path / "backups", keep=2)
    assert dest.exists()

    conn = sqlite3.connect(str(dest))
    try:
        assert conn.execute("SELECT name FROM t").fetchone() == ("hello",)
    finally:
        conn.close()


def test_backup_prunes_old_backups(tmp_path):
    db = tmp_path / "moneyball.db"
    _seed_db(db)

    backup_dir = tmp_path / "backups"
    first = backup_database(db, backup_dir, keep=2)
    second = backup_database(db, backup_dir, keep=2)
    third = backup_database(db, backup_dir, keep=2)

    remaining = sorted(backup_dir.glob("moneyball-*.db"))
    assert first not in remaining
    assert second in remaining
    assert third in remaining
    assert len(remaining) == 2


def test_backup_offsite_copy(tmp_path):
    db = tmp_path / "moneyball.db"
    _seed_db(db)

    offsite = tmp_path / "offsite"
    dest = backup_database(db, tmp_path / "backups", offsite_dir=offsite)
    assert (offsite / dest.name).exists()


def test_backup_missing_db_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        backup_database(tmp_path / "nope.db", tmp_path / "backups")
