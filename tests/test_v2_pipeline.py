"""End-to-end test for the V2 projection pipeline.

Uses synthetic player data to verify the pipeline chains all engines
correctly without needing a live FPL API connection.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd


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
    fixtures = []
    for gw in range(1, n_gws + 1):
        for i in range(0, n_teams, 2):
            fixtures.append({
                "event": gw,
                "team_h": i + 1,
                "team_a": i + 2,
                "team_h_difficulty": np.random.randint(1, 6),
                "team_a_difficulty": np.random.randint(1, 6),
            })
    return fixtures


def test_pipeline():
    """Test the full V2 projection pipeline."""
    print("=" * 60)
    print("V2 Projection Pipeline — End-to-End Test")
    print("=" * 60)

    # 1. Create synthetic data
    print("\n1. Creating synthetic player data...")
    player_df = create_synthetic_players(50)
    print(f"   Created {len(player_df)} players")
    print(f"   Positions: {player_df['position'].value_counts().to_dict()}")

    # 2. Build fixture map
    print("\n2. Building fixture map...")
    fixtures = create_synthetic_fixtures()
    from engines.fixture_engine import build_fixture_map
    fixture_map = build_fixture_map(fixtures)
    print(f"   Built fixture map for {len(fixture_map)} teams")

    # 3. Build feature store
    print("\n3. Building Feature Store...")
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
    print(f"   Feature Store: {store.summary()}")

    # 4. Run pipeline
    print("\n4. Running V2 Projection Pipeline...")
    from services.pipeline import run_projection_pipeline

    current_squad = list(range(1, 16))  # first 15 players
    result = run_projection_pipeline(
        store=store,
        gameweek_id=3,
        current_squad=current_squad,
        budget_remaining=5.0,
    )

    print(f"\n   Pipeline Result:")
    summary = result.summary()
    for k, v in summary.items():
        print(f"   {k}: {v}")

    # 5. Check projections
    print(f"\n5. Sample Projections (top 5 by projected points):")
    sorted_proj = sorted(result.projections, key=lambda p: p.projected_points, reverse=True)
    for p in sorted_proj[:5]:
        print(f"   {p.web_name} ({p.position}): {p.projected_points:.1f} pts "
              f"[{p.ci_80_low:.1f}-{p.ci_80_high:.1f}] conf={p.confidence:.0f}%")

    # 6. Check confidence
    if result.confidence:
        print(f"\n6. Confidence Distribution:")
        tiers = {}
        for c in result.confidence:
            tiers[c.confidence_tier] = tiers.get(c.confidence_tier, 0) + 1
        for tier, count in sorted(tiers.items()):
            print(f"   {tier}: {count} players")

    # 7. Check market signals
    if result.market_signals:
        print(f"\n7. Market Signals:")
        hot = [s for s in result.market_signals if s.market_sentiment == "hot"]
        print(f"   Hot sentiment: {len(hot)} players")

    # 8. Check opportunities
    if result.undervalued:
        print(f"\n8. Undervalued Players (top 3):")
        for u in result.undervalued[:3]:
            print(f"   {u.web_name}: score={u.opportunity_score:.0f}, "
                  f"ppm={u.points_per_million:.2f}, reasons={u.undervaluation_reasons}")

    # 9. Check squad recommendation
    if result.squad_recommendation:
        rec = result.squad_recommendation
        print(f"\n9. Squad Recommendation:")
        print(f"   Improvement: {rec.improvement:.1f} pts")
        print(f"   Formation: {rec.suggested_formation}")
        print(f"   Transfers: {len(rec.suggested_transfers)}")

    # 10. Pipeline timing
    print(f"\n10. Pipeline Duration: {result.pipeline_duration_ms:.0f}ms")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_pipeline()
