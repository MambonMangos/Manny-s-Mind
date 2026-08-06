"""Player Comparison page – compare selected players side-by-side."""

from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.sidebar import render_refresh_button
from components.theme import (
    divider,
    inject_theme,
    page_header,
    section_label,
)
from database.crud import get_teams_dataframe
from database.database import get_session
from engines.fixture_engine import (
    build_fixture_heatmap_data,
    build_fixture_summary,
    compute_player_fixture_scores,
)
from services.fixture_service import (
    build_fixture_comparison,
    fetch_fixtures,
)
from services.player_service import get_scored_players
from utils.helpers import ensure_data_loaded

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Player Comparison", layout="wide")
inject_theme()
page_header("Player Comparison", "Head-to-head analysis with radar charts, fixture difficulty, and efficiency metrics.")

ensure_data_loaded()
render_refresh_button()

# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

session = get_session()
try:
    df = get_scored_players(session)
finally:
    session.close()

if df.empty:
    st.warning("No player data available.")
    st.stop()

# ---------------------------------------------------------------------------
# Player selector
# ---------------------------------------------------------------------------

player_options = {
    f"{row['web_name']} ({row['team_short']}) – {row['position']} £{row['price']:.1f}m": row["id"]
    for _, row in df.iterrows()
}

selected_labels = st.multiselect(
    "Select players to compare",
    options=list(player_options.keys()),
    max_selections=5,
    placeholder="Search for players…",
    label_visibility="collapsed",
)

