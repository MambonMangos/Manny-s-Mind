"""CRUD helpers – thin wrappers around SQLAlchemy queries."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Sequence

import pandas as pd
from sqlalchemy import func, inspect
from sqlalchemy.orm import Session

from database.models import (
    EngineAccuracy,
    ErrorClassification,
    Player,
    Team,
    Gameweek,
    PredictionVersion,
    Projection,
    PlayerSnapshot,
    ExperimentRun,
    DecisionLog,
    ValidationMetrics,
    RecommendationOutcome,
)
from utils.constants import POSITION_MAP

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

def upsert_player(session: Session, data: dict) -> Player:
    """Insert or update a single player row.

    Returns the Player instance.
    """
    player = session.get(Player, data["id"])
    if player is None:
        player = Player(id=data["id"])
        session.add(player)
    for key, value in data.items():
        setattr(player, key, value)
    session.flush()
    return player


def upsert_players_bulk(session: Session, records: list[dict]) -> int:
    """Bulk-upsert player records.

    Returns the number of rows affected.
    """
    count = 0
    for rec in records:
        upsert_player(session, rec)
        count += 1
    session.commit()
    return count


def get_all_players(session: Session) -> list[Player]:
    """Return all players ordered by total_points descending."""
    return session.query(Player).order_by(Player.total_points.desc()).all()


def get_players_dataframe(session: Session) -> pd.DataFrame:
    """Return a DataFrame with all players joined to team names."""
    rows = (
        session.query(
            Player,
            Team.name.label("team_name"),
            Team.short_name.label("team_short_name"),
            Team.strength_overall_home,
            Team.strength_overall_away,
        )
        .join(Team, Player.team_id == Team.id)
        .all()
    )
    records: list[dict] = []
    for player, team_name, team_short, home_str, away_str in rows:
        rec: dict = {
            "id": player.id,
            "web_name": player.web_name,
            "first_name": player.first_name,
            "second_name": player.second_name,
            "team_id": player.team_id,
            "team_name": team_name,
            "team_short": team_short,
            "position_id": player.element_type,
            "position": _position_label(player.element_type),
            "price": player.now_cost / 10.0,
            "minutes": player.minutes,
            "goals_scored": player.goals_scored,
            "assists": player.assists,
            "total_points": player.total_points,
            "bonus": player.bonus,
            "bps": player.bps,
            "influence": player.influence,
            "creativity": player.creativity,
            "threat": player.threat,
            "ict_index": player.ict_index,
            "expected_goals": player.expected_goals,
            "expected_assists": player.expected_assists,
            "expected_goal_involvements": player.expected_goal_involvements,
            "expected_goals_conceded": player.expected_goals_conceded,
            "form": player.form,
            "selected_by_percent": player.selected_by_percent,
            "transfers_in_event": player.transfers_in_event,
            "transfers_out_event": player.transfers_out_event,
            "status": player.status,
            "news": player.news,
            "clean_sheets": player.clean_sheets,
            "yellow_cards": player.yellow_cards,
            "red_cards": player.red_cards,
            "saves": player.saves,
            "penalties_order": player.penalties_order,
            "direct_freekicks_order": player.direct_freekicks_order,
            "corners_and_indirect_freekicks_order": player.corners_and_indirect_freekicks_order,
            "strength_overall_home": home_str,
            "strength_overall_away": away_str,
        }
        records.append(rec)
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

def upsert_team(session: Session, data: dict) -> Team:
    """Insert or update a single team row."""
    team = session.get(Team, data["id"])
    if team is None:
        team = Team(id=data["id"])
        session.add(team)
    for key, value in data.items():
        setattr(team, key, value)
    session.flush()
    return team


def upsert_teams_bulk(session: Session, records: list[dict]) -> int:
    """Bulk-upsert team records."""
    count = 0
    for rec in records:
        upsert_team(session, rec)
        count += 1
    session.commit()
    return count


def get_all_teams(session: Session) -> Sequence[Team]:
    """Return all teams ordered by id."""
    return session.query(Team).order_by(Team.id).all()


def get_teams_dataframe(session: Session) -> pd.DataFrame:
    """Return a DataFrame of all teams."""
    teams = get_all_teams(session)
    records: list[dict] = []
    for t in teams:
        records.append(
            {
                "id": t.id,
                "name": t.name,
                "short_name": t.short_name,
                "strength_overall_home": t.strength_overall_home,
                "strength_overall_away": t.strength_overall_away,
                "strength_attack_home": t.strength_attack_home,
                "strength_attack_away": t.strength_attack_away,
                "strength_defence_home": t.strength_defence_home,
                "strength_defence_away": t.strength_defence_away,
            }
        )
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# Gameweeks
# ---------------------------------------------------------------------------

def upsert_gameweek(session: Session, data: dict) -> Gameweek:
    """Insert or update a single gameweek row."""
    gw = session.get(Gameweek, data["id"])
    if gw is None:
        gw = Gameweek(id=data["id"])
        session.add(gw)
    for key, value in data.items():
        setattr(gw, key, value)
    session.flush()
    return gw


def upsert_gameweeks_bulk(session: Session, records: list[dict]) -> int:
    """Bulk-upsert gameweek records."""
    count = 0
    for rec in records:
        upsert_gameweek(session, rec)
        count += 1
    session.commit()
    return count


# ---------------------------------------------------------------------------
# Prediction Ledger — PredictionVersion
# ---------------------------------------------------------------------------

def create_prediction_version(
    session: Session,
    version_tag: str,
    model_name: str,
    config_hash: str | None = None,
    features_used: list[str] | None = None,
    weights_snapshot: dict | None = None,
    notes: str | None = None,
) -> PredictionVersion:
    """Create a new prediction version record. Append-only, never update."""
    pv = PredictionVersion(
        version_tag=version_tag,
        model_name=model_name,
        config_hash=config_hash,
        features_used=features_used,
        weights_snapshot=weights_snapshot,
        notes=notes,
    )
    session.add(pv)
    session.flush()
    logger.info("Created PredictionVersion: %s (id=%d)", version_tag, pv.id)
    return pv


def get_prediction_version_by_tag(
    session: Session,
    version_tag: str,
) -> PredictionVersion | None:
    """Look up a prediction version by its unique tag."""
    return (
        session.query(PredictionVersion)
        .filter_by(version_tag=version_tag)
        .first()
    )


def get_prediction_versions(
    session: Session,
    model_name: str | None = None,
    limit: int = 50,
) -> list[PredictionVersion]:
    """Return recent prediction versions, newest first."""
    q = session.query(PredictionVersion)
    if model_name:
        q = q.filter_by(model_name=model_name)
    return q.order_by(PredictionVersion.created_at.desc()).limit(limit).all()


def update_prediction_version_metrics(
    session: Session,
    version_id: int,
    mae: float | None = None,
    rmse: float | None = None,
    coverage_80: float | None = None,
    coverage_95: float | None = None,
) -> None:
    """Update quality metrics on a prediction version (post-validation only)."""
    pv = session.get(PredictionVersion, version_id)
    if pv is None:
        logger.warning("PredictionVersion id=%d not found", version_id)
        return
    if mae is not None:
        pv.mae = mae
    if rmse is not None:
        pv.rmse = rmse
    if coverage_80 is not None:
        pv.coverage_80 = coverage_80
    if coverage_95 is not None:
        pv.coverage_95 = coverage_95
    session.flush()


# ---------------------------------------------------------------------------
# Prediction Ledger — Projection (bulk insert + queries)
# ---------------------------------------------------------------------------

def insert_projections_bulk(
    session: Session,
    version_id: int,
    projections: list,
) -> int:
    """Bulk-insert Projection rows from PlayerProjection dataclass instances.

    Append-only: each call creates new rows, never updates existing ones.
    Returns the number of rows inserted.
    """
    rows = []
    for p in projections:
        row = Projection(
            version_id=version_id,
            player_id=p.player_id,
            gameweek_id=p.gameweek_id,
            projected_points=p.projected_points,
            ci_80_low=p.ci_80_low,
            ci_80_high=p.ci_80_high,
            ci_95_low=p.ci_95_low,
            ci_95_high=p.ci_95_high,
            minutes_proj=p.minutes_proj,
            goals_proj=p.goals_proj,
            assists_proj=p.assists_proj,
            clean_sheet_proj=p.clean_sheet_proj,
            bonus_proj=p.bonus_proj,
            other_proj=p.other_proj,
            actual_points=None,  # filled in after GW finishes
        )
        rows.append(row)

    session.add_all(rows)
    session.flush()
    logger.info("Inserted %d Projection rows for version_id=%d", len(rows), version_id)
    return len(rows)


def get_projections(
    session: Session,
    version_id: int,
    gameweek_id: int | None = None,
) -> list[Projection]:
    """Return all projections for a given version, optionally filtered by GW."""
    q = session.query(Projection).filter_by(version_id=version_id)
    if gameweek_id is not None:
        q = q.filter_by(gameweek_id=gameweek_id)
    return q.order_by(Projection.player_id).all()


def get_projection_for_player(
    session: Session,
    version_id: int,
    player_id: int,
    gameweek_id: int,
) -> Projection | None:
    """Return the projection for a specific player in a specific version + GW."""
    return (
        session.query(Projection)
        .filter_by(
            version_id=version_id,
            player_id=player_id,
            gameweek_id=gameweek_id,
        )
        .first()
    )


def get_projection_actuals(
    session: Session,
    version_id: int,
    gameweek_id: int,
) -> dict[int, int]:
    """Return a dict of player_id → actual_points for a version + GW.

    Only returns rows where actual_points has been filled in.
    """
    rows = (
        session.query(Projection)
        .filter_by(version_id=version_id, gameweek_id=gameweek_id)
        .filter(Projection.actual_points.isnot(None))
        .all()
    )
    return {r.player_id: r.actual_points for r in rows}


def update_projection_actuals_bulk(
    session: Session,
    version_id: int,
    gameweek_id: int,
    actuals: dict[int, int],
) -> int:
    """Update actual_points for a batch of projections.

    Returns the number of rows updated.
    """
    rows = (
        session.query(Projection)
        .filter_by(version_id=version_id, gameweek_id=gameweek_id)
        .all()
    )
    count = 0
    for row in rows:
        if row.player_id in actuals:
            row.actual_points = actuals[row.player_id]
            count += 1
    session.flush()
    logger.info(
        "Updated %d actual_points for version_id=%d, gw=%d",
        count, version_id, gameweek_id,
    )
    return count


def get_projections_with_actuals(
    session: Session,
    gameweek_id: int,
) -> list[Projection]:
    """Return all projections for a GW that have actual_points filled in.

    Used by the Validation Engine to compute accuracy metrics.
    """
    return (
        session.query(Projection)
        .filter_by(gameweek_id=gameweek_id)
        .filter(Projection.actual_points.isnot(None))
        .all()
    )


def get_latest_version_for_gw(
    session: Session,
    gameweek_id: int,
) -> PredictionVersion | None:
    """Return the most recent PredictionVersion that has projections for this GW."""
    pv = (
        session.query(PredictionVersion)
        .join(Projection, Projection.version_id == PredictionVersion.id)
        .filter(Projection.gameweek_id == gameweek_id)
        .order_by(PredictionVersion.created_at.desc())
        .first()
    )
    return pv


# ---------------------------------------------------------------------------
# Prediction Ledger — PlayerSnapshot
# ---------------------------------------------------------------------------

def insert_player_snapshots_bulk(
    session: Session,
    snapshots: list[dict],
) -> int:
    """Bulk-insert PlayerSnapshot rows.

    Each dict should contain the fields of the PlayerSnapshot model.
    Append-only: creates new rows, never updates.
    """
    rows = [PlayerSnapshot(**s) for s in snapshots]
    session.add_all(rows)
    session.flush()
    logger.info("Inserted %d PlayerSnapshot rows", len(rows))
    return len(rows)


def get_player_snapshots(
    session: Session,
    player_id: int,
    gameweek_id: int | None = None,
    limit: int = 50,
) -> list[PlayerSnapshot]:
    """Return snapshots for a player, most recent first."""
    q = session.query(PlayerSnapshot).filter_by(player_id=player_id)
    if gameweek_id is not None:
        q = q.filter_by(gameweek_id=gameweek_id)
    return q.order_by(PlayerSnapshot.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Prediction Ledger — ExperimentRun
# ---------------------------------------------------------------------------

def create_experiment_run(
    session: Session,
    run_name: str,
    experiment_type: str,
    baseline_version: str | None = None,
    treatment_version: str | None = None,
    config_diff: dict | None = None,
    notes: str | None = None,
) -> ExperimentRun:
    """Create a new experiment run."""
    er = ExperimentRun(
        run_name=run_name,
        experiment_type=experiment_type,
        baseline_version=baseline_version,
        treatment_version=treatment_version,
        config_diff=config_diff,
        notes=notes,
        status="pending",
    )
    session.add(er)
    session.flush()
    logger.info("Created ExperimentRun: %s (id=%d)", run_name, er.id)
    return er


def update_experiment_run_results(
    session: Session,
    experiment_id: int,
    baseline_mae: float | None = None,
    treatment_mae: float | None = None,
    improvement_pct: float | None = None,
    status: str | None = None,
    notes: str | None = None,
) -> None:
    """Update experiment run with results and/or status."""
    er = session.get(ExperimentRun, experiment_id)
    if er is None:
        logger.warning("ExperimentRun id=%d not found", experiment_id)
        return
    if baseline_mae is not None:
        er.baseline_mae = baseline_mae
    if treatment_mae is not None:
        er.treatment_mae = treatment_mae
    if improvement_pct is not None:
        er.improvement_pct = improvement_pct
    if status is not None:
        er.status = status
    if notes is not None:
        er.notes = notes
    if status in ("completed", "failed"):
        er.completed_at = datetime.now(timezone.utc)
    session.flush()


def get_experiment_runs(
    session: Session,
    experiment_type: str | None = None,
    limit: int = 50,
) -> list[ExperimentRun]:
    """Return experiment runs, newest first."""
    q = session.query(ExperimentRun)
    if experiment_type:
        q = q.filter_by(experiment_type=experiment_type)
    return q.order_by(ExperimentRun.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Prediction Ledger — DecisionLog queries
# ---------------------------------------------------------------------------

def get_decision_log_for_validation(
    session: Session,
    team_id: int,
    gameweek_id: int,
) -> list[DecisionLog]:
    """Return all decisions for a team + GW, for validation."""
    return (
        session.query(DecisionLog)
        .filter_by(team_id=team_id, gameweek_id=gameweek_id)
        .all()
    )


def update_decision_log_outcome(
    session: Session,
    decision_id: int,
    actual_points: float,
    was_accurate: bool,
) -> None:
    """Update the outcome of a decision after GW finishes."""
    dl = session.get(DecisionLog, decision_id)
    if dl is None:
        return
    dl.actual_points = actual_points
    dl.was_accurate = was_accurate
    session.flush()


# ---------------------------------------------------------------------------
# Prediction Ledger — aggregate queries for dashboard
# ---------------------------------------------------------------------------

def get_projection_accuracy_summary(
    session: Session,
    version_id: int,
) -> dict:
    """Compute aggregate accuracy stats for a prediction version.

    Returns a dict with MAE, RMSE, coverage, count, per-position breakdown.
    Only considers projections where actual_points is populated.
    """
    rows = (
        session.query(Projection)
        .filter_by(version_id=version_id)
        .filter(Projection.actual_points.isnot(None))
        .all()
    )

    if not rows:
        return {"count": 0, "mae": None, "rmse": None}

    errors = [abs(r.projected_points - r.actual_points) for r in rows]
    squared_errors = [(r.projected_points - r.actual_points) ** 2 for r in rows]

    mae = sum(errors) / len(errors)
    rmse = (sum(squared_errors) / len(squared_errors)) ** 0.5

    ci_80_hits = sum(
        1 for r in rows
        if r.ci_80_low is not None and r.ci_80_high is not None
        and r.ci_80_low <= r.actual_points <= r.ci_80_high
    )
    ci_95_hits = sum(
        1 for r in rows
        if r.ci_95_low is not None and r.ci_95_high is not None
        and r.ci_95_low <= r.actual_points <= r.ci_95_high
    )

    return {
        "count": len(rows),
        "mae": round(mae, 3),
        "rmse": round(rmse, 3),
        "coverage_80": round(ci_80_hits / len(rows), 3) if rows else 0,
        "coverage_95": round(ci_95_hits / len(rows), 3) if rows else 0,
        "bias": round(sum(r.projected_points - r.actual_points for r in rows) / len(rows), 3),
    }


# ---------------------------------------------------------------------------
# Validation Platform CRUD
# ---------------------------------------------------------------------------


def insert_validation_metrics(session: Session, data: dict) -> ValidationMetrics:
    """Insert a ValidationMetrics row (computed by Validation Engine)."""
    row = ValidationMetrics(**data)
    session.add(row)
    session.flush()
    return row


def get_validation_metrics(
    session: Session,
    version_id: int | None = None,
    gameweek_id: int | None = None,
) -> list[ValidationMetrics]:
    """Fetch validation metrics, optionally filtered by version or GW."""
    q = session.query(ValidationMetrics)
    if version_id is not None:
        q = q.filter_by(version_id=version_id)
    if gameweek_id is not None:
        q = q.filter_by(gameweek_id=gameweek_id)
    return q.order_by(ValidationMetrics.gameweek_id).all()


def insert_error_classifications(session: Session, rows_data: list[dict]) -> int:
    """Bulk insert ErrorClassification rows."""
    if not rows_data:
        return 0
    rows = [ErrorClassification(**d) for d in rows_data]
    session.add_all(rows)
    session.flush()
    return len(rows)


def get_error_classifications(
    session: Session,
    version_id: int | None = None,
    gameweek_id: int | None = None,
    error_type: str | None = None,
) -> list[ErrorClassification]:
    """Fetch error classifications, optionally filtered."""
    q = session.query(ErrorClassification)
    if version_id is not None:
        q = q.filter_by(version_id=version_id)
    if gameweek_id is not None:
        q = q.filter_by(gameweek_id=gameweek_id)
    if error_type is not None:
        q = q.filter_by(error_type=error_type)
    return q.all()


def insert_recommendation_outcome(session: Session, data: dict) -> RecommendationOutcome:
    """Insert a RecommendationOutcome row."""
    row = RecommendationOutcome(**data)
    session.add(row)
    session.flush()
    return row


def get_recommendation_outcomes(
    session: Session,
    version_id: int | None = None,
    gameweek_id: int | None = None,
    recommendation_type: str | None = None,
) -> list[RecommendationOutcome]:
    """Fetch recommendation outcomes, optionally filtered."""
    q = session.query(RecommendationOutcome)
    if version_id is not None:
        q = q.filter_by(version_id=version_id)
    if gameweek_id is not None:
        q = q.filter_by(gameweek_id=gameweek_id)
    if recommendation_type is not None:
        q = q.filter_by(recommendation_type=recommendation_type)
    return q.all()


def insert_engine_accuracy(session: Session, data: dict) -> EngineAccuracy:
    """Insert an EngineAccuracy row."""
    row = EngineAccuracy(**data)
    session.add(row)
    session.flush()
    return row


def get_engine_accuracy(
    session: Session,
    version_id: int | None = None,
    gameweek_id: int | None = None,
    engine_name: str | None = None,
) -> list[EngineAccuracy]:
    """Fetch engine accuracy metrics, optionally filtered."""
    q = session.query(EngineAccuracy)
    if version_id is not None:
        q = q.filter_by(version_id=version_id)
    if gameweek_id is not None:
        q = q.filter_by(gameweek_id=gameweek_id)
    if engine_name is not None:
        q = q.filter_by(engine_name=engine_name)
    return q.all()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _position_label(element_type: int) -> str:
    return POSITION_MAP.get(element_type, "UNK")
