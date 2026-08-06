#!/usr/bin/env python3
"""WAL-consistent SQLite backup with retention and optional offsite copy.

The app runs SQLite in WAL mode, so a plain file copy is not guaranteed to
be consistent. This script uses the SQLite online backup API instead.

Usage::

    python scripts/backup_db.py                          # default DB + data/backups
    python scripts/backup_db.py --keep 30
    python scripts/backup_db.py --offsite-dir ~/backups/moneyball

Schedule locally (cron)::

    0 3 * * * cd /path/to/repo && .venv/bin/python scripts/backup_db.py
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("data/moneyball.db")
DEFAULT_BACKUP_DIR = Path("data/backups")


def backup_database(
    db_path: Path,
    backup_dir: Path,
    keep: int = 14,
    offsite_dir: Path | None = None,
) -> Path:
    """Create a consistent timestamped backup; prune old ones; optional offsite copy.

    Returns the path of the newly created backup file.
    """
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    dest = backup_dir / f"moneyball-{stamp}.db"

    src = sqlite3.connect(str(db_path))
    try:
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    if offsite_dir:
        offsite_dir = Path(offsite_dir)
        offsite_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dest, offsite_dir / dest.name)

    if keep > 0:
        backups = sorted(backup_dir.glob("moneyball-*.db"))
        for stale in backups[:-keep]:
            stale.unlink()

    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help="SQLite database file (default: data/moneyball.db)",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help="Backup directory (default: data/backups)",
    )
    parser.add_argument(
        "--keep",
        type=int,
        default=14,
        help="Number of backups to retain (default: 14)",
    )
    parser.add_argument(
        "--offsite-dir",
        type=Path,
        default=None,
        help="Optional second copy destination",
    )
    args = parser.parse_args()

    dest = backup_database(
        args.db,
        args.backup_dir,
        keep=args.keep,
        offsite_dir=args.offsite_dir,
    )
    print(f"Backup written: {dest}")


if __name__ == "__main__":
    main()
