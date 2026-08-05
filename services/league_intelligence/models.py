"""League Intelligence — domain models.

Pure dataclasses (no streamlit, no DB). All inputs are injected; nothing here
touches the network or mutates prediction objects.

Design contract (see docs/league_intelligence.md):
  - League context ADAPTS recommendations only. It never modifies projection
    values — every recommendation carries the untouched ``xpts`` value.
  - No hidden state: each run produces a self-contained report.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlayerExposure:
    """Ownership/exposure snapshot for one player across contexts.

    Global ownership is the only one guaranteed to be present; league, rival
    and captain figures are populated only when the relevant provider has data.
    """

    player_id: int
    web_name: str
    position: str
    global_ownership: float = 0.0          # % of all FPL teams
    league_ownership: float | None = None  # % of mini-league squads
    rival_ownership: float | None = None   # % of tracked rival squads
    captain_pct: float = 0.0               # % of teams captaining (poll)
    top10k_ownership: float | None = None  # % among top 10k (community)
    effective_ownership: float = 0.0       # EO = selected + captained + TC
    exposure_tier: str = "unknown"         # low | moderate | high | unknown
    source: str = ""                       # which provider populated this

    @property
    def is_differential(self) -> bool:
        return self.exposure_tier == "low"


@dataclass
class DifferentialScore:
    """Config-weighted strategic score for a transfer/differential candidate.

    ``xpts`` is the projection engine's value, carried through unchanged —
    the League Intelligence Layer never re-scores or alters predictions.
    """

    player_id: int
    web_name: str
    position: str
    xpts: float = 0.0
    expected_minutes: float = 0.0
    global_ownership: float = 0.0
    transfer_velocity: float = 0.0
    price_movement: float = 0.0
    fixture_attractiveness: float = 0.0
    score: float = 0.0
    is_differential: bool = False
    components: dict = field(default_factory=dict)  # normalised inputs
    config_version: str = ""


@dataclass
class StrategicRecommendation:
    """A league-aware suggestion to hand to the recommendation engine.

    type is one of: differential_pick | captaincy_hedge | threat_response |
    rival_edge | league_hold.

    ``xpts`` is the untouched projection value; ``strategy_score`` is the
    league-aware signal computed on top of it.
    """

    type: str
    player_id: int
    web_name: str
    position: str
    xpts: float = 0.0
    strategy_score: float = 0.0
    confidence: float = 0.0
    reasoning: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class MiniLeagueAnalysis:
    """Analytical-only view of the user's mini-league (Phase 3).

    Produces no recommendations — only facts about overlap, differentials,
    similarity and threats.
    """

    gameweek_id: int
    league_id: int | None = None
    n_teams: int = 0
    position: int | None = None
    common_players: list = field(default_factory=list)
    league_differentials: list = field(default_factory=list)
    captain_overlap: dict = field(default_factory=dict)
    ownership_overlap: dict = field(default_factory=dict)
    risk_profile: dict = field(default_factory=dict)
    squad_similarity: dict = field(default_factory=dict)
    threats: list = field(default_factory=list)
    notes: list = field(default_factory=list)


@dataclass
class RivalAnalysis:
    """Analytical-only comparison against specific rivals (Phase 4).

    Pure comparison — never changes the user's team or the projections.
    """

    gameweek_id: int
    rival_ids: list = field(default_factory=list)
    rival_names: dict = field(default_factory=dict)
    squad_comparison: list = field(default_factory=list)
    captain_comparison: dict = field(default_factory=dict)
    differential_opportunities: list = field(default_factory=list)
    transfer_divergence: list = field(default_factory=list)
    weak_positions: list = field(default_factory=list)
    xpts_comparison: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


@dataclass
class LeagueIntelligenceReport:
    """Output of a single run of the League Intelligence Layer.

    Assembled by ``engine.run_league_intelligence``. Everything downstream of
    this object (recommendation engine) may consume it; nothing upstream
    (prediction layer) is ever changed.
    """

    gameweek_id: int
    team_id: int
    config_version: str = ""
    computed_at: str = ""
    exposures: list = field(default_factory=list)          # list[PlayerExposure]
    differentials: list = field(default_factory=list)      # list[DifferentialScore]
    mini_league: MiniLeagueAnalysis | None = None
    rivals: RivalAnalysis | None = None
    recommendations: list = field(default_factory=list)    # list[StrategicRecommendation]
    inputs: dict = field(default_factory=dict)             # what was (not) available
    notes: list = field(default_factory=list)

    def summary(self) -> dict:
        """Short dict for logs / UI headers."""
        return {
            "gameweek_id": self.gameweek_id,
            "team_id": self.team_id,
            "n_exposures": len(self.exposures),
            "n_differentials": len(self.differentials),
            "n_recommendations": len(self.recommendations),
            "league_analyzed": self.mini_league is not None,
            "rivals_analyzed": self.rivals is not None,
            "config_version": self.config_version,
        }
