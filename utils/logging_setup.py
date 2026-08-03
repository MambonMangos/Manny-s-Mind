"""Centralised logging configuration.

Every application entry point should call ``setup_logging()`` once at
startup, before any request handling begins.

Level and optional file output are controlled via environment variables so
behaviour is identical locally and in production:

    LOG_LEVEL   (default: INFO)
    LOG_FILE    (default: unset → console only)

Principle — zero silent failures: loggers are configured before any
API/database work starts, so failures are visible instead of dropped.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import utils.env  # noqa: F401  (load .env before reading LOG_*)

_DEFAULT_LEVEL = "INFO"
_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def _resolve_level() -> int:
    raw = os.getenv("LOG_LEVEL", _DEFAULT_LEVEL).strip().upper()
    level = getattr(logging, raw, None)
    if not isinstance(level, int):
        logging.getLogger(__name__).warning(
            "Unknown LOG_LEVEL=%r, falling back to %s", raw, _DEFAULT_LEVEL
        )
        return logging.INFO
    return level


def setup_logging() -> None:
    """Configure root logging once. Idempotent — safe to call from every entry point."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    log_file = os.getenv("LOG_FILE", "").strip()
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(path))

    logging.basicConfig(
        level=_resolve_level(),
        format=_FORMAT,
        handlers=handlers,
        force=True,
    )
