"""Bookmaker Engine — integrates betting odds data for fixture predictions.

Owns:
  - Odds fetching and parsing (via Odds API)
  - Goal expectancy from bookmaker markets
  - Clean sheet probability from bookmaker markets
  - Graceful degradation when odds unavailable

Reads from: FPL API (indirectly via odds service)
Config: config/bookmaker/bookmaker_v1.yaml
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class FixtureOdds:
    """Bookmaker odds for a single fixture."""

    fixture_id: int
    gameweek: int
    home_team_id: int
    away_team_id: int

    # Goal expectancy
    home_goals_expected: float  # bookmaker-implied home goals
    away_goals_expected: float  # bookmaker-implied away goals
    total_goals_expected: float  # home + away

    # Clean sheet probability
    home_clean_sheet_prob: float
    away_clean_sheet_prob: float

    # Match outcome probabilities
    home_win_prob: float
    draw_prob: float
    away_win_prob: float

    # Source metadata
    bookmaker: str
    odds_timestamp: str


@dataclass
class BookmakerProjection:
    """Bookmaker-enhanced projection for a single player."""

    player_id: int
    web_name: str

    # Adjustments from bookmaker data
    goals_boost: float  # adjustment to goals projection
    assists_boost: float  # adjustment to assists projection
    clean_sheet_boost: float  # adjustment to clean sheet projection

    # Overall impact
    points_boost: float  # total points adjustment from bookmaker
    confidence_boost: float  # adjustment to confidence (bookmaker = extra signal)

    # Data availability
    odds_available: bool
    bookmaker_used: str


def project_from_odds(
    store,
    projections: list,
    odds_data: list[FixtureOdds] | None = None,
) -> list[BookmakerProjection]:
    """Enhance projections with bookmaker odds data.

    Parameters
    ----------
    store : FeatureStore
        Feature store with player data.
    projections : list[PlayerProjection]
        Base projections from the Projection Engine.
    odds_data : list[FixtureOdds], optional
        Bookmaker odds. If None or empty, returns zero-boost projections.

    Returns
    -------
    list[BookmakerProjection]
        One per player. Apply boosts to base projections.
    """
    cfg = load_config("bookmaker")
    name_mapping = cfg.get("team_name_mapping", {})

    if not odds_data:
        return _no_odds_projections(projections)

    # Build odds lookup by team_id
    odds_by_team = _build_odds_lookup(odds_data, name_mapping)

    results = []
    for proj in projections:
        result = _compute_player_odds_boost(proj, store, odds_by_team)
        results.append(result)

    return results


def apply_bookmaker_adjustments(
    projections: list,
    bookmaker_projections: list[BookmakerProjection],
) -> list:
    """Apply bookmaker adjustments to base projections."""
    bm_map = {bp.player_id: bp for bp in bookmaker_projections}

    for proj in projections:
        bm = bm_map.get(proj.player_id)
        if bm is None or not bm.odds_available:
            continue

        # Apply boosts
        proj.goals_proj = max(0, proj.goals_proj + bm.goals_boost)
        proj.assists_proj = max(0, proj.assists_proj + bm.assists_boost)
        proj.clean_sheet_proj = max(0, proj.clean_sheet_proj + bm.clean_sheet_boost)

        # Recalculate total
        # (simplified: just add the net boost to projected_points)
        proj.projected_points = max(0, proj.projected_points + bm.points_boost)

    return projections


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_odds_lookup(
    odds_data: list[FixtureOdds],
    name_mapping: dict,
) -> dict[int, FixtureOdds]:
    """Build team_id → FixtureOdds lookup."""
    lookup = {}
    for odds in odds_data:
        lookup[odds.home_team_id] = odds
        lookup[odds.away_team_id] = odds
    return lookup


def _compute_player_odds_boost(
    proj,
    store,
    odds_by_team: dict,
) -> BookmakerProjection:
    """Compute bookmaker adjustments for a single player."""
    df = store.df
    player_row = df[df["player_id"] == proj.player_id]
    if player_row.empty:
        return _empty_bookmaker(proj)

    row = player_row.iloc[0]
    team_id = int(row.get("team_id", 0) or 0)
    position = str(row.get("position", ""))

    odds = odds_by_team.get(team_id)
    if odds is None:
        return _empty_bookmaker(proj)

    # Determine if player's team is home or away
    is_home = odds.home_team_id == team_id
    team_goals_exp = odds.home_goals_expected if is_home else odds.away_goals_expected
    cs_prob = odds.home_clean_sheet_prob if is_home else odds.away_clean_sheet_prob

    # Goals boost: bookmaker expected goals vs xG-based projection
    xg_per_game = float(row.get("expected_goals", 0) or 0) / max(1, float(row.get("minutes", 90) or 90) / 90)
    goals_diff = team_goals_exp - xg_per_game
    goals_boost = goals_diff * 0.3  # partial adjustment

    # Assists boost: rough 30% of goal boost
    assists_boost = goals_boost * 0.3

    # Clean sheet boost: bookmaker CS prob vs base CS projection
    cs_boost = (cs_prob - 0.3) * 2  # relative to baseline 30% CS

    # Points boost by position
    position_weights = {"GKP": 10, "DEF": 6, "MID": 5, "FWD": 4}
    pos_weight = position_weights.get(position, 5)

    points_boost = (
        goals_boost * pos_weight
        + assists_boost * 3
        + cs_boost
    )

    # Confidence boost: bookmaker data = extra validation
    confidence_boost = 5.0 if odds.odds_available else 0.0

    return BookmakerProjection(
        player_id=proj.player_id,
        web_name=proj.web_name,
        goals_boost=round(goals_boost, 3),
        assists_boost=round(assists_boost, 3),
        clean_sheet_boost=round(cs_boost, 3),
        points_boost=round(points_boost, 2),
        confidence_boost=round(confidence_boost, 1),
        odds_available=True,
        bookmaker_used=odds.bookmaker,
    )


def _no_odds_projections(
    projections: list,
) -> list[BookmakerProjection]:
    """Return zero-boost projections when no odds data is available."""
    return [
        BookmakerProjection(
            player_id=proj.player_id,
            web_name=proj.web_name,
            goals_boost=0.0,
            assists_boost=0.0,
            clean_sheet_boost=0.0,
            points_boost=0.0,
            confidence_boost=0.0,
            odds_available=False,
            bookmaker_used="none",
        )
        for proj in projections
    ]


def _empty_bookmaker(proj) -> BookmakerProjection:
    """Return empty bookmaker projection for missing players."""
    return BookmakerProjection(
        player_id=proj.player_id,
        web_name=proj.web_name,
        goals_boost=0.0,
        assists_boost=0.0,
        clean_sheet_boost=0.0,
        points_boost=0.0,
        confidence_boost=0.0,
        odds_available=False,
        bookmaker_used="none",
    )
