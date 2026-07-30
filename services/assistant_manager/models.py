"""Data models for the Assistant Manager engine.

Every recommendation type is a plain dataclass.  No ORM, no Streamlit, no
API calls — pure data that the engine produces and the UI consumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Squad Evaluation (Section 1)
# ---------------------------------------------------------------------------

@dataclass
class PlayerAssessment:
    """Evaluation of a single player in the squad."""
    player_id: int
    web_name: str
    team_id: int
    team_short: str
    position: str
    price: float
    total_points: int
    form: float
    xgi_per_90: float
    value_score: float
    minutes_played: int
    minutes_fraction: float
    status: str
    news: str
    selected_by_percent: float
    cost_change_start: int

    # Fixture analysis
    next_3_fixtures: list[FixtureInfo] = field(default_factory=list)
    next_6_fixtures: list[FixtureInfo] = field(default_factory=list)
    avg_difficulty_3gw: float = 0.0
    avg_difficulty_6gw: float = 0.0

    # Classification flags
    strength_flags: list[str] = field(default_factory=list)
    weakness_flags: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    opportunity_flags: list[str] = field(default_factory=list)

    # Overall rating for this player 0–100
    squad_rating: float = 0.0


@dataclass
class FixtureInfo:
    """Single fixture for a player's upcoming schedule."""
    gameweek: int
    opponent: str
    opponent_short: str
    home: bool
    difficulty: int  # 1–5
    difficulty_label: str = ""  # "Very Easy", "Easy", "Neutral", "Hard", "Very Hard"


@dataclass
class SquadEvaluation:
    """Full evaluation of the current squad."""
    overall_rating: float
    total_value: float
    bank: float
    free_transfers: int
    saved_transfers: int

    players: list[PlayerAssessment] = field(default_factory=list)

    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    injuries: list[str] = field(default_factory=list)
    rotation_risks: list[str] = field(default_factory=list)
    poor_fixtures: list[str] = field(default_factory=list)
    excellent_fixtures: list[str] = field(default_factory=list)
    price_risers: list[str] = field(default_factory=list)
    price_fallers: list[str] = field(default_factory=list)
    underperformers: list[str] = field(default_factory=list)
    emerging_bargains: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Transfer Engine (Section 2)
# ---------------------------------------------------------------------------

@dataclass
class TransferRecommendation:
    """A single transfer recommendation."""
    player_out: PlayerAssessment
    player_in: PlayerAssessment
    price_difference: float
    expected_points_gained: float
    value_score_difference: float
    fixture_improvement: float
    minutes_projection: float
    ownership_difference: float
    risk_level: str  # "Low", "Medium", "High"
    confidence_rating: float  # 0–100
    rank: int = 0
    reasoning: str = ""


@dataclass
class TransferPlan:
    """Complete transfer plan for the gameweek."""
    action: str  # "hold", "free_transfer", "hit_4", "hit_8", "wildcard", "free_hit"
    transfers: list[TransferRecommendation] = field(default_factory=list)
    total_expected_gain: float = 0.0
    total_hit_cost: int = 0
    net_expected_gain: float = 0.0
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Chip Strategy (Section 4)
# ---------------------------------------------------------------------------

@dataclass
class ChipRecommendation:
    """Recommendation for a specific chip."""
    chip_name: str  # "wildcard", "free_hit", "bboost", "3xc"
    chip_label: str  # "Wildcard", "Free Hit", "Bench Boost", "Triple Captain"
    should_play: bool
    confidence: float  # 0–100
    best_gameweek: int | None = None
    projected_gain: float = 0.0
    reasoning: str = ""
    available: bool = True
    used: bool = False


# ---------------------------------------------------------------------------
# Future Planning (Section 5)
# ---------------------------------------------------------------------------

@dataclass
class FixtureWindow:
    """Fixture analysis for a specific gameweek window."""
    gameweek_start: int
    gameweek_end: int
    avg_difficulty: float
    easy_fixtures: int
    hard_fixtures: int
    fixture_list: list[FixtureInfo] = field(default_factory=list)


@dataclass
class FuturePlan:
    """Forward-looking analysis for the squad."""
    window_3gw: FixtureWindow | None = None
    window_6gw: FixtureWindow | None = None
    window_10gw: FixtureWindow | None = None

    fixture_swings: list[str] = field(default_factory=list)
    upcoming_difficult_runs: list[str] = field(default_factory=list)
    upcoming_easy_runs: list[str] = field(default_factory=list)
    price_rise_targets: list[str] = field(default_factory=list)
    price_drop_warnings: list[str] = field(default_factory=list)
    captain_opportunities: list[str] = field(default_factory=list)
    transfer_plan: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Assistant Manager Report (aggregate)
# ---------------------------------------------------------------------------

@dataclass
class AssistantReport:
    """Complete output of the Assistant Manager engine for one run."""
    team_id: int
    generated_at: datetime
    current_gameweek: int | None = None

    # Section 1
    squad_evaluation: SquadEvaluation | None = None

    # Section 2 + 3
    transfer_plan: TransferPlan | None = None

    # Section 4
    chip_recommendations: list[ChipRecommendation] = field(default_factory=list)

    # Section 5
    future_plan: FuturePlan | None = None

    # Section 7
    executive_summary: str = ""

    # V2 Pipeline Output (populated when V2 pipeline runs)
    v2_pipeline_result: object | None = None  # PipelineResult from services/pipeline.py
