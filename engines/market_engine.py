"""Market Engine – single source of truth for transfer volumes, ownership trends, price movements.

Consolidates:
  - get_top_transfers_in/out (from 2_Player_Rankings.py)
  - get_price_risers/fallers (from 2_Player_Rankings.py)
  - classify_demand (from squad_evaluator.py + transfer_engine.py)
"""

from __future__ import annotations

import pandas as pd


def get_top_transfers_in(player_df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Get the top N players by transfers in this gameweek.

    This is the SINGLE implementation — never do nlargest on transfers_in_event inline.
    """
    top = player_df.nlargest(n, "transfers_in_event")
    if top.empty:
        return top
    return top.sort_values("transfers_in_event", ascending=True)


def get_top_transfers_out(player_df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Get the top N players by transfers out this gameweek."""
    top = player_df.nlargest(n, "transfers_out_event")
    if top.empty:
        return top
    return top.sort_values("transfers_out_event", ascending=True)


def get_price_risers(player_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Get the top N players by price rise this season."""
    risers = player_df[player_df["cost_change_start"] > 0].nlargest(n, "cost_change_start")
    if risers.empty:
        return risers
    return risers.sort_values("cost_change_start", ascending=True)


def get_price_fallers(player_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Get the top N players by price drop this season."""
    fallers = player_df[player_df["cost_change_start"] < 0].nsmallest(n, "cost_change_start")
    if fallers.empty:
        return fallers
    return fallers.sort_values("cost_change_start", ascending=False)


def classify_demand(transfers_in: int, transfers_out: int, selected: float) -> list[str]:
    """Classify market demand signals for a player.

    This is the SINGLE implementation — never do demand classification inline.
    Returns a list of opportunity/risk flags.
    """
    flags: list[str] = []
    if transfers_in > transfers_out * 1.5 and transfers_in > 3000:
        flags.append(f"High demand ({transfers_in:,} transfers in)")
    if selected < 5.0:
        flags.append(f"Low ownership ({selected:.1f}%)")
    return flags


def get_market_momentum(player_df: pd.DataFrame) -> dict:
    """Compute aggregate market momentum statistics."""
    if player_df.empty:
        return {}

    total_in = player_df["transfers_in_event"].sum()
    total_out = player_df["transfers_out_event"].sum()
    net = total_in - total_out

    risers = len(player_df[player_df["cost_change_start"] > 0])
    fallers = len(player_df[player_df["cost_change_start"] < 0])
    unchanged = len(player_df[player_df["cost_change_start"] == 0])

    return {
        "total_transfers_in": int(total_in),
        "total_transfers_out": int(total_out),
        "net_transfers": int(net),
        "price_risers": risers,
        "price_fallers": fallers,
        "price_unchanged": unchanged,
    }
