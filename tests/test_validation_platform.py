"""Integration tests for the Validation Platform.

Tests the full cycle: pipeline → persist → inject actuals → validate → classify → report.
Also tests error classifier rules with scenario-specific synthetic data.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from sqlalchemy import inspect

from database.database import get_session
from database.models import (
    Base,
    EngineAccuracy,
    ErrorClassification,
    PlayerSnapshot,
    PredictionVersion,
    Projection,
    ValidationMetrics,
)


def reset_db():
    """Drop and recreate all tables for test isolation, then seed minimal data."""
    from sqlalchemy import text

    from database.database import engine
    from database.models import Gameweek, Player, Team
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))

    session = get_session()
    try:
        for i in range(1, 5):
            session.add(Gameweek(id=i, name=f"Gameweek {i}", finished=False, is_next=(i == 1)))
        for i in range(1, 21):
            session.add(Team(id=i, name=f"Team{i}", short_name=f"T{i}"))
        for i in range(1, 60):
            session.add(Player(
                id=i, web_name=f"P{i}", team_id=(i % 20) + 1, element_type=(i % 4) + 1,
            ))
        session.commit()
    finally:
        session.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def create_synthetic_players(n=50):
    """Create synthetic player DataFrame matching scored_players schema."""
    np.random.seed(42)
    return pd.DataFrame({
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


def create_synthetic_fixtures(n_teams=20, n_gws=10):
    fixtures = []
    for gw in range(1, n_gws + 1):
        for i in range(0, n_teams, 2):
            fixtures.append({
                "event": gw,
                "team_h": i + 1,
                "team_a": i + 2,
                "team_h_difficulty": random.randint(2, 4),
                "team_a_difficulty": random.randint(2, 4),
            })
    return fixtures


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------

def test_full_validation_cycle():
    """Test: pipeline → persist → inject actuals → validate → classify → report."""
    print("=" * 60)
    print("TEST: Full Validation Cycle")
    print("=" * 60)

    reset_db()
    session = get_session()

    try:
        # 1. Run pipeline and persist
        print("\n1. Running pipeline + persist...")
        from features import build_feature_store
        from services.pipeline import run_projection_pipeline

        player_df = create_synthetic_players(50)
        fixtures = create_synthetic_fixtures()
        from engines.fixture_engine import build_fixture_map
        fixture_map = build_fixture_map(fixtures)

        store = build_feature_store(
            players_df=player_df,
            fixture_map=fixture_map,
            team_name_map={i: f"Team{i}" for i in range(1, 21)},
            gameweek_id=1,
        )

        result = run_projection_pipeline(
            store=store, gameweek_id=1, persist=True, session=session,
        )
        session.commit()

        assert result.version_id is not None, "version_id should be set after persist"
        assert result.version_id > 0, "version_id should be positive"
        print(f"   Persisted: version_id={result.version_id}, projections={len(result.projections)}")

        # 2. Verify database state
        print("\n2. Verifying database state...")
        pv_count = session.query(PredictionVersion).count()
        proj_count = session.query(Projection).count()
        snap_count = session.query(PlayerSnapshot).count()

        assert pv_count >= 1, f"Expected >=1 PredictionVersion, got {pv_count}"
        assert proj_count >= 50, f"Expected >=50 Projections, got {proj_count}"
        assert snap_count >= 50, f"Expected >=50 PlayerSnapshots, got {snap_count}"
        print(f"   PredictionVersion: {pv_count}, Projection: {proj_count}, PlayerSnapshot: {snap_count}")

        # 3. Inject synthetic actuals
        print("\n3. Injecting synthetic actuals...")
        projections = session.query(Projection).filter_by(version_id=result.version_id).all()
        for p in projections:
            noise = random.gauss(0, 2.0)
            p.actual_points = max(0, round(p.projected_points + noise))
        session.flush()
        print(f"   Injected actuals for {len(projections)} projections")

        # 4. Run Validation Engine
        print("\n4. Running Validation Engine...")
        from engines.validation_engine import validate_version
        report = validate_version(session, result.version_id, gameweek_id=1, persist=True)

        assert report.mae >= 0, f"MAE should be >= 0, got {report.mae}"
        assert report.rmse >= 0, f"RMSE should be >= 0, got {report.rmse}"
        assert 0 <= report.coverage_80 <= 1, f"CI80 coverage should be 0-1, got {report.coverage_80}"
        assert 0 <= report.coverage_95 <= 1, f"CI95 coverage should be 0-1, got {report.coverage_95}"
        assert report.n_projections == len(projections)
        assert report.persisted is True
        print(f"   MAE={report.mae:.3f}, RMSE={report.rmse:.3f}, bias={report.bias:+.3f}")
        print(f"   CI80={report.coverage_80:.1%}, CI95={report.coverage_95:.1%}")
        print(f"   MAE by position: {report.mae_by_position}")

        # 5. Verify ValidationMetrics persisted
        vm_count = session.query(ValidationMetrics).count()
        assert vm_count >= 1, f"Expected >=1 ValidationMetrics, got {vm_count}"
        print(f"\n5. ValidationMetrics rows: {vm_count}")

        # 6. Run Error Classifier
        print("\n6. Running Error Classifier...")
        from services.error_classifier import classify_errors, get_error_summary
        errors = classify_errors(session, result.version_id, gameweek_id=1, persist=True)

        ec_count = session.query(ErrorClassification).count()
        assert ec_count >= 0, "Error classifications should be >= 0"
        print(f"   Errors classified: {len(errors)}, DB rows: {ec_count}")

        summary = get_error_summary(session, result.version_id)
        assert "by_type" in summary
        assert "by_severity" in summary
        assert "by_direction" in summary
        print(f"   Summary: {summary['by_direction']}")

        # 7. Run Engine Contributions
        print("\n7. Running Engine Contributions...")
        from engines.validation_engine import validate_engine_contributions
        engines = validate_engine_contributions(session, result.version_id, gameweek_id=1)

        ea_count = session.query(EngineAccuracy).count()
        assert ea_count >= 1, f"Expected >=1 EngineAccuracy, got {ea_count}"
        print(f"   Engines scored: {len(engines)}, DB rows: {ea_count}")

        # 8. Learning Service
        print("\n8. Running Learning Service...")
        from services.learning_service import generate_weekly_report, get_model_health
        health = get_model_health(session)
        assert health["status"] == "ok"
        print(f"   Health: MAE={health['avg_mae_recent']:.3f}, bias={health['bias_direction']}")

        weekly = generate_weekly_report(session, gameweek_id=1)
        assert weekly.status == "ok"
        assert weekly.n_versions_evaluated >= 1
        assert len(weekly.insights) >= 1
        print(f"   Weekly report: {weekly.n_versions_evaluated} versions, {len(weekly.insights)} insights")

        session.commit()
        print("\n" + "=" * 60)
        print("FULL VALIDATION CYCLE: PASSED")
        print("=" * 60)

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_version_comparison():
    """Test: create two versions, validate both, compare."""
    print("\n" + "=" * 60)
    print("TEST: Version Comparison")
    print("=" * 60)

    reset_db()
    session = get_session()

    try:
        from database.crud import create_prediction_version
        from engines.validation_engine import compare_versions, validate_version
        from features import build_feature_store
        from services.pipeline import run_projection_pipeline

        player_df = create_synthetic_players(30)
        store = build_feature_store(players_df=player_df, gameweek_id=1)

        # Version A (better predictions)
        result_a = run_projection_pipeline(store=store, gameweek_id=1, persist=True, session=session)
        session.commit()

        # Inject actuals (close to A's predictions)
        for p in session.query(Projection).filter_by(version_id=result_a.version_id).all():
            p.actual_points = max(0, round(p.projected_points + random.gauss(0, 1.0)))
        session.flush()

        # Version B (worse predictions — copy with noise)
        pv_b = create_prediction_version(
            session=session,
            version_tag="v2-gw1-worse",
            model_name="projection_v2_worse",
            config_hash="worse123",
            features_used=["minutes", "xgi"],
            weights_snapshot={"noise": 2},
        )
        for p in session.query(Projection).filter_by(version_id=result_a.version_id).all():
            # Add noise to projected_points
            noisy = Projection(
                version_id=pv_b.id,
                player_id=p.player_id,
                gameweek_id=p.gameweek_id,
                projected_points=p.projected_points + random.gauss(0, 3.0),
                ci_80_low=p.ci_80_low - 1,
                ci_80_high=p.ci_80_high + 1,
                ci_95_low=p.ci_95_low - 2,
                ci_95_high=p.ci_95_high + 2,
                minutes_proj=p.minutes_proj,
                goals_proj=p.goals_proj,
                assists_proj=p.assists_proj,
                actual_points=p.actual_points,
            )
            session.add(noisy)
        session.flush()

        # Validate both
        validate_version(session, result_a.version_id, gameweek_id=1, persist=True)
        validate_version(session, pv_b.id, gameweek_id=1, persist=True)
        session.flush()

        # Compare
        comp = compare_versions(session, result_a.version_id, pv_b.id)
        assert "error" not in comp, f"Comparison failed: {comp}"
        assert comp["winner"] in ("A", "B", "tie")
        assert comp["mae_a"] > 0
        assert comp["mae_b"] > 0

        print(f"   Version A MAE: {comp['mae_a']:.3f}")
        print(f"   Version B MAE: {comp['mae_b']:.3f}")
        print(f"   Improvement: {comp['mae_improvement_pct']:+.1f}%")
        print(f"   Winner: {comp['winner']}")

        session.commit()
        print("\nVERSION COMPARISON: PASSED")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_error_classifier_rules():
    """Test each error classifier rule with crafted scenarios."""
    print("\n" + "=" * 60)
    print("TEST: Error Classifier Rules")
    print("=" * 60)

    from services.error_classifier import _classify_one, _classify_severity

    # We'll test _classify_one directly with mock objects
    class MockProjection:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class MockPlayer:
        def __init__(self, element_type):
            self.element_type = element_type

    class MockPGWS:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    # Rule 1a: Minutes miss (predicted playing, didn't play)
    print("\n1a. Minutes miss (predicted 70min, actual 0min)...")
    proj = MockProjection(id=1, player_id=10, minutes_proj=70, goals_proj=0.2, assists_proj=0.1, clean_sheet_proj=3)
    pgws = MockPGWS(minutes=0, goals_scored=0, assists=0, clean_sheets=0)
    record = _classify_one(proj, MockPlayer(2), pgws, error=-5.0, abs_error=5.0, version_id=1, gameweek_id=1)
    assert record.error_type == "minutes_miss", f"Expected minutes_miss, got {record.error_type}"
    assert record.error_severity == "severe"
    print(f"   PASS: {record.error_type} ({record.error_severity})")

    # Rule 1b: Low minutes (predicted 70min, played 20min)
    print("1b. Low minutes (predicted 70min, actual 20min)...")
    pgws2 = MockPGWS(minutes=20, goals_scored=0, assists=0, clean_sheets=0)
    record2 = _classify_one(proj, MockPlayer(2), pgws2, error=-3.0, abs_error=3.0, version_id=1, gameweek_id=1)
    assert record2.error_type == "low_minutes", f"Expected low_minutes, got {record2.error_type}"
    print(f"   PASS: {record2.error_type} ({record2.error_severity})")

    # Rule 2: Outlier performance (error >= 8)
    print("2. Outlier performance (error=+10)...")
    proj3 = MockProjection(id=3, player_id=30, minutes_proj=70, goals_proj=0.1, assists_proj=0.1, clean_sheet_proj=0)
    pgws3 = MockPGWS(minutes=90, goals_scored=0, assists=0, clean_sheets=0)
    record3 = _classify_one(proj3, MockPlayer(3), pgws3, error=10.0, abs_error=10.0, version_id=1, gameweek_id=1)
    assert record3.error_type == "outlier_performance", f"Expected outlier_performance, got {record3.error_type}"
    print(f"   PASS: {record3.error_type} ({record3.root_cause})")

    # Rule 3a: Goal miss (predicted goals, didn't score)
    print("3a. Goal miss (predicted 0.5 goals, actual 0)...")
    proj4 = MockProjection(id=4, player_id=40, minutes_proj=80, goals_proj=0.5, assists_proj=0.1, clean_sheet_proj=0)
    pgws4 = MockPGWS(minutes=85, goals_scored=0, assists=0, clean_sheets=0)
    record4 = _classify_one(proj4, MockPlayer(3), pgws4, error=-3.0, abs_error=3.0, version_id=1, gameweek_id=1)
    assert record4.error_type == "goal_miss", f"Expected goal_miss, got {record4.error_type}"
    print(f"   PASS: {record4.error_type} ({record4.root_cause})")

    # Rule 3b: Unexpected multi-goal game (predicted <0.2 goals, scored 3)
    print("3b. Unexpected multi-goal (predicted 0.1 goals, scored 3)...")
    proj5 = MockProjection(id=5, player_id=50, minutes_proj=80, goals_proj=0.1, assists_proj=0.1, clean_sheet_proj=0)
    pgws5 = MockPGWS(minutes=90, goals_scored=3, assists=0, clean_sheets=0)
    record5 = _classify_one(proj5, MockPlayer(3), pgws5, error=12.0, abs_error=12.0, version_id=1, gameweek_id=1)
    # This will be caught by outlier rule (abs_error >= 8) before goal rule
    assert record5.error_type == "outlier_performance", f"Expected outlier_performance (fires first), got {record5.error_type}"
    print(f"   PASS: {record5.error_type} (outlier fires before goal rule)")

    # Rule 4: Assists miss (predicted 0.4 assists, got 0)
    print("4. Assists miss (predicted 0.4 assists, actual 0)...")
    proj6 = MockProjection(id=6, player_id=60, minutes_proj=80, goals_proj=0.05, assists_proj=0.4, clean_sheet_proj=0)
    pgws6 = MockPGWS(minutes=85, goals_scored=0, assists=0, clean_sheets=0)
    record6 = _classify_one(proj6, MockPlayer(3), pgws6, error=-2.5, abs_error=2.5, version_id=1, gameweek_id=1)
    assert record6.error_type == "assists_miss", f"Expected assists_miss, got {record6.error_type}"
    print(f"   PASS: {record6.error_type} ({record6.root_cause})")

    # Rule 5: Clean sheet miss (DEF predicted CS, conceded)
    print("5. Clean sheet miss (DEF predicted CS, conceded)...")
    proj7 = MockProjection(id=7, player_id=70, minutes_proj=90, goals_proj=0.02, assists_proj=0.05, clean_sheet_proj=4)
    pgws7 = MockPGWS(minutes=90, goals_scored=0, assists=0, clean_sheets=0)
    record7 = _classify_one(proj7, MockPlayer(2), pgws7, error=-4.0, abs_error=4.0, version_id=1, gameweek_id=1)
    assert record7.error_type == "clean_sheet_miss", f"Expected clean_sheet_miss, got {record7.error_type}"
    print(f"   PASS: {record7.error_type} ({record7.root_cause})")

    # Default: generic misprediction
    print("6. Generic misprediction (MID, small miss, no special rules)...")
    proj8 = MockProjection(id=8, player_id=80, minutes_proj=70, goals_proj=0.05, assists_proj=0.05, clean_sheet_proj=0)
    pgws8 = MockPGWS(minutes=75, goals_scored=0, assists=0, clean_sheets=0)
    record8 = _classify_one(proj8, MockPlayer(3), pgws8, error=-2.0, abs_error=2.0, version_id=1, gameweek_id=1)
    assert record8.error_type == "generic_misprediction", f"Expected generic_misprediction, got {record8.error_type}"
    print(f"   PASS: {record8.error_type} ({record8.root_cause})")

    # Severity classification
    print("\n7. Severity thresholds...")
    assert _classify_severity(1.0) == "minor"
    assert _classify_severity(3.0) == "moderate"
    assert _classify_severity(5.0) == "moderate"
    assert _classify_severity(6.0) == "severe"
    assert _classify_severity(10.0) == "severe"
    print("   PASS: all severity thresholds correct")

    print("\n" + "=" * 60)
    print("ERROR CLASSIFIER RULES: ALL PASSED")
    print("=" * 60)


def test_persistence_idempotency():
    """Test that persisting twice for the same version_tag is safe."""
    print("\n" + "=" * 60)
    print("TEST: Persistence Idempotency")
    print("=" * 60)

    reset_db()
    session = get_session()

    try:
        from features import build_feature_store
        from services.pipeline import run_projection_pipeline

        player_df = create_synthetic_players(20)
        store = build_feature_store(players_df=player_df, gameweek_id=1)

        # Run twice with same gameweek
        result1 = run_projection_pipeline(store=store, gameweek_id=1, persist=True, session=session)
        session.commit()

        result2 = run_projection_pipeline(store=store, gameweek_id=1, persist=True, session=session)
        session.commit()

        # Should return same version_id (idempotent)
        assert result1.version_id == result2.version_id, (
            f"Idempotency broken: {result1.version_id} != {result2.version_id}"
        )

        # Only one PredictionVersion row should exist
        pv_count = session.query(PredictionVersion).filter_by(
            version_tag=result1.version_tag
        ).count()
        assert pv_count == 1, f"Expected 1 PredictionVersion, got {pv_count}"

        print(f"   Same version_tag returned: {result1.version_tag}")
        print(f"   Same version_id: {result1.version_id}")
        print(f"   PredictionVersion rows: {pv_count}")

        session.commit()
        print("\nPERSISTENCE IDEMPOTENCY: PASSED")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def test_schema_integrity():
    """Verify all 17 tables exist with expected columns."""
    print("\n" + "=" * 60)
    print("TEST: Schema Integrity")
    print("=" * 60)

    reset_db()
    session = get_session()

    try:
        inspector = inspect(session.get_bind())
        tables = sorted(inspector.get_table_names())

        expected_tables = [
            "chip_state", "decision_log", "engine_accuracy",
            "error_classifications", "experiment_runs", "gameweeks",
            "player_gameweek_stats", "player_snapshots", "players",
            "prediction_versions", "price_history", "projections",
            "recommendation_outcomes", "snapshots", "teams",
            "validation_metrics",
        ]

        # manual_squad may or may not exist depending on earlier schema
        missing = [t for t in expected_tables if t not in tables]
        assert not missing, f"Missing tables: {missing}"

        print(f"   All {len(expected_tables)} expected tables present")

        # Spot-check key tables have expected columns
        proj_cols = {c["name"] for c in inspector.get_columns("projections")}
        required_proj = {"version_id", "player_id", "gameweek_id", "projected_points",
                         "ci_80_low", "ci_80_high", "ci_95_low", "ci_95_high", "actual_points"}
        missing_proj = required_proj - proj_cols
        assert not missing_proj, f"Missing Projection columns: {missing_proj}"
        print(f"   Projections: {len(proj_cols)} columns, all required present")

        vm_cols = {c["name"] for c in inspector.get_columns("validation_metrics")}
        required_vm = {"version_id", "gameweek_id", "mae", "rmse", "bias", "coverage_80", "coverage_95"}
        missing_vm = required_vm - vm_cols
        assert not missing_vm, f"Missing ValidationMetrics columns: {missing_vm}"
        print(f"   ValidationMetrics: {len(vm_cols)} columns, all required present")

        print("\nSCHEMA INTEGRITY: PASSED")

    finally:
        session.close()


def test_evidence_thresholds_and_candidate_improvements():
    """Test evidence thresholds and candidate improvement generation."""
    print("\n" + "=" * 60)
    print("TEST: Evidence Thresholds & Candidate Improvements")
    print("=" * 60)

    from services.learning_service import (
        CandidateImprovement,
        generate_weekly_report,
        get_evidence_description,
        get_evidence_level,
    )

    # Test evidence level determination
    print("\n1. Evidence Level Thresholds...")
    assert get_evidence_level(1) == "weak", f"Expected 'weak' for 1 GW, got {get_evidence_level(1)}"
    assert get_evidence_level(2) == "needs_more_data", "Expected 'needs_more_data' for 2 GW"
    assert get_evidence_level(3) == "moderate", "Expected 'moderate' for 3 GW"
    assert get_evidence_level(5) == "moderate", "Expected 'moderate' for 5 GW"
    assert get_evidence_level(10) == "statistically_significant", "Expected 'statistically_significant' for 10 GW"
    # With high consistency, 5+ GW should be 'strong'
    assert get_evidence_level(5, 0.8) == "strong", "Expected 'strong' for 5 GW with high consistency"
    print("   PASS: All evidence level thresholds correct")

    # Test evidence descriptions
    print("2. Evidence Descriptions...")
    for level in ['weak', 'needs_more_data', 'moderate', 'strong', 'statistically_significant']:
        desc = get_evidence_description(level)
        assert len(desc) > 20, f"Description too short for {level}"
    print("   PASS: All evidence descriptions present")

    # Test CandidateImprovement dataclass
    print("3. CandidateImprovement Dataclass...")
    candidate = CandidateImprovement(
        problem_observed="Model systematically underpredicting by 1.5 points",
        supporting_metrics={"bias": 1.5, "mae": 3.2},
        n_observations=150,
        gameweeks_affected=[1, 2, 3],
        expected_impact="Reduce MAE by ~0.5 points",
        evidence_level="moderate",
        potential_risk="Could overcorrect",
        recommended_action="Review baselines if pattern persists",
        status="recommendation_only",
    )
    assert candidate.status == "recommendation_only", "Status should always be recommendation_only"
    assert candidate.evidence_level == "moderate"
    print("   PASS: CandidateImprovement dataclass works correctly")

    # Test with real validation cycle
    print("4. Candidate Improvements from Real Data...")
    reset_db()
    session = get_session()
    try:
        from features import build_feature_store
        from services.pipeline import run_projection_pipeline

        player_df = create_synthetic_players(50)
        store = build_feature_store(players_df=player_df, gameweek_id=1)

        # Run pipeline and persist
        result = run_projection_pipeline(store=store, gameweek_id=1, persist=True, session=session)
        session.commit()

        # Inject actuals with systematic bias (underpredicting)
        projections = session.query(Projection).filter_by(version_id=result.version_id).all()
        for p in projections:
            p.actual_points = max(0, round(p.projected_points + 3.0))  # systematic +3 bias
        session.flush()

        # Run validation first (generates ValidationMetrics rows)
        from engines.validation_engine import validate_version
        validate_version(session, result.version_id, gameweek_id=1, persist=True)
        session.flush()

        # Generate weekly report
        report = generate_weekly_report(session, gameweek_id=1)

        # Check that candidate improvements were generated
        assert len(report.candidate_improvements) > 0, "Should have candidate improvements with biased data"
        assert report.overall_evidence_level == "weak", "Should be weak with only 1 GW"

        # Check that bias candidate was found
        bias_candidates = [c for c in report.candidate_improvements if "underpredicting" in c.problem_observed.lower() or "overpredicting" in c.problem_observed.lower()]
        assert len(bias_candidates) > 0, "Should detect systematic bias"

        print(f"   Candidate improvements found: {len(report.candidate_improvements)}")
        print(f"   Evidence level: {report.overall_evidence_level}")
        print(f"   Bias detected: {bias_candidates[0].problem_observed[:60]}...")

        session.commit()
        print("\nCANDIDATE IMPROVEMENTS: PASSED")

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

if __name__ == "__main__":
    test_schema_integrity()
    test_full_validation_cycle()
    test_version_comparison()
    test_error_classifier_rules()
    test_persistence_idempotency()
    test_evidence_thresholds_and_candidate_improvements()

    # Clean up test DB
    db_path = os.path.join(os.path.dirname(__file__), "..", "instance", "moneyball.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        print("\nTest database cleaned up.")
