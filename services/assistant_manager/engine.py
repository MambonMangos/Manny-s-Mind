"""Assistant Manager engine — main orchestrator.

Ties together all sub-engines (squad evaluation, transfer engine, hit
analysis, chip strategy, future planning, decision log, explainer) into
a single run that produces an AssistantReport.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from database.crud import get_players_dataframe
from engines.fixture_engine import build_fixture_map
from services.assistant_manager.chip_strategist import evaluate_chips
from services.assistant_manager.decision_log import get_chip_states, log_recommendation
from services.assistant_manager.explainer import (
    generate_executive_summary,
)
from services.assistant_manager.future_planner import plan_future
from services.assistant_manager.hit_analyzer import analyze_hit
from services.assistant_manager.models import (
    AssistantReport,
)
from services.assistant_manager.squad_evaluator import evaluate_squad
from services.assistant_manager.transfer_engine import generate_transfer_recommendations
from services.fixture_service import fetch_fixtures
from services.player_service import get_scored_players
from services.team_service import fetch_team_data, resolve_player_names
from utils.team_context import get_current_team_id

logger = logging.getLogger(__name__)


def run_assistant(
    session: Session,
    team_id: int | None = None,
    current_gameweek: int | None = None,
) -> AssistantReport:
    """Run the full Assistant Manager analysis.

    This is the single entry-point that the UI calls.
    It fetches all data, runs every sub-engine, logs recommendations,
    and returns a complete report.

    ``team_id`` is resolved from the session Team Context when omitted.
    """
    if team_id is None:
        team_id = get_current_team_id()
    if team_id is None:
        raise ValueError("No FPL team selected — onboarding required before running the Assistant Manager")
    logger.info("Running Assistant Manager for team %d", team_id)

    report = AssistantReport(
        team_id=team_id,
        generated_at=datetime.utcnow(),  # noqa: DTZ003 - naive UTC matches DB convention
        current_gameweek=current_gameweek,
    )

    # ── Fetch all data ────────────────────────────────────────────────────
    try:
        player_df = get_scored_players(session)
    except Exception as e:  # noqa: BLE001 - report must degrade gracefully, never crash
        logger.error("Failed to fetch player data: %s", e)
        return report

    if player_df.empty:
        logger.warning("No player data available")
        return report

    team_df = get_players_dataframe(session)
    team_name_map: dict[int, str] = {}
    if not team_df.empty and "team_id" in team_df.columns and "team_name" in team_df.columns:
        team_name_map = dict(zip(team_df["team_id"], team_df["team_name"]))

    fixtures_raw = fetch_fixtures()
    fixtures = []
    for f in fixtures_raw:
        fixtures.append({
            "event": f.event,
            "team_h": f.team_h,
            "team_a": f.team_a,
            "team_h_difficulty": f.team_h_difficulty,
            "team_a_difficulty": f.team_a_difficulty,
        })

    # ── Fetch team picks ──────────────────────────────────────────────────
    try:
        team_data = fetch_team_data(team_id, gameweeks=list(range(1, 39)))
    except Exception as e:  # noqa: BLE001 - report must degrade gracefully, never crash
        logger.error("Failed to fetch team data: %s", e)
        return report

    # Find the latest gameweek with picks
    picks_map = team_data.picks
    available_gws = sorted(picks_map.keys()) if picks_map else []

    if not available_gws:
        logger.info("No picks available yet (pre-season)")
        return report

    latest_gw = available_gws[-1]
    if current_gameweek is None:
        current_gameweek = latest_gw
    report.current_gameweek = current_gameweek

    gp = picks_map[latest_gw]
    squad_df = resolve_player_names(gp.picks, player_df)

    if squad_df.empty:
        logger.warning("Could not resolve squad picks")
        return report

    # ── Determine free transfers ──────────────────────────────────────────
    # FPL rules: 1 free transfer baseline, max 5 saved
    # Count transfers made this gameweek
    n_transfers_this_gw = sum(
        1 for t in team_data.transfers if t.event == current_gameweek
    )
    # Free transfers = 1 (baseline) minus transfers made, but minimum 0
    # If user made 0 transfers, they have 1 free transfer
    # If user made 1+ transfers, they used their free transfer(s)
    free_transfers = max(1 - n_transfers_this_gw, 0)
    # If they have 0 free transfers and made 0, they have 1
    if n_transfers_this_gw == 0:
        free_transfers = 1

    # Count transfers made in previous gameweeks to determine saved transfers
    previous_transfers = sum(
        1 for t in team_data.transfers
        if t.event < current_gameweek
    )
    # Simplified: assume 1 free transfer per GW, capped at 5
    saved_transfers = max(0, min(5, (current_gameweek - 1) - previous_transfers))

    # Determine bank from squad value
    # Bank = budget (100) - total squad value + transfer profits
    # Simplified: use the API data if available, otherwise 0
    bank = 0.0
    try:
        # Calculate from squad value
        if not squad_df.empty and "price" in squad_df.columns:
            total_squad_value = squad_df["price"].sum()
            # Bank is what's left from 100m budget after building squad
            # This is approximate - actual bank depends on transfer history
            bank = max(0, 100.0 - total_squad_value)
    except Exception as e:  # noqa: BLE001 - fall back to 0 bank, never crash the report
        logger.warning("Failed to calculate squad bank from squad data: %s", e)

    # ── Production Prediction Pipeline (V3 primary + V1/V2 shadow) ─────────
    # Runs the configured production model (V3 expected points) and persists
    # it append-only to the ledger; V1/V2 continue running as shadow (control)
    # models. All downstream recommendations consume the V3 projections when
    # available and fall back to the legacy value-score engines otherwise.
    fixture_map = build_fixture_map(fixtures)
    store = None
    try:
        from features import build_feature_store
        from services.production_predictor import run_production_predictions
        from utils.config import get_config_hash

        config_hash = get_config_hash("prediction")
        store = build_feature_store(
            players_df=player_df,
            fixture_map=fixture_map,
            team_name_map=team_name_map,
            gameweek_id=current_gameweek or 0,
            config_hash=config_hash,
        )

        current_squad_ids = list(squad_df["id"].values) if not squad_df.empty else []

        production = run_production_predictions(
            store=store,
            gameweek_id=current_gameweek or 0,
            session=session,
            persist=True,
            current_squad=current_squad_ids,
            budget_remaining=bank,
        )

        report.production_pipeline_result = production
        report.production_model_id = production.primary_model_id

        # V3 projections drive every downstream recommendation engine.
        if production.primary and production.primary.projections:
            proj_map = {
                int(p.player_id): float(p.projected_points)
                for p in production.primary.projections
            }
            player_df["projected_points"] = (
                player_df["id"].map(proj_map).fillna(0.0).round(2)
            )
            squad_df["projected_points"] = (
                squad_df["id"].map(proj_map).fillna(0.0).round(2)
            )
        logger.info(
            "Production predictions complete for gw=%d: %s",
            current_gameweek or 0, production.summary(),
        )
    except Exception as e:  # noqa: BLE001 - pipeline failure must never crash the report
        logger.warning("Production prediction pipeline failed (non-critical): %s", e)
    finally:
        if "projected_points" not in player_df.columns:
            player_df["projected_points"] = 0.0

    # ── Section 1: Squad Evaluation ───────────────────────────────────────
    logger.info("Running squad evaluation")
    report.squad_evaluation = evaluate_squad(
        squad_df=squad_df,
        player_df=player_df,
        fixtures=fixtures,
        team_name_map=team_name_map,
        bank=bank,
        free_transfers=free_transfers,
        saved_transfers=saved_transfers,
    )

    # ── Section 2: Transfer Engine ────────────────────────────────────────
    logger.info("Running transfer engine")

    raw_plan = generate_transfer_recommendations(
        squad_eval=report.squad_evaluation,
        player_df=player_df,
        fixture_map=fixture_map,
        team_name_map=team_name_map,
    )

    # ── Section 3: Hit Analysis ──────────────────────────────────────────
    logger.info("Running hit analysis")
    report.transfer_plan = analyze_hit(raw_plan, report.squad_evaluation)

    # ── Section 4: Chip Strategy ──────────────────────────────────────────
    logger.info("Running chip strategy")
    chip_states = get_chip_states(session, team_id)

    # Also sync from API if we have chip data
    if team_data.chips:
        from services.assistant_manager.decision_log import sync_chip_states
        chip_states = sync_chip_states(session, team_id, team_data.chips)

    upcoming_gws = list(range(current_gameweek, min(current_gameweek + 10, 39)))
    report.chip_recommendations = evaluate_chips(
        squad_eval=report.squad_evaluation,
        chip_states=chip_states,
        fixtures=fixtures,
        team_id=team_id,
        upcoming_gameweeks=upcoming_gws,
    )

    # ── Section 5: Future Planning ────────────────────────────────────────
    logger.info("Running future planning")
    report.future_plan = plan_future(
        squad_eval=report.squad_evaluation,
        all_player_df=player_df,
        fixtures=fixtures,
        team_name_map=team_name_map,
    )

    # ── Section 7: Executive Summary ──────────────────────────────────────
    report.executive_summary = generate_executive_summary(
        squad_eval=report.squad_evaluation,
        transfer_plan=report.transfer_plan,
        chip_recs=report.chip_recommendations,
    )

    # ── Section 8: League Intelligence ────────────────────────────────────
    # Consumes the V3 production projections (read-only). Mini-league and rival
    # analysis are optional and best-effort; exposures + differentials always run.
    if store is not None and report.production_pipeline_result is not None:
        logger.info("Running league intelligence")
        try:
            from services.league_intelligence import run_league_intelligence

            primary = report.production_pipeline_result.primary
            v3_projections = primary.projections if primary else []
            current_squad_ids = list(squad_df["id"].values) if not squad_df.empty else []
            captain_id = next(
                (int(r["id"]) for _, r in squad_df.iterrows() if r.get("is_captain")),
                None,
            )

            report.league_intelligence = run_league_intelligence(
                store=store,
                projections=v3_projections,
                team_id=team_id,
                gameweek_id=current_gameweek or 0,
                user_squad=current_squad_ids,
                user_captain=captain_id,
            )
        except Exception as e:  # noqa: BLE001 - league intelligence is best-effort
            logger.warning("League intelligence failed (non-critical): %s", e)

    # ── Section 6: Log recommendations ────────────────────────────────────
    logger.info("Logging recommendations")
    try:
        if report.transfer_plan and report.transfer_plan.transfers:
            for rec in report.transfer_plan.transfers:
                log_recommendation(
                    session=session,
                    team_id=team_id,
                    gameweek=current_gameweek,
                    recommendation_type="transfer",
                    recommendation={
                        "player_out": rec.player_out.web_name,
                        "player_in": rec.player_in.web_name,
                        "expected_gain": rec.expected_points_gained,
                        "risk": rec.risk_level,
                    },
                    confidence=rec.confidence_rating,
                    predicted_points=rec.expected_points_gained,
                )

        for chip_rec in report.chip_recommendations:
            if chip_rec.should_play:
                log_recommendation(
                    session=session,
                    team_id=team_id,
                    gameweek=current_gameweek,
                    recommendation_type="chip",
                    recommendation={
                        "chip": chip_rec.chip_name,
                        "best_gw": chip_rec.best_gameweek,
                    },
                    confidence=chip_rec.confidence,
                )
    except Exception as e:  # noqa: BLE001 - recommendation logging is best-effort
        logger.warning("Failed to log recommendations: %s", e)

    logger.info("Assistant Manager run complete")
    return report
