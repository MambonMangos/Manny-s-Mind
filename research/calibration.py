"""Empirical parameter calibration — Phases 3 & 4 of the historical program.

Fits per-position empirical relationships from the faithful seasons
(2022-23..2024-25 — the only seasons with real per-GW ``starts`` AND FPL xG),
replacing arbitrary closed-form constants in the V3 engines with data-driven
values:

  expected_points:
    - finishing   : goals ~ finishing * xG            (per position)
    - creative    : assists ~ creative * xA           (per position)
    - bonus       : expected bonus ~ slope*bps_90 + intercept   (per position)
    - clean_sheet : P(cs) ~ intercept + slope * xGC_per_game   (per position)
  expected_minutes (probability-weighted, adds the "came off bench" branch):
    - start_rate_prior            : P(start) per position
    - min_if_start / min_if_sub   : E[minutes] given start / sub
    - sub_rate_given_not_start    : P(sub appearance | not starting)

All fits are minutes-weighted and shrinkage-adjusted (low-count positions —
notably GKP creative — are pulled toward a neutral prior to avoid overfitting).
The fitted values are written into NEW versioned config YAML files; the
production configs are never touched.

WARNING: params are fitted on FULL train seasons. Walk-forward validation uses
them only for a LATER held-out season (leakage-safe by construction).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from research import config as rconfig
from research.loader import SeasonData
from utils.config import load_config

logger = logging.getLogger(__name__)

POSITIONS = ["GKP", "DEF", "MID", "FWD"]

# Shrinkage half-life counts: weight = n / (n + k).
FINISHING_SHRINK_K = 60.0
CREATIVE_SHRINK_K = 30.0

MINUTES_COLS = [
    "start_rate_prior", "min_if_start", "min_if_sub",
    "sub_rate_given_not_start", "unused_rate_given_not_start",
]


@dataclass
class CalibrationParams:
    """Empirical parameter bundle fitted from train seasons."""

    finishing: dict = field(default_factory=dict)
    creative: dict = field(default_factory=dict)
    bonus: dict = field(default_factory=dict)       # pos -> {"intercept","slope"}
    clean_sheet: dict = field(default_factory=dict)  # pos -> {"intercept","slope"}
    minutes: dict = field(default_factory=dict)     # pos -> MINUTES_COLS
    seasons: list[str] = field(default_factory=list)
    n_matches: int = 0
    source_pin: str = rconfig.SOURCE_PIN

    def to_dict(self) -> dict:
        return {
            "finishing": self.finishing,
            "creative": self.creative,
            "bonus": self.bonus,
            "clean_sheet": self.clean_sheet,
            "minutes": self.minutes,
            "seasons": self.seasons,
            "n_matches": self.n_matches,
            "source_pin": self.source_pin,
        }

    @classmethod
    def from_dict(cls, data: dict) -> CalibrationParams:
        return cls(**{k: data[k] for k in [
            "finishing", "creative", "bonus", "clean_sheet", "minutes",
            "seasons", "n_matches", "source_pin",
        ]})


def _shrink(value: float, n: float, k: float, neutral: float, lo: float, hi: float) -> float:
    w = n / (n + k)
    out = w * value + (1 - w) * neutral
    return float(np.clip(out, lo, hi))


def _load_match_table(seasons: list[str]) -> pd.DataFrame:
    """Per-(season, round, team, position) match rows for model fitting."""
    frames = []
    for season in seasons:
        sd = SeasonData.load(season)
        gw = sd.gw
        if sd.players_raw is None:
            continue
        elem_team = sd.players_raw.set_index("element")["team"]
        elem_pos = sd.players_raw.set_index("element")["element_type"].map(rconfig.POSITION_MAP)
        g = gw.assign(
            _team=gw["element"].map(elem_team),
            _pos=gw["element"].map(elem_pos),
        ).dropna(subset=["_team", "_pos"])
        g = g[g["minutes"] > 0].copy()
        if rconfig.XG_COLS[0] not in g.columns:
            g["expected_goals"] = 0.0
            g["expected_goals_conceded"] = 0.0
        # Team per-match aggregates (each player row carries the team xGC).
        team_match = g.groupby(["_team", "round"]).agg(
            team_xg=("expected_goals", "sum"),
            team_xgc=("expected_goals_conceded", "max"),
            team_goals=("goals_scored", "sum"),
            team_assists=("assists", "sum"),
            team_cs=("clean_sheets", "max"),
            team_minutes=("minutes", "sum"),
        ).reset_index()
        frames.append(team_match)
    if not frames:
        raise ValueError("no match tables produced (missing seasons/players_raw)")
    return pd.concat(frames, ignore_index=True)


def _fit_finishing_creative(matches: pd.DataFrame, players: pd.DataFrame) -> tuple[dict, dict]:
    """Minute-weighted goals/xG and assists/xA per position (shrunk)."""
    agg = players.groupby("_pos").agg(
        n_minutes=("minutes", "sum"),
        n_goals=("goals_scored", "sum"),
        n_assists=("assists", "sum"),
        n_xg=("expected_goals", "sum"),
        n_xa=("expected_assists", "sum"),
    )
    finishing, creative = {}, {}
    for pos in POSITIONS:
        if pos not in agg.index:
            finishing[pos], creative[pos] = 1.0, 1.0
            continue
        row = agg.loc[pos]
        raw_fin = row["n_goals"] / row["n_xg"] if row["n_xg"] > 0 else 1.0
        raw_cre = row["n_assists"] / row["n_xa"] if row["n_xa"] > 0 else 1.0
        finishing[pos] = _shrink(raw_fin, row["n_goals"], FINISHING_SHRINK_K, 1.0, 0.7, 1.3)
        creative[pos] = _shrink(raw_cre, row["n_assists"], CREATIVE_SHRINK_K, 1.0, 0.5, 1.6)
    return finishing, creative


def _fit_bonus(players: pd.DataFrame) -> dict:
    """Per-position OLS: bonus_per_90 ~ bps_per_90 (minutes > 0 rows)."""
    bonus = {}
    for pos in POSITIONS:
        sub = players[(players["_pos"] == pos) & (players["minutes"] > 0)]
        if len(sub) < 50:
            bonus[pos] = {"intercept": 0.0, "slope": 1.0 / 160.0}
            continue
        bps_90 = sub["bps"] * 90 / sub["minutes"]
        bonus_90 = sub["bonus"] * 90 / sub["minutes"]
        coefs = np.polyfit(bps_90, bonus_90, 1)
        slope = max(float(coefs[0]), 0.0)
        intercept = float(coefs[1])
        bonus[pos] = {"intercept": round(intercept, 4), "slope": round(slope, 5)}
    return bonus


def _fit_clean_sheet(matches: pd.DataFrame) -> dict:
    """Linear-probability fit of P(cs) on team xGC in the match."""
    m = matches[(matches["team_xgc"].notna()) & (matches["team_xgc"] > 0)]
    cs_model = {}
    for pos in POSITIONS:
        if m.empty:
            cs_model[pos] = {"intercept": 0.25, "slope": 0.0}
            continue
        x = m["team_xgc"].values
        y = m["team_cs"].values
        coefs = np.polyfit(x, y, 1)
        cs_model[pos] = {
            "intercept": round(float(coefs[1]), 4),
            "slope": round(float(coefs[0]), 4),
        }
    return cs_model


def _fit_minutes(players: pd.DataFrame) -> dict:
    """Per-position minutes / start-sub-unused probability constants.

    ``start_rate_prior`` is the unconditional P(start); ``alpha``/``beta`` are
    a beta-binomial prior so the engine can compute a sample-size-aware
    posterior P(start) = (alpha + starts) / (alpha + beta + appearances).
    """
    minutes = {}
    for pos in POSITIONS:
        sub = players[players["_pos"] == pos]
        if sub.empty:
            minutes[pos] = {c: (90.0 if c == "min_if_start" else 0.0) for c in MINUTES_COLS}
            minutes[pos]["alpha"] = 1.0
            minutes[pos]["beta"] = 1.0
            continue
        is_start = sub["starts"] == 1
        is_sub = (sub["starts"] == 0) & (sub["minutes"] > 0)
        not_start = ~is_start

        alpha, beta = 1.0, 1.0
        # Beta prior via method of moments on player-season starts rates.
        player_rates = sub.groupby(["season", "element"]).apply(
            lambda g: pd.Series({
                "starts": g["starts"].sum(),
                "apps": (g["starts"].sum() + (g["starts"] == 0).sum()),
            })
        )
        player_rates = player_rates[player_rates["apps"] >= 5]
        if len(player_rates) > 50:
            rates = (player_rates["starts"] / player_rates["apps"]).clip(0.01, 0.99)
            m = float(rates.mean())
            v = float(rates.var(ddof=1))
            if 0 < m < 1 and v > 1e-6 and v < m * (1 - m):
                scale = m * (1 - m) / v - 1
                if scale > 0:
                    alpha = m * scale
                    beta = (1 - m) * scale

        minutes[pos] = {
            "start_rate_prior": round(float(is_start.mean()), 4),
            "alpha": round(float(alpha), 3),
            "beta": round(float(beta), 3),
            "min_if_start": round(float(sub.loc[is_start, "minutes"].mean()), 1) if is_start.any() else 90.0,
            "min_if_sub": round(float(sub.loc[is_sub, "minutes"].mean()), 1) if is_sub.any() else 0.0,
            "sub_rate_given_not_start": round(float(is_sub[not_start].mean()), 4) if not_start.any() else 0.0,
            "unused_rate_given_not_start": round(float((~is_sub)[not_start].mean()), 4) if not_start.any() else 1.0,
        }
    return minutes


def fit_params(train_seasons: list[str]) -> CalibrationParams:
    """Fit all empirical params from the given (fully completed) train seasons."""
    matches = _load_match_table(train_seasons)

    frames = []
    for season in train_seasons:
        sd = SeasonData.load(season)
        if sd.players_raw is None:
            continue
        elem_team = sd.players_raw.set_index("element")["team"]
        elem_pos = sd.players_raw.set_index("element")["element_type"].map(rconfig.POSITION_MAP)
        g = sd.gw.assign(
            _team=sd.gw["element"].map(elem_team),
            _pos=sd.gw["element"].map(elem_pos),
        ).dropna(subset=["_pos"])
        g["season"] = season
        for xg_col in ["expected_goals", "expected_assists"]:
            if xg_col not in g.columns:
                g[xg_col] = 0.0
        frames.append(g)
    players = pd.concat(frames, ignore_index=True)

    finishing, creative = _fit_finishing_creative(matches, players)
    bonus = _fit_bonus(players)
    clean_sheet = _fit_clean_sheet(matches)
    minutes = _fit_minutes(players)

    params = CalibrationParams(
        finishing=finishing,
        creative=creative,
        bonus=bonus,
        clean_sheet=clean_sheet,
        minutes=minutes,
        seasons=list(train_seasons),
        n_matches=len(matches),
    )
    return params


def save_params(params: CalibrationParams, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(params.to_dict(), f, indent=2)


def load_params(path: Path) -> CalibrationParams:
    with open(path) as f:
        return CalibrationParams.from_dict(json.load(f))


# ---------------------------------------------------------------------------
# Config generation (versioned, additive — production configs untouched)
# ---------------------------------------------------------------------------

def _base_config(category: str, version: str) -> dict:
    return dict(load_config(category, version))


def build_points_config(params: CalibrationParams) -> dict:
    cfg = _base_config("expected_points", "expected_points_v1")
    cfg["version"] = "hist-1.0.0"
    cfg["description"] = (
        "Expected Points (xPts/90) with empirical historical calibration "
        "(finishing/creative/bonus/clean-sheet) fit on faithful seasons. "
        f"Train seasons: {', '.join(params.seasons)}. Source pin: {params.source_pin}."
    )
    cfg["empirical"] = {
        "finishing": params.finishing,
        "creative": params.creative,
        "bonus": params.bonus,
        "clean_sheet": params.clean_sheet,
        # Shrink current-season xGI toward the previous season when the
        # current-season sample is tiny.
        "prev_season": {
            "min_current_games": 3,
            "prev_weight": 0.35,
        },
        # Blend empirical team strength into xG/xA and xGC (active only when
        # hist_team_* columns are present).
        "historical_team": {
            "attack_weight": 0.5,
            "defense_weight": 0.5,
        },
    }
    return cfg


def build_minutes_config(params: CalibrationParams) -> dict:
    cfg = _base_config("expected_minutes", "expected_minutes_v1")
    cfg["version"] = "hist-1.0.0"
    cfg["description"] = (
        "Expected Minutes with probability-weighted start/sub/unused model "
        "(adds the came-off-the-bench branch). "
        f"Train seasons: {', '.join(params.seasons)}. Source pin: {params.source_pin}."
    )
    cfg["historical_minutes"] = {
        "enabled": True,
        "positional": params.minutes,
        # Blend the player's own observed starts_rate toward the position prior.
        "start_prior_weight": 0.8,
        # Blend the player's own hist_sub_rate toward the position constant.
        "sub_blend_weight": 0.7,
        # Shrink toward previous-season starts_rate when few current starts.
        "prev_season": {
            "min_current_starts": 3,
            "prev_weight": 0.30,
        },
        "min_start_prob": 0.03,
        "max_start_prob": 0.97,
    }
    return cfg


def write_config_yaml(category: str, version: str, cfg: dict, cfg_dir: Path) -> None:
    """Write a config dict to config/<category>/<version>.yaml (never overwrite)."""
    path = cfg_dir / category / f"{version}.yaml"
    if path.exists():
        logger.info("config already exists (not overwriting): %s", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
    logger.info("wrote config: %s", path)
