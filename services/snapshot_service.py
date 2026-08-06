"""Snapshot Service — persists pipeline output to the Prediction Ledger.

This is the bridge between the in-memory pipeline and the database.
Every pipeline run creates a PredictionVersion and bulk-inserts Projection
rows. Nothing is ever updated — everything is append-only.

Usage::

    from services.snapshot_service import persist_pipeline_result

    version_id = persist_pipeline_result(
        session=session,
        pipeline_result=result,
        model_name="projection_v2",
    )
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from database.crud import (
    create_prediction_version,
    get_prediction_version_by_tag,
    insert_player_snapshots_bulk,
    insert_projections_bulk,
)
from utils.config import get_config_hash

logger = logging.getLogger(__name__)


def persist_pipeline_result(
    session: Session,
    pipeline_result,
    model_name: str = "projection_v2",
    notes: str | None = None,
) -> int:
    """Persist a PipelineResult to the Prediction Ledger.

    Parameters
    ----------
    session : Session
        SQLAlchemy session (caller is responsible for commit/rollback).
    pipeline_result : PipelineResult
        Output of ``run_projection_pipeline()``.
    model_name : str
        Name of the model that produced these projections.
    notes : str, optional
        Human-readable notes for this prediction version.

    Returns
    -------
    int
        The version_id of the created PredictionVersion row.
    """
    # 1. Check for duplicate version_tag (idempotency guard)
    existing = get_prediction_version_by_tag(session, pipeline_result.version_tag)
    if existing is not None:
        logger.info(
            "PredictionVersion %s already exists (id=%d), skipping persist",
            pipeline_result.version_tag, existing.id,
        )
        return existing.id

    # 2. Create PredictionVersion
    config_hash = pipeline_result.config_hash
    weights_snapshot = _capture_weights()
    features_used = _capture_feature_list()

    pv = create_prediction_version(
        session=session,
        version_tag=pipeline_result.version_tag,
        model_name=model_name,
        config_hash=config_hash,
        features_used=features_used,
        weights_snapshot=weights_snapshot,
        notes=notes or f"Pipeline run for gw={pipeline_result.gameweek_id}",
    )

    # 3. Bulk-insert Projection rows
    projections = pipeline_result.projections
    if projections:
        n_inserted = insert_projections_bulk(
            session=session,
            version_id=pv.id,
            projections=projections,
        )
        logger.info(
            "Persisted %d projections for version=%s (id=%d)",
            n_inserted, pipeline_result.version_tag, pv.id,
        )
    else:
        logger.warning("No projections to persist for version=%s", pipeline_result.version_tag)

    # 4. Store PlayerSnapshot records (pre-GW snapshot of player state)
    _persist_player_snapshots(session, pipeline_result)

    return pv.id


def persist_predictions_only(
    session: Session,
    version_tag: str,
    model_name: str,
    gameweek_id: int,
    projections: list,
    config_hash: str | None = None,
    notes: str | None = None,
) -> int:
    """Persist predictions without a full PipelineResult.

    Useful when running engines individually (e.g., testing).
    """
    existing = get_prediction_version_by_tag(session, version_tag)
    if existing is not None:
        return existing.id

    pv = create_prediction_version(
        session=session,
        version_tag=version_tag,
        model_name=model_name,
        config_hash=config_hash or get_config_hash("prediction"),
        features_used=_capture_feature_list(),
        weights_snapshot=_capture_weights(),
        notes=notes,
    )

    insert_projections_bulk(session, pv.id, projections)
    return pv.id


def mark_actuals(
    session: Session,
    version_id: int,
    gameweek_id: int,
    actuals: dict[int, int],
) -> int:
    """Attach actual points to persisted projections.

    Parameters
    ----------
    session : Session
    version_id : int
        The prediction version to update.
    gameweek_id : int
        The gameweek that just finished.
    actuals : dict[int, int]
        player_id → actual FPL points.

    Returns
    -------
    int
        Number of projections updated.
    """
    from database.crud import update_projection_actuals_bulk

    n = update_projection_actuals_bulk(session, version_id, gameweek_id, actuals)
    if n > 0:
        logger.info(
            "Marked %d actuals for version_id=%d, gw=%d",
            n, version_id, gameweek_id,
        )
    return n


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _persist_player_snapshots(
    session: Session,
    pipeline_result,
) -> None:
    """Create PlayerSnapshot rows from the pipeline's FeatureStore data.

    This captures the point-in-time state of every player at the moment
    the projection was made.
    """
    if not hasattr(pipeline_result, '_store') or pipeline_result._store is None:
        return

    store = pipeline_result._store
    df = store.df
    snapshots = []

    # Validate player_id column exists (canonicalized by build_feature_store)
    if "player_id" not in df.columns:
        logger.warning("store.df has no player_id column — skipping snapshot persist")
        return

    for _, row in df.iterrows():
        player_id = int(row.get("player_id", 0) or 0)
        if player_id == 0:
            logger.warning("Skipping snapshot row with player_id=0 (web_name=%s)", row.get("web_name", "unknown"))
            continue

        snapshots.append({
            "player_id": player_id,
            "gameweek_id": pipeline_result.gameweek_id,
            "snapshot_type": "pre",
            "now_cost": int(row.get("price", 0) * 10),
            "total_points": int(row.get("total_points", 0)),
            "minutes": int(row.get("minutes", 0)),
            "goals_scored": int(row.get("goals_scored", 0)),
            "assists": int(row.get("assists", 0)),
            "clean_sheets": int(row.get("clean_sheets", 0)),
            "goals_conceded": 0,  # not carried through FeatureStore
            "expected_goals": float(row.get("expected_goals", 0) or 0),
            "expected_assists": float(row.get("expected_assists", 0) or 0),
            "expected_goal_involvements": float(row.get("expected_goal_involvements", 0) or 0),
            "expected_goals_conceded": float(row.get("expected_goals_conceded", 0) or 0),
            "form": float(row.get("form", 0) or 0),
            "selected_by_percent": float(row.get("selected_by_percent", 0) or 0),
            "influence": float(row.get("influence", 0) or 0),
            "creativity": float(row.get("creativity", 0) or 0),
            "threat": float(row.get("threat", 0) or 0),
            "ict_index": float(row.get("ict_index", 0) or 0),
            "status": str(row.get("status", "a") or "a"),
            "news": str(row.get("news", "") or ""),
            "chance_of_playing_next_round": None,  # not in FeatureStore
            "chance_of_playing_this_round": None,  # not in FeatureStore
            "transfers_in_event": int(row.get("transfers_in_event", 0) or 0),
            "transfers_out_event": int(row.get("transfers_out_event", 0) or 0),
            "xgi_per_90": float(row.get("xgi_per_90", 0) or 0),
            "minutes_fraction": float(row.get("minutes_fraction", 0) or 0),
            "team_strength_raw": float(row.get("team_strength_raw", 100) or 100),
            "fixture_score_raw": float(row.get("fixture_score_raw", 50) or 50),
            "set_piece_raw": float(row.get("set_piece_raw", 0) or 0),
        })

    if snapshots:
        insert_player_snapshots_bulk(session, snapshots)


def _capture_weights() -> dict:
    """Snapshot the current weights for traceability."""
    from utils.constants import WEIGHTS
    return dict(WEIGHTS)


def _capture_feature_list() -> list[str]:
    """List the feature categories available in the FeatureStore."""
    return [
        "minutes", "xgi", "fixture", "value",
        "market", "availability", "set_piece", "trend",
    ]
