"""Game Theory Engine — architecture and interfaces ONLY (Phase 7).

The strategic objective is *Expected League Position Gain*: choose captain,
transfers and chips to maximise the expected gain in league position, not raw
points. This module defines the interfaces and data shapes the future engine
will implement. There is deliberately no scoring logic yet.

Design sketch (see docs/league_intelligence.md for the full write-up):
  - Inputs: league standing, gap to rivals ahead/behind, effective ownership
    of candidates, captaincy overlap with rivals, differential opportunities,
    remaining fixtures, chip inventory, risk tolerance.
  - Output: per-move ``ExpectedLeaguePositionGain`` with a risk profile, so the
    recommendation engine can pick the move with the best risk-adjusted gain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from utils.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class PositionGainInput:
    """Everything a game-theory move needs to estimate position gain."""

    gameweek_id: int
    league_position: int
    n_teams: int
    points_to_rival_ahead: float
    points_ahead_of_rival_behind: float
    n_gameweeks_remaining: int
    risk_tolerance: str = "balanced"  # conservative | balanced | aggressive
    captain_overlap_with_rivals: float = 0.0  # fraction of rivals on your captain
    chip_inventory: dict = field(default_factory=dict)  # e.g. {"wc": True, "tc": True}
    fixtures_strength_remaining: float = 0.0  # average opponent strength index


@dataclass
class ExpectedLeaguePositionGain:
    """Result shape for one candidate move (captain/transfer/chip)."""

    move_type: str          # "captain" | "transfer_in" | "chip"
    player_id: int | None
    expected_position_gain: float  # +x.xx places, or negative for loss
    variance: float         # spread of the gain estimate
    risk_level: str         # low | medium | high
    rationale: str = ""
    detail: dict = field(default_factory=dict)


@runtime_checkable
class GameTheoryEngine(Protocol):
    """Protocol — defines the interface the future engine must meet.

    The v1 League Intelligence Layer ships this interface only; no concrete
    implementation exists yet. Activating requires a validated differential
    scoring model plus at least one mini-league gameweek of data.
    """

    def estimate(self, inputs: PositionGainInput) -> list[ExpectedLeaguePositionGain]:
        """Return per-move expected position gains, best move first."""
        ...


def game_theory_enabled(config: dict | None = None) -> bool:
    """Whether the game-theory engine is enabled (false in v1)."""
    if config is None:
        config = load_config("league_intelligence")
    return bool(config.get("game_theory", {}).get("enabled", False))


class _UnimplementedGameTheoryEngine:
    """Guards every game-theory entry point until a real engine ships."""

    def estimate(self, inputs: PositionGainInput) -> list[ExpectedLeaguePositionGain]:
        logger.warning(
            "Game Theory Engine is architecture-only in v1 — no estimate available."
        )
        return []


def get_game_theory_engine() -> GameTheoryEngine:
    """Return the active game-theory engine.

    Always returns the unimplemented guard in v1. A future implementation swaps
    in here, keeping the rest of the layer unchanged.
    """
    return _UnimplementedGameTheoryEngine()
