"""Centralised environment bootstrap.

Loads the project ``.env`` file into the process environment on import.

Every module that reads configuration from the environment should import
this module (directly or transitively) before reading environment variables,
so ``.env``-based configuration works identically in local development and
in containerised deployments.

Single source of truth for where the ``.env`` file lives.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


def load_env() -> None:
    """Load ``.env`` into the environment if present. Safe to call repeatedly."""
    load_dotenv(_ENV_FILE)


load_env()
