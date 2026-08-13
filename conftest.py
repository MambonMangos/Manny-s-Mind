"""Pytest root configuration.

Ensures the repository root is on ``sys.path`` so tests can import top-level
packages (``utils``, ``features``, ``engines``, ``services``) and the
``tests`` package when pytest is invoked as a plain binary (as CI does), not
just via ``python -m pytest``.
"""

from __future__ import annotations
