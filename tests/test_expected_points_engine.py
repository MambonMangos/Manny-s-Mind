"""Tests for the Expected Points Engine (xPts/90).

Verifies math correctness, position-specific behaviour, missing-data handling,
determinism and the penalty-taker bonus. No database required.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pandas as pd
from synthetic import create_synthetic_players

from engines.expected_points_engine import (
    expected_points_to_dataframe,
    project_expected_points,
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
    projections = project_expected_points(store, gameweek_id=1)

    assert len(projections) == 50
    ids = [p.player_id for p in projections]
    assert ids == sorted(ids), "Projections should be sorted by player_id"


def test_xpts_per_90_non_negative_and_finite():
    store = build_store(50)
    for p in project_expected_points(store, gameweek_id=1):
        assert np.isfinite(p.xpts_per_90)
        assert p.xpts_per_90 >= 0


def test_formula_math_controlled():
    """A FWD with xG=2 over 2 games, neutral fixture → exactly 2.0 xPts/90.

    FWD goal value = 4, fixture difficulty 3 → multiplier 0.5, no CS value,
    no bonus/saves/cards/set pieces.
    """
    row = {
        "player_id": 1, "web_name": "Calc", "position": "FWD", "team_id": 1,
        "price": 5.0, "total_points": 50, "minutes": 180, "goals_scored": 1,
        "assists": 0, "expected_goals": 2.0, "expected_assists": 0.0,
        "expected_goal_involvements": 2.0, "expected_goals_conceded": 3.0,
        "form": 3.0, "selected_by_percent": 10.0, "transfers_in_event": 0,
        "transfers_out_event": 0, "cost_change_start": 0, "cost_change_event": 0,
        "status": "a", "news": "", "chance_of_playing_next_round": 100,
        "chance_of_playing_this_round": 100, "penalties_order": None,
        "direct_freekicks_order": None, "corners_and_indirect_freekicks_order": None,
        "influence": 30, "creativity": 30, "threat": 30, "ict_index": 30,
        "value_form": 3, "value_season": 10, "event_points": 5,
        "strength_overall_home": 1000, "strength_overall_away": 1000,
        "clean_sheets": 2, "saves": 0, "bonus": 0, "bps": 0, "red_cards": 0,
        "yellow_cards": 0, "starts": 2,
    }
    store = build_feature_store(players_df=pd.DataFrame([row]), gameweek_id=1)
    (proj,) = project_expected_points(store, gameweek_id=1)

    assert proj.xg_90 == 1.0, f"Expected xg_90=1.0, got {proj.xg_90}"
    assert proj.fixture_multiplier == 0.5
    assert proj.clean_sheet_prob == 0.0, "FWD should have no clean-sheet value"
    assert proj.xpts_per_90 == 2.0, f"Expected exactly 2.0, got {proj.xpts_per_90}"


def test_clean_sheet_only_for_gkp_def():
    store = build_store(50)
    for p in project_expected_points(store, gameweek_id=1):
        if p.position in ("GKP", "DEF"):
            assert 0.0 <= p.clean_sheet_prob <= 1.0
        else:
            assert p.clean_sheet_prob == 0.0


def test_clean_sheet_prob_decreases_with_xgc():
    """A team conceding more should have a lower clean-sheet probability."""
    gk_bad = build_store(1, seed=1, expected_goals_conceded=[22.0], position=["GKP"])
    gk_good = build_store(1, seed=2, expected_goals_conceded=[5.0], position=["GKP"])
    bad = project_expected_points(gk_bad)[0]
    good = project_expected_points(gk_good)[0]
    assert good.clean_sheet_prob > bad.clean_sheet_prob


def test_penalty_taker_bonus():
    base = build_store(2, seed=7)
    bonus_df = build_store(2, seed=7)
    bonus_df.df.loc[0, "penalties_order"] = 1
    bonus_df.df.loc[0, "set_piece_raw"] = 80

    base_p = {p.player_id: p.xpts_per_90 for p in project_expected_points(base)}
    bonus_p = {p.player_id: p.xpts_per_90 for p in project_expected_points(bonus_df)}

    pid = base.df.iloc[0]["player_id"]
    assert bonus_p[pid] > base_p[pid], "Penalty taker should earn a bonus"


def test_missing_data_handling():
    """A player with no data still gets a valid, low-confidence projection."""
    store = build_store(
        2, seed=3,
        minutes=[0, 500],
        bps=[0, 100],
        expected_goal_involvements=[0.0, 5.0],
        expected_goals=[0.0, 2.0],
        expected_assists=[0.0, 1.0],
        form=[0.0, 3.0],
        status=["i", "a"],
    )
    projections = project_expected_points(store, gameweek_id=1)
    by_id = {p.player_id: p for p in projections}

    empty = by_id[int(store.df.iloc[0]["player_id"])]
    assert empty.data_quality == "none"
    assert np.isfinite(empty.xpts_per_90)
    assert empty.games_played == 1
    assert empty.xpts_per_90 == 0.0


def test_determinism():
    a = project_expected_points(build_store(50, seed=9))
    b = project_expected_points(build_store(50, seed=9))
    assert a == b, "Same input must produce identical output"


def test_dataframe_conversion():
    store = build_store(10)
    df = expected_points_to_dataframe(project_expected_points(store))
    assert "xpts_per_90" in df.columns
    assert "clean_sheet_prob" in df.columns
    assert len(df) == 10
