"""Expected Minutes Engine — projects probability-weighted minutes for next GW.

This is the next-generation (V3) minutes model. Unlike the V2 Minutes Engine
(which projects a raw minutes tier + modifiers), this engine estimates:

  expected_minutes = start_probability * minutes_if_starting * (1 - substitution_risk)

so the output is an honest expectation of minutes played next gameweek. It is
consumed by the Expected Projection Engine to scale per-90 rates::

    xPts = xPts_per_90 * (expected_minutes / 90)

Owns:
  - start_probability: probability of being in the starting XI
  - minutes_if_starting: expected minutes given a start
  - substitution_risk: probability of being subbed off early
  - expected_minutes: the composite probability-weighted expectation

Reads from: FeatureStore (minutes, availability, trend features)
Config: config/expected_minutes/expected_minutes_v1.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class ExpectedMinutesProjection:
    """Expected minutes for one player in the next gameweek."""

    player_id: int
    web_name: str
    position: str
    team_id: int

    # Core outputs
    expected_minutes: float  # probability-weighted expectation, 0-90
    start_probability: float  # 0.0-1.0
    minutes_if_starting: float  # E[minutes | starts], 0-90
    substitution_risk: float  # 0.0-1.0
    sub_rate_given_not_start: float  # 0.0-1.0 (empirical model)
    rotation_risk: str  # "Low", "Medium", "High"

    # Confidence
    confidence: float  # 0-100
    data_quality: str  # "none", "limited", "moderate", "good"
    games_played: int

    # Explainability
    contributing_factors: dict = field(default_factory=dict)


def project_expected_minutes(
    store,
    gameweek_id: int = 0,
    config_version: str | None = None,
) -> list[ExpectedMinutesProjection]:
    """Compute expected minutes for every player in the FeatureStore.

    Parameters
    ----------
    store : FeatureStore
        Central feature store (single source of truth for all inputs).
    gameweek_id : int
        Target gameweek (used only for metadata/rounding consistency).
    config_version : str | None
        Optional version of the ``expected_minutes`` config to load (e.g.
        "expected_minutes_v1_hist"). None loads the active version — the
        production behaviour, byte-for-byte unchanged.

    Returns
    -------
    list[ExpectedMinutesProjection]
        One per player, sorted by player_id.
    """
    cfg = load_config("expected_minutes", config_version)
    positional_minutes = cfg.get("minutes_if_starting", _default_positional_minutes())
    start_cfg = cfg.get("start_probability", {})
    sub_cfg = cfg.get("substitution", {})
    history_cfg = cfg.get("history", {})
    rotation_cfg = cfg.get("rotation_risk", {})
    confidence_cfg = cfg.get("confidence", {})
    hist_min = cfg.get("historical_minutes", {}) or {}

    minutes_feats = store.minutes_features()
    availability = store.availability_features()
    df = store.df

    projections = []
    for idx, row in df.iterrows():
        player_id = int(row.get("player_id", idx))
        web_name = str(row.get("web_name", ""))
        position = str(row.get("position", ""))
        team_id = int(row.get("team_id", 0) or 0)

        minutes_season = float(row.get("minutes", 0) or 0)
        games_played = _games_played(minutes_season)
        starts = int(float(row.get("starts", 0) or 0))
        starts_rate = float(_col(minutes_feats, idx, "starts_rate"))
        minutes_per_game = float(_col(minutes_feats, idx, "minutes_per_game"))

        status = str(row.get("status", "a") or "a")
        chance_next = float(_col(availability, idx, "chance_next"))
        form = float(row.get("form", 0) or 0)

        hist_mode = bool(hist_min.get("enabled", False))
        if hist_mode:
            # Empirical probability-weighted model: P(start) + P(sub|not start).
            start_prob, minutes_if_starting, substitution_risk, expected_minutes, sub_rate_not_start = (
                _compute_historical_expected_minutes(
                    row, starts, starts_rate, minutes_per_game, position,
                    status, chance_next, form,
                    start_cfg, sub_cfg, history_cfg, hist_min,
                )
            )
        else:
            # 1. Start probability
            start_prob = _compute_start_probability(
                status, starts_rate, chance_next, form, start_cfg,
            )

            # 2. Minutes if starting (history blended with positional baseline)
            minutes_if_starting = _compute_minutes_if_starting(
                starts, minutes_per_game, position, positional_minutes, history_cfg,
            )

            # 3. Substitution risk
            substitution_risk = _compute_substitution_risk(
                minutes_if_starting, sub_cfg,
            )

            # 4. Composite expected minutes
            expected_minutes = start_prob * minutes_if_starting * (1 - substitution_risk)
            expected_minutes = float(np.clip(expected_minutes, 0.0, 90.0))
            sub_rate_not_start = 0.0

        # 5. Rotation risk classification
        rotation_risk = _classify_rotation_risk(start_prob, rotation_cfg)

        # 6. Data quality + confidence
        data_quality, n_sources = _assess_data_quality(row, starts, chance_next)
        confidence = float(confidence_cfg.get(data_quality, 45) or 45)

        projections.append(ExpectedMinutesProjection(
            player_id=player_id,
            web_name=web_name,
            position=position,
            team_id=team_id,
            expected_minutes=round(expected_minutes, 1),
            start_probability=round(start_prob, 3),
            minutes_if_starting=round(minutes_if_starting, 1),
            substitution_risk=round(substitution_risk, 3),
            sub_rate_given_not_start=round(sub_rate_not_start, 3),
            rotation_risk=rotation_risk,
            confidence=round(confidence, 1),
            data_quality=data_quality,
            games_played=games_played,
            contributing_factors={
                "gameweek_id": gameweek_id,
                "starts_rate": round(starts_rate, 3),
                "chance_next": round(chance_next, 3),
                "historical_minutes_per_game": round(minutes_per_game, 1),
                "status": status,
                "sub_rate_given_not_start": round(sub_rate_not_start, 3),
                "data_sources": n_sources,
            },
        ))

    projections.sort(key=lambda p: p.player_id)
    return projections


def expected_minutes_to_dataframe(
    projections: list[ExpectedMinutesProjection],
) -> pd.DataFrame:
    """Convert a list of ExpectedMinutesProjection to a DataFrame."""
    return pd.DataFrame([vars(p) for p in projections])


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _col(features_df: pd.DataFrame, idx, name: str) -> float:
    """Safely read a column value from a feature DataFrame by index."""
    try:
        return float(features_df[name].iloc[idx])
    except (KeyError, IndexError):
        return 0.0


def _games_played(minutes_season: float) -> int:
    """Estimate games played from season minutes."""
    return max(1, int(minutes_season / 90))


def _compute_start_probability(
    status: str,
    starts_rate: float,
    chance_next: float,
    form: float,
    start_cfg: dict,
) -> float:
    """Estimate the probability of starting the next match."""
    unavailable = start_cfg.get("unavailable_statuses", ["i", "s", "u"])
    if status in unavailable:
        return 0.0
    if status == start_cfg.get("doubtful_status", "d"):
        return float(start_cfg.get("doubtful_prob", 0.40) or 0.40)

    history_weight = float(start_cfg.get("history_weight", 0.60) or 0.60)
    chance_weight = float(start_cfg.get("chance_of_playing_weight", 0.40) or 0.40)

    observed = np.clip(starts_rate, 0.0, 1.0) * history_weight
    declared = np.clip(chance_next, 0.0, 1.0) * chance_weight
    prob = observed + declared

    # Form adjustment
    high_form = float(start_cfg.get("high_form_threshold", 6.0) or 6.0)
    low_form = float(start_cfg.get("low_form_threshold", 2.0) or 2.0)
    if form >= high_form:
        prob += float(start_cfg.get("high_form_boost", 0.05) or 0.05)
    elif form < low_form:
        prob -= float(start_cfg.get("low_form_penalty", 0.05) or 0.05)

    max_prob = float(start_cfg.get("max_start_prob", 0.97) or 0.97)
    min_prob = float(start_cfg.get("min_start_prob", 0.05) or 0.05)
    return float(np.clip(prob, min_prob, max_prob))


def _compute_minutes_if_starting(
    starts: int,
    minutes_per_game: float,
    position: str,
    positional_minutes: dict,
    history_cfg: dict,
) -> float:
    """Blend historical minutes-per-start with a positional baseline."""
    baseline = float(
        positional_minutes.get(position, positional_minutes.get("MID", 80)) or 80,
    )
    min_starts = int(history_cfg.get("min_starts_for_history", 3) or 3)
    if starts < min_starts or minutes_per_game <= 0:
        return float(np.clip(baseline, 0.0, 90.0))

    history_blend = float(history_cfg.get("history_blend", 0.6) or 0.6)
    base_blend = float(history_cfg.get("base_blend", 0.4) or 0.4)
    blended = history_blend * minutes_per_game + base_blend * baseline
    return float(np.clip(blended, 0.0, 90.0))


def _compute_substitution_risk(
    minutes_if_starting: float,
    sub_cfg: dict,
) -> float:
    """Estimate the probability of being subbed off early."""
    baseline = float(sub_cfg.get("baseline_risk", 0.10) or 0.10)
    threshold = float(sub_cfg.get("high_minutes_threshold", 78) or 78)
    risk_if_full = float(sub_cfg.get("risk_if_expected_full", 0.25) or 0.25)
    if minutes_if_starting >= threshold:
        return max(baseline, risk_if_full)
    return baseline


def _compute_historical_expected_minutes(
    row,
    starts: int,
    starts_rate: float,
    minutes_per_game: float,
    position: str,
    status: str,
    chance_next: float,
    form: float,
    start_cfg: dict,
    sub_cfg: dict,
    history_cfg: dict,
    hist_min: dict,
) -> tuple[float, float, float, float, float]:
    """Probability-weighted minutes: P(start) + P(sub appearance | not start).

    Adds the "came off the bench" branch that the closed-form model ignores::

        E[min] = P(start) * E[min|start] * (1 - sub_risk)
               + P(not start) * P(sub|not start) * E[min|sub]

    Positional constants come from the ``historical_minutes`` config section
    (fit empirically by ``research.calibration``). Player-specific rates are
    read from the injected ``hist_*`` columns when present (research states)
    and otherwise default to the observed in-state rates.
    """
    hm = hist_min.get("positional", {}) or {}
    pos_hist = hm.get(position, hm.get("MID", {})) or {}
    if not pos_hist:
        pos_hist = {"start_rate_prior": 0.5, "min_if_start": 80.0,
                    "min_if_sub": 30.0, "sub_rate_given_not_start": 0.2}

    # --- P(start) -----------------------------------------------------------
    unavailable = start_cfg.get("unavailable_statuses", ["i", "s", "u"])
    if status in unavailable:
        start_prob = 0.0
    elif status == start_cfg.get("doubtful_status", "d"):
        start_prob = float(start_cfg.get("doubtful_prob", 0.40) or 0.40)
    else:
        prior = float(pos_hist.get("start_rate_prior", 0.5) or 0.5)
        alpha = float(pos_hist.get("alpha", 1.0) or 1.0)
        beta = float(pos_hist.get("beta", 1.0) or 1.0)
        hist_appearances = float(row.get("hist_appearances", np.nan))
        hist_starts = float(row.get("hist_starts", np.nan))

        if np.isfinite(hist_appearances) and np.isfinite(hist_starts) and (alpha + beta + hist_appearances) > 0:
            # Beta-binomial posterior: sample-size-aware P(start).
            observed = (alpha + hist_starts) / (alpha + beta + hist_appearances)
        else:
            # Fallback: fixed-weight blend of observed rate toward position prior.
            prior_weight = float(hist_min.get("start_prior_weight", 0.8) or 0.8)
            observed = prior_weight * np.clip(starts_rate, 0.0, 1.0) + (1 - prior_weight) * prior
        observed = float(np.clip(observed, 0.0, 1.0))

        # Previous-season shrinkage for tiny current-season start samples.
        prev_cfg = hist_min.get("prev_season", {}) or {}
        if starts < int(prev_cfg.get("min_current_starts", 3)):
            prev_rate = float(row.get("hist_prev_starts_rate", np.nan))
            if np.isfinite(prev_rate):
                prev_w = float(prev_cfg.get("prev_weight", 0.0) or 0.0)
                observed = (1 - prev_w) * observed + prev_w * np.clip(prev_rate, 0.0, 1.0)

        start_prob = observed
        if form >= float(start_cfg.get("high_form_threshold", 6.0) or 6.0):
            start_prob += float(start_cfg.get("high_form_boost", 0.05) or 0.05)
        elif form < float(start_cfg.get("low_form_threshold", 2.0) or 2.0):
            start_prob -= float(start_cfg.get("low_form_penalty", 0.05) or 0.05)

    chance_w = float(start_cfg.get("chance_of_playing_weight", 0.40) or 0.40)
    declared = np.clip(chance_next, 0.0, 1.0) * chance_w
    start_prob = start_prob * (1 - chance_w) + declared

    min_prob = float(hist_min.get("min_start_prob", 0.03) or 0.03)
    max_prob = float(hist_min.get("max_start_prob", 0.97) or 0.97)
    start_prob = float(np.clip(start_prob, min_prob, max_prob))

    # --- E[min | start] ------------------------------------------------------
    min_if_start = float(pos_hist.get("min_if_start", 80.0) or 80.0)
    min_starts = int(history_cfg.get("min_starts_for_history", 3) or 3)
    if starts >= min_starts and minutes_per_game > 0:
        history_blend = float(history_cfg.get("history_blend", 0.6) or 0.6)
        base_blend = float(history_cfg.get("base_blend", 0.4) or 0.4)
        min_if_start = history_blend * minutes_per_game + base_blend * min_if_start
    min_if_start = float(np.clip(min_if_start, 0.0, 90.0))

    # --- P(sub | not start) ---------------------------------------------------
    sub_rate = float(pos_hist.get("sub_rate_given_not_start", 0.2) or 0.2)
    player_sub = float(row.get("hist_sub_rate", np.nan))
    if np.isfinite(player_sub):
        blend = float(hist_min.get("sub_blend_weight", 0.7) or 0.7)
        sub_rate = blend * np.clip(player_sub, 0.0, 1.0) + (1 - blend) * sub_rate
    sub_rate = float(np.clip(sub_rate, 0.0, 1.0))

    # --- E[min | sub] ---------------------------------------------------------
    min_if_sub = float(pos_hist.get("min_if_sub", 30.0) or 30.0)

    # --- Substitution risk (informational; the empirical min_if_start/min_if_sub
    # already embed being subbed off, so it is NOT applied to expected minutes)
    substitution_risk = _compute_substitution_risk(min_if_start, sub_cfg)

    expected_minutes = (
        start_prob * min_if_start
        + (1 - start_prob) * sub_rate * min_if_sub
    )
    expected_minutes = float(np.clip(expected_minutes, 0.0, 90.0))
    return start_prob, min_if_start, substitution_risk, expected_minutes, sub_rate


def _classify_rotation_risk(
    start_prob: float,
    thresholds: dict,
) -> str:
    """Classify rotation risk based on start probability."""
    high = float(thresholds.get("high_threshold", 0.30) or 0.30)
    medium = float(thresholds.get("medium_threshold", 0.60) or 0.60)
    if start_prob < high:
        return "High"
    if start_prob < medium:
        return "Medium"
    return "Low"


def _assess_data_quality(
    row: pd.Series,
    starts: int,
    chance_next: float,
) -> tuple[str, int]:
    """Count available data sources and map to a quality tier."""
    sources = 0
    if float(row.get("minutes", 0) or 0) > 0:
        sources += 1
    if starts > 0:
        sources += 1
    if chance_next > 0:
        sources += 1
    if str(row.get("status", "a") or "a") == "a":
        sources += 1

    if sources >= 3:
        return "good", sources
    if sources == 2:
        return "moderate", sources
    if sources == 1:
        return "limited", sources
    return "none", sources


def _default_positional_minutes() -> dict:
    return {"GKP": 90, "DEF": 88, "MID": 78, "FWD": 75}
