"""Validation Engine — computes accuracy metrics for prediction versions.

This is validation infrastructure, not prediction logic. It measures how
accurate past predictions were, enabling evidence-based model improvement.

Usage::

    from engines.validation_engine import validate_version

    metrics = validate_version(session, version_id=1, gameweek_id=5)
    print(metrics.mae, metrics.coverage_80)
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
from sqlalchemy.orm import Session

from database.crud import (
    get_engine_accuracy,
    get_projections,
    get_validation_metrics,
    insert_engine_accuracy,
    insert_validation_metrics,
)
from database.models import Player, ValidationMetrics

logger = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    """Complete validation result for a version + GW."""

    gameweek_id: int
    version_id: int

    # Overall metrics
    mae: float = 0.0
    rmse: float = 0.0
    bias: float = 0.0  # mean(actual - projected), positive = underpredicted
    median_ae: float = 0.0

    # CI calibration
    coverage_80: float = 0.0
    coverage_95: float = 0.0
    ci_width_avg: float = 0.0

    # Per-position breakdown
    mae_by_position: dict = field(default_factory=dict)
    rmse_by_position: dict = field(default_factory=dict)
    n_by_position: dict = field(default_factory=dict)

    # Top/bottom
    best_predicted_player_id: int | None = None
    worst_predicted_player_id: int | None = None
    worst_error: float = 0.0

    # Per-engine breakdown
    engine_scores: list = field(default_factory=list)

    n_projections: int = 0
    persisted: bool = False


POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}


def validate_version(
    session: Session,
    version_id: int,
    gameweek_id: int,
    persist: bool = True,
) -> ValidationReport:
    """Compute all accuracy metrics for a prediction version against a gameweek.

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    version_id : int
        The PredictionVersion to evaluate.
    gameweek_id : int
        The gameweek to evaluate against.
    persist : bool
        If True, store metrics in ValidationMetrics table.

    Returns
    -------
    ValidationReport
        Complete metrics report.
    """
    report = ValidationReport(gameweek_id=gameweek_id, version_id=version_id)

    # Fetch projections with actuals
    projections = get_projections(session, version_id, gameweek_id)
    with_actuals = [p for p in projections if p.actual_points is not None]

    if not with_actuals:
        logger.warning(
            "No projections with actuals for version_id=%s gw=%s",
            version_id, gameweek_id,
        )
        return report

    report.n_projections = len(with_actuals)

    # Extract arrays
    predicted = np.array([p.projected_points for p in with_actuals], dtype=float)
    actual = np.array([p.actual_points for p in with_actuals], dtype=float)
    errors = actual - predicted
    abs_errors = np.abs(errors)

    # Overall metrics
    report.mae = float(np.mean(abs_errors))
    report.rmse = float(np.sqrt(np.mean(errors ** 2)))
    report.bias = float(np.mean(errors))
    report.median_ae = float(np.median(abs_errors))

    # CI calibration
    ci_80_hits = 0
    ci_95_hits = 0
    ci_widths = []
    for p in with_actuals:
        if p.ci_80_low is not None and p.ci_80_high is not None:
            if p.ci_80_low <= p.actual_points <= p.ci_80_high:
                ci_80_hits += 1
            ci_widths.append(p.ci_80_high - p.ci_80_low)
        if p.ci_95_low is not None and p.ci_95_high is not None:
            if p.ci_95_low <= p.actual_points <= p.ci_95_high:
                ci_95_hits += 1

    report.coverage_80 = ci_80_hits / len(with_actuals) if with_actuals else 0
    report.coverage_95 = ci_95_hits / len(with_actuals) if with_actuals else 0
    report.ci_width_avg = float(np.mean(ci_widths)) if ci_widths else 0

    # Per-position breakdown (bulk query — no N+1)
    player_ids = list({p.player_id for p in with_actuals})
    players = session.query(Player).filter(Player.id.in_(player_ids)).all()
    player_position = {pl.id: POSITION_MAP.get(pl.element_type, "UNK") for pl in players}

    position_errors = defaultdict(list)
    position_squared_errors = defaultdict(list)
    for p in with_actuals:
        pos = player_position.get(p.player_id, "UNK")
        err = abs(p.projected_points - p.actual_points)
        position_errors[pos].append(err)
        position_squared_errors[pos].append((p.projected_points - p.actual_points) ** 2)

    for pos, errs in position_errors.items():
        report.mae_by_position[pos] = round(float(np.mean(errs)), 3)
        report.n_by_position[pos] = len(errs)
    for pos, sqerrs in position_squared_errors.items():
        report.rmse_by_position[pos] = round(float(np.sqrt(np.mean(sqerrs))), 3)

    # Top/bottom predictions
    best_idx = int(np.argmin(abs_errors))
    worst_idx = int(np.argmax(abs_errors))
    report.best_predicted_player_id = with_actuals[best_idx].player_id
    report.worst_predicted_player_id = with_actuals[worst_idx].player_id
    report.worst_error = float(abs_errors[worst_idx])

    # Persist if requested
    if persist:
        _persist_validation_metrics(session, report)
        report.persisted = True

    logger.info(
        "Validation complete: version_id=%d gw=%d, MAE=%.3f, bias=%.3f, "
        "CI80=%.1f%%, CI95=%.1f%%, n=%d",
        version_id, gameweek_id, report.mae, report.bias,
        report.coverage_80 * 100, report.coverage_95 * 100, report.n_projections,
    )

    return report


def validate_engine_contributions(
    session: Session,
    version_id: int,
    gameweek_id: int,
    store=None,  # noqa: ANN001 — FeatureStore, optional
) -> list[dict]:
    """Analyze per-engine contribution to prediction accuracy.

    This measures correlation between each engine's intermediate output
    and the final prediction accuracy, enabling engine-level scoring.

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    version_id : int
        The PredictionVersion to evaluate.
    gameweek_id : int
        The gameweek to evaluate.
    store : FeatureStore, optional
        Feature store for accessing intermediate features.

    Returns
    -------
    list[dict]
        Engine accuracy records.
    """
    projections = get_projections(session, version_id, gameweek_id)
    with_actuals = [p for p in projections if p.actual_points is not None]

    if len(with_actuals) < 5:
        logger.warning("Not enough samples for engine analysis (%d)", len(with_actuals))
        return []

    actual = np.array([p.actual_points for p in with_actuals], dtype=float)
    predicted = np.array([p.projected_points for p in with_actuals], dtype=float)
    errors = actual - predicted

    # Analyze contribution of each component
    engine_results = []

    # Minutes engine contribution
    minutes_proj = np.array([p.minutes_proj or 0 for p in with_actuals], dtype=float)
    if np.std(minutes_proj) > 0:
        minutes_corr = float(np.corrcoef(minutes_proj, errors)[0, 1])
        engine_results.append({
            "version_id": version_id,
            "gameweek_id": gameweek_id,
            "engine_name": "minutes_engine",
            "correlation": round(minutes_corr, 4),
            "mae": round(float(np.mean(np.abs(errors))), 3),
            "n_samples": len(with_actuals),
        })

    # Goals projection contribution
    goals_proj = np.array([p.goals_proj or 0 for p in with_actuals], dtype=float)
    if np.std(goals_proj) > 0:
        goals_corr = float(np.corrcoef(goals_proj, errors)[0, 1])
        engine_results.append({
            "version_id": version_id,
            "gameweek_id": gameweek_id,
            "engine_name": "goals_projection",
            "correlation": round(goals_corr, 4),
            "mae": round(float(np.mean(np.abs(errors))), 3),
            "n_samples": len(with_actuals),
        })

    # Assists projection contribution
    assists_proj = np.array([p.assists_proj or 0 for p in with_actuals], dtype=float)
    if np.std(assists_proj) > 0:
        assists_corr = float(np.corrcoef(assists_proj, errors)[0, 1])
        engine_results.append({
            "version_id": version_id,
            "gameweek_id": gameweek_id,
            "engine_name": "assists_projection",
            "correlation": round(assists_corr, 4),
            "mae": round(float(np.mean(np.abs(errors))), 3),
            "n_samples": len(with_actuals),
        })

    # Clean sheet projection contribution
    cs_proj = np.array([p.clean_sheet_proj or 0 for p in with_actuals], dtype=float)
    if np.std(cs_proj) > 0:
        cs_corr = float(np.corrcoef(cs_proj, errors)[0, 1])
        engine_results.append({
            "version_id": version_id,
            "gameweek_id": gameweek_id,
            "engine_name": "clean_sheet_projection",
            "correlation": round(cs_corr, 4),
            "mae": round(float(np.mean(np.abs(errors))), 3),
            "n_samples": len(with_actuals),
        })

    # Persist
    for r in engine_results:
        insert_engine_accuracy(session, r)

    return engine_results


def compare_versions(
    session: Session,
    version_id_a: int,
    version_id_b: int,
    gameweek_ids: list[int] | None = None,
) -> dict:
    """Compare accuracy of two prediction versions across gameweeks.

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    version_id_a : int
        Baseline version.
    version_id_b : int
        Treatment version.
    gameweek_ids : list[int], optional
        Gameweeks to compare. If None, uses all available.

    Returns
    -------
    dict
        Comparison results with improvement percentages.
    """
    # Get metrics for both versions
    metrics_a = get_validation_metrics(session, version_id=version_id_a)
    metrics_b = get_validation_metrics(session, version_id=version_id_b)

    if not metrics_a or not metrics_b:
        return {"error": "Insufficient metrics for comparison"}

    # Filter to common gameweeks if specified
    if gameweek_ids:
        metrics_a = [m for m in metrics_a if m.gameweek_id in gameweek_ids]
        metrics_b = [m for m in metrics_b if m.gameweek_id in gameweek_ids]

    if not metrics_a or not metrics_b:
        return {"error": "No common gameweeks with metrics"}

    # Compute averages
    avg_mae_a = sum(m.mae or 0 for m in metrics_a) / len(metrics_a)
    avg_mae_b = sum(m.mae or 0 for m in metrics_b) / len(metrics_b)
    avg_rmse_a = sum(m.rmse or 0 for m in metrics_a) / len(metrics_a)
    avg_rmse_b = sum(m.rmse or 0 for m in metrics_b) / len(metrics_b)
    avg_bias_a = sum(m.bias or 0 for m in metrics_a) / len(metrics_a)
    avg_bias_b = sum(m.bias or 0 for m in metrics_b) / len(metrics_b)
    avg_ci80_a = sum(m.coverage_80 or 0 for m in metrics_a) / len(metrics_a)
    avg_ci80_b = sum(m.coverage_80 or 0 for m in metrics_b) / len(metrics_b)

    # Improvement (negative = B is worse)
    mae_improvement = (avg_mae_a - avg_mae_b) / avg_mae_a * 100 if avg_mae_a else 0
    rmse_improvement = (avg_rmse_a - avg_rmse_b) / avg_rmse_a * 100 if avg_rmse_a else 0

    return {
        "version_a_id": version_id_a,
        "version_b_id": version_id_b,
        "n_gameweeks": min(len(metrics_a), len(metrics_b)),
        "mae_a": round(avg_mae_a, 3),
        "mae_b": round(avg_mae_b, 3),
        "mae_improvement_pct": round(mae_improvement, 2),
        "rmse_a": round(avg_rmse_a, 3),
        "rmse_b": round(avg_rmse_b, 3),
        "rmse_improvement_pct": round(rmse_improvement, 2),
        "bias_a": round(avg_bias_a, 3),
        "bias_b": round(avg_bias_b, 3),
        "ci80_a": round(avg_ci80_a, 3),
        "ci80_b": round(avg_ci80_b, 3),
        "winner": "B" if mae_improvement > 0 else "A" if mae_improvement < 0 else "tie",
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _persist_validation_metrics(session: Session, report: ValidationReport) -> None:
    """Store ValidationReport in the database."""
    # Check for existing (idempotency)
    existing = get_validation_metrics(
        session,
        version_id=report.version_id,
        gameweek_id=report.gameweek_id,
    )
    if existing:
        logger.info(
            "Validation metrics already exist for version_id=%d gw=%d, skipping",
            report.version_id, report.gameweek_id,
        )
        return

    data = {
        "version_id": report.version_id,
        "gameweek_id": report.gameweek_id,
        "mae": report.mae,
        "rmse": report.rmse,
        "bias": report.bias,
        "median_ae": report.median_ae,
        "coverage_80": report.coverage_80,
        "coverage_95": report.coverage_95,
        "ci_width_avg": report.ci_width_avg,
        "mae_by_position": report.mae_by_position,
        "rmse_by_position": report.rmse_by_position,
        "n_by_position": report.n_by_position,
        "best_predicted_player_id": report.best_predicted_player_id,
        "worst_predicted_player_id": report.worst_predicted_player_id,
        "worst_error": report.worst_error,
        "n_projections": report.n_projections,
    }
    insert_validation_metrics(session, data)
    logger.info("Persisted ValidationMetrics for version_id=%d gw=%d",
                report.version_id, report.gameweek_id)
