"""Scoring engine – normalises raw stats and computes composite value scores."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.constants import MAX_SEASON_MINUTES, WEIGHTS

# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _min_max_scale(series: pd.Series) -> pd.Series:
    """Scale a Series to 0–100.  Constant columns become 0."""
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return ((series - mn) / (mx - mn)) * 100.0


# ---------------------------------------------------------------------------
# Derived columns
# ---------------------------------------------------------------------------

def add_derived_columns(
    df: pd.DataFrame,
    fixture_map: dict | None = None,
    team_name_map: dict | None = None,
) -> pd.DataFrame:
    """Add xGI/90, minutes_score, points_per_million etc. without mutating the input.

    Parameters
    ----------
    fixture_map : dict, optional
        team_id → list of fixture dicts. When provided, computes real fixture
        scores instead of the 50.0 placeholder.
    team_name_map : dict, optional
        team_id → team_name. Required when fixture_map is provided.

    Returns a copy with new columns.
    """
    df = df.copy()

    # xGI / 90
    df["xgi_per_90"] = np.where(
        df["minutes"] > 0,
        (df["expected_goal_involvements"] / df["minutes"]) * 90.0,
        0.0,
    )

    # Points per million
    df["points_per_million"] = np.where(
        df["price"] > 0, df["total_points"] / df["price"], 0.0
    )

    # Minutes played fraction
    df["minutes_fraction"] = (df["minutes"] / MAX_SEASON_MINUTES) * 100.0

    # Team strength (use neutral 100.0 as fallback, not 1000.0 which skews results)
    df["team_strength_raw"] = (
        df["strength_overall_home"].fillna(100.0) + df["strength_overall_away"].fillna(100.0)
    ) / 2.0

    # Fixture score — use real data when available, fallback to 50.0
    if fixture_map is not None and team_name_map is not None:
        df["fixture_score_raw"] = df.apply(
            lambda row: _compute_player_fixture_score(row, fixture_map),
            axis=1,
        )
    else:
        df["fixture_score_raw"] = 50.0

    # Set-piece score — based on penalties_order / FK order / corners order
    df["set_piece_raw"] = df.apply(_set_piece_score, axis=1)

    return df


def _compute_player_fixture_score(row, fixture_map: dict) -> float:
    """Compute fixture score for a player based on upcoming fixtures.

    Uses the next 3 fixtures with recency weighting (most recent weighted most).
    """
    team_id = int(row.get("team_id", 0) or 0)
    fixtures = fixture_map.get(team_id, [])
    if not fixtures:
        return 50.0

    # Take next 3 fixtures
    upcoming = fixtures[:3]
    if not upcoming:
        return 50.0

    # Weighted average: most recent fixture weighted most
    weights = [0.5, 0.3, 0.2][: len(upcoming)]
    total_weight = sum(weights)

    weighted_score = 0.0
    for f, w in zip(upcoming, weights):
        difficulty = f.get("difficulty", 3)
        score = ((5 - difficulty) / 4) * 100
        weighted_score += score * w

    return weighted_score / total_weight


def _set_piece_score(row: pd.Series) -> float:
    """Rough proxy: lower order number → higher score."""
    score = 50.0  # baseline
    if pd.notna(row.get("penalties_order")) and row["penalties_order"] is not None:
        order = row["penalties_order"]
        if order == 1:
            score += 30
        elif order == 2:
            score += 15
        elif order == 3:
            score += 5
    if pd.notna(row.get("direct_freekicks_order")) and row["direct_freekicks_order"] is not None:
        fk_order = row["direct_freekicks_order"]
        if fk_order == 1:
            score += 20
        elif fk_order == 2:
            score += 8
    return min(score, 100.0)


# ---------------------------------------------------------------------------
# Composite scoring
# ---------------------------------------------------------------------------

@dataclass
class ScoringResult:
    """Holds normalised components and the final composite score."""

    minutes_norm: pd.Series
    xgi_norm: pd.Series
    value_norm: pd.Series
    team_norm: pd.Series
    fixture_norm: pd.Series
    ownership_norm: pd.Series
    set_piece_norm: pd.Series
    composite: pd.Series
    xgi_per_90: pd.Series
    points_per_million: pd.Series


def compute_value_score(df: pd.DataFrame) -> ScoringResult:
    """Compute the composite Moneyball Value Score.

    Steps:
        1. Add derived columns.
        2. Normalise every component to 0-100.
        3. Combine using WEIGHTS.

    Returns a ScoringResult dataclass.
    """
    df = add_derived_columns(df)

    minutes_norm = _min_max_scale(df["minutes_fraction"])
    xgi_norm = _min_max_scale(df["xgi_per_90"])
    value_norm = _min_max_scale(df["points_per_million"])
    team_norm = _min_max_scale(df["team_strength_raw"])
    fixture_norm = _min_max_scale(df["fixture_score_raw"])
    ownership_norm = _min_max_scale(df["selected_by_percent"])
    set_piece_norm = _min_max_scale(df["set_piece_raw"])

    composite = (
        minutes_norm * WEIGHTS["minutes"]
        + xgi_norm * WEIGHTS["xgi_per_90"]
        + value_norm * WEIGHTS["value"]
        + team_norm * WEIGHTS["team_strength"]
        + fixture_norm * WEIGHTS["fixture"]
        + ownership_norm * WEIGHTS["ownership"]
        + set_piece_norm * WEIGHTS["set_pieces"]
    )

    return ScoringResult(
        minutes_norm=minutes_norm,
        xgi_norm=xgi_norm,
        value_norm=value_norm,
        team_norm=team_norm,
        fixture_norm=fixture_norm,
        ownership_norm=ownership_norm,
        set_piece_norm=set_piece_norm,
        composite=composite,
        xgi_per_90=df["xgi_per_90"],
        points_per_million=df["points_per_million"],
    )
