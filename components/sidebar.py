"""Sidebar filters shared across pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from utils.constants import POSITIONS, get_active_team_id
from services.data_loader import DataLoader, get_data_age_seconds
from database.database import get_session


def _render_team_selector() -> None:
    """Number input for the viewer's FPL team ID (persists per session).

    A ``?team_id=`` URL param (when present) seeds the widget so the box
    always shows the active team. The write must happen before the widget is
    instantiated — Streamlit forbids mutating a widget key after that.
    """
    from streamlit import session_state

    from utils.constants import query_team_id_from_url

    url_id = query_team_id_from_url()
    if url_id is not None:
        session_state["team_id_input"] = url_id
    elif "team_id_input" not in session_state:
        session_state["team_id_input"] = get_active_team_id()
    st.number_input(
        "Your FPL team ID",
        min_value=1,
        max_value=999_999_999,
        step=1,
        key="team_id_input",
    )


def render_refresh_button() -> None:
    """Render a team selector, indicator and data refresh button in the sidebar."""
    with st.sidebar:
        _render_team_selector()
        st.caption(f"Viewing team {get_active_team_id()}")
        age = get_data_age_seconds()
        if age is not None:
            if age < 60:
                age_str = "just now"
            elif age < 3600:
                age_str = f"{int(age / 60)}m ago"
            else:
                age_str = f"{int(age / 3600)}h ago"
            st.caption(f"Data updated {age_str}")

        if st.button("Refresh Data", use_container_width=True, key="refresh_data"):
            with st.spinner("Fetching latest data from FPL API…"):
                session = get_session()
                try:
                    loader = DataLoader()
                    loader.load(session)
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
