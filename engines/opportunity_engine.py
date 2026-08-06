"""Opportunity Engine — identifies undervalued players and transfer opportunities.

Owns:
  - Undervalued player detection (projected points vs price)
  - Transfer opportunity scoring
  - Fixture swing exploitation
  - Differential identification

Reads from: FeatureStore, Projection Engine, Market Intelligence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TransferOpportunity:
    """A recommended transfer opportunity."""

    player_in_id: int
    player_in_name: str
    player_in_position: str
    player_in_price: float

    player_out_id: int
    player_out_name: str
    player_out_position: str
    player_out_price: float

    # Value metrics
    projected_points_gain: float  # over next N GWs
    cost_efficiency: float  # points gained per 0.1m price
    fixture_advantage: float  # fixture score difference

    # Confidence
    confidence: float  # 0-100
    opportunity_type: str  # "value", "fixture", "form", "differential"

    # Metadata
    reasoning: list[str] = field(default_factory=list)


@dataclass
class UndervaluedPlayer:
    """A player identified as undervalued by the projection model."""

    player_id: int
    web_name: str
    position: str
    team_id: int
    price: float

    # Value metrics
    projected_points_1gw: float
    projected_points_3gw: float
    points_per_million: float
    value_rank: int  # rank among all players in same position

    # Why undervalued
    undervaluation_reasons: list[str]
    market_signal: str  # "buying", "selling", "stable"

    # Score
    opportunity_score: float  # 0-100 composite


def find_undervalued_players(
    store,
    projections: list,
    market_signals: list | None = None,
) -> list[UndervaluedPlayer]:
    """Find players whose projected points exceed their price.

    Parameters
    ----------
    store : FeatureStore
        Feature store with player data.
    projections : list[PlayerProjection]
        Projected points for all players.
    market_signals : list[MarketSignal], optional
        Market signals for ownership/transfer context.

    Returns
    -------
    list[UndervaluedPlayer]
        Undervalued players sorted by opportunity score.
    """
    proj_map = {p.player_id: p for p in projections}
    market_map = {}
    if market_signals:
        market_map = {s.player_id: s for s in market_signals}

    df = store.df
    candidates = []

    for _, row in df.iterrows():
        player_id = int(row.get("player_id", 0))
        proj = proj_map.get(player_id)
        if proj is None:
            continue

        price = float(row.get("price", 0) or 0)
        if price <= 0:
            continue

        # Compute value metrics
        ppm_1gw = proj.projected_points / price if price > 0 else 0

        # 3GW projection (approximate)
        (proj.projected_points * 3) / price if price > 0 else 0

        # Check for reasons player might be undervalued
        reasons = []
        market_signal = "stable"

        # Low ownership = potential differential
        selected = float(row.get("selected_by_percent", 0) or 0)
        if selected < 5:
            reasons.append("Low ownership differential")

        # Good xGI relative to price
        xgi = float(row.get("expected_goal_involvements", 0) or 0)
        if xgi > 0 and price < 7.0:
            reasons.append(f"High xGI ({xgi:.1f}) for price ({price:.1f}m)")

        # Easy upcoming fixtures
        team_id = int(row.get("team_id", 0) or 0)
        fixtures = store.fixture_map.get(team_id, [])
        if fixtures:
            avg_diff = np.mean([f["difficulty"] for f in fixtures[:3]])
            if avg_diff <= 2.5:
                reasons.append(f"Easy fixtures (avg {avg_diff:.1f} difficulty)")

        # Positive form
        form = float(row.get("form", 0) or 0)
        if form >= 5:
            reasons.append(f"Strong form ({form:.1f})")

        # Market signal
        if player_id in market_map:
            ms = market_map[player_id]
            market_signal = ms.transfer_direction
            if ms.sentiment_score > 0.3:
                reasons.append("Positive market sentiment")

        # Status check
        status = str(row.get("status", "a") or "a")
        if status != "a":
            continue  # skip unavailable players

        # Compute opportunity score
        score = _compute_opportunity_score(
            ppm_1gw=ppm_1gw,
            form=form,
            n_reasons=len(reasons),
            fixture_avg=np.mean([f["difficulty"] for f in fixtures[:3]]) if fixtures else 3,
            selected=selected,
        )

        candidates.append(UndervaluedPlayer(
            player_id=player_id,
            web_name=str(row.get("web_name", "")),
            position=str(row.get("position", "")),
            team_id=team_id,
            price=price,
            projected_points_1gw=round(proj.projected_points, 2),
            projected_points_3gw=round(proj.projected_points * 3, 2),
            points_per_million=round(ppm_1gw, 2),
            value_rank=0,  # filled below
            undervaluation_reasons=reasons,
            market_signal=market_signal,
            opportunity_score=round(score, 1),
        ))

    # Rank by position
    _assign_value_ranks(candidates)

    # Sort by opportunity score
    candidates.sort(key=lambda c: c.opportunity_score, reverse=True)

    return candidates


def find_transfer_opportunities(
    store,
    projections: list,
    current_squad: list[int] | None = None,
    budget: float = 0.0,
    transfer_count: int = 1,
) -> list[TransferOpportunity]:
    """Find optimal transfer opportunities for the current squad.

    Parameters
    ----------
    store : FeatureStore
        Feature store.
    projections : list[PlayerProjection]
        Projections for all players.
    current_squad : list[int], optional
        List of player_ids currently in the squad.
    budget : float
        Available budget in millions.
    transfer_count : int
        Number of transfers to recommend.

    Returns
    -------
    list[TransferOpportunity]
        Top transfer opportunities, sorted by projected gain.
    """
    if current_squad is None:
        return []

    proj_map = {p.player_id: p for p in projections}
    df = store.df

    opportunities = []

    for out_id in current_squad:
        out_proj = proj_map.get(out_id)
        if out_proj is None:
            continue

        out_row = df[df["player_id"] == out_id]
        if out_row.empty:
            continue
        out_row = out_row.iloc[0]

        # Find better alternatives in same position
        same_pos = df[
            (df["position"] == out_proj.position)
            & (~df["player_id"].isin(current_squad))
            & (df["status"] == "a")
        ]

        for _, in_row in same_pos.iterrows():
            in_id = int(in_row.get("player_id", 0))
            in_proj = proj_map.get(in_id)
            if in_proj is None:
                continue

            in_price = float(in_row.get("price", 0) or 0)
            out_price = float(out_row.get("price", 0) or 0)
            price_diff = in_price - out_price

            # Budget check
            if price_diff > budget + 0.1:  # small tolerance
                continue

            # Points gain
            gain = in_proj.projected_points - out_proj.projected_points
            if gain <= 0:
                continue

            # Fixture advantage
            in_team = int(in_row.get("team_id", 0) or 0)
            out_team = int(out_row.get("team_id", 0) or 0)
            in_fixtures = store.fixture_map.get(in_team, [])
            out_fixtures = store.fixture_map.get(out_team, [])
            in_avg = np.mean([f["difficulty"] for f in in_fixtures[:3]]) if in_fixtures else 3
            out_avg = np.mean([f["difficulty"] for f in out_fixtures[:3]]) if out_fixtures else 3
            fixture_adv = out_avg - in_avg  # positive = easier fixtures

            # Cost efficiency
            cost_eff = gain / max(price_diff, 0.1)

            # Confidence
            confidence = min(50 + gain * 5 + fixture_adv * 5, 95)

            # Reasoning
            reasons = []
            if gain > 2:
                reasons.append(f"Projecting {gain:.1f} more points")
            if fixture_adv > 0.5:
                reasons.append("Easier upcoming fixtures")
            if cost_eff > 5:
                reasons.append("High cost efficiency")

            # Opportunity type
            if fixture_adv > 1:
                opp_type = "fixture"
            elif cost_eff > 10:
                opp_type = "value"
            elif in_proj.projected_points > 5:
                opp_type = "form"
            else:
                opp_type = "value"

            opportunities.append(TransferOpportunity(
                player_in_id=in_id,
                player_in_name=str(in_row.get("web_name", "")),
                player_in_position=str(in_row.get("position", "")),
                player_in_price=in_price,
                player_out_id=out_id,
                player_out_name=str(out_row.get("web_name", "")),
                player_out_position=str(out_row.get("position", "")),
                player_out_price=out_price,
                projected_points_gain=round(gain, 2),
                cost_efficiency=round(cost_eff, 2),
                fixture_advantage=round(fixture_adv, 2),
                confidence=round(confidence, 1),
                opportunity_type=opp_type,
                reasoning=reasons,
            ))

    # Sort by gain
    opportunities.sort(key=lambda o: o.projected_points_gain, reverse=True)

    return opportunities[:20]  # top 20


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_opportunity_score(
    ppm_1gw: float,
    form: float,
    n_reasons: int,
    fixture_avg: float,
    selected: float,
) -> float:
    """Compute a composite opportunity score."""
    score = 0.0

    # Points per million (0-40)
    score += min(ppm_1gw / 10, 1.0) * 40

    # Form (0-20)
    score += min(form / 8, 1.0) * 20

    # Reasons bonus (0-15)
    score += min(n_reasons / 4, 1.0) * 15

    # Fixture quality (0-15)
    fixture_score = (5 - fixture_avg) / 4
    score += max(fixture_score, 0) * 15

    # Differential bonus (0-10)
    if selected < 5:
        score += 10
    elif selected < 10:
        score += 5

    return min(score, 100)


def _assign_value_ranks(candidates: list[UndervaluedPlayer]) -> None:
    """Assign value rank within each position."""
    by_position = {}
    for c in candidates:
        by_position.setdefault(c.position, []).append(c)

    for players in by_position.values():
        players.sort(key=lambda p: p.points_per_million, reverse=True)
        for i, p in enumerate(players):
            p.value_rank = i + 1
