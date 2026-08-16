"""Sidebar filters shared across pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from database.database import get_session
from services.data_loader import DataLoader, get_data_age_seconds
from utils.constants import POSITIONS
from utils.team_context import get_current_team_id


def render_team_switcher() -> None:
    """Show the active team with a persistent "Change Team" option.

    Change Team forgets the session's validated Team ID and returns the
    visitor to the onboarding page — no manual browser-state clearing needed.
    """
    from utils.team_context import clear_current_team_id

    team_id = get_current_team_id()
    if team_id is None:
        return
    st.markdown("**Current Team**")
    st.caption(str(team_id))
    if st.button("Change Team", use_container_width=True, key="change_team"):
        clear_current_team_id()
        try:
            st.switch_page("pages/1_My_Team.py")
        except Exception:  # noqa: BLE001 - fall back to in-place rerun
            st.rerun()


def render_admin_section() -> None:
    """Admin unlock UI. Only rendered when an ``ADMIN_TOKEN`` is configured."""
    from utils.access import admin_authorized, is_admin_enforced, is_admin_token_valid

    if not is_admin_enforced():
        return
    st.markdown("---")
    st.markdown("**Admin**")
    if admin_authorized():
        st.caption("Admin unlocked for this session.")
        if st.button("Lock Admin", use_container_width=True, key="admin_lock"):
            st.session_state["admin_authorized"] = False
            st.rerun()
    else:
        st.caption("Write actions are locked.")
        st.text_input("Admin password", type="password", key="admin_password")
        if st.button("Unlock Admin", use_container_width=True, key="admin_unlock"):
            if is_admin_token_valid(st.session_state.get("admin_password")):
                st.session_state["admin_authorized"] = True
                st.rerun()
            else:
                st.error("Incorrect admin password")


def render_refresh_button() -> None:
    """Render a team selector, admin section, indicator and refresh button."""
    from services.audit import log_audit
    from utils.access import require_admin

    with st.sidebar:
        render_team_switcher()
        team_id = get_current_team_id()
        if team_id is not None:
            st.caption(f"Viewing team {team_id}")
        age = get_data_age_seconds()
        if age is not None:
            if age < 60:
                age_str = "just now"
            elif age < 3600:
                age_str = f"{int(age / 60)}m ago"
            else:
                age_str = f"{int(age / 3600)}h ago"
            st.caption(f"Data updated {age_str}")

        render_admin_section()

        if not require_admin():
            st.caption("Data refresh locked — enter the admin password above.")
            return
        if st.button("Refresh Data", use_container_width=True, key="refresh_data"):
            with st.spinner("Fetching latest data from FPL API…"):
                session = get_session()
                try:
                    loader = DataLoader()
                    loader.load(session)
                    log_audit(session, "data_refresh", detail={"source": "sidebar"})
                    session.commit()
                finally:
                    session.close()
            st.rerun()


def render_sidebar_filters(df: pd.DataFrame) -> dict:
    """Render sidebar widgets and return the selected filter values."""
    with st.sidebar:
        st.markdown(
            '<div class="section-label" style="margin-bottom:1rem;">Filters</div>',
            unsafe_allow_html=True,
        )

        # --- Group 1: Player attributes ---
        st.markdown(
            '<div style="font-size:0.75rem; color:#a1a1aa; font-weight:600; '
            'margin-bottom:0.5rem;">Player</div>',
            unsafe_allow_html=True,
        )

        teams = st.multiselect(
            "Club",
            options=sorted(df["team_name"].unique().tolist()),
            default=[],
            placeholder="All clubs",
            label_visibility="collapsed",
        )

        positions = st.multiselect(
            "Position",
            options=POSITIONS,
            default=[],
            placeholder="All positions",
            label_visibility="collapsed",
        )

        # --- Group 2: Price & minutes ---
        st.markdown(
            '<div style="font-size:0.75rem; color:#a1a1aa; font-weight:600; '
            'margin-top:1.25rem; margin-bottom:0.5rem;">Performance</div>',
            unsafe_allow_html=True,
        )

        max_price = st.slider(
            "Max Price",
            min_value=3.5,
            max_value=float(df["price"].max()),
            value=float(df["price"].max()),
            step=0.1,
            format="£%.1fm",
            label_visibility="collapsed",
        )

        min_minutes = st.slider(
            "Min Minutes",
            min_value=0,
            max_value=int(df["minutes"].max()),
            value=0,
            step=90,
            label_visibility="collapsed",
        )

        # --- Group 3: Ownership ---
        st.markdown(
            '<div style="font-size:0.75rem; color:#a1a1aa; font-weight:600; '
            'margin-top:1.25rem; margin-bottom:0.5rem;">Ownership</div>',
            unsafe_allow_html=True,
        )

        min_ownership = st.slider(
            "Min Ownership",
            min_value=0.0,
            max_value=float(df["selected_by_percent"].max()),
            value=0.0,
            step=0.1,
            format="%.1f%%",
            label_visibility="collapsed",
        )

        max_ownership = st.slider(
            "Max Ownership",
            min_value=0.0,
            max_value=float(df["selected_by_percent"].max()),
            value=float(df["selected_by_percent"].max()),
            step=0.1,
            format="%.1f%%",
            label_visibility="collapsed",
        )

    return {
        "teams": teams,
        "positions": positions,
        "max_price": max_price,
        "min_minutes": min_minutes,
        "min_ownership": min_ownership,
        "max_ownership": max_ownership,
    }
