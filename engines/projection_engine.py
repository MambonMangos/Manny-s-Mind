"""Projection Engine — projects fantasy points per player per gameweek with confidence intervals.

This is the core V2 engine. It combines:
  - Minutes projection (Minutes Engine)
  - xGI rates (FeatureStore)
  - Fixture difficulty (Fixture Engine)
  - Position-based scoring values (config)

Every projection is versioned and persisted. Projections are appended, never
overwritten. Confidence intervals quantify uncertainty from multiple sources.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class PlayerProjection:
    """Point projection for a single player in a single gameweek."""

    player_id: int
    web_name: str
    position: str
    gameweek_id: int

    # Core projection
    projected_points: float
    ci_80_low: float
    ci_80_high: float
    ci_95_low: float
    ci_95_high: float

    # Component breakdown
    minutes_proj: float
    goals_proj: float
    assists_proj: float
    clean_sheet_proj: float
    bonus_proj: float
    other_proj: float

    # Confidence metadata
    confidence: float  # 0-100
    data_quality: str
    variance_total: float  # total standard deviation

    # For debugging / explainability
    contributing_factors: dict = field(default_factory=dict)


def project_all_players(
    store,  # noqa: ANN001
    minutes_df: pd.DataFrame | None = None,
    gameweek_id: int = 0,
) -> list[PlayerProjection]:
    """Project points for all players in the FeatureStore.

    Parameters
    ----------
    store : FeatureStore
        Central feature store with player data.
    minutes_df : DataFrame, optional
        Output of ``compute_minutes_features()``. If None, uses
        store's built-in minutes projection.
    gameweek_id : int
        Target gameweek for projection.

    Returns
    -------
    list[PlayerProjection]
        One projection per player.
    """
    cfg = load_config("prediction")
    position_values = cfg.get("position_values", _default_position_values())
    ci_config = cfg.get("confidence_intervals", {"ci_80_z": 1.28, "ci_95_z": 1.96})
    variance_config = cfg.get("variance_sources", _default_variance_sources())

    df = store.df
    projections = []

    for idx, row in df.iterrows():
        player_id = int(row.get("player_id", idx))
        web_name = str(row.get("web_name", ""))
        position = str(row.get("position", ""))
        team_id = int(row.get("team_id", 0) or 0)

        # Get minutes projection
        if minutes_df is not None and player_id in minutes_df["player_id"].values:
            min_row = minutes_df[minutes_df["player_id"] == player_id].iloc[0]
            minutes_proj = float(min_row["minutes_projected"])
            start_prob = float(min_row["start_probability"])
            data_quality = str(min_row["data_quality"])
            minutes_confidence = float(min_row["confidence"])
        else:
            minutes_proj = float(row.get("minutes_projected", 60))
            start_prob = 0.7
            data_quality = "limited"
            minutes_confidence = 50.0

        # Get fixture context
        fixtures = store.fixture_map.get(team_id, [])
        next_fixture = fixtures[0] if fixtures else {}
        fixture_difficulty = next_fixture.get("difficulty", 3)
        is_home = next_fixture.get("home", False)

        # Position-specific scoring
        pos_vals = position_values.get(position, position_values.get("MID", _default_mid_values()))

        # 1. Project each event type
        xg = float(row.get("expected_goals", 0) or 0)
        xa = float(row.get("expected_assists", 0) or 0)
        xgc = float(row.get("expected_goals_conceded", 0) or 0)
        total_points = float(row.get("total_points", 0) or 0)
        minutes_season = float(row.get("minutes", 1) or 1)

        # Per-90 rates
        minutes_factor = minutes_proj / 90.0
        games_played = max(1, minutes_season / 90)

        xg_per_90 = xg / max(games_played, 1)
        xa_per_90 = xa / max(games_played, 1)

        # Fixture modifier (easier = higher multiplier)
        fixture_mult = (5 - fixture_difficulty) / 4.0  # 0.0 (hard) to 1.0 (easy)
        fixture_mult = max(fixture_mult, 0.5)  # floor at 0.5

        # 2. Project individual events
        goals_proj = xg_per_90 * minutes_factor * fixture_mult
        assists_proj = xa_per_90 * minutes_factor * fixture_mult

        # Clean sheet probability (position-dependent)
        if position in ("GKP", "DEF"):
            cs_base = max(0, 1 - (xgc / max(games_played, 1) * minutes_factor))
            clean_sheet_proj = cs_base * pos_vals.get("clean_sheet", 0)
        elif position == "MID":
            cs_base = max(0, 1 - (xgc / max(games_played, 1) * minutes_factor))
            clean_sheet_proj = cs_base * 1  # MID gets 1 pt for CS
        else:
            clean_sheet_proj = 0  # FWD gets 0 for CS

        # Bonus points (rough heuristic: ~2 pts per game for high-performers)
        points_per_game = total_points / max(games_played, 1)
        bonus_proj = min(points_per_game / 5, 0.6) * minutes_factor

        # 3. Sum total projected points
        other_proj = 0.0  # saves, penalty saves, etc. (hard to project)
        projected_points = (
            goals_proj * pos_vals.get("goal", 0)
            + assists_proj * pos_vals.get("assist", 0)
            + clean_sheet_proj
            + bonus_proj * 3  # bonus max = 3
            + other_proj
        )

        # Apply start probability (if not starting, heavily discounted)
        projected_points *= start_prob
        goals_proj *= start_prob
        assists_proj *= start_prob
        clean_sheet_proj *= start_prob
        bonus_proj *= start_prob

        # 4. Compute variance and confidence intervals
        variance = _compute_variance(
            projected_points=projected_points,
            minutes_confidence=minutes_confidence,
            fixture_difficulty=fixture_difficulty,
            data_quality=data_quality,
            variance_config=variance_config,
        )
        std_dev = np.sqrt(variance)

        ci_80_z = ci_config.get("ci_80_z", 1.28)
        ci_95_z = ci_config.get("ci_95_z", 1.96)

        ci_80_low = max(0, projected_points - ci_80_z * std_dev)
        ci_80_high = projected_points + ci_80_z * std_dev
        ci_95_low = max(0, projected_points - ci_95_z * std_dev)
        ci_95_high = projected_points + ci_95_z * std_dev

        # 5. Overall confidence
        confidence = _compute_overall_confidence(
            minutes_confidence=minutes_confidence,
            data_quality=data_quality,
            fixture_difficulty=fixture_difficulty,
            projected_points=projected_points,
        )

        projections.append(PlayerProjection(
            player_id=player_id,
            web_name=web_name,
            position=position,
            gameweek_id=gameweek_id,
            projected_points=round(projected_points, 2),
            ci_80_low=round(ci_80_low, 2),
            ci_80_high=round(ci_80_high, 2),
            ci_95_low=round(ci_95_low, 2),
            ci_95_high=round(ci_95_high, 2),
            minutes_proj=round(minutes_proj, 1),
            goals_proj=round(goals_proj, 3),
            assists_proj=round(assists_proj, 3),
            clean_sheet_proj=round(clean_sheet_proj, 2),
            bonus_proj=round(bonus_proj, 3),
            other_proj=round(other_proj, 2),
            confidence=round(confidence, 1),
            data_quality=data_quality,
            variance_total=round(variance, 2),
            contributing_factors={
                "fixture_difficulty": fixture_difficulty,
                "is_home": is_home,
                "minutes_factor": round(minutes_factor, 2),
                "start_probability": round(start_prob, 3),
                "xg_per_90": round(xg_per_90, 3),
                "xa_per_90": round(xa_per_90, 3),
            },
        ))

    return projections


def project_to_dataframe(
    projections: list[PlayerProjection],
) -> pd.DataFrame:
    """Convert a list of PlayerProjection objects to a DataFrame."""
    return pd.DataFrame([vars(p) for p in projections])


def compute_projection_version_tag(
    gameweek_id: int,
    config_hash: str,
) -> str:
    """Generate a unique version tag for this projection run."""
    return f"v2-gw{gameweek_id}-{config_hash[:8]}"


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_variance(
    projected_points: float,
    minutes_confidence: float,
    fixture_difficulty: int,
    data_quality: str,
    variance_config: dict,
) -> float:
    """Compute total variance from multiple uncertainty sources.

    Variance sources (weighted):
      - minutes: how uncertain is the minutes projection
      - fixture: how unpredictable is the fixture
      - regression: how likely is mean reversion
      - base: inherent randomness in football
      - historical: past prediction accuracy
    """
    # Minutes uncertainty (0-1, higher = more uncertain)
    minutes_uncertainty = 1 - (minutes_confidence / 100)

    # Fixture uncertainty (difficulty 1-5, harder = more uncertain)
    fixture_uncertainty = (fixture_difficulty - 1) / 4  # 0 (easy) to 1 (hard)

    # Regression uncertainty
    regression_uncertainty = 0.3  # baseline; enhanced by regression engine

    # Base randomness (always present in football)
    base_randomness = 0.4

    # Historical accuracy (from experiment tracking)
    historical_uncertainty = 0.3

    # Data quality factor
    quality_mult = {"none": 1.5, "limited": 1.2, "moderate": 1.0, "good": 0.8}.get(
        data_quality, 1.0
    )

    # Weighted variance sum
    w_minutes = variance_config.get("minutes", 0.30)
    w_fixture = variance_config.get("fixture", 0.15)
    w_regression = variance_config.get("regression", 0.20)
    w_base = variance_config.get("base", 0.25)
    w_historical = variance_config.get("historical", 0.10)

    raw_variance = (
        w_minutes * minutes_uncertainty
        + w_fixture * fixture_uncertainty
        + w_regression * regression_uncertainty
        + w_base * base_randomness
        + w_historical * historical_uncertainty
    )

    # Scale variance by expected points (heteroscedastic)
    # Higher-scoring players have proportionally more variance
    scaled_variance = raw_variance * max(projected_points, 1.0) * quality_mult

    return scaled_variance


def _compute_overall_confidence(
    minutes_confidence: float,
    data_quality: str,
    fixture_difficulty: int,
    projected_points: float,
) -> float:
    """Compute a 0-100 overall confidence rating."""
    # Base from minutes confidence
    base = minutes_confidence

    # Data quality modifier
    quality_adj = {"none": -20, "limited": -10, "moderate": 0, "good": 10}.get(
        data_quality, 0
    )

    # Fixture modifier (harder = less confident)
    fixture_adj = -(fixture_difficulty - 3) * 5  # ±5 per difficulty level

    # Points magnitude modifier (higher projections = more confident in direction)
    if projected_points >= 5:
        points_adj = 5
    elif projected_points <= 2:
        points_adj = -5
    else:
        points_adj = 0

    confidence = base + quality_adj + fixture_adj + points_adj
    return max(min(confidence, 95), 10)


def _default_position_values() -> dict:
    return {
        "GKP": {"goal": 10, "assist": 3, "clean_sheet": 1, "yellow_card": -1, "red_card": -3},
        "DEF": {"goal": 6, "assist": 3, "clean_sheet": 4, "yellow_card": -1, "red_card": -3},
        "MID": {"goal": 5, "assist": 3, "clean_sheet": 1, "yellow_card": -1, "red_card": -3},
        "FWD": {"goal": 4, "assist": 3, "clean_sheet": 0, "yellow_card": -1, "red_card": -3},
    }


def _default_mid_values() -> dict:
    return {"goal": 5, "assist": 3, "clean_sheet": 1, "yellow_card": -1, "red_card": -3}


def _default_variance_sources() -> dict:
    return {
        "minutes": 0.30,
        "fixture": 0.15,
        "regression": 0.20,
        "base": 0.25,
        "historical": 0.10,
    }
