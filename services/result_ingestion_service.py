"""Result Ingestion Service — fetches actual FPL results after a gameweek finishes.

This service is triggered manually from the UI (button on Analytics Dashboard).
It detects finished gameweeks, fetches actual player stats, and attaches them
to the Prediction Ledger. Idempotent — running twice for the same GW is safe.

Usage::

    from services.result_ingestion_service import ingest_gameweek_results

    report = ingest_gameweek_results(session, gameweek_id=1)
    print(report)  # {"status": "ok", "n_actuals": 500, "n_versions_updated": 1}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database.crud import (
    get_latest_version_for_gw,
    get_prediction_versions,
    get_projections,
    update_projection_actuals_bulk,
    update_prediction_version_metrics,
)
from database.models import Gameweek, PlayerGameweekStat, Projection
from services.api_client import fpl_get

logger = logging.getLogger(__name__)


@dataclass
class IngestionReport:
    """Result of a result ingestion run."""

    gameweek_id: int
    status: str  # "ok", "no_data", "error", "already_ingested"
    n_actuals: int = 0  # player actual points fetched
    n_projections_updated: int = 0  # Projection rows updated with actuals
    n_versions_updated: int = 0  # PredictionVersion rows with metrics computed
    n_gw_stats_inserted: int = 0  # PlayerGameweekStat rows created
    error_message: str = ""
    duration_ms: float = 0
    details: dict = field(default_factory=dict)


def ingest_gameweek_results(
    session: Session,
    gameweek_id: int,
) -> IngestionReport:
    """Fetch actual FPL results for a finished gameweek and attach to Prediction Ledger.

    Parameters
    ----------
    session : Session
        SQLAlchemy session.
    gameweek_id : int
        The gameweek to ingest results for.

    Returns
    -------
    IngestionReport
        Summary of what was ingested.
    """
    import time
    start = time.time()

    report = IngestionReport(gameweek_id=gameweek_id, status="ok")

    # 1. Check if gameweek is actually finished
    gw = session.get(Gameweek, gameweek_id)
    if gw is None:
        report.status = "error"
        report.error_message = f"Gameweek {gameweek_id} not found in database"
        return report

    if not gw.finished:
        report.status = "error"
        report.error_message = f"Gameweek {gameweek_id} has not finished yet"
        return report

    # 2. Fetch fresh player data from FPL API
    try:
        raw = fpl_get("/bootstrap-static/")
        players_raw = {p["id"]: p for p in raw.get("elements", [])}
    except Exception:
        report.status = "error"
        report.error_message = "Failed to fetch FPL API data. See application logs."
        logger.exception("Result ingestion failed")
        return report

    # 3. Build actual points dict: player_id → event_points
    actuals: dict[int, int] = {}
    for pid, pdata in players_raw.items():
        event_points = pdata.get("event_points", 0) or 0
        actuals[pid] = int(event_points)

    report.n_actuals = len(actuals)
    logger.info("Fetched actual points for %d players (gw=%d)", len(actuals), gameweek_id)

    # 4. Update all PredictionVersions that have projections for this GW
    versions = get_prediction_versions(session)
    for pv in versions:
        # Check if this version has projections for this GW
        projections = get_projections(session, pv.id, gameweek_id)
        if not projections:
            continue

        # Check if already ingested (idempotency)
        already_has_actuals = any(
            p.actual_points is not None for p in projections
        )
        if already_has_actuals:
            logger.info(
                "Version %s already has actuals for gw=%d, skipping",
                pv.version_tag, gameweek_id,
            )
            continue

        # Update actual_points on each Projection row
        n_updated = update_projection_actuals_bulk(
            session, pv.id, gameweek_id, actuals,
        )
        report.n_projections_updated += n_updated

        # Compute accuracy metrics for this version + GW
        _compute_and_store_version_metrics(session, pv.id, gameweek_id)
        report.n_versions_updated += 1

        logger.info(
            "Updated version %s: %d actuals for gw=%d",
            pv.version_tag, n_updated, gameweek_id,
        )

    # 5. Insert PlayerGameweekStat rows (detailed per-GW stats)
    n_stats = _insert_gameweek_stats(session, gameweek_id, players_raw)
    report.n_gw_stats_inserted = n_stats

    report.duration_ms = (time.time() - start) * 1000

    logger.info(
        "Result ingestion complete for gw=%d: %d actuals, %d projections updated, "
        "%d versions updated, %d stats inserted, %.0fms",
        gameweek_id, report.n_actuals, report.n_projections_updated,
        report.n_versions_updated, report.n_gw_stats_inserted, report.duration_ms,
    )

    return report


def detect_finished_gameweeks(session: Session) -> list[int]:
    """Return a list of gameweek IDs that are finished but not yet ingested.

    Useful for the UI to show which GWs need ingestion.
    """
    finished_gws = (
        session.query(Gameweek)
        .filter_by(finished=True, data_checked=True)
        .order_by(Gameweek.id)
        .all()
    )

    result = []
    for gw in finished_gws:
        # Check if any projections exist for this GW
        projections = (
            session.query(Projection)
            .filter_by(gameweek_id=gw.id)
            .first()
        )
        if projections is None:
            continue

        # Check if already ingested
        has_actuals = (
            session.query(Projection)
            .filter_by(gameweek_id=gw.id)
            .filter(Projection.actual_points.isnot(None))
            .first()
        )
        if has_actuals is None:
            result.append(gw.id)

    return result


def get_ingestion_status(session: Session) -> list[dict]:
    """Return ingestion status for all gameweeks with projections.

    Used by the Analytics Dashboard to show what needs to be ingested.
    """
    gws_with_projections = (
        session.query(Projection.gameweek_id)
        .distinct()
        .all()
    )

    results = []
    for (gw_id,) in gws_with_projections:
        gw = session.get(Gameweek, gw_id)
        total_projections = (
            session.query(Projection)
            .filter_by(gameweek_id=gw_id)
            .count()
        )
        ingested = (
            session.query(Projection)
            .filter_by(gameweek_id=gw_id)
            .filter(Projection.actual_points.isnot(None))
            .count()
        )

        results.append({
            "gameweek_id": gw_id,
            "finished": gw.finished if gw else False,
            "data_checked": gw.data_checked if gw else False,
            "total_projections": total_projections,
            "ingested": ingested,
            "pending": total_projections - ingested,
            "status": "ingested" if ingested == total_projections and ingested > 0
                      else "pending" if gw and gw.finished
                      else "in_progress" if gw and not gw.finished
                      else "unknown",
        })

    return results


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _compute_and_store_version_metrics(
    session: Session,
    version_id: int,
    gameweek_id: int,
) -> None:
    """Compute accuracy metrics for a version + GW and store on PredictionVersion."""
    rows = (
        session.query(Projection)
        .filter_by(version_id=version_id, gameweek_id=gameweek_id)
        .filter(Projection.actual_points.isnot(None))
        .all()
    )

    if not rows:
        return

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

    # Update the PredictionVersion with these metrics
    update_prediction_version_metrics(
        session,
        version_id,
        mae=mae,
        rmse=rmse,
        coverage_80=ci_80_hits / len(rows),
        coverage_95=ci_95_hits / len(rows),
    )


def _insert_gameweek_stats(
    session: Session,
    gameweek_id: int,
    players_raw: dict,
) -> int:
    """Insert PlayerGameweekStat rows from FPL API data."""
    # Check if stats already exist (idempotency)
    existing = (
        session.query(PlayerGameweekStat)
        .filter_by(gameweek_id=gameweek_id)
        .first()
    )
    if existing is not None:
        logger.info("PlayerGameweekStat already exists for gw=%d, skipping", gameweek_id)
        return 0

    rows = []
    for pid, pdata in players_raw.items():
        # Only insert players who actually played this GW
        event_minutes = pdata.get("minutes", 0)
        if event_minutes == 0:
            continue

        row = PlayerGameweekStat(
            player_id=pid,
            gameweek_id=gameweek_id,
            opponent_team=pdata.get("opponent_team"),
            was_home=pdata.get("was_home"),
            minutes=event_minutes,
            goals_scored=pdata.get("goals_scored", 0),
            assists=pdata.get("assists", 0),
            clean_sheets=pdata.get("clean_sheets", 0),
            goals_conceded=pdata.get("goals_conceded", 0),
            own_goals=pdata.get("own_goals", 0),
            penalties_saved=pdata.get("penalties_saved", 0),
            penalties_missed=pdata.get("penalties_missed", 0),
            yellow_cards=pdata.get("yellow_cards", 0),
            red_cards=pdata.get("red_cards", 0),
            saves=pdata.get("saves", 0),
            bonus=pdata.get("bonus", 0),
            bps=pdata.get("bps", 0),
            influence=float(pdata.get("influence", 0) or 0),
            creativity=float(pdata.get("creativity", 0) or 0),
            threat=float(pdata.get("threat", 0) or 0),
            ict_index=float(pdata.get("ict_index", 0) or 0),
            total_points=pdata.get("total_points", 0),
            expected_goals=float(pdata.get("expected_goals", 0) or 0),
            expected_assists=float(pdata.get("expected_assists", 0) or 0),
            expected_goal_involvements=float(pdata.get("expected_goal_involvements", 0) or 0),
            expected_goals_conceded=float(pdata.get("expected_goals_conceded", 0) or 0),
            value=float(pdata.get("now_cost", 0) or 0) / 10.0,
            selected=float(pdata.get("selected_by_percent", 0) or 0),
            transfers_in=pdata.get("transfers_in_event", 0),
            transfers_out=pdata.get("transfers_out_event", 0),
        )
        rows.append(row)

    if rows:
        session.add_all(rows)
        session.flush()
        logger.info("Inserted %d PlayerGameweekStat rows for gw=%d", len(rows), gameweek_id)

    return len(rows)
