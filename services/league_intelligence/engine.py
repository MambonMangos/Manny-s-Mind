"""League Intelligence — run_league_intelligence orchestrator.

Phase 1 foundation: ties together effective ownership, differential scoring,
mini-league analysis, rival tracking and (architecture-only) game theory into a
single self-contained ``LeagueIntelligenceReport``.

Design contract (from docs/league_intelligence.md):
  - Prediction layer is NEVER modified. Projection values flow into
    recommendations untouched (``xpts`` fields).
  - All providers are injectable. The default offline provider reads from the
    feature store; mini-league/rival data is optional and best-effort.
  - No hidden state: one call, one report, nothing mutated.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from services.league_intelligence.models import LeagueIntelligenceReport
from utils.config import get_active_version, load_config

logger = logging.getLogger(__name__)


def run_league_intelligence(
    store,
    projections: list,
    team_id: int,
    gameweek_id: int,
    user_squad: list[int] | None = None,
    user_captain: int | None = None,
    league_id: int | None = None,
    league_squads: dict | None = None,
    rival_squads: dict | None = None,
    rival_names: dict | None = None,
    ownership_provider=None,
    captain_poll_provider=None,
    config: dict | None = None,
    top_differentials: int | None = None,
) -> LeagueIntelligenceReport:
    """Run the full League Intelligence Layer for one gameweek.

    Parameters
    ----------
    store : FeatureStore
        Pre-built feature store (source of default ownership/transfer signals).
    projections : list[ExpectedPlayerProjection]
        V3 xPts projections. Read-only — never modified.
    team_id : int
        User's FPL entry id.
    gameweek_id : int
        Target gameweek.
    user_squad : list[int], optional
        Player IDs in the user's squad. If omitted, tries the FPL API.
    user_captain : int | None, optional
        User's captain player id (multiplier-2 pick).
    league_id : int | None, optional
        Mini-league id (required for mini-league analysis).
    league_squads : dict, optional
        {entry_id: {player_id: multiplier}} for the whole league, incl. user.
    rival_squads : dict, optional
        {entry_id: {player_id: multiplier}} for tracked rivals only.
    rival_names : dict, optional
        {entry_id: team_name}.
    ownership_provider : OwnershipProvider, optional
        Defaults to FeatureStoreOwnershipProvider(store).
    captain_poll_provider : CaptainPollProvider, optional
        Community captaincy poll. Defaults to empty.
    config : dict, optional
        League intelligence config. Defaults to the active version.
    top_differentials : int, optional
        Number of differentials to surface.

    Returns
    -------
    LeagueIntelligenceReport
        Self-contained report of exposures, differentials, league/rival
        analysis and strategic recommendations.
    """
    from services.league_intelligence.differential import DifferentialScorer
    from services.league_intelligence.effective_ownership import (
        EffectiveOwnershipEngine,
    )

    config = config or load_config("league_intelligence")
    config_version = get_active_version("league_intelligence")

    squad, captain = _resolve_squad(
        user_squad, user_captain, team_id, gameweek_id, store
    )
    projections_by_id = {p.player_id: p for p in projections}

    # Effective ownership / exposures ------------------------------------
    ownership = ownership_provider or _default_ownership_provider(store)
    captained = (captain_poll_provider.get_captain_pct(gameweek_id)
                 if captain_poll_provider else {})
    try:
        global_ownership = ownership.get_global_ownership(gameweek_id)
    except Exception as exc:  # noqa: BLE001 - provider boundary, degrade gracefully
        logger.warning("Ownership provider failed: %s", exc)
        global_ownership = {}
    try:
        top10k = ownership.get_top10k_ownership(gameweek_id)
    except Exception as exc:  # noqa: BLE001 - provider boundary, degrade gracefully
        logger.warning("Top-10k ownership provider failed: %s", exc)
        top10k = None

    league_squads_sets = _normalise_squads(league_squads)
    rival_squads_sets = _normalise_squads(rival_squads)
    league_sets = [s for s in league_squads_sets] if league_squads_sets else None
    rival_sets = [s for s in rival_squads_sets] if rival_squads_sets else None

    eo_engine = EffectiveOwnershipEngine(config)
    exposures = []
    for proj in projections:
        pid = proj.player_id
        exposures.append(eo_engine.exposure(
            player_id=pid,
            web_name=proj.web_name,
            position=proj.position,
            global_ownership=global_ownership.get(pid, 0.0),
            captained_pct=captained.get(pid, 0.0),
            top10k_ownership=top10k.get(pid) if top10k else None,
            league_squads=league_sets,
            rival_squads=rival_sets,
            source=getattr(ownership, "__class__", type(None)).__name__,
        ))

    # Differential scoring -------------------------------------------------
    scorer = DifferentialScorer(config)
    try:
        enriched_rows = _enrich_store_rows(store, projections_by_id)
        differentials = scorer.top_differentials(
            enriched_rows,
            squad_ids=squad,
            top_n=top_differentials,
        )
    except Exception as exc:  # noqa: BLE001 - differentials are best-effort
        logger.warning("Differential scoring failed: %s", exc)
        differentials = []

    # Mini-league + rival analysis -----------------------------------------
    mini_league = None
    rivals_report = None
    from services.league_intelligence.mini_league import MiniLeagueAnalyzer
    from services.league_intelligence.rivals import RivalTracker

    if league_id is not None and league_squads:
        mini_league = MiniLeagueAnalyzer(config).analyze(
            user_squad=squad,
            squads=league_squads,
            league_id=league_id,
            position=_league_position(league_squads, team_id),
            gameweek_id=gameweek_id,
            captains=_captain_map(league_squads),
            all_players={p.player_id: p.web_name for p in projections},
        )

    if rival_squads:
        rivals_report = RivalTracker(config).analyze(
            user_squad=squad,
            user_captain=captain,
            projections_by_id=projections_by_id,
            rival_squads=rival_squads,
            rival_names=rival_names,
            position_by_id={p.player_id: p.position for p in projections},
            gameweek_id=gameweek_id,
        )

    # Strategic recommendations --------------------------------------------
    recommendations = _build_recommendations(
        differentials=differentials,
        exposures=exposures,
        mini_league=mini_league,
        rivals=rivals_report,
        config_version=config_version,
    )

    report = LeagueIntelligenceReport(
        gameweek_id=gameweek_id,
        team_id=team_id,
        config_version=config_version,
        computed_at=datetime.now(timezone.utc).isoformat(),
        exposures=exposures,
        differentials=differentials,
        mini_league=mini_league,
        rivals=rivals_report,
        recommendations=recommendations,
        inputs={
            "squad_available": bool(squad),
            "league_available": league_id is not None and bool(league_squads),
            "rivals_available": bool(rival_squads),
            "captain_poll_available": bool(captained),
            "top10k_available": top10k is not None,
        },
        notes=_report_notes(mini_league, rivals_report, squad),
    )
    logger.info(
        "League intelligence gw=%d team=%d: %d exposures, %d differentials, "
        "league=%s, rivals=%s",
        gameweek_id, team_id, len(exposures), len(differentials),
        mini_league is not None, rivals_report is not None,
    )
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_ownership_provider(store):
    from services.league_intelligence.providers import FeatureStoreOwnershipProvider

    return FeatureStoreOwnershipProvider(store=store)


def _enrich_store_rows(store, projections_by_id: dict) -> list[dict]:
    """Copy store rows and attach the projection engine's values (read-only).

    The scorer needs the projection xPts and expected minutes per player; the
    store does not contain them. We overlay the projection values on a copy —
    the store's own columns are never mutated.
    """
    rows = []
    for _, row in store.df.iterrows():
        rec = dict(row)
        proj = projections_by_id.get(int(row.get("player_id", 0) or 0))
        if proj is not None:
            rec["projected_points"] = float(proj.projected_points)
            rec["expected_minutes"] = float(proj.expected_minutes)
        rows.append(rec)
    return rows


def _resolve_squad(user_squad, user_captain, team_id, gameweek_id, store):
    """Return (squad_set, captain_id). Falls back to the FPL API when needed."""
    if user_squad is not None:
        return set(user_squad), user_captain
    try:
        from services.team_service import fetch_picks

        picks = fetch_picks(team_id, gameweek_id)
        squad = {p.player_id for p in picks.picks}
        captain = next((p.player_id for p in picks.picks if p.is_captain), None)
        return squad, captain
    except Exception as exc:  # noqa: BLE001 - squad fetch is best-effort
        logger.warning("Squad fetch failed (%s); continuing without squad.", exc)
        return set(), None


def _normalise_squads(squads: dict | None) -> list[set[int]]:
    """Normalise {entry_id: {player_id: mult}} → list of player sets."""
    if not squads:
        return []
    result = []
    for raw in squads.values():
        result.append(set(raw.keys()) if isinstance(raw, dict) else set(raw))
    return result


def _captain_map(squads: dict) -> dict[int, int]:
    """Extract {entry_id: captain_id} from squads keyed by player → multiplier."""
    captains = {}
    for eid, raw in squads.items():
        if isinstance(raw, dict):
            for pid, mult in raw.items():
                if mult and mult >= 2:
                    captains[eid] = pid
                    break
    return captains


def _league_position(squads: dict, team_id: int) -> int | None:
    """Find the user's 1-based rank inside league squads."""
    if not squads:
        return None
    # Heuristic: user's entry is either passed as team_id key or sized 11/15.
    target = None
    if team_id in squads:
        target = team_id
    else:
        for eid, raw in squads.items():
            size = len(raw)
            if size in (11, 15):
                target = eid
                break
    if target is None:
        return None
    ordered = list(squads.keys())
    try:
        return ordered.index(target) + 1
    except ValueError:
        return None


