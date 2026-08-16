"""Research data loader — reads vendored vaastav CSV files, validates the
per-season schema, and caches a normalized parquet store under
data_research/store/ (completely separate from the production DB).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from research import config
from research.schema import assert_season_schema

logger = logging.getLogger(__name__)

_ENCODINGS = ("utf-8", "latin-1", "cp1252")


def _read_csv(path: pd.io.common.FilePath, **kwargs) -> pd.DataFrame:
    for enc in _ENCODINGS:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"could not decode {path} with any supported encoding")


def _season_dir(season: str) -> pd.io.common.FilePath:
    d = config.VAASTAV_DIR / season
    assert d.exists(), f"vendored data missing for season {season}"
    return d


# ---------------------------------------------------------------------------
# Gameweek files
# ---------------------------------------------------------------------------

def load_gw_season(season: str, use_cache: bool = True) -> pd.DataFrame:
    """Load all non-empty per-GW files for a season into one normalized frame."""
    cache = config.STORE_DIR / f"{season}_gw.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)

    season_dir = _season_dir(season)
    gw_dir = season_dir / "gws"
    assert gw_dir.exists(), f"{season}: no gws/ directory"

    frames = []
    first_header: set[str] | None = None
    for path in sorted(gw_dir.glob("gw*.csv")):
        df = _read_csv(path)
        if df.empty:
            logger.info("[%s] skipping empty gw file: %s", season, path.name)
            continue
        if first_header is None:
            first_header = set(df.columns)
        frames.append(df)

    assert frames, f"{season}: no non-empty gw files"
    gw = pd.concat(frames, ignore_index=True)

    assert_season_schema(season, first_header)

    # Normalize types / names used downstream
    gw["element"] = gw["element"].astype(int)
    gw["round"] = gw["round"].astype(int)
    for col in config.CUMULATIVE_COLS + config.XG_COLS + [config.STARTS_COL, "value", "selected", "transfers_in", "transfers_out"]:
        if col in gw.columns:
            gw[col] = pd.to_numeric(gw[col], errors="coerce").fillna(0)

    gw = gw.sort_values(["round", "element"]).reset_index(drop=True)
    config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    gw.to_parquet(cache)
    logger.info("[%s] loaded %d gw rows across %d rounds", season, len(gw), gw["round"].nunique())
    return gw


# ---------------------------------------------------------------------------
# Season snapshot files
# ---------------------------------------------------------------------------

def load_players_raw(season: str, use_cache: bool = True) -> pd.DataFrame:
    cache = config.STORE_DIR / f"{season}_players_raw.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    raw = _read_csv(_season_dir(season) / "players_raw.csv")
    if "element" not in raw.columns:
        raw["element"] = raw["id"]
    raw["element"] = raw["element"].astype(int)
    for col in ["penalties_order", "direct_freekicks_order", "corners_and_indirect_freekicks_order",
                "selected_by_percent", "chance_of_playing_next_round", "element_type", "team"]:
        if col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
    config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    raw.to_parquet(cache)
    return raw


def load_fixtures(season: str, use_cache: bool = True) -> pd.DataFrame | None:
    cache = config.STORE_DIR / f"{season}_fixtures.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    path = _season_dir(season) / "fixtures.csv"
    if not path.exists():
        logger.info("[%s] no fixtures.csv (season predates fixture data)", season)
        return None
    fx = _read_csv(path)
    for col in ["event", "team_h", "team_a", "team_h_difficulty", "team_a_difficulty"]:
        if col in fx.columns:
            fx[col] = pd.to_numeric(fx[col], errors="coerce")
    config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    fx.to_parquet(cache)
    return fx


def load_teams(season: str, use_cache: bool = True) -> pd.DataFrame | None:
    cache = config.STORE_DIR / f"{season}_teams.parquet"
    if use_cache and cache.exists():
        return pd.read_parquet(cache)
    path = _season_dir(season) / "teams.csv"
    if not path.exists():
        logger.info("[%s] no teams.csv", season)
        return None
    tm = _read_csv(path)
    for col in ["id", "strength_overall_home", "strength_overall_away"]:
        if col in tm.columns:
            tm[col] = pd.to_numeric(tm[col], errors="coerce")
    config.STORE_DIR.mkdir(parents=True, exist_ok=True)
    tm.to_parquet(cache)
    return tm


# ---------------------------------------------------------------------------
# Ownership calibration
# ---------------------------------------------------------------------------

def estimate_total_managers(season: str, gw: pd.DataFrame, players_raw: pd.DataFrame) -> float:
    """Estimate the total manager population from the data itself.

    FPL's own `selected_by_percent` == selected / total_managers * 100. We have
    `selected` counts per GW (data) and the end-of-season `selected_by_percent`
    (players_raw). The ratio gives total managers. Using a single season-level
    constant as the denominator preserves rankings/tiers and is leakage-safe
    (it is a static scale, not a per-GW observation).
    """
    if "selected_by_percent" not in players_raw.columns:
        return 7_000_000.0  # documented fallback constant
    last_round = int(gw["round"].max())
    last_selected = (
        gw[gw["round"] == last_round][["element", "selected"]]
        .set_index("element")["selected"]
    )
    sp = players_raw.set_index("element")["selected_by_percent"].dropna()
    joined = pd.concat([last_selected, sp], axis=1, join="inner").dropna()
    joined.columns = ["selected", "pct"]
    joined = joined[(joined["pct"] > 0.5) & (joined["selected"] > 0)]
    if joined.empty:
        return 7_000_000.0
    est = (joined["selected"] / joined["pct"] * 100.0).median()
    return float(np.clip(est, 1_000_000.0, 25_000_000.0))


# ---------------------------------------------------------------------------
# Season bundle
# ---------------------------------------------------------------------------

@dataclass
class SeasonData:
    """All data for one season, loaded once and reused across gameweeks."""

    season: str
    gw: pd.DataFrame
    players_raw: pd.DataFrame | None = None
    fixtures: pd.DataFrame | None = None
    teams: pd.DataFrame | None = None
    total_managers: float = 7_000_000.0
    _team_name: dict[int, str] = field(default_factory=dict, repr=False)
    _team_short: dict[int, str] = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, season: str, use_cache: bool = True) -> SeasonData:
        gw = load_gw_season(season, use_cache=use_cache)
        raw = load_players_raw(season, use_cache=use_cache)
        fixtures = load_fixtures(season, use_cache=use_cache)
        teams = load_teams(season, use_cache=use_cache)
        total = estimate_total_managers(season, gw, raw) if raw is not None else 7_000_000.0

        team_name, team_short = {}, {}
        if teams is not None:
            team_name = dict(zip(teams["id"].astype(int), teams["name"].astype(str)))
            if "short_name" in teams.columns:
                team_short = dict(zip(teams["id"].astype(int), teams["short_name"].astype(str)))
        return cls(
            season=season, gw=gw, players_raw=raw, fixtures=fixtures,
            teams=teams, total_managers=total,
            _team_name=team_name, _team_short=team_short,
        )

    @property
    def rounds(self) -> list[int]:
        return sorted(self.gw["round"].unique())

    @property
    def team_name(self) -> dict[int, str]:
        return self._team_name

    @property
    def team_short(self) -> dict[int, str]:
        return self._team_short
