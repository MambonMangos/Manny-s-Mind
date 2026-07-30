"""Regression Engine — detects over/underperformance relative to xG/xA and flags regression candidates.

Owns:
  - Finishing ratio analysis (actual goals / xG)
  - Creative ratio analysis (actual assists / xA)
  - Regression candidate scoring
  - Mean reversion adjustments to projections

Reads from: FeatureStore
Config: config/features/features_v1.yaml (regression section)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class RegressionSignal:
    """Regression analysis for a single player."""

    player_id: int
    web_name: str
    position: str

    # Core metrics
    finishing_ratio: float  # actual goals / xG (1.0 = expected)
    creative_ratio: float  # actual assists / xA (1.0 = expected)
    goal_deviation: float  # goals - xG (positive = overperforming)
    assist_deviation: float  # assists - xA (positive = overperforming)

    # Classification
    regression_type: str  # "overperforming", "underperforming", "on_track"
    regression_strength: float  # 0-1, how strong the signal is
    regression_confidence: float  # 0-100

    # Adjustment recommendation
    points_adjustment: float  # recommended adjustment to projected points
    confidence_impact: float  # adjustment to confidence interval width


def compute_regression_signals(
    store,  # noqa: ANN001
) -> list[RegressionSignal]:
    """Analyze all players for regression-to-mean signals.

    Returns a list of RegressionSignal, one per player.
    """
    cfg = load_config("features")
    reg_cfg = cfg.get("regression", {})
    overperform_thresh = reg_cfg.get("finishing_ratio_overperform", 1.3)
    underperform_thresh = reg_cfg.get("finishing_ratio_underperform", 0.7)
    min_sample = reg_cfg.get("min_sample_size", 3)

    df = store.df
    signals = []

    for _, row in df.iterrows():
        signal = _analyze_player_regression(
            row, overperform_thresh, underperform_thresh, min_sample,
        )
        signals.append(signal)

    return signals


def apply_regression_adjustments(
    projections: list,  # noqa: ANN001
    signals: list[RegressionSignal],
) -> list:
    """Apply regression adjustments to projections.

    Modifies projected_points in-place based on regression signals.
    """
    signal_map = {s.player_id: s for s in signals}

    for proj in projections:
        signal = signal_map.get(proj.player_id)
        if signal is None:
            continue

        # Apply points adjustment
        proj.projected_points = max(0, proj.projected_points + signal.points_adjustment)

        # Widen confidence intervals for regression candidates
        if signal.regression_type != "on_track":
            proj.ci_80_low = max(0, proj.ci_80_low - signal.confidence_impact)
            proj.ci_80_high = proj.ci_80_high + signal.confidence_impact
            proj.ci_95_low = max(0, proj.ci_95_low - signal.confidence_impact * 1.5)
            proj.ci_95_high = proj.ci_95_high + signal.confidence_impact * 1.5

    return projections


def get_regression_summary(
    signals: list[RegressionSignal],
) -> dict:
    """Summarize regression landscape across all players."""
    overperforming = [s for s in signals if s.regression_type == "overperforming"]
    underperforming = [s for s in signals if s.regression_type == "underperforming"]

    return {
        "total_players": len(signals),
        "overperforming": len(overperforming),
        "underperforming": len(underperforming),
        "on_track": len(signals) - len(overperforming) - len(underperforming),
        "top_overperformers": sorted(
            overperforming, key=lambda s: s.regression_strength, reverse=True,
        )[:10],
        "top_underperformers": sorted(
            underperforming, key=lambda s: s.regression_strength, reverse=True,
        )[:10],
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _analyze_player_regression(
    row: pd.Series,
    overperform_thresh: float,
    underperform_thresh: float,
    min_sample: int,
) -> RegressionSignal:
    """Analyze regression signals for a single player."""
    player_id = int(row.get("player_id", 0))
    web_name = str(row.get("web_name", ""))
    position = str(row.get("position", ""))

    # Raw stats
    xg = float(row.get("expected_goals", 0) or 0)
    xa = float(row.get("expected_assists", 0) or 0)
    goals = float(row.get("goals_scored", 0) or 0)
    assists = float(row.get("assists", 0) or 0)
    minutes = float(row.get("minutes", 0) or 0)

    # Read canonical ratios from Feature Store (SSOT)
    finishing_ratio = float(row.get("finishing_ratio", 1.0))
    creative_ratio = float(row.get("creative_ratio", 1.0))
    goal_deviation = goals - xg
    assist_deviation = assists - xa

    # Sample size check
    games = max(1, int(minutes / 90))
    sample_sufficient = games >= min_sample

    # Classification
    regression_type = "on_track"
    regression_strength = 0.0
    points_adjustment = 0.0
    confidence_impact = 0.0

    if sample_sufficient:
        # Goal regression
        if finishing_ratio > overperform_thresh:
            regression_type = "overperforming"
            regression_strength = min((finishing_ratio - 1.0) / 0.5, 1.0)
            # Adjust down: expected reversion
            points_adjustment = -goal_deviation * 0.3 * _position_goal_value(position)
            confidence_impact = regression_strength * 2.0
        elif finishing_ratio < underperform_thresh:
            regression_type = "underperforming"
            regression_strength = min((1.0 - finishing_ratio) / 0.5, 1.0)
            # Adjust up: expected reversion
            points_adjustment = abs(goal_deviation) * 0.2 * _position_goal_value(position)
            confidence_impact = regression_strength * 1.5

        # Assist regression (secondary signal)
        if creative_ratio > 1.4:
            points_adjustment -= assist_deviation * 0.2
            regression_strength = max(regression_strength, 0.3)
        elif creative_ratio < 0.6:
            points_adjustment += abs(assist_deviation) * 0.15
            regression_strength = max(regression_strength, 0.2)

    # Confidence in the regression signal itself
    if not sample_sufficient:
        regression_confidence = 30.0
    elif games < 10:
        regression_confidence = 50.0
    elif games < 20:
        regression_confidence = 70.0
    else:
        regression_confidence = 85.0

    return RegressionSignal(
        player_id=player_id,
        web_name=web_name,
        position=position,
        finishing_ratio=round(finishing_ratio, 3),
        creative_ratio=round(creative_ratio, 3),
        goal_deviation=round(goal_deviation, 2),
        assist_deviation=round(assist_deviation, 2),
        regression_type=regression_type,
        regression_strength=round(regression_strength, 3),
        regression_confidence=round(regression_confidence, 1),
        points_adjustment=round(points_adjustment, 2),
        confidence_impact=round(confidence_impact, 2),
    )


def _position_goal_value(position: str) -> float:
    """Relative value of a goal by position (for weighting regression impact)."""
    return {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}.get(position, 5)
