"""Tests for the League Intelligence Layer (Phases 1-7 foundation).

Covers effective ownership, differential scoring, mini-league analysis, rival
tracking, the orchestrator and the architecture-only game-theory guard. All
tests use synthetic data — no network.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from synthetic import create_synthetic_players

from features import build_feature_store


def build_store(n=50, seed=42, **kwargs):
    df = create_synthetic_players(n=n, seed=seed)
    for col, val in kwargs.items():
        df[col] = val
    return build_feature_store(players_df=df, gameweek_id=1)


def make_projection(pid, xpts, minutes=90.0, web_name=None, position="MID"):
    from engines.expected_projection_engine import ExpectedPlayerProjection

    return ExpectedPlayerProjection(
        player_id=pid,
        web_name=web_name or f"Player{pid}",
        position=position,
        gameweek_id=1,
        projected_points=round(xpts, 2),
        xpts_per_90=round(xpts / max(minutes / 90.0, 0.01), 2),
        expected_minutes=minutes,
        ci_80_low=round(xpts * 0.7, 2),
        ci_80_high=round(xpts * 1.3, 2),
        ci_95_low=round(xpts * 0.5, 2),
        ci_95_high=round(xpts * 1.5, 2),
        minutes_proj=minutes,
        goals_proj=0.5,
        assists_proj=0.3,
        clean_sheet_proj=0.2,
        bonus_proj=0.1,
        other_proj=0.0,
        confidence=70.0,
        data_quality="synthetic",
        variance_total=2.0,
        contributing_factors={},
    )


# ---------------------------------------------------------------------------
# Effective Ownership Engine
# ---------------------------------------------------------------------------


def test_effective_ownership_formula():
    from services.league_intelligence.effective_ownership import (
        classify_exposure,
        compute_effective_ownership,
        league_ownership,
        rival_ownership,
    )

    assert compute_effective_ownership(10.0, 0.0, 0.0) == 10.0
    assert compute_effective_ownership(10.0, 5.0, 0.0) == 15.0
    assert compute_effective_ownership(10.0, 5.0, 2.0) == 17.0
    assert classify_exposure(6.0) == "low"
    assert classify_exposure(12.0) == "moderate"
    assert classify_exposure(30.0) == "high"
    assert league_ownership([{1}, {1}, {2}], 1) == 66.67
    assert rival_ownership([{1}, {2}], 3) == 0.0


def test_exposure_engine_builds_rows():
    from services.league_intelligence.effective_ownership import (
        EffectiveOwnershipEngine,
    )

    engine = EffectiveOwnershipEngine()
    exp = engine.exposure(
        player_id=1, web_name="Haaland", position="FWD",
        global_ownership=30.0, captained_pct=10.0,
        league_squads=[{1, 2}, {1}, {3}], rival_squads=[{1}, {2}],
    )
    assert exp.effective_ownership == 40.0
    assert exp.exposure_tier == "high"
    assert exp.league_ownership == 66.67
    assert exp.rival_ownership == 50.0
    assert exp.is_differential is False


def test_exposure_no_data_is_unknown_not_error():
    from services.league_intelligence.effective_ownership import (
        EffectiveOwnershipEngine,
    )

    exp = EffectiveOwnershipEngine().exposure(1, "X", "MID")
    assert exp.effective_ownership == 0.0
    assert exp.exposure_tier == "low"
    assert exp.league_ownership is None
    assert exp.rival_ownership is None


# ---------------------------------------------------------------------------
# Differential Scoring
# ---------------------------------------------------------------------------


def test_differential_scoring_ranks_and_weights():
    from services.league_intelligence.differential import DifferentialScorer

    store = build_store(6)
    scorer = DifferentialScorer()
    rows = [dict(r) for _, r in store.df.iterrows()]
    scored = scorer.score(rows)
    assert len(scored) == 6
    for d in scored:
        assert 0.0 <= d.score <= 1.0
        assert d.config_version == "league_intelligence_v1"
        assert set(d.components) >= {"projected_points", "inverse_ownership"}

    # Higher ownership should penalise score (holding other signals constant).
    a = next(d for d in scored if d.player_id == 1)
    assert a.global_ownership == store.df.iloc[0]["selected_by_percent"]


def test_top_differentials_excludes_squad():
    from services.league_intelligence.differential import DifferentialScorer

    store = build_store(6)
    rows = [dict(r) for _, r in store.df.iterrows()]
    squad_ids = [1, 2, 3]
    top = DifferentialScorer().top_differentials(rows, squad_ids=squad_ids, top_n=2)
    assert len(top) == 2
    assert all(d.player_id not in squad_ids for d in top)
    assert top[0].score >= top[1].score


def test_differential_empty_input():
    from services.league_intelligence.differential import DifferentialScorer

    assert DifferentialScorer().score([]) == []


# ---------------------------------------------------------------------------
# Mini-League Analyzer
# ---------------------------------------------------------------------------


def test_mini_league_common_and_differentials():
    from services.league_intelligence.mini_league import MiniLeagueAnalyzer

    user = {1, 2, 3, 4}
    squads = {
        0: user,                     # user (position 1)
        5: {1, 2, 3, 10},
        6: {1, 2, 3, 11},
        7: {1, 2, 12, 13},
        8: {4, 5, 6, 7},             # peer with low overlap
    }
    report = MiniLeagueAnalyzer().analyze(
        user_squad=user,
        squads=squads,
        league_id=99,
        gameweek_id=1,
    )
    assert report.n_teams == 5
    common_ids = {c["player_id"] for c in report.common_players}
    assert common_ids == {1, 2}  # owned by >=60% of peers; player 3 only by 2/4
    assert 4 not in common_ids  # only 1/4 peers own it
    diff_ids = {d["player_id"] for d in report.league_differentials}
    assert 4 in diff_ids  # user differential
    assert report.risk_profile["n_peers_sharing_any_player"] == 4
    assert max(report.squad_similarity["by_entry"].values()) > 0.0
    assert report.squad_similarity["by_entry"].get(0) is None  # user excluded


def test_mini_league_captain_overlap():
    from services.league_intelligence.mini_league import MiniLeagueAnalyzer

    user = {1, 2, 3}
    squads = {
        0: user,
        5: {1, 2, 4},
        6: {1, 2, 5},
    }
    captains = {0: 1, 5: 1, 6: 2}
    report = MiniLeagueAnalyzer().analyze(
        user_squad=user, squads=squads, gameweek_id=1, captains=captains,
    )
    assert report.captain_overlap["user_captain"] == 1
    assert report.captain_overlap["n_peers_captaining_same"] == 1


def test_mini_league_no_data():
    from services.league_intelligence.mini_league import MiniLeagueAnalyzer

    report = MiniLeagueAnalyzer().analyze(user_squad={1}, squads={})
    assert report.n_teams == 1
    assert report.common_players == []
    assert report.notes


# ---------------------------------------------------------------------------
# Rival Tracker
# ---------------------------------------------------------------------------


def test_rival_squad_and_captain_comparison():
    from services.league_intelligence.rivals import RivalTracker

    projections = {pid: make_projection(pid, float(pid), 90.0) for pid in range(1, 11)}
    user = {1, 2, 3, 4}
    rival_squads = {
        100: {1: 2, 2: 1, 3: 1, 9: 1},   # rival captains player 1
        101: {1: 1, 5: 2, 6: 1, 10: 1},  # rival captains player 5
    }
    report = RivalTracker().analyze(
        user_squad=user,
        user_captain=1,
        projections_by_id=projections,
        rival_squads=rival_squads,
        rival_names={100: "Rival A", 101: "Rival B"},
        position_by_id={pid: "MID" for pid in range(1, 11)},
        gameweek_id=1,
    )
    assert len(report.squad_comparison) == 2
    assert report.captain_comparison["user_captain"] == 1
    assert report.captain_comparison["n_rivals_on_user_captain"] == 1
    assert report.captain_comparison["best_rival_captain"]["entry_id"] == 101
    opps = report.differential_opportunities
    assert all(o["player_id"] not in user for o in opps)
    # Aggregate totals present for user + both rivals.
    assert "user_total_xpts" in report.xpts_comparison
    assert set(report.xpts_comparison["rivals"]) == {100, 101}


def test_rival_no_data():
    from services.league_intelligence.rivals import RivalTracker

    report = RivalTracker().analyze(
        user_squad={1}, user_captain=None,
        projections_by_id={}, rival_squads={}, gameweek_id=1,
    )
    assert report.squad_comparison == []
    assert report.notes


# ---------------------------------------------------------------------------
# Game Theory (architecture-only)
# ---------------------------------------------------------------------------


def test_game_theory_guard_disabled():
    from services.league_intelligence.game_theory import (
        PositionGainInput,
        game_theory_enabled,
        get_game_theory_engine,
    )

    assert game_theory_enabled() is False
    inputs = PositionGainInput(
        gameweek_id=1, league_position=5, n_teams=10,
        points_to_rival_ahead=20.0, points_ahead_of_rival_behind=30.0,
        n_gameweeks_remaining=20,
    )
    engine = get_game_theory_engine()
    assert engine.estimate(inputs) == []


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def test_run_league_intelligence_full_report():
    from services.league_intelligence import run_league_intelligence

    store = build_store(20)
    projections = [
        make_projection(p.player_id, float(p.player_id), web_name=p.web_name)
        for p in store.df.itertuples()
    ]
    squad_ids = [1, 2, 3, 4, 5]
    league_squads = {
        100: {pid: 1 for pid in squad_ids} | {10: 1, 11: 1},
        101: {pid: 1 for pid in squad_ids} | {12: 1, 13: 1},
        102: {pid: 1 for pid in [1, 2, 3]} | {14: 1, 15: 1, 16: 1},
    }
    report = run_league_intelligence(
        store=store,
        projections=projections,
        team_id=100,
        gameweek_id=1,
        user_squad=squad_ids,
        user_captain=1,
        league_id=50,
        league_squads=league_squads,
        rival_squads={101: league_squads[101]},
        rival_names={101: "Rival"},
        top_differentials=3,
    )
    summary = report.summary()
    assert summary["gameweek_id"] == 1
    assert summary["league_analyzed"] is True
    assert summary["rivals_analyzed"] is True
    assert len(report.exposures) == 20
    assert report.differentials and all(not d.is_differential or d.score >= 0.5 for d in report.differentials[:1])
    assert report.mini_league is not None and report.mini_league.position == 1
    assert report.rivals is not None
    types = {r.type for r in report.recommendations}
    assert "differential_pick" in types
    # Projection values are carried through untouched — never re-scored.
    for rec in report.recommendations:
        if rec.type in ("differential_pick", "rival_edge"):
            assert rec.xpts == float(rec.player_id)


def test_run_league_intelligence_minimal_no_network():
    """No squad/league/rival data → still a valid report (degrade gracefully)."""
    from services.league_intelligence import run_league_intelligence

    store = build_store(10)
    projections = [
        make_projection(p.player_id, float(p.player_id), web_name=p.web_name)
        for p in store.df.itertuples()
    ]
    report = run_league_intelligence(
        store=store, projections=projections, team_id=999, gameweek_id=1,
        user_squad=[1], user_captain=None,
    )
    assert report.mini_league is None
    assert report.rivals is None
    assert report.differentials == [] or all(d.player_id != 1 for d in report.differentials)
    assert any("skipped" in n for n in report.notes)


def test_providers_feature_store_based():
    from services.league_intelligence.providers import FeatureStoreOwnershipProvider

    store = build_store(5)
    prov = FeatureStoreOwnershipProvider(store=store)
    ownership = prov.get_global_ownership(1)
    assert len(ownership) == 5
    assert prov.get_top10k_ownership(1) is None
    velocity = prov.get_transfer_velocity(1)
    assert len(velocity) == 5
    assert prov.get_price_movement(1)


def test_providers_fpl_mini_league_degrade():
    """FPL API provider must return empty (not raise) when the API fails."""
    from services.league_intelligence.providers import FPLApiMiniLeagueProvider

    def boom(endpoint):
        raise RuntimeError("network down")

    prov = FPLApiMiniLeagueProvider(api_get=boom)
    assert prov.get_league_standings(1, 1) == []
    assert prov.get_entry_squad(1, 1) == {}
