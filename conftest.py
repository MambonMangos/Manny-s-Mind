"""Pytest root configuration.

Ensures the repository root is on ``sys.path`` so tests can import top-level
packages (``utils``, ``features``, ``engines``, ``services``) and the
``tests`` package when pytest is invoked as a plain binary (as CI does), not
just via ``python -m pytest``.

Isolates the test-session database: ``database.database`` creates its module
engine at import time from ``DATABASE_URL``. Redirecting it here (before any
test module is imported) prevents test ``reset_db()`` helpers from dropping
tables in the real development database on every test run.
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = "sqlite://"