if len(selected_labels) < 2:
    st.markdown(
        """
        <div style="text-align:center; padding:4rem 0; color:#71717a;">
            <div style="font-size:3rem; margin-bottom:1rem; opacity:0.4;">📊</div>
            <div style="font-size:1rem; font-weight:500;">Select at least 2 players to compare</div>
            <div style="font-size:0.85rem; margin-top:0.5rem;">Use the search box above to find players</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.stop()

selected_ids = [player_options[label] for label in selected_labels]
comp_df = df[df["id"].isin(selected_ids)].copy()
comp_df = comp_df.sort_values("value_score", ascending=False)

# ---------------------------------------------------------------------------
# Player cards
# ---------------------------------------------------------------------------

section_label("Selected Players")

card_cols = st.columns(min(len(comp_df), 5))
_colors = ["#6366f1", "#06b6d4", "#34d399", "#fbbf24", "#f87171"]

for i, (_, row) in enumerate(comp_df.iterrows()):
    with card_cols[i]:
        color = _colors[i % len(_colors)]
        web_name = escape(str(row["web_name"]))
        team_short = escape(str(row["team_short"]))
        position = escape(str(row["position"]))
        st.markdown(
            f"""
            <div class="card" style="border-left: 3px solid {color}; text-align:center;">
                <div style="font-size:1.1rem; font-weight:700; color:#fafafa;">{web_name}</div>
                <div style="font-size:0.8rem; color:#71717a; margin-bottom:0.5rem;">{team_short} · {position}</div>
                <div style="font-family:'JetBrains Mono',monospace; font-size:1.4rem; font-weight:700; color:{color};">
                    £{row['price']:.1f}m
                </div>
                <div style="font-size:0.75rem; color:#71717a; margin-top:0.25rem;">
                    {row['total_points']} pts · {row['value_score']:.1f} value
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

divider()

# ---------------------------------------------------------------------------
# Stats table
# ---------------------------------------------------------------------------

section_label("Stats Comparison")

stat_cols = [
    "web_name", "team_short", "position", "price",
    "total_points", "minutes", "goals_scored", "assists",
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "xgi_per_90", "points_per_million",
    "selected_by_percent", "value_score",
    "saves", "saves_per_90",
    "bonus", "bps",
]

present = [c for c in stat_cols if c in comp_df.columns]
table_df = comp_df[present].copy()

rename_map = {
    "web_name": "Player",
    "team_short": "Team",
    "position": "Pos",
    "price": "Price",
    "total_points": "Pts",
    "minutes": "Mins",
    "goals_scored": "Goals",
    "assists": "Assists",
    "expected_goals": "xG",
    "expected_assists": "xA",
    "expected_goal_involvements": "xGI",
    "xgi_per_90": "xGI/90",
    "points_per_million": "Pts/£m",
    "selected_by_percent": "Own%",
    "value_score": "Value",
    "saves": "Saves",
    "saves_per_90": "Saves/90",
    "bonus": "Bonus",
    "bps": "BPS",
}
table_df = table_df.rename(columns=rename_map)
st.table(table_df)

divider()

# ---------------------------------------------------------------------------
# Radar chart
# ---------------------------------------------------------------------------

section_label("Radar Comparison")

radar_metrics = {
    "Value Score": "value_score",
    "xGI/90": "xgi_per_90",
    "Points": "total_points",
    "Minutes": "minutes",
    "Pts/£m": "points_per_million",
    "Ownership": "selected_by_percent",
}

radar_labels = list(radar_metrics.keys())
raw_cols = list(radar_metrics.values())

# Compute column min/max from ALL players for meaningful normalisation
col_ranges: dict[str, tuple[float, float]] = {}
for col in raw_cols:
    col_ranges[col] = (df[col].min(), df[col].max())


def _norm_val(value: float, col: str) -> float:
    mn, mx = col_ranges[col]
    if mx == mn:
        return 50.0
    return ((value - mn) / (mx - mn)) * 100.0


fig_radar = go.Figure()

_radar_colors = ["#6366f1", "#06b6d4", "#34d399", "#fbbf24", "#f87171"]

for i, (_, row) in enumerate(comp_df.iterrows()):
    values = [_norm_val(row[col], col) for col in raw_cols]
    values.append(values[0])  # close the radar
    fig_radar.add_trace(go.Scatterpolar(
        r=values,
        theta=radar_labels + [radar_labels[0]],
        fill="toself",
        name=f"{row['web_name']} ({row['team_short']})",
        line={"color": _radar_colors[i % len(_radar_colors)], "width": 2},
        fillcolor=_radar_colors[i % len(_radar_colors)],
        opacity=0.5,
    ))

fig_radar.update_layout(
    polar={
        "radialaxis": {"visible": True, "range": [0, 100], "gridcolor": "#27272a", "tickfont": {"color": "#71717a"}},
        "angularaxis": {"gridcolor": "#27272a", "tickfont": {"color": "#a1a1aa"}},
        "bgcolor": "#18181b",
    },
    showlegend=True,
    height=500,
    margin={"l": 60, "r": 60, "t": 30, "b": 60},
)
st.plotly_chart(fig_radar, use_container_width=True)

divider()

# ---------------------------------------------------------------------------
# Bar chart comparison
# ---------------------------------------------------------------------------

section_label("Head-to-Head Bar Charts")

bar_metric = st.selectbox(
    "Compare by",
    options=[
        "value_score", "total_points", "xgi_per_90",
        "price", "points_per_million", "selected_by_percent",
        "expected_goal_involvements", "minutes", "saves_per_90",
        "bonus", "bps",
    ],
    format_func=lambda x: {
        "value_score": "Value Score",
        "total_points": "Total Points",
        "xgi_per_90": "xGI per 90",
        "price": "Price",
        "points_per_million": "Pts per £m",
        "selected_by_percent": "Ownership %",
        "expected_goal_involvements": "Expected GI",
        "minutes": "Minutes Played",
        "saves_per_90": "Saves per 90",
        "bonus": "Bonus Points",
        "bps": "BPS Score",
    }.get(x, x),
)

fig_bar = go.Figure()
for i, (_, row) in enumerate(comp_df.iterrows()):
    fig_bar.add_trace(go.Bar(
        x=[row["web_name"]],
        y=[row[bar_metric]],
        text=[round(row[bar_metric], 1) if row[bar_metric] != int(row[bar_metric]) else int(row[bar_metric])],
        textposition="outside",
        marker_color=_radar_colors[i % len(_radar_colors)],
        name=f"{row['web_name']} ({row['team_short']})",
        showlegend=True,
    ))
fig_bar.update_layout(
    barmode="group",
    yaxis_title=bar_metric.replace("_", " ").title(),
    xaxis_title="Player",
    height=400,
    showlegend=True,
)
st.plotly_chart(fig_bar, use_container_width=True)

divider()

# ---------------------------------------------------------------------------
# Efficiency scatter
# ---------------------------------------------------------------------------

section_label("Price vs Value Score")

fig_scatter = go.Figure()

for i, (_, row) in enumerate(comp_df.iterrows()):
    fig_scatter.add_trace(go.Scatter(
        x=[row["price"]],
        y=[row["value_score"]],
        mode="markers+text",
        text=[row["web_name"]],
        textposition="top center",
        marker={"size": 14, "color": _radar_colors[i % len(_radar_colors)]},
        name=f"{row['web_name']} ({row['team_short']})",
    ))

fig_scatter.update_layout(
    xaxis_title="Price (£m)",
    yaxis_title="Value Score",
    height=450,
    showlegend=True,
)
st.plotly_chart(fig_scatter, use_container_width=True)

divider()

# ---------------------------------------------------------------------------
# Fixture Difficulty Comparison
# ---------------------------------------------------------------------------

section_label("Fixture Difficulty – Upcoming GWs")

gw_range = st.slider(
    "Gameweek range",
    min_value=5,
    max_value=20,
    value=(1, 10),
    step=1,
    format="GW %d",
    label_visibility="collapsed",
)

@st.cache_data(ttl=600, show_spinner="Fetching fixtures…")
def _load_fixtures() -> list:
    return fetch_fixtures()


fixtures = _load_fixtures()

session_teams = get_session()
try:
    teams_df = get_teams_dataframe(session_teams)
finally:
    session_teams.close()

team_name_map = dict(zip(teams_df["id"], teams_df["short_name"]))

player_team_ids = comp_df["team_id"].unique().tolist()
gameweeks = list(range(gw_range[0], gw_range[1] + 1))

fixture_df = build_fixture_comparison(fixtures, player_team_ids, team_name_map, gameweeks)

if fixture_df.empty:
    st.info("No fixture data available for this range.")
else:
    fixture_df["team_name"] = fixture_df["team_id"].map(team_name_map).fillna("TBD")

    # --- Average Fixture Score bar chart ---
    player_fixture_scores = compute_player_fixture_scores(comp_df, fixture_df)

    pf_df = pd.DataFrame(player_fixture_scores).sort_values("score", ascending=False)

    fig_avg = go.Figure()
    for i, (_, row) in enumerate(pf_df.iterrows()):
        fig_avg.add_trace(go.Bar(
            x=[f"{row['player']}\n({row['team']})"],
            y=[row["score"]],
            text=[str(row["score"])],
            textposition="outside",
            marker_color=_radar_colors[i % len(_radar_colors)],
            name=row["player"],
            showlegend=False,
        ))
    fig_avg.update_layout(
        title=f"Average Fixture Score (GW{gw_range[0]}–{gw_range[1]})",
        yaxis_title="Fixture Score",
        yaxis={"range": [0, 110]},
        height=350,
    )
    st.plotly_chart(fig_avg, use_container_width=True)

    # --- Difficulty heatmap per gameweek ---
    st.markdown("**Difficulty by Gameweek**")

    pivot_diff, pivot_opp, text_labels = build_fixture_heatmap_data(fixture_df)

    fig_heat = go.Figure(data=go.Heatmap(
        z=pivot_diff.values,
        x=pivot_diff.columns.tolist(),
        y=[f"GW{gw}" for gw in pivot_diff.index],
        colorscale=[
            [0.0, "#10b981"],
            [0.25, "#34d399"],
            [0.5, "#f59e0b"],
            [0.75, "#f97316"],
            [1.0, "#ef4444"],
        ],
        text=text_labels.values,
        texttemplate="%{text}",
        textfont={"size": 11, "color": "#fafafa"},
        showscale=True,
        colorbar={"title": "Difficulty", "tickfont": {"color": "#a1a1aa"}},
        zmin=1,
        zmax=5,
    ))
    fig_heat.update_layout(
        height=max(300, len(pivot_diff) * 40 + 100),
        xaxis_title="Team",
        yaxis={"autorange": "reversed"},
    )
    st.plotly_chart(fig_heat, use_container_width=True)

    # --- Per-player fixture summary table ---
    divider()
    section_label("Fixture Summary")

    summary_rows = build_fixture_summary(comp_df, fixture_df)

    summary_df = pd.DataFrame(summary_rows).sort_values("Avg Score", ascending=False)
    st.dataframe(summary_df, use_container_width=True, hide_index=True)
