"""Player Rankings page – sortable, filterable player table with charts."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from components.metrics import render_top_metrics
from components.sidebar import render_refresh_button, render_sidebar_filters
from components.tables import render_player_table
from components.theme import (
    COLOR_MARKET_BUY,
    COLOR_MARKET_FALLER,
    COLOR_MARKET_RISER,
    COLOR_MARKET_SELL,
    divider,
    inject_theme,
    page_header,
    section_label,
)
from database.database import get_session
from engines.market_engine import (
    get_price_fallers,
    get_price_risers,
    get_top_transfers_in,
    get_top_transfers_out,
)
from services.player_service import filter_players, get_scored_players
from utils.helpers import ensure_data_loaded

st.set_page_config(page_title="Player Rankings", layout="wide")
inject_theme()
page_header("Player Rankings", "Find the best value picks across all 20 Premier League clubs.")

ensure_data_loaded()
render_refresh_button()
session = get_session()

try:
    df = get_scored_players(session)
finally:
    session.close()

if df.empty:
    st.warning("No player data found. Place bootstrap-static.json in data/ and reload.")
    st.stop()

# --- Sidebar filters ---
filters = render_sidebar_filters(df)
filtered = filter_players(
    df,
    teams=filters["teams"] or None,
    positions=filters["positions"] or None,
    max_price=filters["max_price"],
    min_minutes=filters["min_minutes"],
    min_ownership=filters["min_ownership"],
    max_ownership=filters["max_ownership"],
)

# --- Dashboard metrics ---
section_label("Overview")
render_top_metrics(filtered)

divider()

# --- Market Activity ---
section_label("Market Activity")

ma_left, ma_right = st.columns(2)

with ma_left:
    st.markdown("**Most Transferred In**")
    tf_in_count = st.selectbox(
        "Show top", [5, 10, 20], index=0, key="tf_in_n",
        label_visibility="collapsed",
    )
    top_in = get_top_transfers_in(df, tf_in_count)
    if not top_in.empty:
        fig_in = go.Figure(go.Bar(
            y=top_in["web_name"] + " (" + top_in["team_short"] + ")",
            x=top_in["transfers_in_event"],
            orientation="h",
            marker_color=COLOR_MARKET_BUY,
            text=top_in["transfers_in_event"].apply(lambda x: f"{x:,}"),
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Transfers In: %{x:,}<br>"
                "<extra></extra>"
            ),
        ))
        fig_in.update_layout(
            height=max(250, tf_in_count * 36 + 60),
            margin={"l": 10, "r": 60, "t": 10, "b": 10},
            xaxis={"title": "Transfers In", "gridcolor": "#27272a"},
            yaxis={"gridcolor": "#27272a"},
            plot_bgcolor="#18181b", paper_bgcolor="#18181b",
        )
        st.plotly_chart(fig_in, use_container_width=True)

        in_table = top_in[["web_name", "team_short", "position", "price",
                           "transfers_in_event", "selected_by_percent"]].copy()
        in_table.columns = ["Player", "Team", "Pos", "Price", "Transfers In", "Own%"]
        in_table = in_table.sort_values("Transfers In", ascending=False)
        st.dataframe(in_table, use_container_width=True, hide_index=True,
                     height=40 + 35 * len(in_table))

with ma_right:
    st.markdown("**Most Transferred Out**")
    tf_out_count = st.selectbox(
        "Show top", [5, 10, 20], index=0, key="tf_out_n",
        label_visibility="collapsed",
    )
    top_out = get_top_transfers_out(df, tf_out_count)
    if not top_out.empty:
        fig_out = go.Figure(go.Bar(
            y=top_out["web_name"] + " (" + top_out["team_short"] + ")",
            x=top_out["transfers_out_event"],
            orientation="h",
            marker_color=COLOR_MARKET_SELL,
            text=top_out["transfers_out_event"].apply(lambda x: f"{x:,}"),
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Transfers Out: %{x:,}<br>"
                "<extra></extra>"
            ),
        ))
        fig_out.update_layout(
            height=max(250, tf_out_count * 36 + 60),
            margin={"l": 10, "r": 60, "t": 10, "b": 10},
            xaxis={"title": "Transfers Out", "gridcolor": "#27272a"},
            yaxis={"gridcolor": "#27272a"},
            plot_bgcolor="#18181b", paper_bgcolor="#18181b",
        )
        st.plotly_chart(fig_out, use_container_width=True)

        out_table = top_out[["web_name", "team_short", "position", "price",
                             "transfers_out_event", "selected_by_percent"]].copy()
        out_table.columns = ["Player", "Team", "Pos", "Price", "Transfers Out", "Own%"]
        out_table = out_table.sort_values("Transfers Out", ascending=False)
        st.dataframe(out_table, use_container_width=True, hide_index=True,
                     height=40 + 35 * len(out_table))

# --- Market Movers ---
divider()
section_label("Market Movers")

mm_left, mm_right = st.columns(2)

with mm_left:
    st.markdown("**Biggest Price Rises**")
    risers = get_price_risers(df, 10)
    if not risers.empty:
        fig_rise = go.Figure(go.Bar(
            y=risers["web_name"] + " (" + risers["team_short"] + ")",
            x=risers["cost_change_start"] / 10,
            orientation="h",
            marker_color=COLOR_MARKET_RISER,
            text=(risers["cost_change_start"] / 10).apply(lambda x: f"+£{x:.1f}m"),
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Price Rise: +£%{x:.1f}m<br>"
                "<extra></extra>"
            ),
        ))
        fig_rise.update_layout(
            height=max(250, len(risers) * 36 + 60),
            margin={"l": 10, "r": 60, "t": 10, "b": 10},
            xaxis={"title": "Price Change (£m)", "gridcolor": "#27272a"},
            yaxis={"gridcolor": "#27272a"},
            plot_bgcolor="#18181b", paper_bgcolor="#18181b",
        )
        st.plotly_chart(fig_rise, use_container_width=True)
    else:
        st.info("No price rises yet.")

with mm_right:
    st.markdown("**Biggest Price Drops**")
    fallers = get_price_fallers(df, 10)
    if not fallers.empty:
        fig_fall = go.Figure(go.Bar(
            y=fallers["web_name"] + " (" + fallers["team_short"] + ")",
            x=fallers["cost_change_start"] / 10,
            orientation="h",
            marker_color=COLOR_MARKET_FALLER,
            text=(fallers["cost_change_start"] / 10).apply(lambda x: f"£{x:.1f}m"),
            textposition="outside",
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Price Drop: £%{x:.1f}m<br>"
                "<extra></extra>"
            ),
        ))
        fig_fall.update_layout(
            height=max(250, len(fallers) * 36 + 60),
            margin={"l": 10, "r": 60, "t": 10, "b": 10},
            xaxis={"title": "Price Change (£m)", "gridcolor": "#27272a"},
            yaxis={"gridcolor": "#27272a"},
            plot_bgcolor="#18181b", paper_bgcolor="#18181b",
        )
        st.plotly_chart(fig_fall, use_container_width=True)
    else:
        st.info("No price drops yet.")

divider()

# --- Sortable table ---
section_label("All Players")

sort_col = st.selectbox(
    "Sort by",
    options=[
        "value_score",
        "total_points",
        "price",
        "xgi_per_90",
        "selected_by_percent",
        "minutes",
    ],
    index=0,
    label_visibility="collapsed",
)
ascending = st.checkbox("Ascending", value=False)
display_df = filtered.sort_values(sort_col, ascending=ascending).reset_index(drop=True)
render_player_table(display_df)
