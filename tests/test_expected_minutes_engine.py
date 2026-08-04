"""Tests for the Expected Minutes Engine.

Verifies the start-probability model (unavailable/doubtful/fit), the
minutes-if-starting blend, substitution risk, rotation classification and the
composite expected_minutes formula. No database required.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from synthetic import create_synthetic_players

from engines.expected_minutes_engine import (
    _classify_rotation_risk,
    _compute_minutes_if_starting,
    _compute_start_probability,
    _compute_substitution_risk,
    expected_minutes_to_dataframe,
    project_expected_minutes,
)
from features import build_feature_store


def build_store(n=50, seed=42, **kwargs):
    """Build a FeatureStore from synthetic players (optionally overridden)."""
    df = create_synthetic_players(n=n, seed=seed)
    for col, val in kwargs.items():
        df[col] = val
    return build_feature_store(players_df=df, gameweek_id=1)


def test_all_players_projected_and_sorted():
    store = build_store(50)
    projections = project_expected_minutes(store, gameweek_id=1)
    assert len(projections) == 50
    ids = [p.player_id for p in projections]
    assert ids == sorted(ids)


def test_expected_minutes_bounds():
    store = build_store(50)
    for p in project_expected_minutes(store, gameweek_id=1):
        assert 0.0 <= p.expected_minutes <= 90.0
        assert 0.0 <= p.start_probability <= 1.0
        assert 0.0 <= p.substitution_risk <= 1.0


def test_injured_player_zero_start():
    store = build_store(2, seed=1, status=["i", "a"])
    projections = project_expected_minutes(store, gameweek_id=1)
    by_id = {p.player_id: p for p in projections}

    injured = by_id[int(store.df.iloc[0]["player_id"])]
    assert injured.start_probability == 0.0
    assert injured.expected_minutes == 0.0


def test_doubtful_player_reduced():
    store = build_store(2, seed=1, status=["d", "a"])
    projections = project_expected_minutes(store, gameweek_id=1)
    by_id = {p.player_id: p for p in projections}
    doubtful = by_id[int(store.df.iloc[0]["player_id"])]
    assert doubtful.start_probability == 0.40


def test_ever_present_gets_high_minutes():
    store = build_store(
        2, seed=1,
        position=["DEF", "FWD"],
        minutes=[2700, 90],
        starts=[30, 1],
        chance_of_playing_next_round=[100, 50],
        status=["a", "a"],
    )
    projections = project_expected_minutes(store, gameweek_id=1)
    by_id = {p.player_id: p for p in projections}
    ever_present = by_id[int(store.df.iloc[0]["player_id"])]
    part_timer = by_id[int(store.df.iloc[1]["player_id"])]
    assert ever_present.expected_minutes > part_timer.expected_minutes


def test_minutes_if_starting_blend():
    """A long-serving DEF blends history with the positional baseline (88)."""
    positional = {"GKP": 90, "DEF": 88, "MID": 78, "FWD": 75}
    history_cfg = {"min_starts_for_history": 3, "history_blend": 0.6, "base_blend": 0.4}

    blended = _compute_minutes_if_starting(
        starts=30, minutes_per_game=84.0, position="DEF",
        positional_minutes=positional, history_cfg=history_cfg,
    )
    expected = 0.6 * 84.0 + 0.4 * 88.0
    assert abs(blended - expected) < 1e-9

    # Few starts → fall back to positional baseline
    fallback = _compute_minutes_if_starting(
        starts=1, minutes_per_game=84.0, position="DEF",
        positional_minutes=positional, history_cfg=history_cfg,
    )
    assert fallback == 88.0


def test_substitution_risk_increases_for_full_minutes():
    cfg = {"baseline_risk": 0.10, "high_minutes_threshold": 78, "risk_if_expected_full": 0.25}
    low = _compute_substitution_risk(70.0, cfg)
    high = _compute_substitution_risk(90.0, cfg)
    assert low == 0.10
    assert high == 0.25


def test_rotation_classification_thresholds():
    cfg = {"high_threshold": 0.30, "medium_threshold": 0.60}
    assert _classify_rotation_risk(0.10, cfg) == "High"
    assert _classify_rotation_risk(0.45, cfg) == "Medium"
    assert _classify_rotation_risk(0.80, cfg) == "Low"


def test_start_probability_formula():
    cfg = {
        "unavailable_statuses": ["i", "s", "u"],
        "doubtful_status": "d",
        "doubtful_prob": 0.40,
        "history_weight": 0.60,
        "chance_of_playing_weight": 0.40,
        "high_form_threshold": 6.0,
        "high_form_boost": 0.05,
        "low_form_threshold": 2.0,
        "low_form_penalty": 0.05,
        "max_start_prob": 0.97,
        "min_start_prob": 0.05,
    }
    assert _compute_start_probability("i", 0.8, 1.0, 3.0, cfg) == 0.0
    assert _compute_start_probability("d", 0.8, 1.0, 3.0, cfg) == 0.40

    # 0.9*0.6 + 1.0*0.4 + 0.05 = 0.99 → clipped to max_start_prob (0.97)
    prob = _compute_start_probability("a", 0.9, 1.0, 7.0, cfg)
    assert abs(prob - 0.97) < 1e-9


def test_determinism():
    a = project_expected_minutes(build_store(50, seed=9))
    b = project_expected_minutes(build_store(50, seed=9))
    assert a == b


def test_dataframe_conversion():
    store = build_store(10)
    df = expected_minutes_to_dataframe(project_expected_minutes(store))
    assert "expected_minutes" in df.columns
    assert "start_probability" in df.columns
    assert len(df) == 10
