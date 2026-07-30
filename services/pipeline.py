"""Pipeline Orchestrator — chains all V2 engines into a single projection workflow.

This is the entry point for the V2 prediction system. It orchestrates:

  Data → Feature Store → Minutes → Fixtures → Regression →
  Market → Bookmaker → Projection → Confidence → Monte Carlo → Output

Usage::

    from services.pipeline import run_projection_pipeline
    from features import build_feature_store

    store = build_feature_store(players_df, fixture_map, team_name_map, gw)
    result = run_projection_pipeline(store, gameweek_id=gw)

    # result.projections — list of PlayerProjection
    # result.confidence — list of ConfidenceResult
    # result.simulation — SquadSimulationResult
    # result.opportunities — list of TransferOpportunity
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import pandas as pd

from features import FeatureStore
from utils.config import get_config_hash

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Complete output of the V2 projection pipeline."""

    # Core projections
    projections: list = field(default_factory=list)
    confidence: list = field(default_factory=list)

    # Adjusted projections (after regression + bookmaker)
    adjusted_projections: list = field(default_factory=list)

    # Simulations
    simulation: object = None  # SquadSimulationResult

    # Market & opportunity
    market_signals: list = field(default_factory=list)
    opportunities: list = field(default_factory=list)
    undervalued: list = field(default_factory=list)

    # Squad optimization
    squad_recommendation: object = None  # SquadRecommendation

    # Metadata
    gameweek_id: int = 0
    version_tag: str = ""
    config_hash: str = ""
    pipeline_duration_ms: float = 0

    # Persistence (set by pipeline when persist=True)
    version_id: int | None = None

    # Internal: reference to FeatureStore for snapshot persistence
    _store: object = field(default=None, repr=False, compare=False)

    def summary(self) -> dict:
        """Return a summary dict for UI display."""
        return {
            "gameweek_id": self.gameweek_id,
            "version_tag": self.version_tag,
            "n_projections": len(self.projections),
            "n_confidence": len(self.confidence),
            "n_market_signals": len(self.market_signals),
            "n_opportunities": len(self.opportunities),
            "n_undervalued": len(self.undervalued),
            "pipeline_duration_ms": round(self.pipeline_duration_ms, 1),
            "config_hash": self.config_hash[:12] if self.config_hash else "none",
            "version_id": self.version_id,
            "persisted": self.version_id is not None,
        }


def run_projection_pipeline(
    store: FeatureStore,
    gameweek_id: int = 0,
    current_squad: list[int] | None = None,
    budget_remaining: float = 0.0,
    odds_data: list | None = None,
    session=None,  # noqa: ANN001 — SQLAlchemy Session, optional
    persist: bool = False,
) -> PipelineResult:
    """Run the complete V2 projection pipeline.

    Parameters
    ----------
    store : FeatureStore
        Pre-built feature store.
    gameweek_id : int
        Target gameweek.
    current_squad : list[int], optional
        Current squad player_ids (for transfer recommendations).
    budget_remaining : float
        Remaining budget in millions.
    odds_data : list, optional
        Bookmaker odds (list of FixtureOdds).
    session : Session, optional
        SQLAlchemy session. Required when persist=True.
    persist : bool
        If True, write projections to the Prediction Ledger.

    Returns
    -------
    PipelineResult
        Complete pipeline output.
    """
    start_time = time.time()
    config_hash = get_config_hash("prediction")

    logger.info("Starting V2 projection pipeline for gw=%d", gameweek_id)

    # 1. Minutes Engine
    logger.info("Step 1/7: Minutes Engine")
    from engines.minutes_engine import compute_minutes_features
    minutes_df = compute_minutes_features(store)

    # 2. Projection Engine
    logger.info("Step 2/7: Projection Engine")
    from engines.projection_engine import project_all_players, compute_projection_version_tag
    projections = project_all_players(store, minutes_df, gameweek_id)

    # 3. Regression Engine
    logger.info("Step 3/7: Regression Engine")
    from engines.regression_engine import compute_regression_signals, apply_regression_adjustments
    regression_signals = compute_regression_signals(store)
    projections = apply_regression_adjustments(projections, regression_signals)

    # 4. Bookmaker Engine (if odds available)
    logger.info("Step 4/7: Bookmaker Engine")
    from engines.bookmaker_engine import project_from_odds, apply_bookmaker_adjustments
    if odds_data:
        from engines.bookmaker_engine import FixtureOdds
        bm_projections = project_from_odds(store, projections, odds_data)
        projections = apply_bookmaker_adjustments(projections, bm_projections)
    else:
        bm_projections = []

    # 5. Confidence Engine
    logger.info("Step 5/7: Confidence Engine")
    from engines.confidence_engine import compute_confidence_batch
    confidence = compute_confidence_batch(projections, store, minutes_df)

    # 6. Market Intelligence
    logger.info("Step 6/7: Market Intelligence")
    from engines.market_intelligence_engine import compute_market_signals
    market_signals = compute_market_signals(store)

    # 7. Opportunity Engine
    logger.info("Step 7/7: Opportunity Engine")
    from engines.opportunity_engine import find_undervalued_players, find_transfer_opportunities
    undervalued = find_undervalued_players(store, projections, market_signals)

    opportunities = []
    if current_squad:
        opportunities = find_transfer_opportunities(
            store, projections, current_squad, budget_remaining,
        )

    # 8. Monte Carlo (quick squad sim if we have a squad)
    logger.info("Bonus: Monte Carlo Simulation")
    simulation = None
    if current_squad:
        from engines.monte_carlo_engine import simulate_squad
        # Use top projected players as starting XI
        sorted_proj = sorted(projections, key=lambda p: p.projected_points, reverse=True)
        starting_xi = [p.player_id for p in sorted_proj[:11]]
        captain = sorted_proj[0].player_id if sorted_proj else 0
        simulation = simulate_squad(projections, starting_xi, captain)

    # 9. Squad Recommendation
    logger.info("Bonus: Squad Optimization")
    squad_rec = None
    from engines.squad_optimizer import get_squad_recommendation
    squad_rec = get_squad_recommendation(store, projections, current_squad, budget_remaining)

    # Assemble result
    version_tag = compute_projection_version_tag(gameweek_id, config_hash)
    duration_ms = (time.time() - start_time) * 1000

    result = PipelineResult(
        projections=projections,
        confidence=confidence,
        adjusted_projections=projections,  # same list after adjustments
        simulation=simulation,
        market_signals=market_signals,
        opportunities=opportunities,
        undervalued=undervalued,
        squad_recommendation=squad_rec,
        gameweek_id=gameweek_id,
        version_tag=version_tag,
        config_hash=config_hash,
        pipeline_duration_ms=duration_ms,
        _store=store,
    )

    # Persist to Prediction Ledger if requested
    if persist and session is not None:
        try:
            from services.snapshot_service import persist_pipeline_result
            version_id = persist_pipeline_result(session, result)
            result.version_id = version_id
            session.commit()
            logger.info("Pipeline results persisted: version_id=%d", version_id)
        except Exception as e:
            logger.error("Failed to persist pipeline results: %s", e)
            session.rollback()
    elif persist and session is None:
        logger.warning("persist=True but no session provided — skipping persistence")

    logger.info(
        "Pipeline complete: %d projections, %.0fms, version=%s",
        len(projections), duration_ms, version_tag,
    )

    return result
