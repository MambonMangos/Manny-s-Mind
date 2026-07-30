"""Confidence Engine — quantifies prediction uncertainty from multiple sources.

Owns:
  - Confidence intervals (80%, 95%)
  - Confidence ratings (0-100)
  - Uncertainty decomposition (which factor contributes most)
  - Data quality assessment

Reads from: FeatureStore, Minutes Engine output
Config: config/prediction/prediction_v1.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceResult:
    """Confidence assessment for a single player projection."""

    player_id: int
    web_name: str

    # Overall confidence (0-100)
    confidence: float
    confidence_tier: str  # "Very High", "High", "Medium", "Low", "Very Low"

    # Interval outputs
    ci_80_low: float
    ci_80_high: float
    ci_95_low: float
    ci_95_high: float

    # Uncertainty decomposition
    uncertainty_minutes: float  # 0-1 contribution from minutes
    uncertainty_fixture: float  # 0-1 contribution from fixture
    uncertainty_regression: float  # 0-1 contribution from regression
    uncertainty_base: float  # 0-1 contribution from base randomness
    uncertainty_historical: float  # 0-1 contribution from historical accuracy

    # Data quality
    data_quality: str
    data_sources_available: int  # how many data sources we have

    # Explainability
    limiting_factor: str  # what's dragging confidence down most
    improving_factor: str  # what's boosting confidence most


def compute_confidence_batch(
    projections: list,  # noqa: ANN001
    store,  # noqa: ANN001
    minutes_df: pd.DataFrame | None = None,
) -> list[ConfidenceResult]:
    """Compute confidence for a batch of projections.

    Parameters
    ----------
    projections : list[PlayerProjection]
        Output of ``project_all_players()``.
    store : FeatureStore
        Feature store with player data.
    minutes_df : DataFrame, optional
        Minutes engine output.

    Returns
    -------
    list[ConfidenceResult]
        Confidence results aligned with projections.
    """
    cfg = load_config("prediction")
    thresholds = cfg.get("confidence_thresholds", {
        "very_high": 80, "high": 65, "medium": 50, "low": 35,
    })

    results = []
    for proj in projections:
        result = _compute_single_confidence(proj, store, minutes_df, thresholds)
        results.append(result)

    return results


def _compute_single_confidence(
    proj,  # noqa: ANN001
    store,  # noqa: ANN001
    minutes_df: pd.DataFrame | None,
    thresholds: dict,
) -> ConfidenceResult:
    """Compute confidence for a single player projection."""
    df = store.df
    player_row = df[df["player_id"] == proj.player_id]
    if player_row.empty:
        return _empty_confidence(proj)

    row = player_row.iloc[0]

    # 1. Data quality assessment
    data_quality, data_sources = _assess_data_sources(row, minutes_df, proj.player_id)

    # 2. Uncertainty decomposition
    uncertainty_minutes = _minutes_uncertainty(row, minutes_df, proj.player_id)
    uncertainty_fixture = _fixture_uncertainty(row, store)
    uncertainty_regression = _regression_uncertainty(row)
    uncertainty_base = 0.4  # inherent football randomness
    uncertainty_historical = _historical_uncertainty(proj)

    # 3. Total uncertainty (weighted)
    total_uncertainty = (
        0.30 * uncertainty_minutes
        + 0.15 * uncertainty_fixture
        + 0.20 * uncertainty_regression
        + 0.25 * uncertainty_base
        + 0.10 * uncertainty_historical
    )

    # 4. Overall confidence (inverse of uncertainty, scaled 0-100)
    raw_confidence = (1 - total_uncertainty) * 100

    # 5. Data source bonus
    source_bonus = (data_sources / 5) * 10  # up to 10 pts for 5 sources
    confidence = min(raw_confidence + source_bonus, 95)

    # 6. Confidence tier
    confidence_tier = _classify_tier(confidence, thresholds)

    # 7. Identify limiting and improving factors
    factors = {
        "minutes": uncertainty_minutes,
        "fixture": uncertainty_fixture,
        "regression": uncertainty_regression,
        "base": uncertainty_base,
        "historical": uncertainty_historical,
    }
    limiting_factor = max(factors, key=factors.get)
    improving_factor = min(factors, key=factors.get)

    return ConfidenceResult(
        player_id=proj.player_id,
        web_name=proj.web_name,
        confidence=round(confidence, 1),
        confidence_tier=confidence_tier,
        ci_80_low=proj.ci_80_low,
        ci_80_high=proj.ci_80_high,
        ci_95_low=proj.ci_95_low,
        ci_95_high=proj.ci_95_high,
        uncertainty_minutes=round(uncertainty_minutes, 3),
        uncertainty_fixture=round(uncertainty_fixture, 3),
        uncertainty_regression=round(uncertainty_regression, 3),
        uncertainty_base=round(uncertainty_base, 3),
        uncertainty_historical=round(uncertainty_historical, 3),
        data_quality=data_quality,
        data_sources_available=data_sources,
        limiting_factor=limiting_factor,
        improving_factor=improving_factor,
    )


def _assess_data_sources(
    row: pd.Series,
    minutes_df: pd.DataFrame | None,
    player_id: int,
) -> tuple[str, int]:
    """Assess how many data sources are available for this player."""
    sources = 0

    # Source 1: Minutes data
    if float(row.get("minutes", 0) or 0) > 0:
        sources += 1

    # Source 2: xGI data
    if float(row.get("expected_goal_involvements", 0) or 0) > 0:
        sources += 1

    # Source 3: Minutes engine output
    if minutes_df is not None and player_id in minutes_df["player_id"].values:
        sources += 1

    # Source 4: Form data
    if float(row.get("form", 0) or 0) > 0:
        sources += 1

    # Source 5: Status = fit
    if str(row.get("status", "a")) == "a":
        sources += 1

    quality = "none"
    if sources >= 4:
        quality = "good"
    elif sources >= 3:
        quality = "moderate"
    elif sources >= 1:
        quality = "limited"

    return quality, sources


def _minutes_uncertainty(
    row: pd.Series,
    minutes_df: pd.DataFrame | None,
    player_id: int,
) -> float:
    """Compute uncertainty from minutes projection (0-1, higher = more uncertain)."""
    minutes = float(row.get("minutes", 0) or 0)

    # No minutes data = very uncertain
    if minutes == 0:
        return 0.8

    # Check minutes engine confidence if available
    if minutes_df is not None and player_id in minutes_df["player_id"].values:
        min_row = minutes_df[minutes_df["player_id"] == player_id].iloc[0]
        rotation_risk = str(min_row.get("rotation_risk", "Low"))
        if rotation_risk == "High":
            return 0.6
        if rotation_risk == "Medium":
            return 0.35
        return 0.2

    # Fallback: tier-based
    if minutes >= 270:
        return 0.15
    if minutes >= 180:
        return 0.25
    if minutes >= 90:
        return 0.40
    return 0.60


def _fixture_uncertainty(row: pd.Series, store) -> float:
    """Compute uncertainty from fixture difficulty (0-1)."""
    team_id = int(row.get("team_id", 0) or 0)
    fixtures = store.fixture_map.get(team_id, [])

    if not fixtures:
        return 0.5  # unknown fixtures = moderate uncertainty

    next_diff = fixtures[0].get("difficulty", 3)
    # Easy fixtures: more certain. Hard fixtures: less certain.
    return (next_diff - 1) / 4  # 0 (easy) to 1 (hard)


def _regression_uncertainty(row: pd.Series) -> float:
    """Compute uncertainty from regression-to-mean effects."""
    xg = float(row.get("expected_goals", 0) or 0)
    goals = float(row.get("goals_scored", 0) or 0)
    minutes = float(row.get("minutes", 1) or 1)

    if xg == 0 or minutes == 0:
        return 0.3  # baseline

    games = max(1, minutes / 90)
    finishing_ratio = goals / xg

    # Large deviation from 1.0 = high regression uncertainty
    deviation = abs(finishing_ratio - 1.0)
    return min(0.1 + deviation * 0.4, 0.8)


def _historical_uncertainty(proj) -> float:
    """Estimate uncertainty from historical prediction accuracy."""
    # Placeholder: will be replaced by actual error tracking in Phase 6
    if proj.projected_points >= 5:
        return 0.25  # high-scoring players harder to predict
    if proj.projected_points <= 2:
        return 0.35  # low-scoring players also hard to predict
    return 0.30


def _classify_tier(confidence: float, thresholds: dict) -> str:
    """Classify confidence into a human-readable tier."""
    if confidence >= thresholds.get("very_high", 80):
        return "Very High"
    if confidence >= thresholds.get("high", 65):
        return "High"
    if confidence >= thresholds.get("medium", 50):
        return "Medium"
    if confidence >= thresholds.get("low", 35):
        return "Low"
    return "Very Low"


def _empty_confidence(proj) -> ConfidenceResult:
    """Return a low-confidence result when player data is missing."""
    return ConfidenceResult(
        player_id=proj.player_id,
        web_name=proj.web_name,
        confidence=10.0,
        confidence_tier="Very Low",
        ci_80_low=0, ci_80_high=0,
        ci_95_low=0, ci_95_high=0,
        uncertainty_minutes=0.8,
        uncertainty_fixture=0.5,
        uncertainty_regression=0.3,
        uncertainty_base=0.4,
        uncertainty_historical=0.3,
        data_quality="none",
        data_sources_available=0,
        limiting_factor="minutes",
        improving_factor="base",
    )
