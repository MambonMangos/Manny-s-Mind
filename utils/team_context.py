"""Team Context — the per-session FPL team identity.

This is the single source of truth for "whose data is being shown". A visitor's
FPL Team ID becomes runtime state (Streamlit session state) after it has been
validated on the onboarding page. No module reads a hardcoded ``TEAM_ID`` and no
default to a personal team exists — unvalidated visitors are sent to onboarding.

Session architecture
--------------------
::

    Anonymous Visitor
            |
            v
        Enter Team ID
            |
            v  (validated against the FPL API)
    Session Team Context  (``session_state.team_id``)
            |
            v
      Every personalized service reads ``get_current_team_id()``

The context layer is deliberately thin so a future login system can hand a
persistent user profile to the same provider without changing call sites.
"""

from __future__ import annotations

import logging

import streamlit as st

logger = logging.getLogger(__name__)

_TEAM_ID_KEY = "team_id"
_TEAM_NAME_KEY = "team_name"
_MAX_TEAM_ID = 99_999_999


def set_current_team_id(team_id: int, *, team_name: str = "") -> None:
    """Store the validated team id (and optional display name) for this session."""
    st.session_state[_TEAM_ID_KEY] = int(team_id)
    if team_name:
        st.session_state[_TEAM_NAME_KEY] = team_name


def clear_current_team_id() -> None:
    """Forget the current team. Used by the "Change Team" workflow."""
    st.session_state.pop(_TEAM_ID_KEY, None)
    st.session_state.pop(_TEAM_NAME_KEY, None)


def get_current_team_id() -> int | None:
    """Return the validated team id for this session, or ``None`` when unset.

    Never falls back to a personal/default team — an unvalidated visitor has no
    team, not Manny's team.
    """
    raw = st.session_state.get(_TEAM_ID_KEY)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Corrupt team id in session state; clearing it")
        st.session_state.pop(_TEAM_ID_KEY, None)
        return None


def get_current_team_name() -> str:
    """Return the display name captured at validation time (may be empty)."""
    return str(st.session_state.get(_TEAM_NAME_KEY, ""))


def is_onboarded() -> bool:
    """True once a validated team id exists for this session."""
    return get_current_team_id() is not None


def seed_from_url() -> int | None:
    """Read a ``?team_id=`` URL param as an onboarding pre-fill hint.

    A URL param is never trusted as the active team — it only seeds the
    onboarding input. The team still has to be validated by the visitor.
    """
    try:
        params = st.query_params
    except Exception:  # noqa: BLE001 - non-Streamlit contexts report no params
        return None
    raw = params.get("team_id")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not raw:
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.debug("Ignoring invalid team_id URL param")
        return None
    if 1 <= value <= _MAX_TEAM_ID:
        return value
    return None


def require_team() -> int:
    """Gate for personalized pages.

    Returns the validated team id when the session is onboarded. Otherwise
    renders the onboarding/welcome UI and stops the page script.
    """
    team_id = get_current_team_id()
    if team_id is not None:
        return team_id
    from components.onboarding import render_onboarding

    render_onboarding()
    st.stop()
