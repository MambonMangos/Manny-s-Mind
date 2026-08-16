"""Preseason prior — Phase 5 of the historical-data program.

The 2026-27 ``players_raw.csv`` is the FPL preseason snapshot: it carries each
player's previous-season (2025-26) performance totals (minutes, starts,
points, xG/xA) alongside their current price, position, team, set-piece
orders and availability. There is no ``gws/`` directory for 2026-27 yet, so
this module is purely a *prior construction* deliverable:

  - ``build_preseason_prior()``  — normalized per-player preseason prior table
  - ``build_preseason_state()``  — engine-schema frame for a GW1 projection
  - ``validate_preseason_prior()`` — structural + plausibility checks

Per the directive, preseason signals are NOT assumed to translate into
goals; they are validated structurally (schema + sanity) and offered as the
GW1 baseline only.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from research import config
from research.loader import load_players_raw

logger = logging.getLogger(__name__)

PRESEASON_SEASON = "2026-27"

PRIOR_COLUMNS = [
    "element", "web_name", "position", "team_id", "team_name", "price",
    "status", "chance_of_playing_next_round", "selected_by_percent",
    "penalties_order", "direct_freekicks_order",
    "corners_and_indirect_freekicks_order",
    "last_season_minutes", "last_season_starts", "last_season_games",
    "last_season_points", "last_season_xg", "last_season_xa",
    "last_season_xg_per_90", "last_season_xa_per_90",
    "last_season_xgi_per_90", "last_season_points_per_90",
    "last_season_starts_rate", "last_season_minutes_per_start",
]

_STATE_COLUMNS = [
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


def _f(df: pd.DataFrame, col: str, default=0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _rate(num: pd.Series, den: pd.Series) -> pd.Series:
    out = num / den.replace(0, np.nan)
    return out.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)


def load_preseason_raw() -> pd.DataFrame:
    """Load the 2026-27 players_raw snapshot (preseason; no gws/)."""
    return load_players_raw(PRESEASON_SEASON)


def build_preseason_prior() -> pd.DataFrame:
    """Normalized per-player preseason prior table (see PRIOR_COLUMNS)."""
    raw = load_preseason_raw()
    team_map = {}
    teams = None
    try:
        from research.loader import load_teams

        teams = load_teams(PRESEASON_SEASON)
    except AssertionError:
        teams = None
    if teams is not None and "id" in teams.columns and "name" in teams.columns:
        team_map = dict(zip(teams["id"].astype(int), teams["name"].astype(str)))

    minutes = _f(raw, "minutes")
    starts = _f(raw, "starts")
    games = pd.Series(38.0, index=raw.index)  # full 2025-26 season at snapshot

    prior = pd.DataFrame(index=raw.index)
    prior["element"] = raw["element"].astype(int)
    prior["web_name"] = raw.get("web_name", pd.Series("", index=raw.index)).astype(str)
    prior["position"] = raw["element_type"].map(config.POSITION_MAP)
    prior["team_id"] = _f(raw, "team").astype(int)
    prior["team_name"] = prior["team_id"].map(team_map).fillna("")
    prior["price"] = _f(raw, "now_cost") / 10.0
    prior["status"] = raw.get("status", pd.Series("a", index=raw.index)).fillna("a").astype(str)
    prior["chance_of_playing_next_round"] = _f(raw, "chance_of_playing_next_round", 100.0)
    prior["selected_by_percent"] = _f(raw, "selected_by_percent")
    for c in ["penalties_order", "direct_freekicks_order", "corners_and_indirect_freekicks_order"]:
        prior[c] = _f(raw, c, np.nan)

    prior["last_season_minutes"] = minutes
    prior["last_season_starts"] = starts
    prior["last_season_games"] = games
    prior["last_season_points"] = _f(raw, "total_points")
    prior["last_season_xg"] = _f(raw, "expected_goals")
    prior["last_season_xa"] = _f(raw, "expected_assists")
    prior["last_season_xg_per_90"] = _rate(prior["last_season_xg"], minutes / 90)
    prior["last_season_xa_per_90"] = _rate(prior["last_season_xa"], minutes / 90)
    prior["last_season_xgi_per_90"] = prior["last_season_xg_per_90"] + prior["last_season_xa_per_90"]
    prior["last_season_points_per_90"] = _rate(prior["last_season_points"], minutes / 90)
    prior["last_season_starts_rate"] = _rate(starts, games)
    prior["last_season_minutes_per_start"] = _rate(minutes, starts).clip(upper=90.0)

    return prior[PRIOR_COLUMNS]


def build_preseason_state() -> pd.DataFrame:
    """Engine-schema players frame for a GW1 preseason projection.

    Mirrors ``research.state.OUTPUT_COLUMNS`` so the engines can run on the
    preseason snapshot before any 2026-27 gameweek has finished.
    """
    raw = load_preseason_raw()
    prior = build_preseason_prior().set_index("element")
    raw_by_el = raw.set_index("element")

    def _raw_val(el: int, col: str, default=0.0) -> float:
        if col not in raw_by_el.columns:
            return default
        return float(pd.to_numeric(raw_by_el.loc[el, col], errors="coerce"))

    def _raw_str(el: int, col: str) -> str:
        if col not in raw_by_el.columns:
            return ""
        return str(raw_by_el.loc[el, col])

    rows = []
    for el, r in prior.iterrows():
        form = _raw_val(el, "form", 0.0)
        price_val = float(r["price"])
        points_val = float(r["last_season_points"])
        value_form = form / price_val if price_val > 0 else 0.0
        value_season = points_val / price_val if price_val > 0 else 0.0

        rows.append({
            "id": el,
            "web_name": r["web_name"],
            "first_name": _raw_str(el, "first_name"),
            "second_name": _raw_str(el, "second_name"),
            "team_id": int(r["team_id"]),
            "team_name": r["team_name"],
            "team_short": "",
            "position_id": int(_raw_val(el, "element_type", 0)),
            "position": r["position"],
            "price": price_val,
            "minutes": float(r["last_season_minutes"]),
            "starts": float(r["last_season_starts"]),
            "goals_scored": _raw_val(el, "goals_scored"),
            "assists": _raw_val(el, "assists"),
            "total_points": points_val,
            "bonus": _raw_val(el, "bonus"),
            "bps": _raw_val(el, "bps"),
            "influence": _raw_val(el, "influence"),
            "creativity": _raw_val(el, "creativity"),
            "threat": _raw_val(el, "threat"),
            "ict_index": _raw_val(el, "ict_index"),
            "expected_goals": float(r["last_season_xg"]),
            "expected_assists": float(r["last_season_xa"]),
            "expected_goal_involvements": float(r["last_season_xg"]) + float(r["last_season_xa"]),
            "expected_goals_conceded": _raw_val(el, "expected_goals_conceded"),
            "form": round(form, 1),
            "selected_by_percent": float(r["selected_by_percent"]),
            "transfers_in_event": 0.0,
            "transfers_out_event": 0.0,
            "cost_change_start": 0.0,
            "cost_change_event": 0.0,
            "value_form": round(value_form, 2),
            "value_season": round(value_season, 2),
            "status": r["status"],
            "news": "",
            "chance_of_playing_next_round": float(r["chance_of_playing_next_round"]),
            "chance_of_playing_this_round": 100.0,
            "event_points": 0.0,
            "clean_sheets": _raw_val(el, "clean_sheets"),
            "yellow_cards": _raw_val(el, "yellow_cards"),
            "red_cards": _raw_val(el, "red_cards"),
            "saves": _raw_val(el, "saves"),
            "penalties_order": float(r["penalties_order"]) if pd.notna(r["penalties_order"]) else np.nan,
            "direct_freekicks_order": float(r["direct_freekicks_order"]) if pd.notna(r["direct_freekicks_order"]) else np.nan,
            "corners_and_indirect_freekicks_order": float(r["corners_and_indirect_freekicks_order"]) if pd.notna(r["corners_and_indirect_freekicks_order"]) else np.nan,
            "strength_overall_home": np.nan,
            "strength_overall_away": np.nan,
        })

    return pd.DataFrame(rows, columns=_STATE_COLUMNS)


def run_preseason_baseline(
    points_version: str = "expected_points_v1_hist",
    minutes_version: str = "expected_minutes_v1_hist",
) -> pd.DataFrame:
    """GW1 preseason baseline: run the hist-config engines on the snapshot.

    No ``hist_*`` columns are injected (no in-season history exists yet); the
    empirical finishing/creative/bonus/clean-sheet calibration applies directly
    to the previous-season cumulative rates.
    """
    from features import build_feature_store

    players_df = build_preseason_state()
    store = build_feature_store(players_df=players_df, fixture_map={}, team_name_map={}, gameweek_id=1)

    from engines.expected_minutes_engine import project_expected_minutes
    from engines.expected_points_engine import project_expected_points

    xpts = project_expected_points(store, 1, config_version=points_version)
    mins = project_expected_minutes(store, 1, config_version=minutes_version)

    out = pd.DataFrame([vars(p) for p in xpts])
    mins_df = pd.DataFrame([vars(p) for p in mins])
    out = out.merge(
        mins_df[["player_id", "expected_minutes", "start_probability",
                 "minutes_if_starting", "substitution_risk"]],
        on="player_id", how="left",
    )
    out["predicted_points"] = out["xpts_per_90"] * out["expected_minutes"] / 90.0
    out["season"] = PRESEASON_SEASON
    out["round"] = 1
    return out


def validate_preseason_prior(prior: pd.DataFrame) -> dict:
    """Structural + plausibility checks over the preseason prior table."""
    checks = {}
    checks["n_players"] = len(prior)
    checks["columns_present"] = all(c in prior.columns for c in PRIOR_COLUMNS)
    checks["positions_valid"] = set(prior["position"].unique()) <= {"GKP", "DEF", "MID", "FWD"}
    checks["price_bounds"] = bool(prior["price"].between(3.5, 16.0).all())
    checks["statuses_valid"] = set(prior["status"].unique()) <= {"a", "i", "d", "s", "u", "n"}
    meaningful = prior[prior["last_season_minutes"] >= 90]
    checks["rate_bounds"] = bool(
        meaningful["last_season_xg_per_90"].between(0, 2).all()
        and meaningful["last_season_points_per_90"].between(0, 12).all()
        and meaningful["last_season_starts_rate"].between(0, 1).all()
    )
    checks["set_piece_orders_bounded"] = bool(
        prior["penalties_order"].fillna(99).between(0, 99).all()
        and prior["direct_freekicks_order"].fillna(99).between(0, 99).all()
    )
    checks["sane_elite_signal"] = bool(
        prior.loc[prior["last_season_minutes"] >= 2000, "last_season_xg_per_90"].max() > 0.3
    )
    return checks
