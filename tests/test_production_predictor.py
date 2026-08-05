"""Tests for the Production Predictor — V3 primary + V2 shadow dispatch.

Covers config-driven model selection, the primary/shadow dispatch with
append-only persistence, ledger lookup, unknown-model guarding, and the V3
projection preference in the captain engine.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from sqlalchemy import text
from synthetic import create_synthetic_fixtures, create_synthetic_players

from database.database import engine, get_session
from database.models import Base, Gameweek, Player, Team
from features import build_feature_store
from utils.config import (
    get_primary_model_id,
    get_production_config,
    get_shadow_model_ids,
)


def build_store(n=50, seed=42):
    """Build a FeatureStore from synthetic players."""
    from engines.fixture_engine import build_fixture_map

    df = create_synthetic_players(n=n, seed=seed)
    fixture_map = build_fixture_map(create_synthetic_fixtures())
    return build_feature_store(
        players_df=df,
        fixture_map=fixture_map,
        team_name_map={i: f"Team{i}" for i in range(1, 21)},
        gameweek_id=1,
    )


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


# ------------------------------------------------------------------
# Config-driven model selection
# ------------------------------------------------------------------

def test_production_config_primary_is_v3():
    """The production config selects expected_points_v1 as primary."""
    assert get_primary_model_id() == "expected_points_v1"


def test_production_config_shadow_is_v2():
    """V2 is configured as the shadow/control model."""
    assert get_shadow_model_ids() == ["projection_v2"]


def test_production_config_loadable():
    config = get_production_config()
    assert config["primary_model"] == "expected_points_v1"
    assert "projection_v2" in config["shadow_models"]


# ------------------------------------------------------------------
# Dispatch: V3 primary + V2 shadow
# ------------------------------------------------------------------

def test_run_production_predictions_primary_is_v3():
    from services.production_predictor import run_production_predictions

    store = build_store()
    out = run_production_predictions(store=store, gameweek_id=1, persist=False)

    assert out.primary_model_id == "expected_points_v1"
    assert out.primary.model_id == "expected_points_v1"
    assert len(out.primary.projections) == 50
    assert out.primary.error is None

    shadow_ids = [s.model_id for s in out.shadows]
    assert "projection_v2" in shadow_ids
    v2 = next(s for s in out.shadows if s.model_id == "projection_v2")
    assert len(v2.projections) == 50


def test_run_production_predictions_unknown_model_raises():
    from services.production_predictor import run_model

    store = build_store()
    try:
        run_model(store, gameweek_id=1, model_id="does_not_exist")
    except ValueError as exc:
        assert "Unsupported production model id" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown model id")


def test_run_production_predictions_persist_idempotent():
    """Both V3 primary and V2 shadow persist append-only; reruns are idempotent."""
    from services.production_predictor import run_production_predictions

    reset_db()
    store = build_store()
    session = get_session()

    try:
        first = run_production_predictions(
            store=store, gameweek_id=1, session=session, persist=True,
        )
        session.commit()

        assert first.persisted is True
        assert first.primary.version_id is not None
        v2 = next(s for s in first.shadows if s.model_id == "projection_v2")
        assert v2.version_id is not None
        assert v2.error is None

        second = run_production_predictions(
            store=store, gameweek_id=1, session=session, persist=True,
        )
        session.commit()

        assert second.primary.version_id == first.primary.version_id
        second_v2 = next(s for s in second.shadows if s.model_id == "projection_v2")
        assert second_v2.version_id == v2.version_id

        session.commit()
    finally:
        session.close()


def test_load_persisted_projections_returns_v3_map():
    """load_persisted_projections reads the primary (V3) ledger by default."""
    from services.production_predictor import (
        load_persisted_projections,
        run_production_predictions,
    )

    reset_db()
    store = build_store()
    session = get_session()

    try:
        out = run_production_predictions(
            store=store, gameweek_id=1, session=session, persist=True,
        )
        session.commit()

        proj_map = load_persisted_projections(session, gameweek_id=1)
        assert len(proj_map) == 50
        # Spot-check against the primary run output.
        primary = {int(p.player_id): float(p.projected_points) for p in out.primary.projections}
        for pid, pts in proj_map.items():
            assert abs(pts - primary[pid]) < 1e-6

        session.commit()
    finally:
        session.close()


def test_load_persisted_projections_defaults_to_primary_model():
    """Without model_id, lookup uses the configured primary (V3)."""
    from services.production_predictor import load_persisted_projections
    from utils.config import get_primary_model_id

    reset_db()
    session = get_session()
    try:
        proj_map = load_persisted_projections(session)
        assert proj_map == {}
        assert get_primary_model_id() == "expected_points_v1"
        session.commit()
    finally:
        session.close()


# ------------------------------------------------------------------
# Captain engine consumes V3 projections when present
# ------------------------------------------------------------------

def test_rank_captains_prefers_v3_projected_points():
    """With a projected_points column, V3 xPts drive the captain ranking."""
    import pandas as pd

    from engines.captain_engine import rank_captains

    squad_df = pd.DataFrame([
        {
            "id": 1, "web_name": "LowValue", "team_short": "T1",
            "position": "MID", "price": 10.0, "total_points": 100,
            "expected_goal_involvements": 1.0, "xgi_per_90": 0.5,
            "value_score": 90.0, "projected_points": 2.0,
        },
        {
            "id": 2, "web_name": "HighXpts", "team_short": "T2",
            "position": "FWD", "price": 8.0, "total_points": 80,
            "expected_goal_involvements": 1.5, "xgi_per_90": 0.7,
            "value_score": 40.0, "projected_points": 9.0,
        },
    ])

    ranked = rank_captains(squad_df, top_n=2)
    assert not ranked.empty
    # V3 xPts beats a high legacy value score.
    assert ranked.iloc[0]["web_name"] == "HighXpts"


def test_rank_captains_falls_back_to_value_score():
    """Without projected_points, the legacy value-score ranking is used."""
    import pandas as pd

    from engines.captain_engine import rank_captains

    squad_df = pd.DataFrame([
        {
            "id": 1, "web_name": "HighValue", "team_short": "T1",
            "position": "MID", "price": 10.0, "total_points": 100,
            "expected_goal_involvements": 1.0, "xgi_per_90": 0.5,
            "value_score": 90.0,
        },
        {
            "id": 2, "web_name": "LowValue", "team_short": "T2",
            "position": "FWD", "price": 8.0, "total_points": 80,
            "expected_goal_involvements": 1.5, "xgi_per_90": 0.7,
            "value_score": 40.0,
        },
    ])

    ranked = rank_captains(squad_df, top_n=2)
    assert ranked.iloc[0]["web_name"] == "HighValue"
