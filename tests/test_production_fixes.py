"""Tests for the 4 targeted production fixes mandated by the Director.

H-06  V1/V2 consolidation (structural — covered by Task 2 SSOT migration)
H-07  Feature Store single source of truth
H-09  Weekly Report crash on empty data
H-18  player_id = 0 fallback in snapshot_service
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.WARNING)


# ------------------------------------------------------------------
# Synthetic test data
# ------------------------------------------------------------------

def synthetic_players(n=50):
    np.random.seed(420)
    df = pd.DataFrame({
        "id": range(1, n + 1),
        "web_name": [f"P{i}" for i in range(1, n + 1)],
        "position": np.random.choice(["GKP", "DEF", "MID", "FWD"], n, p=[0.12, 0.35, 0.38, 0.15]),
        "team_id": np.random.randint(1, 21, n),
        "price": np.random.uniform(4.0, 14.0, n).round(1),
        "total_points": np.random.randint(10, 200, n),
        "minutes": np.random.randint(90, 3000, n),
        "goals_scored": np.random.randint(0, 15, n),
        "assists": np.random.randint(0, 10, n),
        "expected_goals": np.random.uniform(0, 12, n).round(2),
        "expected_assists": np.random.uniform(0, 8, n).round(2),
        "expected_goal_involvements": np.random.uniform(0, 15, n).round(2),
        "expected_goals_conceded": np.random.uniform(0, 25, n).round(2),
        "form": np.random.uniform(0, 8, n).round(1),
        "selected_by_percent": np.random.uniform(1, 50, n).round(1),
        "transfers_in_event": np.random.randint(0, 30000, n),
        "transfers_out_event": np.random.randint(0, 30000, n),
        "cost_change_start": np.random.randint(-8, 8, n),
        "cost_change_event": np.random.randint(-2, 2, n),
        "status": ["a"] * n,
        "news": [""] * n,
        "chance_of_playing_next_round": [100] * n,
        "chance_of_playing_this_round": [100] * n,
        "penalties_order": [None] * n,
        "direct_freekicks_order": [None] * n,
        "corners_and_indirect_freekicks_order": [None] * n,
        "influence": np.random.uniform(0, 80, n),
        "creativity": np.random.uniform(0, 80, n),
        "threat": np.random.uniform(0, 80, n),
        "ict_index": np.random.uniform(0, 80, n),
        "value_form": np.random.uniform(0, 8, n),
        "value_season": np.random.uniform(0, 40, n),
        "event_points": np.zeros(n, dtype=int),
        "strength_overall_home": [1100] * n,
        "strength_overall_away": [1100] * n,
        "clean_sheets": np.random.randint(0, 15, n),
        "saves": np.zeros(n, dtype=int),
        "bonus": np.random.randint(0, 20, n),
        "bps": np.random.randint(0, 500, n),
        "red_cards": np.zeros(n, dtype=int),
        "yellow_cards": np.random.randint(0, 10, n),
    })
    return df


# ==================================================================
# TASK 2  —  Feature Store canonical columns (H-07)
# ==================================================================

def test_feature_store_has_canonical_columns():
    """H-07: Feature Store must write canonical columns into store.df."""
    from features import build_feature_store

    df = synthetic_players(20)
    store = build_feature_store(players_df=df, gameweek_id=1)

    expected = [
        "finishing_ratio",
        "creative_ratio",
        "net_transfers",
        "ownership_tier",
        "transfer_velocity",
        "price_direction_label",
    ]
    missing = [c for c in expected if c not in store.df.columns]
    assert not missing, f"Canonical columns missing from store.df: {missing}"
    print(f"PASS: All {len(expected)} canonical columns present in store.df")


def test_canonical_values_match_computation():
    """H-07: SSOT values must be equivalent to inline computation."""
    from features import build_feature_store

    df = synthetic_players(20)
    store = build_feature_store(players_df=df, gameweek_id=1)

    for _, row in store.df.iterrows():
        xg = row.get("expected_goals", 0) or 0
        xa = row.get("expected_assists", 0) or 0
        goals = row.get("goals_scored", 0) or 0
        assists = row.get("assists", 0) or 0

        expected_finishing = goals / xg if xg > 0 else 1.0
        expected_creative = assists / xa if xa > 0 else 1.0

        assert abs(row["finishing_ratio"] - expected_finishing) < 0.001, (
            f"finishing_ratio mismatch for {row['web_name']}: "
            f"store={row['finishing_ratio']}, expected={expected_finishing}"
        )
        assert abs(row["creative_ratio"] - expected_creative) < 0.001, (
            f"creative_ratio mismatch for {row['web_name']}: "
            f"store={row['creative_ratio']}, expected={expected_creative}"
        )

    print("PASS: All canonical Finishing/Creative ratios match inline computation")


def test_regression_engine_reads_canonical():
    """H-07: Regression Engine must read finishing/creative ratio from row."""
    from features import build_feature_store
    from engines.regression_engine import _analyze_player_regression

    df = synthetic_players(10)
    store = build_feature_store(players_df=df, gameweek_id=1)

    # Pick a row and manually override the canonical column
    row = store.df.iloc[0].copy()
    row["finishing_ratio"] = 9.999  # absurdly high
    row["creative_ratio"] = 9.999

    signal = _analyze_player_regression(row, 1.3, 0.7, 3)

    assert signal.finishing_ratio == 9.999, (
        f"Engine recomputed finishing_ratio instead of reading canonical: "
        f"{signal.finishing_ratio} != 9.999"
    )
    assert signal.creative_ratio == 9.999, (
        f"Engine recomputed creative_ratio instead of reading canonical: "
        f"{signal.creative_ratio} != 9.999"
    )
    print("PASS: Regression Engine reads canonical finishing/creative ratios")


def test_market_engine_reads_canonical():
    """H-07: Market Intelligence Engine must read canonical market features."""
    from features import build_feature_store
    from engines.market_intelligence_engine import _analyze_player_market

    df = synthetic_players(10)
    store = build_feature_store(players_df=df, gameweek_id=1)

    row = store.df.iloc[0].copy()
    row["net_transfers"] = 99999
    row["transfer_velocity"] = 88.88
    row["ownership_tier"] = "template"
    row["price_direction_label"] = "falling"

    signal = _analyze_player_market(row, {})

    assert signal.net_transfers == 99999, (
        f"Engine recomputed net_transfers: {signal.net_transfers} != 99999"
    )
    assert abs(signal.transfer_velocity - 88.88) < 0.01, (
        f"Engine recomputed transfer_velocity: {signal.transfer_velocity} != 88.88"
    )
    assert signal.ownership_tier == "template", (
        f"Engine recomputed ownership_tier: {signal.ownership_tier} != template"
    )
    assert signal.price_direction == "falling", (
        f"Engine recomputed price_direction: {signal.price_direction} != falling"
    )
    print("PASS: Market Intelligence Engine reads 4 canonical market features")


# ==================================================================
# TASK 3  —  Weekly Report crash resilience (H-09)
# ==================================================================

def test_generate_insights_empty_by_type():
    """H-09: _generate_insights must not crash on empty by_type dict."""
    from services.learning_service import WeeklyReport, _generate_insights

    report = WeeklyReport(gameweek_id=1, status="ok")
    report.version_metrics = []
    report.error_summary = {"by_type": {}, "by_direction": {"over": 0, "under": 0}}

    insights = _generate_insights(report)
    assert isinstance(insights, list), "Should return a list"
    assert len(insights) > 0, "Should have at least one insight"
    print(f"PASS: Empty by_type handled: {len(insights)} insights")


def test_generate_insights_none_by_type():
    """H-09: _generate_insights must not crash on None by_type values."""
    from services.learning_service import WeeklyReport, _generate_insights

    report = WeeklyReport(gameweek_id=1, status="ok")
    report.version_metrics = []
    report.error_summary = {
        "by_type": {"minutes_miss": None, "goal_miss": None},
        "by_direction": {"over": 0, "under": 0},
    }

    insights = _generate_insights(report)
    assert isinstance(insights, list)
    print(f"PASS: None by_type values handled: {len(insights)} insights")


def test_generate_candidate_improvements_empty():
    """H-09: _generate_candidate_improvements must handle empty data."""
    from services.learning_service import WeeklyReport, _generate_candidate_improvements

    report = WeeklyReport(gameweek_id=1, status="ok")
    report.version_metrics = []
    report.error_summary = {}

    candidates = _generate_candidate_improvements(report)
    assert isinstance(candidates, list)
    assert len(candidates) == 0
    print("PASS: Empty candidate improvements handled")


def test_generate_weekly_report_empty():
    """H-09: generate_weekly_report must not crash on empty data."""
    import sqlite3
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from database.models import Base

    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    session = Session(bind=engine)

    from services.learning_service import generate_weekly_report

    report = generate_weekly_report(session, gameweek_id=1)
    assert report.status == "no_data"
    assert isinstance(report.insights, list)
    assert isinstance(report.candidate_improvements, list)
    session.close()
    print("PASS: generate_weekly_report with empty DB returns no_data gracefully")


# ==================================================================
# TASK 4  —  player_id = 0 fix (H-18)
# ==================================================================

def test_snapshot_skips_missing_player_id():
    """H-18: _persist_player_snapshots must skip when store.df has no player_id."""
    from services.snapshot_service import _persist_player_snapshots
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from database.models import Base

    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    session = Session(bind=engine)

    df_no_pid = pd.DataFrame({"id": [1, 2], "web_name": ["A", "B"]})

    class MockStore:
        df = df_no_pid

    class MockResult:
        _store = MockStore()
        gameweek_id = 1

    _persist_player_snapshots(session, MockResult())
    # Should not crash — just log and return
    session.close()
    print("PASS: Missing player_id column handled without crash")


def test_snapshot_skips_zero_player_id():
    """H-18: _persist_player_snapshots must skip rows with player_id=0."""
    from services.snapshot_service import _persist_player_snapshots
    from database.crud import insert_player_snapshots_bulk
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from database.models import Base, PlayerSnapshot

    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    session = Session(bind=engine)

    snap_df = pd.DataFrame({
        "player_id": [0, 42, 0, 99],
        "web_name": ["Skip1", "Keep", "Skip2", "Keep2"],
        "total_points": [10, 20, 30, 40],
        "minutes": [90, 180, 270, 360],
        "goals_scored": [0, 1, 2, 3],
        "assists": [0, 1, 0, 2],
        "clean_sheets": [0, 1, 0, 0],
        "expected_goals": [0.0, 0.5, 0.3, 0.8],
        "expected_assists": [0.0, 0.3, 0.1, 0.6],
        "expected_goal_involvements": [0.0, 0.8, 0.4, 1.4],
        "expected_goals_conceded": [2.0, 1.0, 1.5, 0.8],
        "form": [0, 3, 2, 5],
        "selected_by_percent": [5, 15, 25, 10],
        "transfers_in_event": [0, 100, 200, 300],
        "transfers_out_event": [0, 50, 100, 150],
        "xgi_per_90": [0.0, 0.4, 0.2, 0.6],
        "minutes_fraction": [0.1, 0.5, 0.7, 0.9],
        "team_strength_raw": [100, 110, 95, 105],
        "fixture_score_raw": [50, 55, 45, 60],
        "set_piece_raw": [0, 30, 50, 80],
        "influence": [0, 30, 50, 70],
        "creativity": [0, 20, 40, 60],
        "threat": [0, 25, 35, 55],
        "ict_index": [0, 25, 45, 65],
        "status": ["a", "a", "a", "a"],
        "news": ["", "", "", ""],
        "price": [5.0, 6.0, 7.0, 8.0],
    })

    class MockStore:
        df = snap_df

    class MockResult:
        _store = MockStore()
        gameweek_id = 1

    _persist_player_snapshots(session, MockResult())

    snapshots = session.query(PlayerSnapshot).all()
    assert len(snapshots) == 2, f"Expected 2 snapshots (only player_id 42 and 99), got {len(snapshots)}"
    ids = [s.player_id for s in snapshots]
    assert 42 in ids, "player_id=42 should be persisted"
    assert 99 in ids, "player_id=99 should be persisted"
    assert 0 not in ids, "player_id=0 rows should be skipped"
    session.close()
    print("PASS: Rows with player_id=0 skipped; valid rows persisted")


# ==================================================================
# Main
# ==================================================================

if __name__ == "__main__":
    passed = 0
    failed = 0

    tests = [
        ("H-07  Canonical columns in store.df", test_feature_store_has_canonical_columns),
        ("H-07  Canonical values match computation", test_canonical_values_match_computation),
        ("H-07  Regression Engine reads canonical", test_regression_engine_reads_canonical),
        ("H-07  Market Engine reads canonical", test_market_engine_reads_canonical),
        ("H-09  Empty by_type in insights", test_generate_insights_empty_by_type),
        ("H-09  None by_type in insights", test_generate_insights_none_by_type),
        ("H-09  Empty candidate improvements", test_generate_candidate_improvements_empty),
        ("H-09  Empty weekly report", test_generate_weekly_report_empty),
        ("H-18  Missing player_id column", test_snapshot_skips_missing_player_id),
        ("H-18  Zero player_id rows", test_snapshot_skips_zero_player_id),
    ]

    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
            print("RESULT: PASS")
            passed += 1
        except Exception as e:
            print(f"RESULT: FAIL — {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"TOTAL: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)
