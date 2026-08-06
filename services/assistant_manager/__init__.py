"""Assistant Manager — intelligent FPL decision-support engine."""

from services.assistant_manager.models import (
    AssistantReport,
    ChipRecommendation,
    FixtureInfo,
    FixtureWindow,
    FuturePlan,
    PlayerAssessment,
    SquadEvaluation,
    TransferPlan,
    TransferRecommendation,
)


def run_assistant(*args, **kwargs):
    """Lazy import to avoid circular dependency with fixture_engine."""
    from services.assistant_manager.engine import run_assistant as _run
    return _run(*args, **kwargs)


__all__ = [
    "AssistantReport",
    "ChipRecommendation",
    "FixtureInfo",
    "FixtureWindow",
    "FuturePlan",
    "PlayerAssessment",
    "SquadEvaluation",
    "TransferPlan",
    "TransferRecommendation",
    "run_assistant",
]
