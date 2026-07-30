"""My Team page – personalised squad dashboard for the user's FPL team.

The FPL API picks endpoint is the single source of truth for the user's
squad.  Transfers and substitutions made on the FPL website are reflected
automatically on the next page load.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.formation import get_or_build_formation, get_positions
from components.metrics import render_metric_card
from components.theme import inject_theme, page_header, section_label, section_title, divider
from components.sidebar import render_refresh_button
from database.database import get_session
from services.player_service import get_scored_players
from services.team_service import (
    GameweekPicks,
    ManagerProfile,
    Pick,
    SeasonHistory,
    Transfer,
    build_transfer_log,
    fetch_team_data,
    recommend_captain,
    resolve_player_names,
)
from utils.helpers import ensure_data_loaded
from utils.constants import TEAM_ID

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="My Team", layout="wide")
inject_theme()

ensure_data_loaded()
render_refresh_button()

# ---------------------------------------------------------------------------
# Fetch data – no cache so picks refresh on every page load
# ---------------------------------------------------------------------------

raw = fetch_team_data(TEAM_ID)

# Reconstruct dataclasses from live API data

profile = ManagerProfile(
    id=TEAM_ID,
    name=raw.profile.name,
    team_name=raw.profile.team_name,
    region=raw.profile.region,
    years_active=raw.profile.years_active,
    overall_points=raw.profile.overall_points,
    overall_rank=raw.profile.overall_rank,
    event_points=raw.profile.event_points,
    event_rank=raw.profile.event_rank,
)
transfers = raw.transfers

picks_map: dict[int, GameweekPicks] = raw.picks

# ---------------------------------------------------------------------------
# Manager profile section
# ---------------------------------------------------------------------------

page_header(
    profile.team_name,
    f"Manager: {profile.name} · {profile.region} · {profile.years_active} years active · "
    "Live squad, captain picks & transfer activity",
)

col1, col2, col3, col4 = st.columns(4)
with col1:
    render_metric_card("Overall Points", f"{profile.overall_points:,}" if profile.overall_points else "–", delay=0)
with col2:
    render_metric_card("Overall Rank", f"{profile.overall_rank:,}" if profile.overall_rank else "–", delay=1)
with col3:
    render_metric_card("GW Points", str(profile.event_points) if profile.event_points else "–", delay=2)
with col4:
    render_metric_card("GW Rank", f"{profile.event_rank:,}" if profile.event_rank else "–", delay=3)

divider()

# ---------------------------------------------------------------------------
# Current squad – from FPL API picks (single source of truth)
# ---------------------------------------------------------------------------

session = get_session()
try:
    player_df = get_scored_players(session)
finally:
    session.close()

available_gws = sorted(picks_map.keys()) if picks_map else []

if available_gws:
    section_label("Current Squad")

    gw_choice = st.selectbox(
        "Gameweek",
        options=available_gws,
        index=len(available_gws) - 1,
        format_func=lambda x: f"GW {x}",
        label_visibility="collapsed",
    )

    gp = picks_map[gw_choice]
    squad_df = resolve_player_names(gp.picks, player_df)

    if not squad_df.empty:
        starters = squad_df[squad_df["squad_position"] <= 11]
        defs = len(starters[starters["position"] == "DEF"])
        mids = len(starters[starters["position"] == "MID"])
        fwds = len(starters[starters["position"] == "FWD"])
        formation = f"{defs}-{mids}-{fwds}"

        st.markdown(f"**{formation}**")

        fig = go.Figure()
        PITCH_GREEN = "#3d8b37"
        rows = get_or_build_formation(defs, mids, fwds)
        player_positions = get_positions(rows, starters)

        # Pitch outline
        fig.add_shape(type="rect", x0=0, y0=0, x1=1, y1=1,
                      fillcolor=PITCH_GREEN, line=dict(color="white", width=2.5), layer="below")

        # Centre circle + spot
        cr = 0.146
        fig.add_shape(type="circle", x0=0.5 - cr, y0=0.5 - cr, x1=0.5 + cr, y1=0.5 + cr,
                      line=dict(color="white", width=1.5), fillcolor="rgba(0,0,0,0)", layer="below")
        fig.add_shape(type="circle", x0=0.49, y0=0.493, x1=0.51, y1=0.507,
                      fillcolor="white", line=dict(color="white", width=0), layer="below")

        # Player markers
        for p in player_positions:
            is_c = p["is_captain"]
            is_vc = p["is_vice_captain"]
            badge = ""
            bw = 2.5
            if is_c:
                badge = " (C)"
                bw = 3.5
            elif is_vc:
                badge = " (VC)"
                bw = 3

            fig.add_trace(go.Scatter(
                x=[p["x"]], y=[p["y"]], mode="markers",
                marker=dict(size=38, color="#e53935", line=dict(color="white", width=bw)),
                hovertext=f"{p['web_name']} ({p['team_short']})",
                hoverinfo="text", showlegend=False,
            ))
            fig.add_annotation(
                x=p["x"], y=p["y"],
                text=f"<b>{p['web_name']}{badge}</b><br><span style='font-size:9px'>{p['team_short']}</span>",
                showarrow=False, yshift=-28,
                font=dict(size=11, color="white", family="Inter, sans-serif"), align="center",
            )

        fig.update_layout(
            height=580,
            margin=dict(l=20, r=20, t=10, b=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.04, 1.04]),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.04, 1.08], scaleanchor="x"),
            plot_bgcolor=PITCH_GREEN, paper_bgcolor=PITCH_GREEN,
            hoverlabel=dict(bgcolor="#1a1a2e", bordercolor="#3f3f46", font=dict(size=12, color="white")),
        )

        _pitch_col, _empty_col = st.columns([1, 1])
        with _pitch_col:
            st.plotly_chart(fig, use_container_width=True)

        # Bench
        bench = squad_df[squad_df["squad_position"] > 11].copy()
        if not bench.empty:
            section_label("Bench")
            bench["role"] = ""
            bench.loc[bench["is_captain"], "role"] = " (C)"
            bench.loc[bench["is_vice_captain"], "role"] = " (VC)"
            bench["Player"] = bench["web_name"] + bench["role"]
            bench_display = bench.rename(columns={
                "team_short": "Team", "position": "Pos", "price": "Price",
                "total_points": "Pts", "expected_goal_involvements": "xGI",
            })
            show_cols = [c for c in ["Player", "Team", "Pos", "Price", "Pts", "xGI"] if c in bench_display.columns]
            st.dataframe(bench_display[show_cols], use_container_width=True, hide_index=True,
                         height=40 + 35 * len(bench))

        divider()
        section_label("Captain Recommendation")
        cap_df = recommend_captain(squad_df)
        if not cap_df.empty:
            st.dataframe(cap_df, use_container_width=True, hide_index=True)
            top_cap = cap_df.iloc[0]
            st.info(
                f"**Recommended Captain:** {top_cap['web_name']} "
                f"({top_cap['team_short']}) – Value Score {top_cap['value_score']:.1f}"
            )
        else:
            st.info("Not enough data to recommend a captain.")

else:
    # No picks available – season hasn't started or no squad set yet
    section_label("Current Squad")
    st.info(
        "No squad data available yet. "
        "Your picks will appear here automatically once the first gameweek "
        "deadline has passed and you have registered your team on the FPL website."
    )
    st.caption(
        "Transfers and substitutions made on the FPL website will be "
        "reflected here automatically on the next page load."
    )

# ---------------------------------------------------------------------------
# Transfers
# ---------------------------------------------------------------------------

divider()
section_label("Transfers")

if transfers:
    transfer_df = build_transfer_log(transfers, player_df)
    st.dataframe(transfer_df, use_container_width=True, hide_index=True)
else:
    st.info("No transfers recorded yet this season.")
