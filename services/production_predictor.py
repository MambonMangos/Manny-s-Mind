"""Production Predictor — dispatches the primary and shadow prediction models.

Version 3 (Expected Points / xPts, ledger model ``expected_points_v1``) is the
primary production model. V2 (ledger model ``projection_v2``) and Model D
(V3-HIST-01, ledger model ``v3_hist_d_team``) run as *shadow / control* models.

This module is the single entry point production paths use so the
primary/shadow split is always config-driven (see ``config/production/``).
Never hard-code a model id in a service or page — read it from the production
config via ``get_primary_model_id`` / ``get_shadow_model_ids``.

Design contract:
  - Append-only: every persisted run creates a new PredictionVersion row;
    nothing is ever updated or deleted.
  - Shadow models are never removed. They keep being validated against V3 over
    time (accuracy, calibration, bias, drift).

Usage::

    from services.production_predictor import run_production_predictions

    result = run_production_predictions(
        store=store, gameweek_id=5, session=session, persist=True,
    )
    print(result.primary.model_id, result.summary())
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from utils.config import get_primary_model_id, get_shadow_model_ids

logger = logging.getLogger(__name__)


@dataclass
class ModelRun:
    """Result of running one prediction model for one gameweek."""

    model_id: str
    projections: list = field(default_factory=list)
    version_id: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.projections)


@dataclass
class ProductionPredictionResult:
    """Complete primary + shadow prediction output for one gameweek."""

    gameweek_id: int
    primary_model_id: str
    primary: ModelRun | None = None
    shadows: list[ModelRun] = field(default_factory=list)
    persisted: bool = False

    def summary(self) -> dict:
        """Short dict for logs / UI headers."""
        return {
            "gameweek_id": self.gameweek_id,
            "primary_model": self.primary_model_id,
            "primary_projections": len(self.primary.projections) if self.primary else 0,
            "primary_version_id": self.primary.version_id if self.primary else None,
            "shadows": [
                {
                    "model_id": s.model_id,
                    "n_projections": len(s.projections),
                    "version_id": s.version_id,
                    "error": s.error,
                }
                for s in self.shadows
            ],
            "persisted": self.persisted,
        }


def load_persisted_projections(
    session: Session,
    gameweek_id: int | None = None,
    model_id: str | None = None,
) -> dict[int, float]:
    """Load the latest persisted projection points for a ledger model.

    model_id defaults to the configured primary production model. Iterates the
    most recent prediction versions and returns the first non-empty map as
    ``{player_id: projected_points}`` (empty dict when nothing is persisted).

    This is the cheap, DB-only way for UI pages to consume production (V3)
    projections without re-running the projection engines.
    """
    from database.crud import get_prediction_versions, get_projections

    if model_id is None:
        model_id = get_primary_model_id()

    versions = get_prediction_versions(session, model_name=model_id, limit=20)
    for pv in versions:
        proj_list = get_projections(session, pv.id, gameweek_id)
        if not proj_list:
            continue
        return {int(p.player_id): float(p.projected_points) for p in proj_list}
    return {}


def run_production_predictions(
    store,
    gameweek_id: int = 0,
    session: Session | None = None,
    persist: bool = True,
    current_squad: list[int] | None = None,
    budget_remaining: float = 0.0,
) -> ProductionPredictionResult:
    """Run the primary production model plus all shadow models.

    Parameters
    ----------
    store : FeatureStore
        Pre-built feature store.
    gameweek_id : int
        Target gameweek.
    session : Session, optional
        SQLAlchemy session. Required when persist=True.
    persist : bool
        If True, write each model's forecasts to the Prediction Ledger
        (append-only; duplicates by version tag are skipped).
    current_squad : list[int], optional
        Current squad player_ids (used by the V2 shadow pipeline).
    budget_remaining : float
        Remaining budget in millions.

    Returns
    -------
    ProductionPredictionResult
        Primary projection run plus one run per configured shadow model.
    """
    primary_model_id = get_primary_model_id()

    result = ProductionPredictionResult(
        gameweek_id=gameweek_id,
        primary_model_id=primary_model_id,
    )

    result.primary = run_model(
        store=store,
        gameweek_id=gameweek_id,
        model_id=primary_model_id,
        session=session,
        persist=persist,
        current_squad=current_squad,
        budget_remaining=budget_remaining,
    )

    for shadow_id in get_shadow_model_ids():
        if shadow_id == primary_model_id:
            logger.warning("Shadow model %s equals primary — skipping", shadow_id)
            continue
        result.shadows.append(
            run_model(
                store=store,
                gameweek_id=gameweek_id,
                model_id=shadow_id,
                session=session,
                persist=persist,
                current_squad=current_squad,
                budget_remaining=budget_remaining,
            )
        )

    result.persisted = persist and result.primary.version_id is not None
    logger.info(
        "Production predictions gw=%d: primary=%s (%d projections), "
        "%d shadow run(s) → %s",
        gameweek_id,
        primary_model_id,
        len(result.primary.projections),
        len(result.shadows),
        [s.model_id for s in result.shadows],
    )
    return result


def run_model(
    store,
    gameweek_id: int,
    model_id: str,
    session: Session | None = None,
    persist: bool = False,
    current_squad: list[int] | None = None,
    budget_remaining: float = 0.0,
) -> ModelRun:
    """Run a single prediction model by ledger model id.

    Supported model ids:
      - ``expected_points_v1`` — V3 xPts projection (production primary).
      - ``projection_v2`` — V2 projection pipeline (shadow / control).

    Unknown model ids raise ValueError so misconfiguration is loud, never
    silently ignored.
    """
    if model_id == "expected_points_v1":
        return _run_expected_points(
            store,
            gameweek_id,
            session=session,
            persist=persist,
        )
    if model_id == "projection_v2":
        return _run_projection_v2(
            store,
            gameweek_id,
            session=session,
            persist=persist,
            current_squad=current_squad,
            budget_remaining=budget_remaining,
        )
    if model_id == "v3_hist_d_team":
        return _run_v3_hist_d_team(
            store,
            gameweek_id,
            session=session,
            persist=persist,
        )
    raise ValueError(
        f"Unsupported production model id: {model_id!r} "
        "(expected 'expected_points_v1', 'projection_v2', or 'v3_hist_d_team')"
    )


def _run_expected_points(store, gameweek_id, session, persist) -> ModelRun:
    """Run the V3 expected-points projection and optionally persist it."""
    from engines.expected_projection_engine import run_expected_projection

    try:
        projections = run_expected_projection(store, gameweek_id)
        version_id = None
        if persist and session is not None:
            from services.expected_pipeline import persist_expected_version

            version_id = persist_expected_version(
                session,
                store,
                projections,
                gameweek_id,
            )
            session.commit()
        return ModelRun(
            model_id="expected_points_v1",
            projections=projections,
            version_id=version_id,
        )
    except Exception as exc:  # noqa: BLE001 - a failed model must not crash the app
        logger.warning("V3 expected-points projection failed: %s", exc)
        return ModelRun(model_id="expected_points_v1", error=str(exc))


def _run_projection_v2(
    store,
    gameweek_id,
    session,
    persist,
    current_squad,
    budget_remaining,
) -> ModelRun:
    """Run the V2 projection pipeline as a shadow model and optionally persist it."""
    from services.pipeline import run_projection_pipeline

    try:
        result = run_projection_pipeline(
            store=store,
            gameweek_id=gameweek_id,
            current_squad=current_squad,
            budget_remaining=budget_remaining,
            session=session,
            persist=persist,
        )
        return ModelRun(
            model_id="projection_v2",
            projections=result.projections,
            version_id=result.version_id,
        )
    except Exception as exc:  # noqa: BLE001 - a failed shadow must not crash the app
        logger.warning("V2 shadow pipeline failed: %s", exc)
        return ModelRun(model_id="projection_v2", error=str(exc))


def _run_v3_hist_d_team(store, gameweek_id, session, persist) -> ModelRun:
    """Run Model D (V3 + hist features) as a shadow model and optionally persist it."""
    from engines.expected_projection_engine import run_expected_projection

    try:
        projections = run_expected_projection(
            store,
            gameweek_id,
            points_version="expected_points_v1_hist",
            minutes_version="expected_minutes_v1_hist",
        )
        version_id = None
        if persist and session is not None:
            from services.expected_pipeline import persist_expected_version

            version_id = persist_expected_version(
                session,
                store,
                projections,
                gameweek_id,
                model_name="v3_hist_d_team",
            )
            session.commit()
        return ModelRun(
            model_id="v3_hist_d_team",
            projections=projections,
            version_id=version_id,
        )
    except Exception as exc:  # noqa: BLE001 - a failed shadow must not crash the app
        logger.warning("V3 hist D-team shadow failed: %s", exc)
        return ModelRun(model_id="v3_hist_d_team", error=str(exc))
