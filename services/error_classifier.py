"""Error Classifier — rule-based classification of prediction misses.

After the Validation Engine computes metrics, the Error Classifier analyzes
each mispredicted player and categorizes WHY the prediction was wrong.

This is diagnostic infrastructure, not prediction logic. It produces
human-readable error labels that feed the Analytics Dashboard.

Usage::

    from services.error_classifier import classify_errors

    classifications = classify_errors(session, version_id=1, gameweek_id=5)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from database.crud import (
    get_error_classifications,
    get_projections,
    insert_error_classifications,
)
from database.models import Player, PlayerGameweekStat

logger = logging.getLogger(__name__)


@dataclass
class ErrorRecord:
    """One classified prediction error."""

    projection_id: int
    player_id: int
    version_id: int
    gameweek_id: int

    error: float  # actual - projected
    abs_error: float
    error_direction: str  # "over" or "under"

    error_type: str  # minutes_miss, outlier_performance, etc.
    error_severity: str  # minor, moderate, severe
    root_cause: str | None

    predicted_minutes: float | None
    actual_minutes: float | None
    predicted_goals: float | None
    actual_goals: int | None
    predicted_assists: float | None
    actual_assists: int | None


# Severity thresholds
SEVERITY_MINOR = 3.0
SEVERITY_MODERATE = 6.0

# Outlier threshold (error beyond this is "outlier performance")
OUTLIER_THRESHOLD = 8.0


def classify_errors(
    session: Session,
    version_id: int,
    gameweek_id: int,
    persist: bool = True,
) -> list[ErrorRecord]:
    """Classify all prediction errors for a version + gameweek.

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    version_id : int
        The PredictionVersion to evaluate.
    gameweek_id : int
        The gameweek to evaluate.
    persist : bool
        If True, store classifications in ErrorClassification table.

    Returns
    -------
    list[ErrorRecord]
        Classified errors, sorted by absolute error descending.
    """
    # Fetch projections with actuals
    projections = get_projections(session, version_id, gameweek_id)
    with_actuals = [p for p in projections if p.actual_points is not None]

    if not with_actuals:
        return []

    # Check if already classified (idempotency)
    existing = get_error_classifications(session, version_id=version_id, gameweek_id=gameweek_id)
    if existing:
        logger.info(
            "Error classifications already exist for version_id=%d gw=%d, returning cached",
            version_id, gameweek_id,
        )
        return []

    classifications = []
    for p in with_actuals:
        error = p.actual_points - p.projected_points
        abs_error = abs(error)

        # Skip small errors (within expected noise)
        if abs_error < 1.5:
            continue

        # Get player context
        player = session.get(Player, p.player_id)
        pgws = (
            session.query(PlayerGameweekStat)
            .filter_by(player_id=p.player_id, gameweek_id=gameweek_id)
            .first()
        )

        record = _classify_one(p, player, pgws, error, abs_error, version_id, gameweek_id)
        classifications.append(record)

    # Sort by severity (severe first)
    classifications.sort(key=lambda r: r.abs_error, reverse=True)

    # Persist
    if persist and classifications:
        _persist_classifications(session, classifications)

    logger.info(
        "Classified %d errors for version_id=%d gw=%d (of %d predictions)",
        len(classifications), version_id, gameweek_id, len(with_actuals),
    )

    return classifications


def get_error_summary(
    session: Session,
    version_id: int,
    gameweek_id: int | None = None,
) -> dict:
    """Get a summary of error types for a version.

    Useful for the Analytics Dashboard to show error distribution.
    """
    classifications = get_error_classifications(session, version_id=version_id, gameweek_id=gameweek_id)

    type_counts = {}
    severity_counts = {"minor": 0, "moderate": 0, "severe": 0}
    direction_counts = {"over": 0, "under": 0}

    for c in classifications:
        type_counts[c.error_type] = type_counts.get(c.error_type, 0) + 1
        severity_counts[c.error_severity] = severity_counts.get(c.error_severity, 0) + 1
        direction_counts[c.error_direction] = direction_counts.get(c.error_direction, 0) + 1

    return {
        "total_errors": len(classifications),
        "by_type": type_counts,
        "by_severity": severity_counts,
        "by_direction": direction_counts,
        "avg_abs_error": sum(c.abs_error for c in classifications) / len(classifications) if classifications else 0,
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _classify_one(
    projection,
    player,
    pgws,
    error: float,
    abs_error: float,
    version_id: int,
    gameweek_id: int,
) -> ErrorRecord:
    """Classify a single prediction error using rule-based logic."""
    error_direction = "under" if error < 0 else "over"
    severity = _classify_severity(abs_error)

    # Default values
    predicted_minutes = projection.minutes_proj
    actual_minutes = pgws.minutes if pgws else None
    predicted_goals = projection.goals_proj
    actual_goals = pgws.goals_scored if pgws else None
    predicted_assists = projection.assists_proj
    actual_assists = pgws.assists if pgws else None

    # Rule 1: Minutes miss — predicted playing, didn't play or played much less
    if actual_minutes is not None and predicted_minutes is not None:
        if actual_minutes == 0 and predicted_minutes > 30:
            return ErrorRecord(
                projection_id=projection.id,
                player_id=projection.player_id,
                version_id=version_id,
                gameweek_id=gameweek_id,
                error=error, abs_error=abs_error, error_direction=error_direction,
                error_type="minutes_miss",
                error_severity="severe",
                root_cause="expected_start_but_benched_or_injured",
                predicted_minutes=predicted_minutes,
                actual_minutes=actual_minutes,
                predicted_goals=predicted_goals,
                actual_goals=actual_goals,
                predicted_assists=predicted_assists,
                actual_assists=actual_assists,
            )
        if actual_minutes > 0 and predicted_minutes > 0:
            minutes_ratio = actual_minutes / predicted_minutes
            if minutes_ratio < 0.4:
                return ErrorRecord(
                    projection_id=projection.id,
                    player_id=projection.player_id,
                    version_id=version_id,
                    gameweek_id=gameweek_id,
                    error=error, abs_error=abs_error, error_direction=error_direction,
                    error_type="low_minutes",
                    error_severity=severity,
                    root_cause="early_substitution_or_rotation",
                    predicted_minutes=predicted_minutes,
                    actual_minutes=actual_minutes,
                    predicted_goals=predicted_goals,
                    actual_goals=actual_goals,
                    predicted_assists=predicted_assists,
                    actual_assists=actual_assists,
                )

    # Rule 2: Outlier performance — unusually high or low actual
    if abs_error >= OUTLIER_THRESHOLD:
        root_cause = "hat_trick_or_anomaly" if error > 0 else "blanked_or_red_card"
        return ErrorRecord(
            projection_id=projection.id,
            player_id=projection.player_id,
            version_id=version_id,
            gameweek_id=gameweek_id,
            error=error, abs_error=abs_error, error_direction=error_direction,
            error_type="outlier_performance",
            error_severity="severe",
            root_cause=root_cause,
            predicted_minutes=predicted_minutes,
            actual_minutes=actual_minutes,
            predicted_goals=predicted_goals,
            actual_goals=actual_goals,
            predicted_assists=predicted_assists,
            actual_assists=actual_assists,
        )

    # Rule 3: Goal miss — predicted goals, didn't score (or scored more)
    if actual_goals is not None and predicted_goals is not None:
        if predicted_goals > 0.3 and actual_goals == 0 and abs_error >= 2:
            return ErrorRecord(
                projection_id=projection.id,
                player_id=projection.player_id,
                version_id=version_id,
                gameweek_id=gameweek_id,
                error=error, abs_error=abs_error, error_direction=error_direction,
                error_type="goal_miss",
                error_severity=severity,
                root_cause="predicted_scoring_opportunity_missed",
                predicted_minutes=predicted_minutes,
                actual_minutes=actual_minutes,
                predicted_goals=predicted_goals,
                actual_goals=actual_goals,
                predicted_assists=predicted_assists,
                actual_assists=actual_assists,
            )
        if predicted_goals < 0.2 and actual_goals >= 2:
            return ErrorRecord(
                projection_id=projection.id,
                player_id=projection.player_id,
                version_id=version_id,
                gameweek_id=gameweek_id,
                error=error, abs_error=abs_error, error_direction=error_direction,
                error_type="outlier_performance",
                error_severity="severe",
                root_cause="unexpected_multi_goal_game",
                predicted_minutes=predicted_minutes,
                actual_minutes=actual_minutes,
                predicted_goals=predicted_goals,
                actual_goals=actual_goals,
                predicted_assists=predicted_assists,
                actual_assists=actual_assists,
            )

    # Rule 4: Assists miss
    if actual_assists is not None and predicted_assists is not None:
        if predicted_assists > 0.3 and actual_assists == 0 and abs_error >= 2:
            return ErrorRecord(
                projection_id=projection.id,
                player_id=projection.player_id,
                version_id=version_id,
                gameweek_id=gameweek_id,
                error=error, abs_error=abs_error, error_direction=error_direction,
                error_type="assists_miss",
                error_severity=severity,
                root_cause="predicted_creative_output_not_realized",
                predicted_minutes=predicted_minutes,
                actual_minutes=actual_minutes,
                predicted_goals=predicted_goals,
                actual_goals=actual_goals,
                predicted_assists=predicted_assists,
                actual_assists=actual_assists,
            )

    # Rule 5: Clean sheet miss (for defenders/GKs)
    if player and player.element_type in (1, 2):  # GKP or DEF
        if pgws:
            # Predicted CS contribution but didn't keep clean sheet
            cs_proj = projection.clean_sheet_proj or 0
            if cs_proj > 2 and pgws.clean_sheets == 0 and abs_error >= 2:
                return ErrorRecord(
                    projection_id=projection.id,
                    player_id=projection.player_id,
                    version_id=version_id,
                    gameweek_id=gameweek_id,
                    error=error, abs_error=abs_error, error_direction=error_direction,
                    error_type="clean_sheet_miss",
                    error_severity=severity,
                    root_cause="predicted_clean_sheet_conceded",
                    predicted_minutes=predicted_minutes,
                    actual_minutes=actual_minutes,
                    predicted_goals=predicted_goals,
                    actual_goals=actual_goals,
                    predicted_assists=predicted_assists,
                    actual_assists=actual_assists,
                )

    # Default: generic under/over performance
    root_cause = "underperformed_expectations" if error < 0 else "overperformed_expectations"
    return ErrorRecord(
        projection_id=projection.id,
        player_id=projection.player_id,
        version_id=version_id,
        gameweek_id=gameweek_id,
        error=error, abs_error=abs_error, error_direction=error_direction,
        error_type="generic_misprediction",
        error_severity=severity,
        root_cause=root_cause,
        predicted_minutes=predicted_minutes,
        actual_minutes=actual_minutes,
        predicted_goals=predicted_goals,
        actual_goals=actual_goals,
        predicted_assists=predicted_assists,
        actual_assists=actual_assists,
    )


def _classify_severity(abs_error: float) -> str:
    """Classify error severity based on absolute error."""
    if abs_error >= SEVERITY_MODERATE:
        return "severe"
    elif abs_error >= SEVERITY_MINOR:
        return "moderate"
    return "minor"


def _persist_classifications(session: Session, classifications: list[ErrorRecord]) -> None:
    """Store ErrorRecords in the database."""
    rows = []
    for c in classifications:
        rows.append({
            "projection_id": c.projection_id,
            "player_id": c.player_id,
            "version_id": c.version_id,
            "gameweek_id": c.gameweek_id,
            "error": c.error,
            "abs_error": c.abs_error,
            "error_direction": c.error_direction,
            "error_type": c.error_type,
            "error_severity": c.error_severity,
            "root_cause": c.root_cause,
            "predicted_minutes": c.predicted_minutes,
            "actual_minutes": c.actual_minutes,
            "predicted_goals": c.predicted_goals,
            "actual_goals": c.actual_goals,
            "predicted_assists": c.predicted_assists,
            "actual_assists": c.actual_assists,
        })

    insert_error_classifications(session, rows)
