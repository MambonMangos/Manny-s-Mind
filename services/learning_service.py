"""Learning Service — orchestrates the validation cycle and feeds evidence into decisions.

This is the coordinator between Result Ingestion, Validation Engine, and
Error Classifier. It produces weekly reports and version comparisons.

Usage::

    from services.learning_service import run_validation_cycle, generate_weekly_report

    report = run_validation_cycle(session, gameweek_id=5)
    print(report["summary"])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from database.crud import (
    get_prediction_versions,
    get_projections,
    get_validation_metrics,
)
from engines.validation_engine import (
    validate_engine_contributions,
    validate_version,
)
from services.error_classifier import classify_errors, get_error_summary

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Evidence Thresholds
# ------------------------------------------------------------------

# Number of gameweeks needed for each evidence level
EVIDENCE_THRESHOLDS = {
    "weak": 1,           # 1 GW: preliminary, could be noise
    "needs_more_data": 2,  # 2 GW: early signal, not reliable
    "moderate": 3,        # 3-4 GW: consistent pattern emerging
    "strong": 5,          # 5-9 GW: reliable pattern
    "statistically_significant": 10,  # 10+ GW: most mature evidence available
}

# NOTE: these levels are SAMPLE-SIZE maturity heuristics, not formal
# statistical significance. No hypothesis test, p-value, or confidence
# interval is computed; the labels describe how much validation data backs
# a claim, not a rejection of a null hypothesis.


def get_evidence_level(n_gameweeks: int, consistency_score: float = 0.0) -> str:
    """Determine the evidence level based on gameweeks observed and consistency.

    Parameters
    ----------
    n_gameweeks : int
        Number of gameweeks with validation data.
    consistency_score : float, optional
        0-1 score indicating how consistent the pattern is across gameweeks.
        1.0 = perfectly consistent, 0.0 = random.

    Returns
    -------
    str
        Evidence level: "weak", "needs_more_data", "moderate", "strong", "statistically_significant"
    """
    if n_gameweeks >= EVIDENCE_THRESHOLDS["statistically_significant"]:
        return "statistically_significant"
    elif n_gameweeks >= EVIDENCE_THRESHOLDS["strong"]:
        # For strong evidence, require some consistency
        if consistency_score >= 0.6:
            return "strong"
        else:
            return "moderate"
    elif n_gameweeks >= EVIDENCE_THRESHOLDS["moderate"]:
        return "moderate"
    elif n_gameweeks >= EVIDENCE_THRESHOLDS["needs_more_data"]:
        return "needs_more_data"
    else:
        return "weak"


def get_evidence_description(level: str) -> str:
    """Get a human-readable description of an evidence level."""
    descriptions = {
        "weak": "Preliminary data from 1 gameweek. Could be noise. Do not act on this alone.",
        "needs_more_data": "Early signal from 2 gameweeks. Not yet reliable for decisions.",
        "moderate": "Consistent pattern across 3-4 gameweeks. Worth monitoring, but not conclusive.",
        "strong": "Reliable pattern across 5+ gameweeks. Strong candidate for investigation.",
        "statistically_significant": "Validated across 10+ gameweeks — the most extensive evidence available. Ready for action.",
    }
    return descriptions.get(level, "Unknown evidence level")


@dataclass
class CandidateImprovement:
    """A potential model improvement backed by evidence."""

    problem_observed: str
    supporting_metrics: dict = field(default_factory=dict)
    n_observations: int = 0
    gameweeks_affected: list = field(default_factory=list)
    expected_impact: str = ""
    evidence_level: str = "weak"
    potential_risk: str = ""
    recommended_action: str = ""
    status: str = "recommendation_only"  # always recommendation_only, never automatic


@dataclass
class WeeklyReport:
    """Comprehensive weekly validation report."""

    gameweek_id: int
    status: str  # "ok", "no_data", "partial"

    # Metrics per version
    version_metrics: list = field(default_factory=list)

    # Error breakdown
    error_summary: dict = field(default_factory=dict)

    # Engine contribution analysis
    engine_analysis: list = field(default_factory=list)

    # Recommendations (human-readable)
    insights: list = field(default_factory=list)

    # Candidate improvements (evidence-based)
    candidate_improvements: list = field(default_factory=list)

    # Evidence summary
    overall_evidence_level: str = "weak"
    evidence_description: str = ""

    # Metadata
    n_versions_evaluated: int = 0
    n_predictions_with_actuals: int = 0
    n_errors_classified: int = 0
    computed_at: str = ""


def run_validation_cycle(
    session: Session,
    gameweek_id: int,
    persist: bool = True,
) -> dict:
    """Run the full validation cycle for a finished gameweek.

    This orchestrates:
    1. Validate each prediction version (compute metrics)
    2. Classify errors for each version
    3. Analyze engine contributions

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    gameweek_id : int
        The finished gameweek to validate.
    persist : bool
        If True, persist all results to database.

    Returns
    -------
    dict
        Summary with status and key metrics.
    """
    versions = get_prediction_versions(session)
    if not versions:
        return {"status": "no_data", "message": "No prediction versions found"}

    results = []
    for pv in versions:
        # Check if this version has projections with actuals for this GW
        projections = get_projections(session, pv.id, gameweek_id)
        with_actuals = [p for p in projections if p.actual_points is not None]
        if not with_actuals:
            continue

        # Validate
        validation = validate_version(session, pv.id, gameweek_id, persist=persist)

        # Classify errors
        errors = classify_errors(session, pv.id, gameweek_id, persist=persist)

        # Engine contribution analysis
        engine_scores = validate_engine_contributions(
            session, pv.id, gameweek_id, persist=persist,
        )

        results.append({
            "version_id": pv.id,
            "version_tag": pv.version_tag,
            "mae": validation.mae,
            "rmse": validation.rmse,
            "bias": validation.bias,
            "ci80": validation.coverage_80,
            "ci95": validation.coverage_95,
            "n_predictions": validation.n_projections,
            "n_errors": len(errors),
            "engine_scores": engine_scores,
        })

    if persist:
        session.commit()

    logger.info(
        "Validation cycle complete for gw=%d: %d versions evaluated",
        gameweek_id, len(results),
    )

    return {
        "status": "ok",
        "gameweek_id": gameweek_id,
        "n_versions": len(results),
        "results": results,
    }


def generate_weekly_report(
    session: Session,
    gameweek_id: int,
) -> WeeklyReport:
    """Generate a comprehensive weekly validation report.

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    gameweek_id : int
        The gameweek to report on.

    Returns
    -------
    WeeklyReport
        Full report with metrics, errors, and insights.
    """
    report = WeeklyReport(
        gameweek_id=gameweek_id,
        status="ok",
        computed_at=datetime.utcnow().isoformat(),  # noqa: DTZ003 - naive UTC matches DB convention
    )

    # Get validation metrics for all versions
    all_metrics = get_validation_metrics(session, gameweek_id=gameweek_id)
    report.version_metrics = all_metrics
    report.n_versions_evaluated = len(all_metrics)

    if not all_metrics:
        report.status = "no_data"
        return report

    # Get projections with actuals count
    for pv in get_prediction_versions(session):
        projections = get_projections(session, pv.id, gameweek_id)
        with_actuals = [p for p in projections if p.actual_points is not None]
        report.n_predictions_with_actuals += len(with_actuals)

    # Error summary (use first version as representative)
    if all_metrics:
        first_version_id = all_metrics[0].version_id
        error_summary = get_error_summary(session, first_version_id, gameweek_id)
        report.error_summary = error_summary
        report.n_errors_classified = error_summary.get("total_errors", 0)

    # Generate insights
    try:
        report.insights = _generate_insights(report)
    except Exception:
        logger.exception("Failed to generate insights for gw=%d", gameweek_id)
        report.insights = ["Error generating insights — review logs"]

    # Generate candidate improvements
    try:
        report.candidate_improvements = _generate_candidate_improvements(report)
    except Exception:
        logger.exception("Failed to generate candidate improvements for gw=%d", gameweek_id)
        report.candidate_improvements = []

    # Compute overall evidence level
    report.overall_evidence_level = get_evidence_level(
        report.n_versions_evaluated,
        _compute_consistency(report),
    )
    report.evidence_description = get_evidence_description(report.overall_evidence_level)

    return report


def get_model_health(session: Session) -> dict:
    """Get overall model health metrics across recent gameweeks.

    Useful for the Analytics Dashboard to show trend over time.
    """
    # Get all validation metrics, grouped by version
    all_metrics = []
    for pv in get_prediction_versions(session):
        vm = get_validation_metrics(session, version_id=pv.id)
        for m in vm:
            all_metrics.append({
                "version_tag": pv.version_tag,
                "gameweek_id": m.gameweek_id,
                "mae": m.mae,
                "rmse": m.rmse,
                "bias": m.bias,
                "ci80": m.coverage_80,
                "ci95": m.coverage_95,
            })

    if not all_metrics:
        return {"status": "no_data", "message": "No validation metrics available"}

    # Sort by gameweek
    all_metrics.sort(key=lambda x: x["gameweek_id"])

    # Compute trends
    recent = all_metrics[-5:] if len(all_metrics) > 5 else all_metrics
    avg_mae = sum(m["mae"] or 0 for m in recent) / len(recent)
    avg_bias = sum(m["bias"] or 0 for m in recent) / len(recent)

    # Bias direction
    if avg_bias > 0.5:
        bias_direction = "underpredicting"
    elif avg_bias < -0.5:
        bias_direction = "overpredicting"
    else:
        bias_direction = "well_calibrated"

    return {
        "status": "ok",
        "n_gameweeks": len({m["gameweek_id"] for m in all_metrics}),
        "n_versions": len({m["version_tag"] for m in all_metrics}),
        "avg_mae_recent": round(avg_mae, 3),
        "avg_bias_recent": round(avg_bias, 3),
        "bias_direction": bias_direction,
        "trend": all_metrics,
    }


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _generate_insights(report: WeeklyReport) -> list[str]:
    """Generate human-readable insights from the weekly report."""
    insights = []

    if not report.version_metrics:
        return ["No validation data available for this gameweek"]

    for m in report.version_metrics:
        # MAE insight
        if m.mae and m.mae > 5:
            insights.append(
                f"High prediction error (MAE={m.mae:.1f}) for version {m.version_id} — "
                "review error classifications for systematic issues"
            )
        elif m.mae and m.mae < 2:
            insights.append(
                f"Strong prediction accuracy (MAE={m.mae:.1f}) for version {m.version_id}"
            )

        # Bias insight
        if m.bias and m.bias > 1:
            insights.append(
                f"Model underpredicting by {m.bias:.1f} pts on average — "
                "may need to increase projection baselines"
            )
        elif m.bias and m.bias < -1:
            insights.append(
                f"Model overpredicting by {abs(m.bias):.1f} pts on average — "
                "may need to decrease projection baselines"
            )

        # CI calibration
        if m.coverage_80 and m.coverage_80 < 0.6:
            insights.append(
                f"80% CI too narrow ({m.coverage_80:.0%} coverage) — "
                "increase variance estimates"
            )
        elif m.coverage_80 and m.coverage_80 > 0.95:
            insights.append(
                f"80% CI too wide ({m.coverage_80:.0%} coverage) — "
                "decrease variance estimates"
            )

    # Error pattern insight
    if report.error_summary:
        by_type = report.error_summary.get("by_type", {})
        if by_type and any(v is not None for v in by_type.values()):
            try:
                top_error = max(by_type, key=by_type.get)
                insights.append(
                    f"Most common error type: {top_error} ({by_type[top_error]} occurrences)"
                )
            except (ValueError, TypeError):
                logger.warning("Could not compute top error type from by_type=%s", by_type)

        by_direction = report.error_summary.get("by_direction", {})
        if by_direction.get("over", 0) > by_direction.get("under", 0) * 2:
            insights.append(
                "Model systematically overpredicting — check for overly optimistic baselines"
            )
        elif by_direction.get("under", 0) > by_direction.get("over", 0) * 2:
            insights.append(
                "Model systematically underpredicting — check for conservative baselines"
            )

    return insights if insights else ["Predictions performing within expected parameters"]


def _generate_candidate_improvements(report: WeeklyReport) -> list[CandidateImprovement]:
    """Generate evidence-based candidate improvements from the weekly report."""
    candidates = []

    if not report.version_metrics:
        return candidates

    for m in report.version_metrics:
        # Check for systematic bias
        if m.bias and abs(m.bias) > 1.0:
            direction = "underpredicting" if m.bias > 0 else "overpredicting"
            candidate = CandidateImprovement(
                problem_observed=f"Model systematically {direction} by {abs(m.bias):.1f} points on average",
                supporting_metrics={
                    "bias": m.bias,
                    "mae": m.mae,
                    "n_projections": m.n_projections,
                },
                n_observations=m.n_projections,
                gameweeks_affected=[m.gameweek_id],
                expected_impact=f"Reduce MAE by ~{abs(m.bias) * 0.3:.1f} points" if abs(m.bias) > 2 else "Minor improvement",
                evidence_level=get_evidence_level(1, 0.5),
                potential_risk="Could overcorrect and introduce opposite bias",
                recommended_action="Review projection baselines and adjust if pattern persists for 3+ gameweeks",
                status="recommendation_only",
            )
            candidates.append(candidate)

        # Check for CI calibration issues
        if m.coverage_80 and m.coverage_80 < 0.65:
            candidate = CandidateImprovement(
                problem_observed=f"80% confidence intervals too narrow ({m.coverage_80:.0%} actual coverage)",
                supporting_metrics={
                    "coverage_80": m.coverage_80,
                    "ci_width_avg": m.ci_width_avg,
                },
                n_observations=m.n_projections,
                gameweeks_affected=[m.gameweek_id],
                expected_impact="Better uncertainty quantification, more reliable intervals",
                evidence_level=get_evidence_level(1, 0.5),
                potential_risk="Wider intervals reduce differentiation between players",
                recommended_action="Increase variance estimates in Confidence Engine if pattern persists",
                status="recommendation_only",
            )
            candidates.append(candidate)

        elif m.coverage_80 and m.coverage_80 > 0.90:
            candidate = CandidateImprovement(
                problem_observed=f"80% confidence intervals too wide ({m.coverage_80:.0%} actual coverage)",
                supporting_metrics={
                    "coverage_80": m.coverage_80,
                    "ci_width_avg": m.ci_width_avg,
                },
                n_observations=m.n_projections,
                gameweeks_affected=[m.gameweek_id],
                expected_impact="Better differentiation between players",
                evidence_level=get_evidence_level(1, 0.5),
                potential_risk="Intervals may become too narrow, reducing coverage",
                recommended_action="Decrease variance estimates in Confidence Engine if pattern persists",
                status="recommendation_only",
            )
            candidates.append(candidate)

    # Check for position-specific issues
    if report.error_summary:
        by_type = report.error_summary.get("by_type", {})
        if by_type.get("minutes_miss", 0) > 5:
            candidate = CandidateImprovement(
                problem_observed=f"High rate of minutes misses ({by_type['minutes_miss']} occurrences)",
                supporting_metrics={"minutes_miss_count": by_type["minutes_miss"]},
                n_observations=by_type["minutes_miss"],
                gameweeks_affected=[report.gameweek_id],
                expected_impact="Reduce minutes-related prediction errors",
                evidence_level=get_evidence_level(1, 0.5),
                potential_risk="May need to incorporate more rotation risk data",
                recommended_action="Review Minutes Engine rotation risk model",
                status="recommendation_only",
            )
            candidates.append(candidate)

    return candidates


def _compute_consistency(report: WeeklyReport) -> float:
    """Compute a consistency score (0-1) for metrics across gameweeks."""
    if not report.version_metrics or len(report.version_metrics) < 2:
        return 0.5  # neutral for single observation

    # Check if MAE is consistent across versions
    maes = [m.mae for m in report.version_metrics if m.mae is not None]
    if not maes:
        return 0.5

    # Compute coefficient of variation (lower = more consistent)
    import numpy as np
    mean_mae = np.mean(maes)
    if mean_mae == 0:
        return 1.0

    cv = np.std(maes) / mean_mae
    # Convert to consistency score (0-1, where 1 = perfectly consistent)
    consistency = max(0.0, 1.0 - cv)
    return consistency
