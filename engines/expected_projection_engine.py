"""Expected Projection Engine — combines xPts/90 with expected minutes.

This is the V3 projection compositor. It produces a full gameweek expected
points forecast for every player using the two new engines::

    xPts = xPts_per_90 * (expected_minutes / 90)

where ``xPts_per_90`` comes from the Expected Points Engine and
``expected_minutes`` from the Expected Minutes Engine.

The output dataclass (``ExpectedPlayerProjection``) intentionally exposes the
same attribute names as the V2 ``PlayerProjection`` (``projected_points``,
``ci_80_low``, ``minutes_proj``, ``goals_proj``, ...) so it can be persisted to
the append-only prediction ledger and validated by the existing validation
platform — enabling a side-by-side V2-vs-V3 comparison without changing any
production code path.

Reads from: Expected Points Engine + Expected Minutes Engine outputs
Config: config/expected_points/expected_points_v1.yaml (CIs + variance sources)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from engines.expected_minutes_engine import (
    ExpectedMinutesProjection,
    project_expected_minutes,
)
from engines.expected_points_engine import (
    ExpectedPointsProjection,
    project_expected_points,
)
from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class ExpectedPlayerProjection:
    """Full gameweek xPts projection for one player (V3).

    Attribute names mirror the V2 PlayerProjection so persistence and
    validation work unchanged.
    """

    player_id: int
    web_name: str
    position: str
    gameweek_id: int

    # Core output
    projected_points: float  # xPts for the gameweek
    xpts_per_90: float
    expected_minutes: float

    # Confidence intervals
    ci_80_low: float
    ci_80_high: float
    ci_95_low: float
    ci_95_high: float

    # Component breakdown (aligned to V2 schema for the ledger)
    minutes_proj: float
    goals_proj: float
    assists_proj: float
    clean_sheet_proj: float
    bonus_proj: float
    other_proj: float

    # Confidence metadata
    confidence: float  # 0-100
    data_quality: str
    variance_total: float

    # Explainability
    contributing_factors: dict = field(default_factory=dict)


def run_expected_projection(
    store,
    gameweek_id: int = 0,
    points_version: str | None = None,
    minutes_version: str | None = None,
) -> list[ExpectedPlayerProjection]:
    """Run both V3 engines and compose the final xPts projection.

    Parameters
    ----------
    store : FeatureStore
        Central feature store.
    gameweek_id : int
        Target gameweek.
    points_version : str | None
        Optional ``expected_points`` config version (None = active/production).
    minutes_version : str | None
        Optional ``expected_minutes`` config version (None = active/production).

    Returns
    -------
    list[ExpectedPlayerProjection]
        One per player, sorted by player_id.
    """
    xpts_90 = project_expected_points(store, gameweek_id, config_version=points_version)
    minutes = project_expected_minutes(store, gameweek_id, config_version=minutes_version)
    return compose_expected_projections(xpts_90, minutes, gameweek_id, points_version)


def compose_expected_projections(
    xpts_90: list[ExpectedPointsProjection],
    minutes: list[ExpectedMinutesProjection],
    gameweek_id: int = 0,
    points_version: str | None = None,
) -> list[ExpectedPlayerProjection]:
    """Compose per-90 rates with expected minutes into full gameweek xPts.

    ``xPts = xPts_per_90 * (expected_minutes / 90)`` with variance propagated
    from both the rate estimate and the minutes estimate.
    """
    cfg = load_config("expected_points", points_version)
    ci_config = cfg.get("confidence_intervals", {"ci_80_z": 1.28, "ci_95_z": 1.96})
    variance_config = cfg.get("variance_sources", _default_variance_sources())
    quality_multipliers = cfg.get("confidence", {}).get(
        "quality_multipliers",
        {"none": 1.5, "limited": 1.2, "moderate": 1.0, "good": 0.8},
    )
    position_values = cfg.get("position_values", {})

    xpts_map = {p.player_id: p for p in xpts_90}
    projections = []

    for m in minutes:
        rate = xpts_map.get(m.player_id)
        if rate is None:
            logger.warning("No xPts/90 for player_id=%d, skipping", m.player_id)
            continue

        minutes_factor = m.expected_minutes / 90.0

        # Core formula
        projected_points = rate.xpts_per_90 * minutes_factor

        # Component breakdown (per-90 rates scaled by minutes factor)
        pos_vals = position_values.get(
            m.position, position_values.get("MID", {}),
        )
        goals_proj = rate.xg_90 * minutes_factor * rate.fixture_multiplier
        assists_proj = rate.xa_90 * minutes_factor * rate.fixture_multiplier
        clean_sheet_proj = rate.clean_sheet_prob * pos_vals.get("clean_sheet", 0) * minutes_factor
        bonus_proj = rate.expected_bonus * minutes_factor
        other_proj = (
            rate.expected_saves + rate.expected_cards + rate.set_piece_bonus
        ) * minutes_factor

        # Variance from both engines + base randomness
        variance = _compute_variance(
            projected_points=projected_points,
            rate_confidence=rate.confidence,
            minutes_confidence=m.confidence,
            data_quality=_merge_data_quality(rate.data_quality, m.data_quality),
            quality_multipliers=quality_multipliers,
            variance_config=variance_config,
        )
        std_dev = np.sqrt(max(variance, 0.0))

        ci_80_z = ci_config.get("ci_80_z", 1.28)
        ci_95_z = ci_config.get("ci_95_z", 1.96)

        confidence = _compute_overall_confidence(
            rate_confidence=rate.confidence,
            minutes_confidence=m.confidence,
            projected_points=projected_points,
        )

        projections.append(ExpectedPlayerProjection(
            player_id=m.player_id,
            web_name=m.web_name,
            position=m.position,
            gameweek_id=gameweek_id,
            projected_points=round(projected_points, 2),
            xpts_per_90=round(rate.xpts_per_90, 3),
            expected_minutes=round(m.expected_minutes, 1),
            ci_80_low=round(max(0, projected_points - ci_80_z * std_dev), 2),
            ci_80_high=round(projected_points + ci_80_z * std_dev, 2),
            ci_95_low=round(max(0, projected_points - ci_95_z * std_dev), 2),
            ci_95_high=round(projected_points + ci_95_z * std_dev, 2),
            minutes_proj=round(m.expected_minutes, 1),
            goals_proj=round(goals_proj, 3),
            assists_proj=round(assists_proj, 3),
            clean_sheet_proj=round(clean_sheet_proj, 2),
            bonus_proj=round(bonus_proj, 3),
            other_proj=round(other_proj, 2),
            confidence=round(confidence, 1),
            data_quality=_merge_data_quality(rate.data_quality, m.data_quality),
            variance_total=round(variance, 3),
            contributing_factors={
                "xpts_per_90": round(rate.xpts_per_90, 3),
                "expected_minutes": round(m.expected_minutes, 1),
                "start_probability": round(m.start_probability, 3),
                "minutes_factor": round(minutes_factor, 3),
                "rotation_risk": m.rotation_risk,
                "data_quality_rate": rate.data_quality,
                "data_quality_minutes": m.data_quality,
            },
        ))

    projections.sort(key=lambda p: p.player_id)
    return projections


def expected_projection_to_dataframe(
    projections: list[ExpectedPlayerProjection],
) -> pd.DataFrame:
    """Convert a list of ExpectedPlayerProjection to a DataFrame."""
    return pd.DataFrame([vars(p) for p in projections])


def compare_to_v2(
    v3_projections: list[ExpectedPlayerProjection],
    v2_projections: list,
) -> dict:
    """Side-by-side alignment report between V3 xPts and V2 projections.

    Pre-validation comparison: does not require actuals. Reports mean xPts,
    correlation, mean absolute difference and agreement on top-ranked players.
    """
    if not v3_projections or not v2_projections:
        return {"error": "Both projection lists must be non-empty"}

    v3_by_id = {p.player_id: p.projected_points for p in v3_projections}
    v2_by_id = {p.player_id: p.projected_points for p in v2_projections}

    common = sorted(set(v3_by_id) & set(v2_by_id))
    if not common:
        return {"error": "No common players between the two projections"}

    import numpy as np

    v3_pts = np.array([v3_by_id[pid] for pid in common], dtype=float)
    v2_pts = np.array([v2_by_id[pid] for pid in common], dtype=float)

    diff = v3_pts - v2_pts
    corr = float(np.corrcoef(v2_pts, v3_pts)[0, 1]) if np.std(v2_pts) > 0 else 0.0

    return {
        "n_common_players": len(common),
        "v2_mean_pts": round(float(np.mean(v2_pts)), 3),
        "v3_mean_pts": round(float(np.mean(v3_pts)), 3),
        "mean_diff_v3_minus_v2": round(float(np.mean(diff)), 3),
        "mean_abs_diff": round(float(np.mean(np.abs(diff))), 3),
        "correlation": round(corr, 4),
        "corr_pct": round(corr * 100, 1),
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_variance(
    projected_points: float,
    rate_confidence: float,
    minutes_confidence: float,
    data_quality: str,
    quality_multipliers: dict,
    variance_config: dict,
) -> float:
    """Combine rate and minutes uncertainty into total variance.

    Variance scales with expected points (heteroscedastic), matching the
    behaviour of the V2 projection engine.
    """
    rate_uncertainty = 1 - (rate_confidence / 100)
    minutes_uncertainty = 1 - (minutes_confidence / 100)
    base_randomness = 0.4

    w_rate = variance_config.get("rate", 0.40)
    w_minutes = variance_config.get("minutes", 0.35)
    w_base = variance_config.get("base", 0.25)

    raw_variance = (
        w_rate * rate_uncertainty
        + w_minutes * minutes_uncertainty
        + w_base * base_randomness
    )

    quality_mult = quality_multipliers.get(data_quality, 1.0)
    return raw_variance * max(projected_points, 1.0) * quality_mult


def _compute_overall_confidence(
    rate_confidence: float,
    minutes_confidence: float,
    projected_points: float,
) -> float:
    """Blend the two engine confidences into a single 0-100 rating."""
    blended = 0.5 * rate_confidence + 0.5 * minutes_confidence
    if projected_points >= 5:
        blended += 5
    elif projected_points <= 2:
        blended -= 5
    return float(np.clip(blended, 10.0, 95.0))


def _merge_data_quality(a: str, b: str) -> str:
    """Merge two data-quality tiers, taking the more conservative."""
    rank = {"none": 0, "limited": 1, "moderate": 2, "good": 3}
    return min((a, b), key=lambda q: rank.get(q, 0))


def _default_variance_sources() -> dict:
    return {
        "rate": 0.40,
        "minutes": 0.35,
        "base": 0.25,
    }
