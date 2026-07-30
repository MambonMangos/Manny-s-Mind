"""Player service – high-level queries and transformations."""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session

from database.crud import get_players_dataframe, get_teams_dataframe
from services.scoring import add_derived_columns, compute_value_score


def get_scored_players(session: Session) -> pd.DataFrame:
    """Return a DataFrame of all players with value scores attached.

    This is the main entry-point used by the Streamlit pages.
    """
    df = get_players_dataframe(session)
    if df.empty:
        return df

    scored = compute_value_score(df)
    df["value_score"] = scored.composite.round(2)
    df["minutes_score"] = scored.minutes_norm.round(2)
    df["xgi_score"] = scored.xgi_norm.round(2)
    df["xgi_per_90"] = scored.xgi_per_90
    df["points_per_million"] = scored.points_per_million

    import numpy as np
    df["saves_per_90"] = np.where(
        df["minutes"] > 0,
        (df["saves"] / df["minutes"]) * 90.0,
        0.0,
    ).round(2)

    return df


def get_team_summary(session: Session) -> pd.DataFrame:
    """Return a summary of each team with player count and average stats."""
    player_df = get_players_dataframe(session)
    if player_df.empty:
        return pd.DataFrame()

    grouped = (
        player_df.groupby("team_name")
        .agg(
            player_count=("id", "count"),
            avg_price=("price", "mean"),
            total_points=("total_points", "sum"),
            avg_points=("total_points", "mean"),
            total_minutes=("minutes", "sum"),
            avg_xgi=("expected_goal_involvements", "mean"),
            total_xgi=("expected_goal_involvements", "sum"),
        )
        .reset_index()
    )
    grouped["avg_price"] = grouped["avg_price"].round(1)
    grouped["avg_points"] = grouped["avg_points"].round(1)
    grouped["avg_xgi"] = grouped["avg_xgi"].round(2)
    grouped["total_xgi"] = grouped["total_xgi"].round(2)
    return grouped.sort_values("total_points", ascending=False)


def filter_players(
    df: pd.DataFrame,
    *,
    teams: list[str] | None = None,
    positions: list[str] | None = None,
    max_price: float | None = None,
    min_minutes: int | None = None,
    min_ownership: float | None = None,
    max_ownership: float | None = None,
) -> pd.DataFrame:
    """Apply sidebar filters to a player DataFrame."""
    filtered = df.copy()

    if teams:
        filtered = filtered[filtered["team_name"].isin(teams)]

    if positions:
        filtered = filtered[filtered["position"].isin(positions)]

    if max_price is not None:
        filtered = filtered[filtered["price"] <= max_price]

    if min_minutes is not None:
        filtered = filtered[filtered["minutes"] >= min_minutes]

    if min_ownership is not None:
        filtered = filtered[filtered["selected_by_percent"] >= min_ownership]

    if max_ownership is not None:
        filtered = filtered[filtered["selected_by_percent"] <= max_ownership]

    return filtered