def _build_recommendations(
    differentials,
    exposures,
    mini_league,
    rivals,
    config_version,
) -> list:
    """Turn analysis into typed StrategicRecommendation objects.

    Every recommendation carries the projection engine's untouched ``xpts``.
    """
    from services.league_intelligence.models import StrategicRecommendation

    recs: list[StrategicRecommendation] = []

    exposure_by_id = {e.player_id: e for e in exposures}
    for diff in differentials:
        exposure = exposure_by_id.get(diff.player_id)
        league_owned = exposure.league_ownership if exposure else None
        reasoning = (
            f"Differential pick: xPts {diff.xpts:.1f}, global ownership "
            f"{diff.global_ownership:.1f}%"
            + (f", league ownership {league_owned:.0f}%" if league_owned is not None else "")
        )
        recs.append(StrategicRecommendation(
            type="differential_pick",
            player_id=diff.player_id,
            web_name=diff.web_name,
            position=diff.position,
            xpts=diff.xpts,
            strategy_score=diff.score,
            confidence=min(diff.score, 0.95),
            reasoning=reasoning,
            detail={"differential_score": diff.score, "config_version": config_version},
        ))

    # League captaincy-hedge: user owns the league's most common player but is
    # not captaining them → flag a shared-exposure risk.
    if mini_league and mini_league.captain_overlap:
        overlap = mini_league.captain_overlap
        cap_id = overlap.get("user_captain")
        share = overlap.get("peers_sharing_captain_pct", 0.0)
        if cap_id is not None and share >= 50.0:
            recs.append(StrategicRecommendation(
                type="captaincy_hedge",
                player_id=cap_id,
                web_name=f"P{cap_id}",
                position="",
                strategy_score=round(share / 100.0, 2),
                confidence=0.6,
                reasoning=(
                    f"{share:.0f}% of league peers share your captain — a captaincy "
                    "differential could swing league position."
                ),
            ))

    # Rival edge: the single best differential opportunity no rival owns.
    if rivals and rivals.differential_opportunities:
        top = rivals.differential_opportunities[0]
        recs.append(StrategicRecommendation(
            type="rival_edge",
            player_id=top["player_id"],
            web_name=top["web_name"],
            position=top["position"],
            xpts=top["xpts"],
            strategy_score=top["xpts"],
            confidence=0.5,
            reasoning=f"Best differential opportunity vs rivals: no tracked rival owns "
                      f"{top['web_name']} (xPts {top['xpts']:.1f}).",
        ))

    # Threat response: highest-similarity rival.
    if mini_league and mini_league.threats:
        top_threat = mini_league.threats[0]
        recs.append(StrategicRecommendation(
            type="threat_response",
            player_id=top_threat["entry_id"],
            web_name=str(top_threat["entry_id"]),
            position="",
            strategy_score=top_threat["similarity"],
            confidence=0.5,
            reasoning=(
                f"Rival entry {top_threat['entry_id']} shares "
                f"{top_threat['similarity']:.0%} of your squad — direct match-up."
            ),
        ))

    return recs


def _report_notes(mini_league, rivals, squad) -> list[str]:
    notes: list[str] = []
    if not squad:
        notes.append("Squad unavailable — differential recommendations exclude squad only by API fallback.")
    if mini_league is None:
        notes.append("Mini-league analysis skipped: no league squads provided.")
    if rivals is None:
        notes.append("Rival analysis skipped: no rival squads provided.")
    return notes
