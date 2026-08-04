"""Tests for the Expected Projection Engine (compositor) and V2-vs-V3 comparison.

Verifies the xPts = xPts/90 * (minutes/90) formula, component consistency,
confidence intervals, and the full persistence + validation cycle through the
existing validation platform (requires a real DB).
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from sqlalchemy import text
from synthetic import create_synthetic_fixtures, create_synthetic_players

from database.database import engine, get_session
from database.models import Base, Gameweek, Player, Projection, Team
from engines.expected_projection_engine import (
    compare_to_v2,
    run_expected_projection,
)
from features import build_feature_store


def build_store(n=50, seed=42, **kwargs):
    """Build a FeatureStore from synthetic players (optionally overridden)."""
    df = create_synthetic_players(n=n, seed=seed)
    for col, val in kwargs.items():
        df[col] = val
    return build_feature_store(players_df=df, gameweek_id=1)


def test_xpts_formula():
    """xPts = xPts/90 * (expected_minutes / 90)."""
    store = build_store(50)
    for p in run_expected_projection(store, gameweek_id=1):
        expected = p.xpts_per_90 * (p.expected_minutes / 90.0)
        assert abs(p.projected_points - expected) <= 0.01, (
            f"player_id={p.player_id}: {p.projected_points} != {expected}"
        )


def test_components_reconcile_with_points():
    """Components (raw rates) should reconcile with xPts after applying FPL values.

    goals_proj/assists_proj are stored as raw expected event rates (matching the
    V2 schema), so headline points = goals*goal_value + assists*assist_value +
    clean_sheet + bonus + other.
    """
    from utils.config import load_config

    pos_vals = load_config("expected_points")["position_values"]
    store = build_store(50)
    for p in run_expected_projection(store, gameweek_id=1):
        vals = pos_vals.get(p.position, pos_vals["MID"])
        total = (
            p.goals_proj * vals["goal"]
            + p.assists_proj * vals["assist"]
            + p.clean_sheet_proj
            + p.bonus_proj
            + p.other_proj
        )
        # Headline xPts clamps to 0; raw card deductions may keep components
        # slightly negative for card-heavy, low-scoring players.
        assert abs(max(total, 0.0) - p.projected_points) <= 0.05, (
            f"player_id={p.player_id}: reconciled {total} != projected {p.projected_points}"
        )


def test_confidence_intervals_well_formed():
    store = build_store(50)
    for p in run_expected_projection(store, gameweek_id=1):
        assert 0 <= p.ci_80_low <= p.projected_points <= p.ci_80_high
        assert 0 <= p.ci_95_low <= p.projected_points <= p.ci_95_high
        assert p.ci_95_high >= p.ci_80_high
        assert 10.0 <= p.confidence <= 95.0


def test_zero_minutes_produces_zero_xpts():
    store = build_store(2, seed=1, minutes=[0, 500], status=["i", "a"])
    projections = run_expected_projection(store, gameweek_id=1)
    by_id = {p.player_id: p for p in projections}
    absent = by_id[int(store.df.iloc[0]["player_id"])]
    assert absent.expected_minutes == 0.0
    assert absent.projected_points == 0.0


def test_compare_to_v2_alignment():
    """In-memory alignment report against the V2 baseline (no actuals)."""
    store = build_store(50)
    from services.pipeline import run_projection_pipeline

    v2 = run_projection_pipeline(store=store, gameweek_id=1).projections
    v3 = run_expected_projection(store, gameweek_id=1)

    report = compare_to_v2(v3, v2)
    assert "error" not in report
    assert report["n_common_players"] == 50
    assert 0.0 <= report["mean_abs_diff"] <= 50.0
    assert -1.0 <= report["correlation"] <= 1.0
    assert "v3_mean_pts" in report


def test_compare_to_v2_empty_guard():
    assert "error" in compare_to_v2([], [])
    store = build_store(5)
    v3 = run_expected_projection(store, gameweek_id=1)
    assert "error" in compare_to_v2(v3, [])


# ------------------------------------------------------------------
# Integration: persistence + validation through the existing platform
# ------------------------------------------------------------------

def reset_db():
    """Drop and recreate all tables, then seed minimal reference data."""
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


def test_full_comparison_cycle():
    """Pipeline → persist V2+V3 → inject actuals → validate → compare."""
    reset_db()
    session = get_session()

    try:
        from engines.validation_engine import validate_version
        from services.expected_pipeline import (
            compare_expected_vs_baseline,
            run_expected_points_comparison,
        )

        player_df = create_synthetic_players(50)
        fixture_map = build_fixture_map(create_synthetic_fixtures())
        store = build_feature_store(
            players_df=player_df,
            fixture_map=fixture_map,
            team_name_map={i: f"Team{i}" for i in range(1, 21)},
            gameweek_id=1,
        )

        # 1. Run comparison + persist both versions
        result = run_expected_points_comparison(
            store=store, session=session, gameweek_id=1, persist=True,
        )
        session.commit()

        assert result.persisted is True
        assert result.baseline_version_id is not None
        assert result.expected_version_id is not None
        assert result.baseline_version_id != result.expected_version_id
        assert result.alignment["n_common_players"] == 50

        # 2. Idempotency: rerun returns the same version ids
        result2 = run_expected_points_comparison(
            store=store, session=session, gameweek_id=1, persist=True,
        )
        session.commit()
        assert result2.expected_version_id == result.expected_version_id
        assert result2.baseline_version_id == result.baseline_version_id

        # 3. Inject synthetic actuals into both versions
        for version_id in (result.baseline_version_id, result.expected_version_id):
            for p in session.query(Projection).filter_by(version_id=version_id).all():
                p.actual_points = max(0, round(p.projected_points + random.gauss(0, 2.0)))
        session.flush()

        # 4. Validate both versions through the existing validation engine
        validate_version(session, result.baseline_version_id, gameweek_id=1, persist=True)
        validate_version(session, result.expected_version_id, gameweek_id=1, persist=True)
        session.flush()

        # 5. Compare via the validation platform
        comp = compare_expected_vs_baseline(
            session, result.baseline_version_id, result.expected_version_id,
        )
        assert "error" not in comp, f"Comparison failed: {comp}"
        assert comp["winner"] in ("A", "B", "tie")
        assert comp["mae_a"] > 0 and comp["mae_b"] > 0

        session.commit()
    finally:
        session.close()


def build_fixture_map(fixtures):
    from engines.fixture_engine import build_fixture_map as _bfm
    return _bfm(fixtures)
