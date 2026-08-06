"""Write-action access control.

Mutating actions (result ingestion, validation cycles, persist-to-ledger
comparisons, manual data refresh) are admin-only. Reads stay public so the
app can be shared via ``?team_id=``.

Security model
--------------
- If no ``ADMIN_TOKEN`` is configured, write actions are unrestricted
  (single-owner default — this preserves current behaviour).
- If ``ADMIN_TOKEN`` is configured (Streamlit secrets or environment
  variable), a session must be unlocked by entering the token in the
  sidebar before any write action is shown. Unlock state lives in
  ``session_state.admin_authorized``.

Token comparison uses :func:`hmac.compare_digest` to avoid timing attacks.
"""

from __future__ import annotations

import hmac
import logging
import os

logger = logging.getLogger(__name__)


def _configured_token() -> str | None:
    """Return the configured admin token (secrets → env) or None if unset."""
    try:
        from streamlit import secrets

        token = secrets.get("ADMIN_TOKEN")
        if token:
            return token
    except Exception as exc:  # noqa: BLE001 - non-Streamlit contexts fall back to env
        logger.debug("Streamlit secrets unavailable; using environment: %s", exc)
    return os.getenv("ADMIN_TOKEN") or None


def is_admin_enforced() -> bool:
    """True when an admin token is configured (write actions are gated)."""
    return _configured_token() is not None


def is_admin_token_valid(candidate: str | None) -> bool:
    """Constant-time check of a candidate against the configured token.

    When no token is configured (single-owner mode) every candidate —
    including None — is accepted.
    """
    token = _configured_token()
    if not token:
        return True
    if not candidate:
        return False
    return hmac.compare_digest(candidate, token)


def admin_authorized() -> bool:
    """Whether the current Streamlit session has been unlocked for writes."""
    try:
        from streamlit import session_state
    except Exception:  # noqa: BLE001 - non-Streamlit contexts are not a session
        return False
    return bool(session_state.get("admin_authorized"))


def require_admin() -> bool:
    """Whether the current session may perform write actions.

    True when no token is configured; otherwise requires an unlocked
    admin session (see :func:`admin_authorized`).
    """
    if not is_admin_enforced():
        return True
    return admin_authorized()
