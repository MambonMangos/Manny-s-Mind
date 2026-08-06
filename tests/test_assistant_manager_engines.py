"""Regression tests for the Assistant Manager production-path bugs.

AM-01  engine.run_assistant: fixture_map was undefined at the production
       prediction block, so V3 never persisted via the Assistant Manager.
       fixture_map is now built before the block and passed to the store.
AM-02  transfer_engine.generate_transfer_recommendations: transfers_in /
       transfers_out / selected were undefined and _build_reasoning did not
       exist, so the transfer loop raised NameError whenever any candidate
       existed. Both are now implemented.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from types import SimpleNamespace
from unittest import mock

import pandas as pd

from services.assistant_manager.models import (
    PlayerAssessment,
    SquadEvaluation,
    TransferPlan,
)

# ------------------------------------------------------------------
# Synthetic data
# ------------------------------------------------------------------

def synthetic_players(n=10):
    df = pd.DataFrame({
        "id": range(1, n + 1),
        "web_name": [f"P{i}" for i in range(1, n + 1)],
        "position": ["FWD"] * n,
        "team_id": [i % 20 + 1 for i in range(n)],
        "team_short": [f"T{i % 20 + 1}" for i in range(n)],
        "price": [8.0] * n,
        "total_points": [50] * n,
        "form": [2.0] * n,
        "xgi_per_90": [0.5] * n,
        "value_score": [50.0] * n,
        "minutes": [90] * n,
        "minutes_fraction": [1.0] * n,
        "status": ["a"] * n,
        "news": [""] * n,
        "selected_by_percent": [30.0] * n,
        "cost_change_start": [0] * n,
        "projected_points": [4.0] * n,
        "transfers_in_event": [5000] * n,
        "transfers_out_event": [1000] * n,
        "cost_change_event": [0] * n,
    })
    return df


def make_squad_eval():
    out = PlayerAssessment(
        player_id=1, web_name="Haaland", team_id=2, team_short="MCI",
        position="FWD", price=15.0, total_points=30, form=1.0,
        xgi_per_90=1.0, value_score=5.0, minutes_played=90,
        minutes_fraction=1.0, status="a", news="",
        selected_by_percent=50.0, cost_change_start=0,
        avg_difficulty_3gw=2.5, weakness_flags=["Difficult next 3 GWs"],
    )
    return SquadEvaluation(
        overall_rating=70.0, total_value=100.0, bank=0.0,
        free_transfers=1, saved_transfers=0, players=[out],
    )


# ==================================================================
# AM-01  engine.run_assistant production pipeline
# ==================================================================

def test_run_assistant_passes_fixture_map_to_feature_store():
    """AM-01: production pipeline runs and receives fixture_map, not NameError."""
    from services.assistant_manager import engine

    player_df = synthetic_players(5)
    squad_df = player_df.iloc[[0]].copy()

    fixtures = [
        SimpleNamespace(
            event=1, team_h=1, team_a=2,
            team_h_difficulty=2, team_a_difficulty=3,
        )
    ]

    picks = SimpleNamespace(
        player_id=1, position=1, is_captain=False,
        is_vice_captain=False, multiplier=1,
    )
    team_data = SimpleNamespace(
        picks={1: SimpleNamespace(picks=[picks])},
        transfers=[],
        chips=[],
    )

    class FakeProjection:
        player_id = 1
        projected_points = 5.0

    class FakePrimary:
        def __init__(self):
            self.projections = [FakeProjection]

    class FakeProduction:
        primary_model_id = "expected_points_v1"

        @property
        def primary(self):
            return FakePrimary

        def summary(self):
            return "production ok"

    capture = {}

    def fake_build_feature_store(players_df, **kwargs):
        capture["fixture_map"] = kwargs.get("fixture_map")
        return mock.MagicMock(df=players_df.copy())

    with mock.patch.object(
        engine, "get_scored_players", return_value=player_df
    ), mock.patch.object(
        engine, "get_players_dataframe", return_value=pd.DataFrame()
    ), mock.patch.object(
        engine, "fetch_fixtures", return_value=fixtures
    ), mock.patch.object(
        engine, "fetch_team_data", return_value=team_data
    ), mock.patch.object(
        engine, "resolve_player_names", return_value=squad_df
    ), mock.patch(
        "utils.config.get_config_hash", return_value="test-hash"
    ), mock.patch(
        "features.build_feature_store", side_effect=fake_build_feature_store
    ), mock.patch(
        "services.production_predictor.run_production_predictions",
        return_value=FakeProduction(),
    ), mock.patch.object(
        engine, "evaluate_squad", return_value=make_squad_eval()
    ), mock.patch.object(
        engine, "generate_transfer_recommendations",
        return_value=TransferPlan(action="hold"),
    ), mock.patch.object(
        engine, "analyze_hit", side_effect=lambda plan, _: plan
    ), mock.patch.object(
        engine, "evaluate_chips", return_value=[]
    ), mock.patch.object(
        engine, "plan_future", return_value=None
    ), mock.patch.object(
        engine, "generate_executive_summary", return_value=""
    ), mock.patch.object(
        engine, "get_chip_states", return_value=[]
    ), mock.patch.object(
        engine, "log_recommendation", return_value=None
    ):

        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from database.models import Base

        db_engine = create_engine("sqlite://")
        Base.metadata.create_all(db_engine)
        session = Session(bind=db_engine)

        report = engine.run_assistant(session, team_id=1, current_gameweek=1)
        session.close()

    assert capture.get("fixture_map") is not None, (
        "build_feature_store must receive fixture_map (was NameError before fix)"
    )
    assert report.production_pipeline_result is not None, (
        "production pipeline must complete (it silently failed before fix)"
    )
    assert report.production_model_id == "expected_points_v1"
    print("PASS: run_assistant runs production pipeline with fixture_map")


# ==================================================================
# AM-02  transfer engine NameError + missing reasoning
# ==================================================================

def test_transfer_engine_runs_without_nameerror():
    """AM-02: generate_transfer_recommendations completes and reasons."""
    from services.assistant_manager.transfer_engine import (
        generate_transfer_recommendations,
    )

    player_df = synthetic_players(3)
    player_df.loc[1, "id"] = 99  # candidate not in squad
    player_df.loc[1, "transfers_in_event"] = 8000
    player_df.loc[1, "selected_by_percent"] = 3.0

    squad = make_squad_eval()
    fixture_map = {
        player_df.loc[1, "team_id"]: [
            {"difficulty": 2, "event": 1},
            {"difficulty": 2, "event": 2},
            {"difficulty": 2, "event": 3},
        ]
    }

    plan = generate_transfer_recommendations(squad, player_df, fixture_map, {})

    assert plan.transfers, "Expected at least one recommendation"
    rec = plan.transfers[0]
    assert rec.player_in.player_id == 99
    assert rec.reasoning, "Recommendation must carry reasoning text"
    assert rec.player_in.selected_by_percent == 3.0
    assert "Risk level" in rec.reasoning
    print(f"PASS: transfer engine produced {len(plan.transfers)} recommendation(s)")


def test_build_reasoning_returns_string():
    """AM-02: _build_reasoning produces a readable explanation."""
    from services.assistant_manager.transfer_engine import _build_reasoning

    squad = make_squad_eval()
    text = _build_reasoning(
        out_a=squad.players[0],
        in_name="Watkins",
        in_team="AVL",
        expected_gain=1.5,
        fixture_improvement=0.5,
        risk_level="Low",
        price_diff=-7.0,
        in_form=3.0,
        in_xgi=0.8,
        out_weaknesses=["Difficult next 3 GWs"],
        in_opportunities=["High demand (8,000 transfers in)"],
    )
    assert isinstance(text, str) and len(text) > 0
    assert "Watkins (AVL)" in text
    print("PASS: _build_reasoning returns explanation text")


# ==================================================================
# Main
# ==================================================================

if __name__ == "__main__":
    passed = 0
    failed = 0

    tests = [
        ("AM-01  run_assistant production pipeline", test_run_assistant_passes_fixture_map_to_feature_store),
        ("AM-02  transfer engine no NameError", test_transfer_engine_runs_without_nameerror),
        ("AM-02  _build_reasoning", test_build_reasoning_returns_string),
    ]

    for name, fn in tests:
        print(f"\n--- {name} ---")
        try:
            fn()
            print("RESULT: PASS")
            passed += 1
        except Exception as e:  # noqa: BLE001 - test harness must record the failure
            print(f"RESULT: FAIL — {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*60}")
    print(f"TOTAL: {passed} passed, {failed} failed out of {len(tests)}")
    print(f"{'='*60}")

    if failed > 0:
        sys.exit(1)
