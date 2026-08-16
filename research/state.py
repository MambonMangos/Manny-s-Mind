"""Leakage-safe historical state reconstruction.

build_state(season, gw_n) produces exactly what the production pipeline sees
before gameweek gw_n kicks off, using only:
  - results from rounds < gw_n            (cumulative + rolling features)
  - snapshots from round gw_n-1           (price, ownership, transfers)
  - fixtures for rounds >= gw_n           (upcoming difficulty)
  - season-level identity metadata        (position, team, set-piece orders)

The output DataFrame mirrors the schema produced by
``database.crud.get_players_dataframe`` so that ``build_feature_store`` and the
V3 engines consume it exactly as they do in production — read-only.

Documented approximations (no fabrication of missing player data):
  - `starts` is 0 for pre-2022-23 seasons (column does not exist). Marked via
    the season's data_quality tier in the backtest results.
  - chance_of_playing_* = 100%, status='a' (per-GW availability news is not in
    vaastav; FPL-Core-Insights covers 2024-25+ only).
  - team strength comes from teams.csv (season-level snapshot).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from research import config
from research.loader import SeasonData

# Columns emitted, mirroring database.crud.get_players_dataframe
OUTPUT_COLUMNS = [
    "id", "web_name", "first_name", "second_name", "team_id", "team_name",
    "team_short", "position_id", "position", "price", "minutes", "starts",
    "goals_scored", "assists", "total_points", "bonus", "bps", "influence",
    "creativity", "threat", "ict_index", "expected_goals", "expected_assists",
    "expected_goal_involvements", "expected_goals_conceded", "form",
    "selected_by_percent", "transfers_in_event", "transfers_out_event",
    "cost_change_start", "cost_change_event", "value_form", "value_season",
    "status", "news", "chance_of_playing_next_round",
    "chance_of_playing_this_round", "event_points", "clean_sheets",
    "yellow_cards", "red_cards", "saves", "penalties_order",
    "direct_freekicks_order", "corners_and_indirect_freekicks_order",
    "strength_overall_home", "strength_overall_away",
]


def _rolling_form(results: pd.DataFrame) -> pd.Series:
    """FPL-style form: mean points over the last <=5 rounds (0 for blanks).

    Handles double gameweeks by first summing points per (element, round).
    """
    pr = results.groupby(["element", "round"])["total_points"].sum()
    out = {}
    for element, sub in pr.groupby(level=0):
        rounds = sub.index.get_level_values(1).values
        series = sub.droplevel(0)
        lo = max(rounds.max() - config.FORM_WINDOW + 1, rounds.min())
        window = series.reindex(range(lo, rounds.max() + 1)).fillna(0)
        out[element] = window.mean()
    return pd.Series(out, dtype=float)


def build_state(
    sd: SeasonData,
    gw_n: int,
    fixture_map: dict[int, list[dict]] | None = None,
    team_name_map: dict[int, str] | None = None,
) -> tuple[pd.DataFrame, dict[int, list[dict]], dict[int, str]]:
    """Return (players_df, fixture_map, team_name_map) as known before gw_n."""
    gw = sd.gw
    past = gw[gw["round"] < gw_n]
    if past.empty:
        raise ValueError(f"{sd.season} gw{gw_n}: no history before target round")

    raw = sd.players_raw
    has_starts_col = config.STARTS_COL in gw.columns
    has_xg = config.XG_COLS[0] in gw.columns

    # --- cumulative results (rounds < gw_n) ---------------------------------
    agg = {"minutes": "sum", "total_points": "sum", "bps": "sum",
           "bonus": "sum", "saves": "sum", "yellow_cards": "sum",
           "red_cards": "sum", "goals_scored": "sum", "assists": "sum",
           "clean_sheets": "sum", "influence": "sum", "creativity": "sum",
           "threat": "sum", "ict_index": "sum"}
    if has_starts_col:
        agg[config.STARTS_COL] = "sum"
    for xg in config.XG_COLS:
        if has_xg:
            agg[xg] = "sum"
    cum = past.groupby("element").agg(agg)

    # --- rolling form + last event points ------------------------------------
    form = _rolling_form(past)
    last_round = int(past["round"].max())
    last_points = (
        past[past["round"] == last_round]
        .groupby("element")["total_points"].sum()
    )

    # --- snapshot columns (most recent round < gw_n) -------------------------
    snaps = (
        past.sort_values("round")
        .groupby("element")[config.SNAPSHOT_COLS]
        .last()
    )
    prevs = (
        past[past["round"] < last_round]
        .sort_values("round")
        .groupby("element")[["value"]]
        .last()
    )
    firsts = (
        past.sort_values("round")
        .groupby("element")[["value"]]
        .first()
    )

    # --- identity from players_raw -------------------------------------------
    if raw is not None:
        ident = raw.set_index("element")
        element_type = ident["element_type"]
        team = ident["team"]
        pos_orders = {
            c: ident[c]
            for c in ["penalties_order", "direct_freekicks_order",
                      "corners_and_indirect_freekicks_order"]
            if c in ident.columns
        }
        web_name = ident.get("web_name", pd.Series(dtype=str))
        first_name = ident.get("first_name", pd.Series(dtype=str))
        second_name = ident.get("second_name", pd.Series(dtype=str))
    else:
        element_type = pd.Series(dtype=float)
        team = pd.Series(dtype=float)
        pos_orders = {}
        web_name = pd.Series(dtype=str)
        first_name = pd.Series(dtype=str)
        second_name = pd.Series(dtype=str)

    # --- assemble the per-player frame ---------------------------------------
    elements = sorted(set(cum.index) | set(snaps.index) | set(form.index))
    rows = []
    for el in elements:
        price_t = snaps.loc[el, "value"] / 10.0 if el in snaps.index else 0.0
        total_pts = float(cum.loc[el, "total_points"]) if el in cum.index else 0.0
        minutes = float(cum.loc[el, "minutes"]) if el in cum.index else 0.0
        frm = float(form.get(el, 0.0))

        tid = int(team.get(el)) if el in team.index and pd.notna(team.get(el)) else 0
        et = element_type.get(el)
        pos = config.POSITION_MAP.get(int(et)) if pd.notna(et) else None
        if pos is None and "position" in gw.columns:
            gpos = gw[(gw["element"] == el)]["position"].dropna()
            pos = str(gpos.iloc[0]) if len(gpos) else None
        pos = pos or "MID"

        value_now = float(snaps.loc[el, "value"]) if el in snaps.index else 0.0
        value_prev = float(prevs.loc[el, "value"]) if el in prevs.index else value_now
        value_first = float(firsts.loc[el, "value"]) if el in firsts.index else value_now

        selected = float(snaps.loc[el, "selected"]) if el in snaps.index else 0.0

        rows.append({
            "id": el,
            "web_name": str(web_name.get(el)) if el in web_name.index else f"P{el}",
            "first_name": str(first_name.get(el)) if el in first_name.index else "",
            "second_name": str(second_name.get(el)) if el in second_name.index else "",
            "team_id": tid,
            "team_name": sd.team_name.get(tid, ""),
            "team_short": sd.team_short.get(tid, ""),
            "position_id": int(et) if pd.notna(et) else 0,
            "position": pos,
            "price": price_t,
            "minutes": minutes,
            "starts": float(cum.loc[el, config.STARTS_COL]) if has_starts_col and el in cum.index else 0.0,
            "goals_scored": float(cum.loc[el, "goals_scored"]) if el in cum.index else 0.0,
            "assists": float(cum.loc[el, "assists"]) if el in cum.index else 0.0,
            "total_points": total_pts,
            "bonus": float(cum.loc[el, "bonus"]) if el in cum.index else 0.0,
            "bps": float(cum.loc[el, "bps"]) if el in cum.index else 0.0,
            "influence": float(cum.loc[el, "influence"]) if el in cum.index else 0.0,
            "creativity": float(cum.loc[el, "creativity"]) if el in cum.index else 0.0,
            "threat": float(cum.loc[el, "threat"]) if el in cum.index else 0.0,
            "ict_index": float(cum.loc[el, "ict_index"]) if el in cum.index else 0.0,
            "expected_goals": float(cum.loc[el, "expected_goals"]) if has_xg and el in cum.index else 0.0,
            "expected_assists": float(cum.loc[el, "expected_assists"]) if has_xg and el in cum.index else 0.0,
            "expected_goal_involvements": float(cum.loc[el, "expected_goal_involvements"]) if has_xg and el in cum.index else 0.0,
            "expected_goals_conceded": float(cum.loc[el, "expected_goals_conceded"]) if has_xg and el in cum.index else 0.0,
            "form": round(frm, 1),
            "selected_by_percent": selected / sd.total_managers * 100.0 if sd.total_managers > 0 else 0.0,
            "transfers_in_event": float(snaps.loc[el, "transfers_in"]) if el in snaps.index else 0.0,
            "transfers_out_event": float(snaps.loc[el, "transfers_out"]) if el in snaps.index else 0.0,
            "cost_change_start": value_now - value_first,
            "cost_change_event": value_now - value_prev,
            "value_form": frm / price_t if price_t > 0 else 0.0,
            "value_season": total_pts / price_t if price_t > 0 else 0.0,
            "status": "a",
            "news": "",
            "chance_of_playing_next_round": 100.0,
            "chance_of_playing_this_round": 100.0,
            "event_points": float(last_points.get(el, 0.0)),
            "clean_sheets": float(cum.loc[el, "clean_sheets"]) if el in cum.index else 0.0,
            "yellow_cards": float(cum.loc[el, "yellow_cards"]) if el in cum.index else 0.0,
            "red_cards": float(cum.loc[el, "red_cards"]) if el in cum.index else 0.0,
            "saves": float(cum.loc[el, "saves"]) if el in cum.index else 0.0,
            "penalties_order": float(pos_orders["penalties_order"].get(el)) if "penalties_order" in pos_orders and el in pos_orders["penalties_order"].index else np.nan,
            "direct_freekicks_order": float(pos_orders["direct_freekicks_order"].get(el)) if "direct_freekicks_order" in pos_orders and el in pos_orders["direct_freekicks_order"].index else np.nan,
            "corners_and_indirect_freekicks_order": float(pos_orders["corners_and_indirect_freekicks_order"].get(el)) if "corners_and_indirect_freekicks_order" in pos_orders and el in pos_orders["corners_and_indirect_freekicks_order"].index else np.nan,
            "strength_overall_home": float(sd.teams.set_index("id").loc[tid, "strength_overall_home"]) if sd.teams is not None and tid in sd.teams["id"].values else np.nan,
            "strength_overall_away": float(sd.teams.set_index("id").loc[tid, "strength_overall_away"]) if sd.teams is not None and tid in sd.teams["id"].values else np.nan,
        })

    players = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    # --- upcoming fixtures for rounds >= gw_n (leakage-safe) -----------------
    if fixture_map is None or team_name_map is None:
        from engines.fixture_engine import build_fixture_map

        if fixture_map is None:
            fixture_map = {}
            if sd.fixtures is not None:
                fx = sd.fixtures[sd.fixtures["event"] >= gw_n].copy()
                fx["team_h_difficulty"] = fx["team_h_difficulty"].fillna(3)
                fx["team_a_difficulty"] = fx["team_a_difficulty"].fillna(3)
                fx["event"] = fx["event"].fillna(0).astype(int)
                fx["team_h"] = fx["team_h"].fillna(0).astype(int)
                fx["team_a"] = fx["team_a"].fillna(0).astype(int)
                fixture_map = build_fixture_map(
                    fx.to_dict("records")
                )
        if team_name_map is None:
            team_name_map = dict(sd.team_name)

    return players, fixture_map, team_name_map
