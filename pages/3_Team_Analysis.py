"""Team Analysis page – aggregate team statistics and visual comparisons."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from components.tables import render_team_table
from components.theme import (
    inject_theme,
    page_header,
    section_label,
    section_title,
    divider,
    style_px_chart,
)
from components.sidebar import render_refresh_button
from database.database import get_session
from services.player_service import get_scored_players, get_team_summary
from utils.helpers import ensure_data_loaded

st.set_page_config(page_title="Team Analysis", layout="wide")
inject_theme()
page_header("Team Analysis", "Compare all 20 Premier League clubs side by side.")

ensure_data_loaded()
render_refresh_button()
session = get_session()

try:
    team_df = get_team_summary(session)
    player_df = get_scored_players(session)
finally:
    session.close()

if team_df.empty:
    st.warning("No team data found.")
    st.stop()

# --- Summary table ---
section_label("Team Summary")
render_team_table(team_df)

divider()

# --- Charts ---
section_label("Points & Output")

chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    fig1 = px.bar(
        team_df,
        x="team_name",
        y="total_points",
        title="Total Points by Team",
        labels={"team_name": "Team", "total_points": "Total Points"},
    )
    style_px_chart(fig1, xaxis_tickangle=-45)
    st.plotly_chart(fig1, use_container_width=True)

with chart_col2:
    fig2 = px.bar(
        team_df,
        x="team_name",
        y="total_xgi",
        title="Total xGI by Team",
        labels={"team_name": "Team", "total_xgi": "Total xGI"},
    )
    style_px_chart(fig2, xaxis_tickangle=-45)
    st.plotly_chart(fig2, use_container_width=True)

divider()

section_label("Value & Composition")

chart_col3, chart_col4 = st.columns(2)

with chart_col3:
    fig3 = px.bar(
        team_df,
        x="team_name",
        y="avg_price",
        title="Average Price by Team",
        labels={"team_name": "Team", "avg_price": "Avg Price (£m)"},
    )
    style_px_chart(fig3, xaxis_tickangle=-45)
    st.plotly_chart(fig3, use_container_width=True)

with chart_col4:
    fig4 = px.bar(
        team_df,
        x="team_name",
        y="player_count",
        title="Squad Size",
        labels={"team_name": "Team", "player_count": "Players"},
    )
    style_px_chart(fig4, xaxis_tickangle=-45)
    st.plotly_chart(fig4, use_container_width=True)

divider()

# --- Player breakdown by team ---
if not player_df.empty:
    section_label("Value Score by Team")
    team_value = (
        player_df.groupby("team_name")["value_score"]
        .mean()
        .reset_index()
        .sort_values("value_score", ascending=False)
    )
    fig5 = px.bar(
        team_value,
        x="team_name",
        y="value_score",
        title="Average Value Score by Team",
        labels={"team_name": "Team", "value_score": "Avg Value Score"},
    )
    style_px_chart(fig5, xaxis_tickangle=-45)
    st.plotly_chart(fig5, use_container_width=True)
