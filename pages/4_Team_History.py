"""Team History page – season-by-season performance and GW-by-GW breakdown."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from components.metrics import render_metric_card
from components.theme import inject_theme, page_header, section_label, section_title, divider
from components.sidebar import render_refresh_button
from database.database import get_session
from services.team_service import (
    GameweekPicks,
    ManagerProfile,
    Pick,
    SeasonHistory,
    Transfer,
    fetch_team_data,
)
from utils.helpers import ensure_data_loaded
from utils.constants import get_active_team_id

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Team History", layout="wide")
inject_theme()

ensure_data_loaded()
render_refresh_button()

# ---------------------------------------------------------------------------
# Fetch data (cached)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner="Fetching team history…")
def _load_history(team_id: int) -> dict:
    td = fetch_team_data(team_id)
    return {
        "profile_name": td.profile.name,
        "profile_team_name": td.profile.team_name,
        "profile_region": td.profile.region,
        "profile_years_active": td.profile.years_active,
        "profile_overall_points": td.profile.overall_points,
        "profile_overall_rank": td.profile.overall_rank,
        "history": [
            (h.season_name, h.total_points, h.rank, h.rank_percentage)
            for h in td.history
        ],
        "current": td.current,
    }


raw = _load_history(get_active_team_id())

# Reconstruct
profile = ManagerProfile(
    id=get_active_team_id(),
    name=raw["profile_name"],
    team_name=raw["profile_team_name"],
    region=raw["profile_region"],
    years_active=raw["profile_years_active"],
    overall_points=raw["profile_overall_points"],
    overall_rank=raw["profile_overall_rank"],
)
history = [SeasonHistory(*h) for h in raw["history"]]

# ---------------------------------------------------------------------------
# Profile header
# ---------------------------------------------------------------------------

page_header(
    profile.team_name,
    f"Manager: {profile.name} · {profile.region} · {profile.years_active} years active · "
    "Season-by-season performance & GW breakdown",
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    render_metric_card("Overall Points", f"{profile.overall_points:,}" if profile.overall_points else "–", delay=0)
with col2:
    render_metric_card("Overall Rank", f"{profile.overall_rank:,}" if profile.overall_rank else "–", delay=1)
with col3:
    render_metric_card("All-Time Seasons", str(len(history)), delay=2)
with col4:
    if history:
        best = min(history, key=lambda h: h.rank)
        render_metric_card("Best Season Rank", f"{best.rank:,}", delay=3)

divider()

# ---------------------------------------------------------------------------
# Season history
# ---------------------------------------------------------------------------

if history:
    section_label("Season History")

    hist_df = pd.DataFrame([
        {
            "Season": h.season_name,
            "Points": h.total_points,
            "Rank": h.rank,
            "Top %": h.rank_percentage,
        }
        for h in history
    ])

    # Points bar chart
    fig_pts = px.bar(
        hist_df,
        x="Season",
        y="Points",
        text="Points",
        title="Total Points by Season",
        color="Points",
        color_continuous_scale=["#27272a", "#6366f1"],
    )
    fig_pts.update_traces(texttemplate="%{text:,}", textposition="outside")
    fig_pts.update_layout(
        xaxis_tickangle=-45,
        showlegend=False,
        coloraxis_showscale=False,
        height=400,
    )
    st.plotly_chart(fig_pts, use_container_width=True)

    # Rank trend (reversed y-axis)
    fig_rank = px.line(
        hist_df,
        x="Season",
        y="Rank",
        title="Overall Rank Trend (lower is better)",
        markers=True,
    )
    fig_rank.update_layout(xaxis_tickangle=-45, yaxis_autorange="reversed", height=400)
    st.plotly_chart(fig_rank, use_container_width=True)

    divider()

    section_label("Season Details")
    st.dataframe(hist_df, use_container_width=True, hide_index=True)
else:
    st.info("No season history available.")

# ---------------------------------------------------------------------------
# Gameweek-by-gameweek breakdown (current season)
# ---------------------------------------------------------------------------

current_gw_data = raw.get("current", [])
if current_gw_data:
    divider()
    section_label("Current Season – Gameweek Breakdown")

    gw_df = pd.DataFrame([
        {
            "GW": g["event"],
            "Points": g["points"],
            "Rank": g.get("rank"),
            "Total": g.get("total_points"),
        }
        for g in current_gw_data
    ])

    fig_gw = px.bar(
        gw_df,
        x="GW",
        y="Points",
        text="Points",
        title="Points per Gameweek",
        color="Points",
        color_continuous_scale=["#27272a", "#10b981"],
    )
    fig_gw.update_traces(texttemplate="%{text}", textposition="outside")
    fig_gw.update_layout(showlegend=False, coloraxis_showscale=False, height=400)
    st.plotly_chart(fig_gw, use_container_width=True)

    # Cumulative points line
    if "Total" in gw_df.columns:
        fig_cum = px.line(
            gw_df,
            x="GW",
            y="Total",
            title="Cumulative Points",
            markers=True,
        )
        fig_cum.update_layout(xaxis_title="Gameweek", yaxis_title="Total Points", height=400)
        st.plotly_chart(fig_cum, use_container_width=True)

    divider()
    section_label("Gameweek Details")
    st.dataframe(gw_df, use_container_width=True, hide_index=True)
