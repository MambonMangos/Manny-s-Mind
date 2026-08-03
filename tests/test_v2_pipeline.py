"""End-to-end test for the V2 projection pipeline.

Uses synthetic player data to verify the pipeline chains all engines
correctly without needing a live FPL API connection.

Assertion-based: each stage verifies invariants rather than relying on
"no exception == pass".
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

# Ensure project root is importable when run via pytest.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def create_synthetic_players(n=50):
    """Create synthetic player DataFrame for testing."""
    np.random.seed(42)

    positions = np.random.choice(["GKP", "DEF", "MID", "FWD"], n, p=[0.15, 0.35, 0.35, 0.15])
    team_ids = np.random.randint(1, 21, n)

    data = {
        "player_id": range(1, n + 1),
        "web_name": [f"Player{i}" for i in range(1, n + 1)],
        "position": positions,
        "team_id": team_ids,
        "price": np.random.uniform(4.0, 14.0, n).round(1),
        "total_points": np.random.randint(0, 200, n),
        "minutes": np.random.randint(0, 3000, n),
        "goals_scored": np.random.randint(0, 20, n),
        "assists": np.random.randint(0, 15, n),
        "expected_goals": np.random.uniform(0, 15, n).round(2),
        "expected_assists": np.random.uniform(0, 10, n).round(2),
        "expected_goal_involvements": np.random.uniform(0, 20, n).round(2),
        "expected_goals_conceded": np.random.uniform(0, 30, n).round(2),
        "form": np.random.uniform(0, 10, n).round(1),
        "selected_by_percent": np.random.uniform(0.5, 60, n).round(1),
        "transfers_in_event": np.random.randint(0, 50000, n),
        "transfers_out_event": np.random.randint(0, 50000, n),
        "cost_change_start": np.random.randint(-10, 10, n),
        "cost_change_event": np.random.randint(-3, 3, n),
        "status": np.random.choice(["a", "a", "a", "d", "i"], n),
        "news": [""] * n,
        "chance_of_playing_next_round": np.random.choice([0, 50, 75, 100], n),
        "chance_of_playing_this_round": np.random.choice([0, 50, 75, 100], n),
        "penalties_order": np.random.choice([None, 1, 2, 3, 99], n),
        "direct_freekicks_order": np.random.choice([None, 1, 2, 3, 99], n),
        "corners_and_indirect_freekicks_order": np.random.choice([None, 1, 2, 3, 99], n),
        "influence": np.random.uniform(0, 100, n),
        "creativity": np.random.uniform(0, 100, n),
        "threat": np.random.uniform(0, 100, n),
        "ict_index": np.random.uniform(0, 100, n),
        "value_form": np.random.uniform(0, 10, n),
        "value_season": np.random.uniform(0, 50, n),
        "event_points": np.random.randint(0, 20, n),
        "strength_overall_home": np.random.randint(100, 1400, n),
        "strength_overall_away": np.random.randint(100, 1400, n),
        "starts": (np.random.randint(0, 3000, n) / 90).round().astype(int),
    }

    return pd.DataFrame(data)


def create_synthetic_fixtures(n_teams=20, n_gws=10):
    """Create synthetic fixture data."""
    rng = np.random.default_rng(42)
    fixtures = []
    for gw in range(1, n_gws + 1):
        for i in range(0, n_teams, 2):
            fixtures.append({
                "event": gw,
                "team_h": i + 1,
                "team_a": i + 2,
                "team_h_difficulty": int(rng.integers(1, 6)),
                "team_a_difficulty": int(rng.integers(1, 6)),
            })
    return fixtures


def test_pipeline():
    """Test the full V2 projection pipeline with assertions at every stage."""
    # 1. Synthetic data shape
    player_df = create_synthetic_players(50)
    assert len(player_df) == 50, "Expected 50 synthetic players"
    assert set(player_df["position"].unique()) <= {"GKP", "DEF", "MID", "FWD"}

    # 2. Fixture map
    fixtures = create_synthetic_fixtures()
    from engines.fixture_engine import build_fixture_map
    fixture_map = build_fixture_map(fixtures)
    assert len(fixture_map) == 20, f"Expected 20 teams in fixture map, got {len(fixture_map)}"

    # 3. Feature Store
    from features import build_feature_store
    from utils.config import get_config_hash

    config_hash = get_config_hash("prediction")
    store = build_feature_store(
        players_df=player_df,
        fixture_map=fixture_map,
        team_name_map={i: f"Team{i}" for i in range(1, 21)},
        gameweek_id=3,
        config_hash=config_hash,
    )
    summary = store.summary()
    assert summary.get("n_players", 0) > 0, "Feature Store must contain players"
    assert store.config_hash == config_hash, "Config hash must propagate to Feature Store"

    # 4. Pipeline run
    from services.pipeline import run_projection_pipeline

    current_squad = list(range(1, 16))
    result = run_projection_pipeline(
        store=store,
        gameweek_id=3,
        current_squad=current_squad,
        budget_remaining=5.0,
    )

    # 5. Projections: one per player, valid point range, sane CIs
    assert len(result.projections) > 0, "Pipeline must produce projections"
    for p in result.projections:
        assert p.projected_points >= 0, f"Negative projection for {p.web_name}"
        if p.ci_80_low is not None and p.ci_80_high is not None:
            assert p.ci_80_low <= p.ci_80_high, "80% CI bounds must be ordered"

    # 6. Confidence: tiers are from a known set
    if result.confidence:
        known_tiers = {"Very High", "High", "Medium", "Low", "Very Low"}
        for c in result.confidence:
            assert c.confidence_tier in known_tiers, f"Unknown tier {c.confidence_tier}"

    # 7. Market signals: sentiment values are valid
    if result.market_signals:
        for s in result.market_signals:
            assert s.market_sentiment in {"hot", "warm", "cold", "neutral"}, (
                f"Unknown sentiment {s.market_sentiment}"
            )

    # 8. Undervalued players carry a score
    for u in result.undervalued:
        assert u.opportunity_score > 0, "Opportunity score must be positive"
        assert u.points_per_million >= 0, "Pts/£m must be non-negative"
        assert u.web_name, "Undervalued player must have a name"

    # 9. Squad recommendation: transfers reference real player names
    if result.squad_recommendation:
        rec = result.squad_recommendation
        assert rec.improvement >= 0, "Recommended improvement must be non-negative"
        for t in rec.suggested_transfers:
            assert isinstance(t, dict), "Each transfer must be a dict"
            assert t.get("out") and t.get("in"), "Transfer must name both players"

    # 10. Timing: pipeline finished, duration recorded
    assert result.pipeline_duration_ms >= 0, "Pipeline duration must be recorded"


if __name__ == "__main__":
    test_pipeline()
    print("\nALL TESTS PASSED!")
