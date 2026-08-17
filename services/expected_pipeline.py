"""Expected Points Pipeline — runs the V3 xPts model side-by-side with V2.

This service orchestrates the next-generation model without touching any
production behaviour:

  1. Runs the V3 expected projection (xPts/90 x expected minutes / 90).
  2. Runs the existing V2 pipeline as the baseline.
  3. Produces an in-memory alignment report (no actuals required).
  4. Optionally persists the V3 forecast as its own append-only prediction
     version, so it can be validated and compared through the existing
     validation platform once actuals arrive.

Usage::

    from services.expected_pipeline import run_expected_points_comparison

    result = run_expected_points_comparison(
        store=store, session=session, gameweek_id=5, persist=True,
    )
    print(result.alignment)

    # Post-gameweek:
    from services.expected_pipeline import compare_expected_vs_baseline
    comparison = compare_expected_vs_baseline(
        session, result.baseline_version_id, result.expected_version_id,
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from engines.expected_points_engine import compute_expected_points_version_tag
from engines.expected_projection_engine import (
    ExpectedPlayerProjection,
    compare_to_v2,
    run_expected_projection,
)
from services.pipeline import run_projection_pipeline
from utils.config import get_config_hash

logger = logging.getLogger(__name__)


@dataclass
class ExpectedComparisonResult:
    """Side-by-side V2 vs V3 comparison for one gameweek."""

    gameweek_id: int
    expected_projections: list = field(default_factory=list)
    baseline_projections: list = field(default_factory=list)
    alignment: dict = field(default_factory=dict)

    # Persistence (set when persist=True and a session is provided)
    baseline_version_id: int | None = None
    expected_version_id: int | None = None
    persisted: bool = False

    def summary(self) -> dict:
        """Return a short summary for logs / UI."""
        return {
            "gameweek_id": self.gameweek_id,
            "n_expected_projections": len(self.expected_projections),
            "n_baseline_projections": len(self.baseline_projections),
            "alignment": self.alignment,
            "persisted": self.persisted,
            "baseline_version_id": self.baseline_version_id,
            "expected_version_id": self.expected_version_id,
        }


def run_expected_points_comparison(
    store,
    gameweek_id: int = 0,
    session=None,
    persist: bool = False,
    baseline_result=None,
) -> ExpectedComparisonResult:
    """Run the V3 xPts model alongside the V2 baseline for comparison.

    Parameters
    ----------
    store : FeatureStore
        Pre-built feature store.
    gameweek_id : int
        Target gameweek.
    session : Session, optional
        SQLAlchemy session. Required when persist=True.
    persist : bool
        If True, persist both baseline (V2) and expected (V3) versions.
    baseline_result : PipelineResult, optional
        Pre-built V2 pipeline result. If None, the baseline pipeline is run.

    Returns
    -------
    ExpectedComparisonResult
        Projections, alignment report and persisted version IDs.
    """
    # 1. V3 expected projection
    logger.info("Running V3 expected projection for gw=%d", gameweek_id)
    expected_projections = run_expected_projection(store, gameweek_id)

    # 2. V2 baseline
    if baseline_result is None:
        logger.info("Running V2 baseline pipeline for gw=%d", gameweek_id)
        baseline_result = run_projection_pipeline(
            store=store,
            gameweek_id=gameweek_id,
            session=session,
            persist=persist,
        )
    baseline_projections = baseline_result.projections

    # 3. In-memory alignment report
    alignment = compare_to_v2(expected_projections, baseline_projections)
    logger.info("V2-vs-V3 alignment: %s", alignment)

    result = ExpectedComparisonResult(
        gameweek_id=gameweek_id,
        expected_projections=expected_projections,
        baseline_projections=baseline_projections,
        alignment=alignment,
        baseline_version_id=baseline_result.version_id,
    )

    # 4. Persist the V3 version (idempotent, append-only)
    if persist and session is not None:
        expected_version_id = persist_expected_version(
            session,
            store,
            expected_projections,
            gameweek_id,
        )
        result.expected_version_id = expected_version_id
        result.persisted = True
        session.commit()
        logger.info("Persisted expected version id=%d", expected_version_id)
    elif persist and session is None:
        logger.warning("persist=True but no session provided — V3 not persisted")

    return result


def persist_expected_version(
    session,
    store,
    expected_projections: list[ExpectedPlayerProjection],
    gameweek_id: int,
    *,
    model_name: str = "expected_points_v1",
) -> int:
    """Persist the V3 forecast as an append-only prediction version.

    Idempotent: if a version with the same tag already exists, its id is
    returned and nothing is written. Public entry point used by the production
    predictor so all V3 persistence flows through one code path.

    ``model_name`` allows shadow models (e.g. ``v3_hist_d_team``) to persist
    under their own ledger name while reusing the same projection format.
    """
    return _persist_expected_version(
        session,
        store,
        expected_projections,
        gameweek_id,
        model_name=model_name,
    )


def compare_expected_vs_baseline(
    session,
    baseline_version_id: int,
    expected_version_id: int,
    gameweek_ids: list[int] | None = None,
) -> dict:
    """Compare validated V2 baseline vs V3 expected via the validation platform.

    Requires validation metrics to exist for both versions (i.e. actuals have
    been injected and ``validate_version`` run). Delegates to the existing
    validation engine's ``compare_versions``.
    """
    from engines.validation_engine import compare_versions

    return compare_versions(
        session,
        baseline_version_id,
        expected_version_id,
        gameweek_ids,
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _persist_expected_version(
    session,
    store,
    expected_projections: list[ExpectedPlayerProjection],
    gameweek_id: int,
    *,
    model_name: str = "expected_points_v1",
) -> int:
    """Persist the V3 forecast as its own append-only prediction version."""
    from database.crud import get_prediction_version_by_tag
    from services.snapshot_service import persist_predictions_only

    config_hash = get_config_hash("expected_points")
    version_tag = compute_expected_points_version_tag(gameweek_id, config_hash)

    existing = get_prediction_version_by_tag(session, version_tag)
    if existing is not None:
        logger.info(
            "Expected version %s already exists (id=%d), skipping",
            version_tag,
            existing.id,
        )
        return existing.id

    version_id = persist_predictions_only(
        session=session,
        version_tag=version_tag,
        model_name=model_name,
        gameweek_id=gameweek_id,
        projections=expected_projections,
        config_hash=config_hash,
        notes=f"V3 expected points projection ({model_name}) for gw={gameweek_id}",
    )
    return version_id
