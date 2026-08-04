"""FPL domain models for the UI layer.

Streamlit-free dataclasses that give the presentation layer a stable
vocabulary. Pages / adapters convert backend objects (assistant manager,
projection engines, comparison reports) into these shapes; the presenters in
:mod:`components.domain` render them.

Import rule: this module imports nothing from Streamlit, pandas, or the
backend services.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    """How much historical support a claim has."""
    level: str  # weak | needs_more_data | moderate | strong | statistically_significant
    n_gameweeks: int = 0
    description: str = ""
    consistency_score: float = 0.0  # 0-1


@dataclass
class TrustSection:
    """The trust block rendered on every recommendation card.

    ``model_agreement`` is a 0-1 rate of V3-vs-V2 agreement (or None when no
    comparison exists). ``historical_accuracy`` is a 0-1 rate of observed
    prediction accuracy (or None when never measured). Both must stay None
    rather than being fabricated.
    """
    evidence: Evidence | None = None
    confidence_pct: float | None = None  # 0-100
    reasoning: list[str] = field(default_factory=list)
    model_agreement: float | None = None  # 0-1
    historical_accuracy: float | None = None  # 0-1
    data_quality: str = ""  # high | medium | low | ""


@dataclass
class PlayerRef:
    """The minimum identifying info a card needs about a player."""
    player_id: int
    web_name: str
    team_short: str = ""
    position: str = ""
    price: float = 0.0


@dataclass
class ProjectionCard:
    """One player's gameweek projection (V3 xPts)."""
    player: PlayerRef
    gameweek_id: int
    projected_points: float
    ci_80_low: float
    ci_80_high: float
    ci_95_low: float
    ci_95_high: float
    confidence_pct: float
    data_quality: str
    contributing_factors: dict = field(default_factory=dict)
    trust: TrustSection | None = None


@dataclass
class CaptainCard:
    """A captaincy recommendation for a gameweek."""
    player: PlayerRef
    gameweek_id: int
    projected_points: float
    rationale: str = ""
    next_opponent: str = ""
    next_opponent_difficulty: int | None = None  # 1-5
    trust: TrustSection | None = None


@dataclass
class TransferCard:
    """A single transfer recommendation (out -> in)."""
    out: PlayerRef
    in_: PlayerRef
    price_difference: float
    expected_points_gained: float
    value_score_difference: float = 0.0
    fixture_improvement: float = 0.0
    minutes_projection: float = 0.0
    ownership_difference: float = 0.0
    risk_level: str = "medium"  # low | medium | high
    confidence_pct: float | None = None
    rank: int = 0
    reasoning: str = ""
    trust: TrustSection | None = None


@dataclass
class ChipCard:
    """A recommendation for a single chip."""
    chip_name: str  # wildcard | free_hit | bboost | 3xc
    chip_label: str
    should_play: bool
    confidence_pct: float
    best_gameweek: int | None = None
    projected_gain: float = 0.0
    reasoning: str = ""
    available: bool = True
    used: bool = False


@dataclass
class FixtureCard:
    """A single fixture in a player/team schedule."""
    gameweek: int
    opponent: str
    opponent_short: str = ""
    home: bool = True
    difficulty: int = 3  # 1-5
    difficulty_label: str = ""  # Very Easy .. Very Hard
    note: str = ""
