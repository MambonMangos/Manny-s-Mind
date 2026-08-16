"""Historical feature store — Phase 2 of the historical-data program.

Builds leakage-safe ``hist_*`` features for a gameweek-N state using ONLY:
  - per-GW results from rounds < N           (player minutes/sub/start rates)
  - team aggregates from rounds < N          (attack/defence strength)
  - the previous completed season            (prev-season priors via identity)

These columns are injected into the ``players_df`` before
``build_feature_store`` so they flow through to the engines exactly like any
other player column (verified: ``services.scoring.add_derived_columns``
preserves unknown columns). The production pipeline never injects them, so
production behaviour is unchanged; the experimental engines only engage the
historical sections when the config requests them AND the columns exist.

Substitution semantics (documented limitation of the vaastav data, which has
no per-GW ``status`` column):
  - sub appearance      : starts == 0 AND minutes > 0  (came off the bench)
  - unused / not-squad  : starts == 0 AND minutes == 0 (indistinguishable)
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from research import config
from research.identity import previous_season_prior

logger = logging.getLogger(__name__)


def _per_90(series: pd.Series, minutes: pd.Series) -> pd.Series:
    """Aggregate → per-90 rate (0 when minutes are 0)."""
    return (series / (minutes / 90)).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)


def _safe_rate(num: pd.Series, den: pd.Series) -> pd.Series:
    out = pd.to_numeric(num, errors="coerce") / pd.to_numeric(den, errors="coerce").replace(0, np.nan)
    return out.fillna(0.0).replace([float("inf"), float("-inf")], 0.0).clip(0.0, 1.0)


def _player_features(past: pd.DataFrame) -> pd.DataFrame:
    """Per-player rates from rounds < gw_n. Indexed by element."""
    if past.empty:
        return pd.DataFrame()

    starts = config.STARTS_COL if config.STARTS_COL in past.columns else None
    has_xg = config.XG_COLS[0] in past.columns

    appearances = past.groupby("element").size()
    minutes = past.groupby("element")["minutes"].sum()
    points = past.groupby("element")["total_points"].sum()
    bps = past.groupby("element")["bps"].sum()
    xgi = (
        past.groupby("element")["expected_goal_involvements"].sum()
        if has_xg else pd.Series(0.0, index=appearances.index)
    )
    xg = (
        past.groupby("element")["expected_goals"].sum()
        if has_xg else pd.Series(0.0, index=appearances.index)
    )
    xa = (
        past.groupby("element")["expected_assists"].sum()
        if has_xg else pd.Series(0.0, index=appearances.index)
    )

    feats = pd.DataFrame(index=appearances.index)
    feats["hist_appearances"] = appearances
    feats["hist_minutes"] = minutes
    feats["hist_points"] = points
    feats["hist_xgi"] = xgi
    feats["hist_xg"] = xg
    feats["hist_xa"] = xa

    if starts is not None:
        n_starts = past.groupby("element")["starts"].sum()
        subs = past[(past["starts"] == 0) & (past["minutes"] > 0)].groupby("element").size()
        unused = past[(past["starts"] == 0) & (past["minutes"] == 0)].groupby("element").size()
        feats["hist_starts"] = n_starts
        feats["hist_starts_rate"] = _safe_rate(n_starts, appearances)
        feats["hist_sub_rate"] = _safe_rate(subs, appearances - n_starts)
        feats["hist_unused_rate"] = _safe_rate(unused, appearances - n_starts)
        feats["hist_minutes_per_start"] = np.minimum(
            (minutes / n_starts.replace(0, np.nan)).fillna(0.0), 90.0,
        )
    else:
        for c in ["hist_starts", "hist_starts_rate", "hist_sub_rate",
                  "hist_unused_rate", "hist_minutes_per_start"]:
            feats[c] = 0.0

    feats["hist_minutes_per_game"] = (minutes / appearances).fillna(0.0)
    feats["hist_xgi_per_90"] = _per_90(xgi, minutes)
    feats["hist_xg_per_90"] = _per_90(xg, minutes)
    feats["hist_xa_per_90"] = _per_90(xa, minutes)
    feats["hist_points_per_90"] = _per_90(points, minutes)
    feats["hist_bps_per_90"] = _per_90(bps, minutes)

    # FPL-style form: mean total_points over the last <= FORM_WINDOW rounds.
    last_5 = []
    for element, sub in past.groupby("element"):
        r = sub["round"].max()
        lo = max(r - config.FORM_WINDOW + 1, past["round"].min())
        window = sub[sub["round"] >= lo]["total_points"]
        last_5.append((element, window.sum() / config.FORM_WINDOW))
    form = pd.Series(dict(last_5))
    feats["hist_avg_pts_last_5"] = form.reindex(feats.index).fillna(0.0)

    return feats


def _team_features(past: pd.DataFrame, sd) -> pd.DataFrame:
    """Per-team attack/defence strength from rounds < gw_n. Indexed by team id."""
    if past.empty or sd.players_raw is None:
        return pd.DataFrame()

    elem_team = sd.players_raw.set_index("element")["team"]
    past = past.assign(_team=past["element"].map(elem_team))
    active = past[past["_team"].notna()]

    team_games = active[active["minutes"] > 0].groupby("_team")["round"].nunique()
    goals = active.groupby("_team")["goals_scored"].sum()
    xg = (
        active.groupby("_team")["expected_goals"].sum()
        if config.XG_COLS[0] in past.columns
        else pd.Series(0.0, index=team_games.index)
    )
    xgc = (
        active.groupby("_team")["expected_goals_conceded"].sum()
        if config.XG_COLS[0] in past.columns
        else pd.Series(0.0, index=team_games.index)
    )
    cs = active[active["clean_sheets"] > 0].groupby("_team")["round"].nunique()

    feats = pd.DataFrame(index=team_games.index)
    feats["hist_team_games"] = team_games
    feats["hist_team_goals_per_game"] = (goals / team_games).fillna(0.0)
    feats["hist_team_xg_per_game"] = (xg / team_games).fillna(0.0)
    feats["hist_team_xgc_per_game"] = (xgc / team_games).fillna(0.0)
    feats["hist_team_cs_rate"] = (cs / team_games).fillna(0.0)

    lg_xg = feats["hist_team_xg_per_game"].mean()
    lg_xgc = feats["hist_team_xgc_per_game"].mean()
    feats["hist_team_attack_adj"] = (feats["hist_team_xg_per_game"] / lg_xg).fillna(1.0) if lg_xg > 0 else 1.0
    feats["hist_team_defense_adj"] = (feats["hist_team_xgc_per_game"] / lg_xgc).fillna(1.0) if lg_xgc > 0 else 1.0
    return feats


def _prev_season_features(players_df: pd.DataFrame, sd, prev_prior: pd.DataFrame | None) -> pd.DataFrame:
    """Prev-season priors joined onto players_df via FPL code. Indexed by element."""
    if prev_prior is None or prev_prior.empty or sd.players_raw is None:
        return pd.DataFrame()

    code_by_element = sd.players_raw.set_index("element")["code"]
    elems = pd.DataFrame({"element": players_df["id"].values})
    elems["code"] = elems["element"].map(code_by_element)
    elems = elems.dropna(subset=["code"])
    elems["code"] = elems["code"].astype(int)

    prior = prev_prior.drop(columns=["element"], errors="ignore").set_index("code")
    merged = elems.join(prior, on="code", how="left")
    keep = [c for c in ["hist_prev_minutes", "hist_prev_games", "hist_prev_points",
                        "hist_prev_starts", "hist_prev_xg_per_90", "hist_prev_xa_per_90",
                        "hist_prev_points_per_90", "hist_prev_starts_rate",
                        "hist_prev_position", "hist_prev_team"] if c in merged.columns]
    if "prev_minutes" in merged.columns:
        merged["hist_prev_minutes"] = merged["prev_minutes"]
        merged["hist_prev_games"] = merged["prev_games"]
        merged["hist_prev_points"] = merged["prev_points"]
        merged["hist_prev_starts"] = merged.get("prev_starts", 0)
        merged["hist_prev_xg_per_90"] = merged["prev_xg_per_90"]
        merged["hist_prev_xa_per_90"] = merged["prev_xa_per_90"]
        merged["hist_prev_points_per_90"] = merged["prev_points_per_90"]
        merged["hist_prev_starts_rate"] = merged["prev_starts_rate"]
        merged["hist_prev_position"] = merged["prev_position"]
        merged["hist_prev_team"] = merged["prev_team"]
        keep = [c for c in ["hist_prev_minutes", "hist_prev_games", "hist_prev_points",
                            "hist_prev_starts", "hist_prev_xg_per_90", "hist_prev_xa_per_90",
                            "hist_prev_points_per_90", "hist_prev_starts_rate",
                            "hist_prev_position", "hist_prev_team"] if c in merged.columns]

    out = merged.set_index("element")[keep]
    for c in keep:
        out[c] = pd.to_numeric(out[c], errors="coerce") if c != "hist_prev_position" else out[c]
    return out


def add_historical_features(
    players_df: pd.DataFrame,
    sd,
    gw_n: int,
    include: tuple[str, ...] = ("player", "team", "prev"),
    prev_prior: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return a copy of ``players_df`` with ``hist_*`` columns appended.

    ``include`` selects feature groups: "player" (per-player rates),
    "team" (team strength), "prev" (previous-season priors). All features are
    strictly past (rounds < gw_n) or fully completed seasons — no look-ahead.

    Raises ``ValueError`` when there is no history before ``gw_n`` (mirrors
    ``build_state``).
    """
    gw = sd.gw
    past = gw[gw["round"] < gw_n]
    if past.empty:
        raise ValueError(f"{sd.season} gw{gw_n}: no history before target round")

    out = players_df.copy()

    if "player" in include:
        feats = _player_features(past)
        if not feats.empty:
            feats = feats.reindex(out["id"].values).set_axis(out.index, axis=0)
            out = pd.concat([out, feats], axis=1)

    if "team" in include:
        tfeats = _team_features(past, sd)
        if not tfeats.empty:
            team_map = tfeats.reindex(out["team_id"].values)
            team_map.index = out.index
            out = pd.concat([out, team_map], axis=1)

    if "prev" in include:
        if prev_prior is None:
            prev_prior = previous_season_prior(sd.season)
        pfeats = _prev_season_features(out, sd, prev_prior)
        if not pfeats.empty:
            out = pd.concat([out, pfeats.reindex(out.index)], axis=1)

    return out
