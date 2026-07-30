"""Reusable table rendering helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def render_player_table(df: pd.DataFrame, max_rows: int = 200) -> None:
    """Display the main player DataFrame as a styled table."""
    if df.empty:
        st.info("No players match the current filters.")
        return

    display_cols = [
        "web_name",
        "team_short",
        "position",
        "price",
        "minutes",
        "total_points",
        "expected_goal_involvements",
        "xgi_per_90",
        "selected_by_percent",
        "value_score",
    ]

    present = [c for c in display_cols if c in df.columns]
    subset = df[present].head(max_rows).copy()

    rename_map = {
        "web_name": "Player",
        "team_short": "Team",
        "position": "Pos",
        "price": "Price",
        "minutes": "Mins",
        "total_points": "Pts",
        "expected_goal_involvements": "xGI",
        "xgi_per_90": "xGI/90",
        "selected_by_percent": "Own%",
        "value_score": "Value",
    }
    subset = subset.rename(columns=rename_map)

    st.dataframe(
        subset,
        use_container_width=True,
        hide_index=True,
        height=min(420, 35 + len(subset) * 32),
        column_config={
            "Price": st.column_config.NumberColumn(format="£%.1fm"),
            "Own%": st.column_config.NumberColumn(format="%.1f%%"),
            "Value": st.column_config.NumberColumn(format="%.1f"),
            "xGI/90": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def render_team_table(df: pd.DataFrame) -> None:
    """Display a team summary table."""
    if df.empty:
        st.info("No team data available.")
        return

    rename_map = {
        "team_name": "Team",
        "player_count": "Players",
        "avg_price": "Avg Price",
        "total_points": "Total Pts",
        "avg_points": "Avg Pts",
        "total_minutes": "Total Mins",
        "avg_xgi": "Avg xGI",
        "total_xgi": "Total xGI",
    }
    subset = df.rename(columns=rename_map)
    st.dataframe(
        subset,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Avg Price": st.column_config.NumberColumn(format="£%.1fm"),
        },
    )
