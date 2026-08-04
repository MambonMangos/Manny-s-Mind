"""Shared synthetic data helpers for tests.

Deterministic (seeded) player and fixture DataFrames matching the FeatureStore
input schema. Used by the expected-points engine tests to avoid a live FPL API.
"""

import numpy as np
import pandas as pd


def create_synthetic_players(n=50, seed=42):
    """Create a synthetic player DataFrame matching the FeatureStore schema."""
    rng = np.random.default_rng(seed)

    positions = rng.choice(["GKP", "DEF", "MID", "FWD"], n, p=[0.12, 0.35, 0.38, 0.15])

    data = {
        "player_id": range(1, n + 1),
        "web_name": [f"Player{i}" for i in range(1, n + 1)],
        "position": positions,
        "team_id": rng.integers(1, 21, n),
        "price": rng.uniform(4.0, 14.0, n).round(1),
        "total_points": rng.integers(10, 200, n),
        "minutes": rng.integers(90, 3000, n),
        "goals_scored": rng.integers(0, 15, n),
        "assists": rng.integers(0, 10, n),
        "expected_goals": rng.uniform(0, 12, n).round(2),
        "expected_assists": rng.uniform(0, 8, n).round(2),
        "expected_goal_involvements": rng.uniform(0, 15, n).round(2),
        "expected_goals_conceded": rng.uniform(0, 25, n).round(2),
        "form": rng.uniform(0, 8, n).round(1),
        "selected_by_percent": rng.uniform(1, 50, n).round(1),
        "transfers_in_event": rng.integers(0, 30000, n),
        "transfers_out_event": rng.integers(0, 30000, n),
        "cost_change_start": rng.integers(-8, 8, n),
        "cost_change_event": rng.integers(-2, 2, n),
        "status": ["a"] * n,
        "news": [""] * n,
        "chance_of_playing_next_round": [100] * n,
        "chance_of_playing_this_round": [100] * n,
        "penalties_order": [None] * n,
        "direct_freekicks_order": [None] * n,
        "corners_and_indirect_freekicks_order": [None] * n,
        "influence": rng.uniform(0, 80, n),
        "creativity": rng.uniform(0, 80, n),
        "threat": rng.uniform(0, 80, n),
        "ict_index": rng.uniform(0, 80, n),
        "value_form": rng.uniform(0, 8, n),
        "value_season": rng.uniform(0, 40, n),
        "event_points": rng.integers(0, 20, n),
        "strength_overall_home": rng.integers(900, 1400, n),
        "strength_overall_away": rng.integers(900, 1400, n),
        "clean_sheets": rng.integers(0, 15, n),
        "saves": rng.integers(0, 120, n),
        "bonus": rng.integers(0, 20, n),
        "bps": rng.integers(0, 500, n),
        "red_cards": rng.integers(0, 1, n),
        "yellow_cards": rng.integers(0, 10, n),
        "starts": rng.integers(1, 34, n),
    }

    return pd.DataFrame(data)


def create_synthetic_fixtures(n_teams=20, n_gws=10, seed=42):
    """Create synthetic fixture data for all teams and gameweeks."""
    rng = np.random.default_rng(seed)
    fixtures = []
    for gw in range(1, n_gws + 1):
        for i in range(1, n_teams + 1, 2):
            home = i
            away = i + 1 if i + 1 <= n_teams else 1
            fixtures.append({
                "event": gw,
                "team_h": home,
                "team_a": away,
                "team_h_difficulty": int(rng.integers(1, 6)),
                "team_a_difficulty": int(rng.integers(1, 6)),
            })
    return fixtures
