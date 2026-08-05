"""Effective Ownership Engine — reusable ownership/exposure service.

Computes the community "effective ownership" figure and exposes the same
mechanism for league and rival contexts::

    EO% = selected_by% + captained% + triple_captained%

(the sum of teams owning, captaining or triple-captaining a player, expressed
as a percentage). This matches the convention used by fpl community tools
(e.g. fantasyfootballpundit's live EO table).

Pure functions + a small class wrapper so it can be used standalone or from the
orchestrator. Never touches projections; reads ownership inputs only.
"""

from __future__ import annotations

import logging

from services.league_intelligence.models import PlayerExposure
from utils.config import load_config

logger = logging.getLogger(__name__)


def compute_effective_ownership(
    selected_pct: float,
    captained_pct: float = 0.0,
    triple_captained_pct: float = 0.0,
) -> float:
    """EO for a player given the three ownership components.

    All inputs are percentages (e.g. 18.5 means 18.5% of teams). The triple
    captain chip counts once, like captaincy.
    """
    return round(float(selected_pct) + float(captained_pct) + float(triple_captained_pct), 2)


def classify_exposure(eo: float, config: dict | None = None) -> str:
    """Map an EO% to an exposure tier: low | moderate | high | unknown."""
    if config is None:
        config = load_config("league_intelligence")
    tiers = config.get("effective_ownership", {}).get("exposure_tiers", {})
    low = float(tiers.get("low", 8.0))
    moderate = float(tiers.get("moderate", 15.0))
    high = float(tiers.get("high", 25.0))
    if eo <= low:
        return "low"
    if eo <= moderate:
        return "moderate"
    if eo <= high:
        return "high"
    return "high"


def league_ownership(squads: list[set[int]], player_id: int) -> float:
    """% of league squads that own ``player_id`` (0.0 when no squads)."""
    if not squads:
        return 0.0
    owned = sum(1 for squad in squads if player_id in squad)
    return round(100.0 * owned / len(squads), 2)


def rival_ownership(rival_squads: list[set[int]], player_id: int) -> float:
    """% of tracked rival squads owning ``player_id`` (0.0 when none)."""
    if not rival_squads:
        return 0.0
    owned = sum(1 for squad in rival_squads if player_id in squad)
    return round(100.0 * owned / len(rival_squads), 2)


class EffectiveOwnershipEngine:
    """Builds PlayerExposure rows for a set of player IDs.

    All providers are optional: global ownership is the baseline; league/rival
    figures are only added when squads are supplied. No data → a valid
    exposure with unknown tier rather than an error.
    """

    def __init__(self, config: dict | None = None):
        self._config = config or load_config("league_intelligence")

    def exposure(
        self,
        player_id: int,
        web_name: str,
        position: str,
        global_ownership: float = 0.0,
        captained_pct: float = 0.0,
        triple_captained_pct: float = 0.0,
        top10k_ownership: float | None = None,
        league_squads: list[set[int]] | None = None,
        rival_squads: list[set[int]] | None = None,
        source: str = "feature_store",
    ) -> PlayerExposure:
        """Compute one player's exposure across available contexts."""
        eo = compute_effective_ownership(global_ownership, captained_pct, triple_captained_pct)
        exposure = PlayerExposure(
            player_id=player_id,
            web_name=web_name,
            position=position,
            global_ownership=round(float(global_ownership), 2),
            captain_pct=round(float(captained_pct), 2),
            top10k_ownership=top10k_ownership,
            effective_ownership=eo,
            exposure_tier=classify_exposure(eo, self._config),
            source=source,
        )
        if league_squads:
            exposure.league_ownership = league_ownership(league_squads, player_id)
        if rival_squads:
            exposure.rival_ownership = rival_ownership(rival_squads, player_id)
        return exposure
