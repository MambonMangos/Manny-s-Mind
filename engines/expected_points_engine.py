"""Expected Points Engine — projects Expected Points per 90 minutes (xPts/90).

This is the next-generation (V3) points-rate model. It estimates how many FPL
points a player is expected to earn **per 90 minutes on the pitch**, from
underlying xGI rates, expected clean-sheet probability, bonus expectation,
saves (GKP), card risk and set-piece duties. It deliberately makes **no**
statement about how many minutes the player will actually play — that is the
job of the Expected Minutes Engine. The two are combined by the Expected
Projection Engine using::

    xPts = xPts_per_90 * (expected_minutes / 90)

Owns:
  - xpts_per_90: expected points per 90 minutes
  - xg_90 / xa_90: underlying expected goal involvement rates
  - clean_sheet_prob: expected clean-sheet probability
  - expected_bonus / expected_saves / expected_cards: auxiliary point sources
  - set_piece_bonus: penalty / free-kick / corner duty bonus

Reads from: FeatureStore (xgi, set_piece, availability, trend features)
Config: config/expected_points/expected_points_v1.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class ExpectedPointsProjection:
    """Expected points per 90 minutes for one player."""

    player_id: int
    web_name: str
    position: str
    team_id: int

    # Core output
    xpts_per_90: float  # expected points per 90 minutes

    # Component breakdown (all per 90 minutes)
    xg_90: float
    xa_90: float
    xgc_90: float
    clean_sheet_prob: float  # 0.0-1.0
    expected_bonus: float
    expected_saves: float
    expected_cards: float
    set_piece_bonus: float
    fixture_multiplier: float

    # Confidence
    confidence: float  # 0-100
    data_quality: str  # "none", "limited", "moderate", "good"
    games_played: int

    # Explainability
    contributing_factors: dict = field(default_factory=dict)


def project_expected_points(
    store,
    gameweek_id: int = 0,
    config_version: str | None = None,
) -> list[ExpectedPointsProjection]:
    """Compute xPts/90 for every player in the FeatureStore.

    Parameters
    ----------
    store : FeatureStore
        Central feature store (single source of truth for all inputs).
    gameweek_id : int
        Target gameweek (used only for metadata/rounding consistency).
    config_version : str | None
        Optional version of the ``expected_points`` config to load (e.g.
        "expected_points_v1_hist"). None loads the active version — the
        production behaviour, byte-for-byte unchanged.

    Returns
    -------
    list[ExpectedPointsProjection]
        One per player, sorted by player_id.
    """
    cfg = load_config("expected_points", config_version)
    position_values = cfg.get("position_values", _default_position_values())
    cs_cfg = cfg.get("clean_sheet", {})
    bonus_cfg = cfg.get("bonus", {})
    saves_cfg = cfg.get("saves", {})
    cards_cfg = cfg.get("cards", {})
    set_piece_cfg = cfg.get("set_pieces", {})
    fixture_cfg = cfg.get("fixture", {})
    confidence_cfg = cfg.get("confidence", {})
    empirical = cfg.get("empirical", {})

    xgi = store.xgi_features()
    set_pieces = store.set_piece_features()
    df = store.df

    projections = []
    for idx, row in df.iterrows():
        player_id = int(row.get("player_id", idx))
        web_name = str(row.get("web_name", ""))
        position = str(row.get("position", ""))
        team_id = int(row.get("team_id", 0) or 0)

        minutes_season = float(row.get("minutes", 0) or 0)
        games_played = _games_played(minutes_season)
        fixture_multiplier = _fixture_multiplier(team_id, store, fixture_cfg)

        # Underlying rates per 90
        xg_90 = _per_90(_col(xgi, idx, "xg_raw"), games_played)
        xa_90 = _per_90(_col(xgi, idx, "xa_raw"), games_played)
        xgc_90 = _per_90(_col(xgi, idx, "xgc_raw"), games_played)

        # --- Empirical historical calibration (optional, config-gated) ------
        finishing = empirical.get("finishing", {}) if empirical else {}
        creative = empirical.get("creative", {}) if empirical else {}
        if finishing:
            xg_90 *= float(finishing.get(position, 1.0) or 1.0)
        if creative:
            xa_90 *= float(creative.get(position, 1.0) or 1.0)

        # Previous-season shrinkage for tiny current-season samples.
        prev_blend = empirical.get("prev_season", {}) if empirical else {}
        if prev_blend and games_played < int(prev_blend.get("min_current_games", 3)):
            prev_w = float(prev_blend.get("prev_weight", 0.0) or 0.0)
            prev_xg = float(row.get("hist_prev_xg_per_90", 0) or 0)
            prev_xa = float(row.get("hist_prev_xa_per_90", 0) or 0)
            xg_90 = (1 - prev_w) * xg_90 + prev_w * prev_xg
            xa_90 = (1 - prev_w) * xa_90 + prev_w * prev_xa

        # Empirical team-strength adjustment (active only with hist_team_* cols).
        team_adj = empirical.get("historical_team", {}) if empirical else {}
        if team_adj:
            attack_adj = float(row.get("hist_team_attack_adj", 1.0) or 1.0)
            defense_adj = float(row.get("hist_team_defense_adj", 1.0) or 1.0)
            a_w = float(team_adj.get("attack_weight", 0.0) or 0.0)
            d_w = float(team_adj.get("defense_weight", 0.0) or 0.0)
            xg_90 *= 1 - a_w + a_w * attack_adj
            xa_90 *= 1 - a_w + a_w * attack_adj
            xgc_90 *= 1 - d_w + d_w * defense_adj

        xgc_90 = _team_strength_adjust(xgc_90, row, cs_cfg)

        # Clean-sheet probability (GKP/DEF only)
        if position in ("GKP", "DEF"):
            clean_sheet_prob = _clean_sheet_prob(xgc_90, cs_cfg, empirical)
        else:
            clean_sheet_prob = 0.0

        # Auxiliary point sources
        bps_per_90 = _per_90(float(row.get("bps", 0) or 0), games_played)
        expected_bonus = _expected_bonus(bps_per_90, bonus_cfg, empirical, position)

        saves_per_90 = _per_90(float(row.get("saves", 0) or 0), games_played)
        expected_saves = _expected_saves(saves_per_90, position, saves_cfg)

        yellow_per_90 = _per_90(float(row.get("yellow_cards", 0) or 0), games_played)
        red_per_90 = _per_90(float(row.get("red_cards", 0) or 0), games_played)
        expected_cards = _expected_cards(
            yellow_per_90, red_per_90, cards_cfg,
        )

        set_piece_bonus = _set_piece_bonus(set_pieces, idx, set_piece_cfg)

        # Position-specific scoring values
        pos_vals = position_values.get(position, position_values.get("MID", {}))

        # Sum xPts/90
        xpts_per_90 = (
            xg_90 * fixture_multiplier * pos_vals.get("goal", 0)
            + xa_90 * fixture_multiplier * pos_vals.get("assist", 0)
            + clean_sheet_prob * pos_vals.get("clean_sheet", 0)
            + expected_bonus
            + expected_saves
            + expected_cards  # negative for cards
            + set_piece_bonus
        )
        xpts_per_90 = max(xpts_per_90, 0.0)

        # Data quality + confidence
        data_quality, n_sources = _assess_data_quality(row, xgi, idx)
        confidence = _data_quality_confidence(data_quality, confidence_cfg)

        projections.append(ExpectedPointsProjection(
            player_id=player_id,
            web_name=web_name,
            position=position,
            team_id=team_id,
            xpts_per_90=round(xpts_per_90, 3),
            xg_90=round(xg_90, 3),
            xa_90=round(xa_90, 3),
            xgc_90=round(xgc_90, 3),
            clean_sheet_prob=round(clean_sheet_prob, 3),
            expected_bonus=round(expected_bonus, 3),
            expected_saves=round(expected_saves, 3),
            expected_cards=round(expected_cards, 3),
            set_piece_bonus=round(set_piece_bonus, 3),
            fixture_multiplier=round(fixture_multiplier, 3),
            confidence=round(confidence, 1),
            data_quality=data_quality,
            games_played=games_played,
            contributing_factors={
                "gameweek_id": gameweek_id,
                "xg_90": round(xg_90, 3),
                "xa_90": round(xa_90, 3),
                "clean_sheet_prob": round(clean_sheet_prob, 3),
                "fixture_multiplier": round(fixture_multiplier, 3),
                "set_piece_bonus": round(set_piece_bonus, 3),
                "data_sources": n_sources,
            },
        ))

    projections.sort(key=lambda p: p.player_id)
    return projections


def expected_points_to_dataframe(
    projections: list[ExpectedPointsProjection],
) -> pd.DataFrame:
    """Convert a list of ExpectedPointsProjection to a DataFrame."""
    return pd.DataFrame([vars(p) for p in projections])


def compute_expected_points_version_tag(
    gameweek_id: int,
    config_hash: str,
) -> str:
    """Generate a unique version tag for an xPts/90 projection run."""
    return f"xpts-gw{gameweek_id}-{config_hash[:8]}"


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


def _per_90(value: float, games_played: int) -> float:
    """Scale a season aggregate to a per-90 rate."""
    return value / max(games_played, 1)


def _fixture_multiplier(
    team_id: int,
    store,
    fixture_cfg: dict,
) -> float:
    """Difficulty → scoring multiplier. Easier fixtures → higher multiplier."""
    base = fixture_cfg.get("base_difficulty", 3)
    floor = fixture_cfg.get("floor_multiplier", 0.5)
    fixtures = store.fixture_map.get(team_id, [])
    difficulty = fixtures[0].get("difficulty", base) if fixtures else base
    multiplier = (5 - difficulty) / 4.0
    return max(multiplier, floor)


def _team_strength_adjust(xgc_90: float, row: pd.Series, cs_cfg: dict) -> float:
    """Blend conceded goals toward the league average using team strength.

    A defence stronger than average (strength > anchor) concedes less than its
    raw xGC/90 suggests, and vice versa. Falls back to raw xGC when strength
    data is unavailable.
    """
    anchor = float(cs_cfg.get("team_strength_anchor", 1000) or 1000)
    try:
        team_strength = float(row.get("team_strength_raw", 0) or 0)
    except (TypeError, ValueError):
        team_strength = 0.0
    if team_strength <= 0:
        return xgc_90
    return xgc_90 * (anchor / team_strength)


def _clean_sheet_prob(xgc_90: float, cs_cfg: dict, empirical: dict | None = None) -> float:
    """Estimate clean-sheet probability from xGC/90.

    Empirical (historical) model, when configured:
        cs_prob = clip(intercept + slope * xgc_90, 0, max_clean_sheet_prob)
    otherwise the default anchored closed form (production behaviour).
    """
    max_prob = float(cs_cfg.get("max_clean_sheet_prob", 0.6) or 0.6)
    min_prob = float(cs_cfg.get("min_clean_sheet_prob", 0.0) or 0.0)
    cs_emp = empirical.get("clean_sheet", {}) if empirical else {}
    if cs_emp:
        model = cs_emp.get("GKP", cs_emp.get("DEF")) or {}
        if model:
            prob = float(model.get("intercept", 0.0) or 0.0) + float(model.get("slope", 0.0) or 0.0) * xgc_90
            return float(np.clip(prob, min_prob, max_prob))

    league_avg = float(cs_cfg.get("league_avg_xgc_per_90", 1.4) or 1.4)
    multiplier = float(cs_cfg.get("cs_rate_multiplier", 0.5) or 0.5)
    if league_avg <= 0:
        return 0.25
    prob = (league_avg - xgc_90) / league_avg * multiplier
    return float(np.clip(prob, min_prob, max_prob))


def _expected_bonus(
    bps_per_90: float,
    bonus_cfg: dict,
    empirical: dict | None = None,
    position: str | None = None,
) -> float:
    """Convert expected BPS/90 into expected bonus points.

    Empirical (historical) model, when configured for the position:
        expected_bonus = clip(intercept + slope * bps_per_90, 0, max_bonus_points)
    otherwise the default divisor model (production behaviour).
    """
    cap = float(bonus_cfg.get("max_bonus_points", 3) or 3)
    bonus_emp = empirical.get("bonus", {}) if empirical else {}
    if position and bonus_emp:
        model = bonus_emp.get(position) or {}
        if model and "slope" in model:
            prob = float(model.get("intercept", 0.0) or 0.0) + float(model.get("slope", 0.0) or 0.0) * bps_per_90
            return float(np.clip(prob, 0.0, cap))

    divisor = float(bonus_cfg.get("bps_per_bonus_point", 160) or 160)
    if divisor <= 0:
        return 0.0
    return float(np.clip(bps_per_90 / divisor, 0.0, cap))


def _expected_saves(saves_per_90: float, position: str, saves_cfg: dict) -> float:
    """Expected save points (GKP only): 1 point per 2 saves."""
    if position != "GKP":
        return 0.0
    divisor = float(saves_cfg.get("saves_per_bonus_point", 2.0) or 2.0)
    cap = float(saves_cfg.get("max_saves_per_90", 6.0) or 6.0)
    if divisor <= 0:
        return 0.0
    return float(np.clip(saves_per_90 / divisor, 0.0, cap))


def _expected_cards(
    yellow_per_90: float,
    red_per_90: float,
    cards_cfg: dict,
) -> float:
    """Expected card deductions (negative points)."""
    yellow_weight = float(cards_cfg.get("yellow_card_rate_weight", 1.0) or 1.0)
    red_weight = float(cards_cfg.get("red_card_rate_weight", 1.0) or 1.0)
    return -(yellow_per_90 * yellow_weight * 1.0 + red_per_90 * red_weight * 3.0)


def _set_piece_bonus(
    set_pieces: pd.DataFrame,
    idx,
    set_piece_cfg: dict,
) -> float:
    """Bonus xPts/90 for designated primary set-piece takers."""
    bonus = 0.0
    if _col(set_pieces, idx, "is_penalty_taker") == 1.0:
        bonus += float(set_piece_cfg.get("penalty_taker_bonus", 0.25) or 0.25)
    if _col(set_pieces, idx, "is_fk_taker") == 1.0:
        bonus += float(set_piece_cfg.get("fk_taker_bonus", 0.05) or 0.05)
    if _col(set_pieces, idx, "is_corner_taker") == 1.0:
        bonus += float(set_piece_cfg.get("corner_taker_bonus", 0.05) or 0.05)
    return bonus


def _assess_data_quality(
    row: pd.Series,
    xgi: pd.DataFrame,
    idx,
) -> tuple[str, int]:
    """Count available data sources and map to a quality tier."""
    sources = 0
    if float(row.get("minutes", 0) or 0) > 0:
        sources += 1
    if _col(xgi, idx, "xgi_raw") > 0:
        sources += 1
    if float(row.get("bps", 0) or 0) > 0:
        sources += 1
    if float(row.get("form", 0) or 0) > 0:
        sources += 1
    if str(row.get("status", "a") or "a") == "a":
        sources += 1

    if sources >= 4:
        return "good", sources
    if sources >= 3:
        return "moderate", sources
    if sources >= 1:
        return "limited", sources
    return "none", sources


def _data_quality_confidence(data_quality: str, confidence_cfg: dict) -> float:
    """Map a data-quality tier to a 0-100 confidence score."""
    return float(confidence_cfg.get(data_quality, 40) or 40)


def _default_position_values() -> dict:
    return {
        "GKP": {"goal": 10, "assist": 3, "clean_sheet": 1, "yellow_card": -1, "red_card": -3},
        "DEF": {"goal": 6, "assist": 3, "clean_sheet": 4, "yellow_card": -1, "red_card": -3},
        "MID": {"goal": 5, "assist": 3, "clean_sheet": 1, "yellow_card": -1, "red_card": -3},
        "FWD": {"goal": 4, "assist": 3, "clean_sheet": 0, "yellow_card": -1, "red_card": -3},
    }
