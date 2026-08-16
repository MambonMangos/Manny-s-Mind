"""Cross-season player identity — Phase 1 of the historical-data program.

FPL's per-season ``element`` id is NOT stable across seasons, but the
``code`` field in ``players_raw.csv`` is FPL's stable per-player identifier
(verified stable for Salah/Saka/Haaland/Watkins across 2022-23..2024-25).
This module builds the ``(season, element) <-> code`` mapping and exposes
leakage-safe previous-season priors for a target season (the previous season
always completed before the target season began).

Documented limitation: ``player_idlist.csv`` only carries ``(first_name,
second_name, id)``, so identity relies on ``players_raw.csv``'s ``code``
column (present in every vendored season). New-join / rebranded players who
share no code simply have no previous-season prior (correct behaviour).
"""

from __future__ import annotations

import logging

import pandas as pd

from research import config
from research.loader import SeasonData, load_players_raw

logger = logging.getLogger(__name__)


def previous_season(target_season: str) -> str | None:
    """Return the season immediately before ``target_season``, or None."""
    try:
        idx = config.ALL_SEASONS.index(target_season)
    except ValueError:
        return None
    if idx == 0:
        return None
    return config.ALL_SEASONS[idx - 1]


def player_codes(seasons: list[str] | None = None) -> pd.DataFrame:
    """Return (season, element, code, web_name, position, team) for all players.

    ``position`` is the FPL positional label (GKP/DEF/MID/FWD) from
    ``element_type``; ``team`` is the FPL team id from ``players_raw``.
    """
    seasons = seasons or config.ALL_SEASONS
    frames = []
    for season in seasons:
        pr = load_players_raw(season)
        cols = ["element", "code", "web_name", "element_type", "team"]
        present = [c for c in cols if c in pr.columns]
        df = pr[present].copy()
        df["season"] = season
        if "code" in df.columns:
            df = df[df["code"].notna()]
            df["code"] = df["code"].astype(int)
        if "element_type" in df.columns:
            df["position"] = df["element_type"].map(config.POSITION_MAP)
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def _season_player_prior(season: str) -> pd.DataFrame:
    """Full-season cumulative + per-90 priors for every player of ``season``.

    Indexed by FPL ``code``. Columns:
      prev_minutes, prev_points, prev_starts, prev_games, prev_goals,
      prev_assists, prev_xg, prev_xa, prev_xg_per_90, prev_xa_per_90,
      prev_points_per_90, prev_starts_rate, prev_position, prev_team.
    """
    sd = SeasonData.load(season)
    gw = sd.gw
    raw = sd.players_raw

    agg: dict = {
        "prev_minutes": ("minutes", "sum"),
        "prev_points": ("total_points", "sum"),
        "prev_games": ("element", "count"),
        "prev_goals": ("goals_scored", "sum"),
        "prev_assists": ("assists", "sum"),
    }
    if config.STARTS_COL in gw.columns:
        agg["prev_starts"] = (config.STARTS_COL, "sum")
    if config.XG_COLS[0] in gw.columns:
        agg["prev_xg"] = (config.XG_COLS[0], "sum")
        agg["prev_xa"] = (config.XG_COLS[1], "sum")

    prior = gw.groupby("element").agg(**agg)
    for col in agg:
        prior[col] = pd.to_numeric(prior[col], errors="coerce").fillna(0)

    if raw is not None:
        ident = raw.set_index("element")
        prior["code"] = pd.to_numeric(ident["code"], errors="coerce")
        prior["prev_position"] = (
            ident["element_type"].map(config.POSITION_MAP)
        )
        prior["prev_team"] = pd.to_numeric(ident["team"], errors="coerce")
        prior = prior.dropna(subset=["code"])
        prior["code"] = prior["code"].astype(int)

    prior["prev_starts"] = prior.get("prev_starts", 0)
    prior["prev_xg"] = prior.get("prev_xg", 0.0)
    prior["prev_xa"] = prior.get("prev_xa", 0.0)

    prior["prev_xg_per_90"] = (
        prior["prev_xg"] / (prior["prev_minutes"] / 90)
    ).fillna(0.0).replace([float("inf"), float("-inf")], 0.0)
    prior["prev_xa_per_90"] = (
        prior["prev_xa"] / (prior["prev_minutes"] / 90)
    ).fillna(0.0).replace([float("inf"), float("-inf")], 0.0)
    prior["prev_points_per_90"] = (
        prior["prev_points"] / (prior["prev_minutes"] / 90)
    ).fillna(0.0).replace([float("inf"), float("-inf")], 0.0)
    prior["prev_starts_rate"] = np_safe_divide(
        prior["prev_starts"], prior["prev_games"],
    )
    prior["prev_minutes_per_90"] = prior["prev_minutes"] / 90.0

    return prior.reset_index()


def _np_safe_divide(num, den, fill=0.0):
    import numpy as np

    den = pd.to_numeric(den, errors="coerce").replace(0, np.nan)
    out = pd.to_numeric(num, errors="coerce") / den
    return out.fillna(fill).replace([float("inf"), float("-inf")], fill)


np_safe_divide = _np_safe_divide


def previous_season_prior(target_season: str) -> pd.DataFrame:
    """Previous-season priors for ``target_season`` (leakage-safe).

    Empty DataFrame when the target season has no previous season in the
    vendored data (2016-17) or the previous season is unloaded.
    """
    prev = previous_season(target_season)
    if prev is None:
        logger.info("no previous season for %s; no prev-season prior", target_season)
        return pd.DataFrame()
    try:
        return _season_player_prior(prev)
    except AssertionError as exc:
        logger.warning("cannot build prev-season prior for %s -> %s: %s",
                       target_season, prev, exc)
        return pd.DataFrame()
