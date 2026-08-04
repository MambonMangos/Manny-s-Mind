"""Empty states and alerts.

Centralises the ad-hoc ``st.info`` / ``st.warning`` / ``st.error`` calls
pages use today into one consistent set of renderers, plus a visual empty
state for "no data" situations.
"""

from __future__ import annotations

import streamlit as st

from components.ui.base import esc

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------


def empty_state_html(icon: str = "", title: str = "No data available", message: str = "") -> str:
    """Return the HTML for a centred empty state block."""
    return (
        f'<div class="empty-state fade-in">'
        f'<div class="empty-state-icon">{icon}</div>'
        f'<div class="empty-state-title">{esc(title)}</div>'
        f'<div class="empty-state-message">{esc(message)}</div>'
        f"</div>"
    )


def render_empty_state(
    icon: str = "",
    title: str = "No data available",
    message: str = "",
    action_label: str = "",
    action_key: str = "",
) -> None:
    """Render a consistent empty state with an optional action button."""
    st.markdown(empty_state_html(icon, title, message), unsafe_allow_html=True)
    if action_label and action_key:
        st.button(action_label, key=action_key, use_container_width=False)


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def render_alert(message: str, kind: str = "info") -> None:
    """Render a standard Streamlit alert with an escaped message.

    ``kind`` is one of: info, warning, error, success.
    """
    message = esc(message)
    fn = {
        "info": st.info,
        "warning": st.warning,
        "error": st.error,
        "success": st.success,
    }.get(kind, st.info)
    fn(message)


def render_info(message: str) -> None:
    render_alert(message, "info")


def render_warning(message: str) -> None:
    render_alert(message, "warning")


def render_error(message: str) -> None:
    render_alert(message, "error")


def render_success(message: str) -> None:
    render_alert(message, "success")
