"""Minutes Engine — projects expected minutes for each player per gameweek.

Owns:
  - minutes_projection: how many minutes a player is expected to play
  - start_probability: probability of starting
  - rotation_risk: classification of rotation risk
  - substitution_risk: probability of being subbed off early

Reads from: FeatureStore
Config: config/minutes/minutes_v1.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class MinutesProjection:
    """Result of the Minutes Engine for one player."""

    player_id: int
    web_name: str
    position: str

    # Core outputs
    projected_minutes: float  # expected minutes next GW (0-90)
    start_probability: float  # 0.0-1.0
    rotation_risk: str  # "Low", "Medium", "High"
    substitution_risk: float  # probability of being subbed

    # Confidence
    confidence: float  # 0-100
    data_quality: str  # "none", "limited", "moderate", "good"

    # Component breakdown
    minutes_tier_base: float  # base from tier system
    modifier_delta: float  # net adjustment from modifiers
    historical_avg: float  # average of recent minutes
    season_phase_label: str  # "preseason", "early_season", "establishing", "established"


def compute_minutes_features(
    store,
) -> pd.DataFrame:
    """Compute minutes projections using the FeatureStore.

    This replaces the ad-hoc ``project_minutes`` function in prediction_engine.py
    with a configurable, data-driven projection.

    Returns a DataFrame with columns:
      player_id, web_name, position, minutes_projected, start_probability,
      rotation_risk, substitution_risk, confidence, data_quality
    """
    cfg = load_config("minutes")
    tier_map = cfg.get("tiers", {0: 60.0, 90: 55.0, 180: 70.0, 270: 85.0})
    modifiers = cfg.get("modifiers", {})
    rotation_thresholds = cfg.get("rotation_risk", {})
    sub_risk_cfg = cfg.get("substitution_risk", {})
    confidence_cfg = cfg.get("confidence", {})

    df = store.df
    results = []

    for idx, row in df.iterrows():
        minutes_season = float(row.get("minutes", 0) or 0)
        status = str(row.get("status", "a") or "a")
        form = float(row.get("form", 0) or 0)
        int(row.get("team_id", 0) or 0)

        # 1. Tier-based base projection
        minutes_tier = _tier_lookup(minutes_season, tier_map)

        # 2. Modifier adjustments
        modifier_delta = _compute_modifiers(
            row, modifiers, store.fixture_map,
        )

        # 3. Raw projection
        raw_minutes = np.clip(minutes_tier + modifier_delta, 0, 90)

        # 4. Start probability
        start_prob = _compute_start_probability(
            minutes_season, status, form, raw_minutes, modifiers,
        )

        # 5. Substitution risk
        sub_risk = _compute_substitution_risk(
            raw_minutes, start_prob, sub_risk_cfg,
        )

        # 6. Rotation risk classification
        rotation_risk = _classify_rotation_risk(
            start_prob, rotation_thresholds,
        )

        # 7. Data quality + confidence
        data_quality, confidence = _assess_data_quality(
            minutes_season, confidence_cfg,
        )

        # 8. Season phase
        season_phase = _detect_season_phase(store.gameweek_id)

        results.append({
            "player_id": int(row.get("player_id", idx)),
            "web_name": row.get("web_name", ""),
            "position": row.get("position", ""),
            "minutes_projected": round(raw_minutes, 1),
            "start_probability": round(start_prob, 3),
            "rotation_risk": rotation_risk,
            "substitution_risk": round(sub_risk, 3),
            "confidence": round(confidence, 1),
            "data_quality": data_quality,
            "minutes_tier_base": minutes_tier,
            "modifier_delta": round(modifier_delta, 1),
            "historical_avg": round(minutes_season / max(1, _games_played(minutes_season)), 1),
            "season_phase_label": season_phase,
        })

    return pd.DataFrame(results)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _tier_lookup(minutes_season: float, tier_map: dict) -> float:
    """Look up the base minutes projection from the tier system."""
    sorted_tiers = sorted(tier_map.items(), key=lambda x: x[0], reverse=True)
    for threshold, projection in sorted_tiers:
        if minutes_season >= threshold:
            return projection
    # Below all tiers — no data
    return sorted_tiers[-1][1] if sorted_tiers else 60.0


def _compute_modifiers(
    row: pd.Series,
    modifiers: dict,
    fixture_map: dict,
) -> float:
    """Compute net modifier delta from fixture, schedule, and status factors."""
    delta = 0.0
    status = str(row.get("status", "a") or "a")
    team_id = int(row.get("team_id", 0) or 0)
    minutes = float(row.get("minutes", 0) or 0)

    # Returning from injury
    if status in ("i", "d"):
        delta += modifiers.get("returning_from_injury", -0.10) * 90

    # Fixture difficulty
    fixtures = fixture_map.get(team_id, [])
    if fixtures:
        next_diff = fixtures[0].get("difficulty", 3)
        if next_diff <= 2:
            delta += modifiers.get("easy_fixture", 0.03) * 90
        elif next_diff >= 4:
            delta += modifiers.get("hard_fixture", -0.02) * 90

    # Congested schedule (3+ games in 7 days) — simplified heuristic
    # If minutes are high, assume rotation risk
    if minutes >= 270:
        delta += modifiers.get("congested_schedule", -0.05) * 90

    return delta


def _compute_start_probability(
    minutes_season: float,
    status: str,
    form: float,
    raw_minutes: float,
    modifiers: dict,
) -> float:
    """Estimate the probability of starting the next match."""
    if status in ("i", "s", "u"):
        return 0.0
    if status == "d":
        return 0.4  # doubtful

    # Base probability from minutes tier
    if minutes_season >= 270:
        base = 0.85
    elif minutes_season >= 180:
        base = 0.70
    elif minutes_season >= 90:
        base = 0.55
    elif minutes_season > 0:
        base = 0.40
    else:
        base = 0.30

    # Form adjustment: high form → more likely to start
    if form >= 6:
        base += 0.05
    elif form < 2:
        base -= 0.05

    return np.clip(base, 0.0, 0.95)


def _compute_substitution_risk(
    raw_minutes: float,
    start_prob: float,
    sub_risk_cfg: dict,
) -> float:
    """Estimate probability of being substituted off early."""
    if start_prob < 0.5:
        return 0.3  # if not starting, likely sub

    high_threshold = sub_risk_cfg.get("high_minutes_threshold", 75)
    if raw_minutes >= high_threshold:
        return 0.35  # more likely to be subbed if playing full 90
    return 0.20


def _classify_rotation_risk(
    start_prob: float,
    thresholds: dict,
) -> str:
    """Classify rotation risk based on start probability."""
    high = thresholds.get("high_threshold", 0.30)
    medium = thresholds.get("medium_threshold", 0.60)

    if start_prob < high:
        return "High"
    if start_prob < medium:
        return "Medium"
    return "Low"


def _assess_data_quality(
    minutes_season: float,
    confidence_cfg: dict,
) -> tuple[str, float]:
    """Determine data quality tier and confidence multiplier."""
    games = _games_played(minutes_season)

    if games == 0:
        return "none", confidence_cfg.get("no_data", 30)
    if games < 5:
        return "limited", confidence_cfg.get("limited_data", 50)
    if games < 15:
        return "moderate", confidence_cfg.get("moderate_data", 70)
    return "good", confidence_cfg.get("good_data", 85)


def _games_played(minutes_season: float) -> int:
    """Estimate games played from total minutes."""
    return max(1, int(minutes_season / 90))


def _detect_season_phase(gameweek_id: int) -> str:
    """Detect the current season phase from gameweek ID."""
    if gameweek_id <= 0:
        return "preseason"
    if gameweek_id <= 3:
        return "early_season"
    if gameweek_id <= 10:
        return "establishing"
    return "established"
