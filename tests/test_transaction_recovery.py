"""Regression tests for AM-03: Transaction-management recovery.

Verifies that a failed database commit in the production prediction pipeline
does not poison the SQLAlchemy session for subsequent Assistant Manager
operations.  Uses isolated in-memory SQLite databases — never touches
production data.

Incident: PendingRollbackError in get_chip_states() caused by missing
session.rollback() in _run_expected_points() and _run_v3_hist_d_team().
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, OperationalError, PendingRollbackError
from sqlalchemy.orm import Session

from database.models import Base, ChipState, PredictionVersion

# ------------------------------------------------------------------
# Fixtures: isolated in-memory SQLite per test
# ------------------------------------------------------------------

@pytest.fixture()
def db():
    """Create a fresh in-memory SQLite database with the full schema."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    yield session
    session.close()
    engine.dispose()


# ==================================================================
# TEST 1 — Failed commit recovery (core SQLAlchemy mechanics)
# ==================================================================

class TestFailedCommitRecovery:
    """Prove that session.rollback() restores a poisoned session."""

    def test_rollback_after_commit_failure(self, db):
        """After a failed commit, rollback lets the session query again.

        This reproduces the exact production bug pattern:
        1. commit() fails with IntegrityError (the original DB error)
        2. Session is marked poisoned (needs rollback)
        3. Subsequent query raises PendingRollbackError (the production error)
        4. rollback() recovers the session
        """
        # Step 1: write a row
        cs = ChipState(team_id=1, chip_name="wildcard", used=False)
        db.add(cs)
        db.commit()

        # Step 2: force a commit failure by inserting a row that violates
        # a unique constraint.  PredictionVersion.version_tag has unique=True.
        pv1 = PredictionVersion(version_tag="test-tag-1", model_name="test")
        db.add(pv1)
        db.commit()

        pv2 = PredictionVersion(version_tag="test-tag-1", model_name="test")
        db.add(pv2)
        try:
            db.commit()
        except IntegrityError:
            pass  # ORIGINAL database error — session is now poisoned

        # Step 3: session is poisoned — subsequent query raises
        # PendingRollbackError (THE EXACT PRODUCTION ERROR)
        with pytest.raises(PendingRollbackError):
            db.query(ChipState).all()

        # Step 4: rollback recovers the session
        db.rollback()

        # Step 5: session works again — the ORIGINAL row is still there
        rows = db.query(ChipState).filter_by(team_id=1).all()
        assert len(rows) == 1
        assert rows[0].chip_name == "wildcard"

    def test_rollback_recovers_after_flush_failure(self, db):
        """A flush failure (autoflush on query) is recovered by rollback."""
        # Insert a PredictionVersion
        pv = PredictionVersion(version_tag="flush-test", model_name="test")
        db.add(pv)
        db.commit()

        # Now add a duplicate AND a new pending object.
        # The duplicate will cause a flush failure on next query.
        pv_dup = PredictionVersion(version_tag="flush-test", model_name="test")
        cs = ChipState(team_id=1, chip_name="bboost", used=True)
        db.add(pv_dup)
        db.add(cs)

        # The autoflush triggered by this query fails with IntegrityError
        with pytest.raises(IntegrityError):
            db.query(ChipState).all()

        # Session is now poisoned — second query raises PendingRollbackError
        with pytest.raises(PendingRollbackError):
            db.query(ChipState).all()

        # Rollback cleans up the poisoned session
        db.rollback()

        # Original data intact, pending objects cleared
        rows = db.query(ChipState).all()
        assert len(rows) == 0


# ==================================================================
# TEST 2 — _run_expected_points failure recovery
# ==================================================================

class TestExpectedPointsRecovery:
    """Verify that _run_expected_points rolls back on persistence failure."""

    def test_rollback_on_commit_failure(self, db):
        """_run_expected_points rolls back after commit failure, session usable."""
        from services.production_predictor import _run_expected_points

        # Seed a PredictionVersion so we can verify nothing was double-inserted
        existing = PredictionVersion(
            version_tag="xpts-gw1-deadbeef",
            model_name="expected_points_v1",
        )
        db.add(existing)
        db.commit()

        # Mock persist_expected_version to raise IntegrityError (simulates
        # a duplicate version_tag collision at commit time).
        with (
            mock.patch(
                "engines.expected_projection_engine.run_expected_projection",
                return_value=[mock.MagicMock(player_id=1, projected_points=5.0)],
            ),
            mock.patch(
                "services.expected_pipeline.persist_expected_version",
                side_effect=IntegrityError(
                    "UNIQUE constraint failed", None, None
                ),
            ),
        ):
            result = _run_expected_points(
                store=mock.MagicMock(),
                gameweek_id=1,
                session=db,
                persist=True,
            )

        # The function should have caught the error and returned an error ModelRun
        assert result.error is not None
        assert result.model_id == "expected_points_v1"

        # Critical: session must NOT be poisoned — verify it can query
        rows = db.query(PredictionVersion).all()
        assert len(rows) == 1  # only the pre-seeded row
        assert rows[0].version_tag == "xpts-gw1-deadbeef"

    def test_session_usable_after_rollback(self, db):
        """After _run_expected_points failure, ChipState query works."""
        from services.production_predictor import _run_expected_points

        # Seed a ChipState that we'll query later
        cs = ChipState(team_id=42, chip_name="free_hit", used=False)
        db.add(cs)
        db.commit()

        # Force _run_expected_points to fail by making persist_expected_version
        # raise an OperationalError (simulates "database is locked")
        with (
            mock.patch(
                "engines.expected_projection_engine.run_expected_projection",
                return_value=[mock.MagicMock(player_id=1, projected_points=3.0)],
            ),
            mock.patch(
                "services.expected_pipeline.persist_expected_version",
                side_effect=OperationalError("database is locked", {}, None),
            ),
        ):
            result = _run_expected_points(
                store=mock.MagicMock(),
                gameweek_id=1,
                session=db,
                persist=True,
            )

        assert result.error is not None

        # The session must be recoverable — query ChipState
        rows = db.query(ChipState).filter_by(team_id=42).all()
        assert len(rows) == 1
        assert rows[0].chip_name == "free_hit"


# ==================================================================
# TEST 3 — _run_v3_hist_d_team failure recovery
# ==================================================================

class TestV3HistDTeamRecovery:
    """Verify that _run_v3_hist_d_team rolls back on persistence failure."""

    def test_rollback_on_commit_failure(self, db):
        """_run_v3_hist_d_team rolls back after commit failure, session usable."""
        from services.production_predictor import _run_v3_hist_d_team

        with (
            mock.patch(
                "engines.expected_projection_engine.run_expected_projection",
                return_value=[mock.MagicMock(player_id=1, projected_points=4.0)],
            ),
            mock.patch(
                "services.expected_pipeline.persist_expected_version",
                side_effect=OperationalError("database is locked", {}, None),
            ),
        ):
            result = _run_v3_hist_d_team(
                store=mock.MagicMock(),
                gameweek_id=1,
                session=db,
                persist=True,
            )

        assert result.error is not None
        assert result.model_id == "v3_hist_d_team"

        # Session must be usable after rollback
        rows = db.query(ChipState).all()  # should not raise
        assert isinstance(rows, list)

    def test_session_usable_for_chip_states(self, db):
        """After _run_v3_hist_d_team failure, get_chip_states works."""
        from services.assistant_manager.decision_log import get_chip_states
        from services.production_predictor import _run_v3_hist_d_team

        # Seed ChipState data
        for chip in ["wildcard", "free_hit", "bboost", "3xc"]:
            db.add(ChipState(team_id=1, chip_name=chip, used=False))
        db.commit()

        # Force failure in _run_v3_hist_d_team
        with (
            mock.patch(
                "engines.expected_projection_engine.run_expected_projection",
                return_value=[mock.MagicMock(player_id=1, projected_points=4.0)],
            ),
            mock.patch(
                "services.expected_pipeline.persist_expected_version",
                side_effect=RuntimeError("connection lost"),
            ),
        ):
            _run_v3_hist_d_team(
                store=mock.MagicMock(),
                gameweek_id=1,
                session=db,
                persist=True,
            )

        # THIS IS THE EXACT OPERATION THAT CRASHED IN PRODUCTION
        states = get_chip_states(db, team_id=1)
        assert len(states) == 4
        assert "wildcard" in states
        assert "free_hit" in states


# ==================================================================
# TEST 4 — run_assistant resilience
# ==================================================================

class TestAssistantManagerResilience:
    """Verify that run_assistant degrades gracefully when predictions fail."""

    def test_run_assistant_survives_prediction_db_failure(self, db):
        """run_assistant returns a partial report when the prediction pipeline
        fails with a database error — it does NOT crash with PendingRollbackError."""
        from services.assistant_manager import engine

        # Seed ChipState so get_chip_states can query after the failure
        cs = ChipState(team_id=1, chip_name="wildcard", used=False)
        db.add(cs)
        db.commit()

        player_df = _synthetic_players(5)
        squad_df = player_df.iloc[[0]].copy()

        fixtures = [mock.Mock(event=1, team_h=1, team_a=2, team_h_difficulty=2, team_a_difficulty=3)]
        picks = mock.Mock(player_id=1, position=1, is_captain=False, is_vice_captain=False, multiplier=1)
        team_data = mock.Mock(picks={1: mock.Mock(picks=[picks])}, transfers=[], chips=[])

        # Mock everything — force the production pipeline to raise a DB error
        with (
            mock.patch.object(engine, "get_scored_players", return_value=player_df),
            mock.patch.object(engine, "get_players_dataframe", return_value=__import__("pandas").DataFrame()),
            mock.patch.object(engine, "fetch_fixtures", return_value=fixtures),
            mock.patch.object(engine, "fetch_team_data", return_value=team_data),
            mock.patch.object(engine, "resolve_player_names", return_value=squad_df),
            mock.patch("utils.config.get_config_hash", return_value="test-hash"),
            mock.patch(
                "features.build_feature_store",
                return_value=mock.MagicMock(df=player_df.copy()),
            ),
            mock.patch(
                "services.production_predictor.run_production_predictions",
                side_effect=OperationalError("database is locked", {}, None),
            ),
            mock.patch.object(engine, "evaluate_squad", return_value=_make_squad_eval()),
            mock.patch.object(engine, "generate_transfer_recommendations", return_value=mock.Mock(transfers=[], action="hold")),
            mock.patch.object(engine, "analyze_hit", side_effect=lambda plan, _: plan),
            mock.patch.object(engine, "evaluate_chips", return_value=[]),
            mock.patch.object(engine, "plan_future", return_value=None),
            mock.patch.object(engine, "generate_executive_summary", return_value=""),
            mock.patch.object(engine, "get_chip_states", return_value={}),
            mock.patch.object(engine, "log_recommendation", return_value=None),
        ):
            report = engine.run_assistant(db, team_id=1, current_gameweek=1)

        # The report must be returned (not crashed)
        assert report is not None
        assert report.team_id == 1

        # Critically: the session must NOT be poisoned.
        # Verify by querying ChipState — this was the operation that
        # produced PendingRollbackError in production.
        rows = db.query(ChipState).filter_by(team_id=1).all()
        assert len(rows) == 1

    def test_run_assistant_survives_prediction_commit_failure(self, db):
        """run_assistant returns partial report when commit inside the
        production pipeline fails — the specific scenario from the incident."""
        from services.assistant_manager import engine

        cs = ChipState(team_id=1, chip_name="wildcard", used=False)
        db.add(cs)
        db.commit()

        player_df = _synthetic_players(5)
        squad_df = player_df.iloc[[0]].copy()

        fixtures = [mock.Mock(event=1, team_h=1, team_a=2, team_h_difficulty=2, team_a_difficulty=3)]
        picks = mock.Mock(player_id=1, position=1, is_captain=False, is_vice_captain=False, multiplier=1)
        team_data = mock.Mock(picks={1: mock.Mock(picks=[picks])}, transfers=[], chips=[])

        # Force run_production_predictions to raise (simulating a failed commit
        # inside _run_expected_points that was NOT caught with rollback before
        # this fix).
        def _fail_on_persist(*args, **kwargs):
            # Write something to dirty the session, then fail —
            # this simulates what happens when persist + commit fails
            session = kwargs.get("session") or (args[2] if len(args) > 2 else None)
            if session is not None:
                session.add(PredictionVersion(version_tag="should-fail", model_name="test"))
            raise OperationalError("database is locked", {}, None)

        with (
            mock.patch.object(engine, "get_scored_players", return_value=player_df),
            mock.patch.object(engine, "get_players_dataframe", return_value=__import__("pandas").DataFrame()),
            mock.patch.object(engine, "fetch_fixtures", return_value=fixtures),
            mock.patch.object(engine, "fetch_team_data", return_value=team_data),
            mock.patch.object(engine, "resolve_player_names", return_value=squad_df),
            mock.patch("utils.config.get_config_hash", return_value="test-hash"),
            mock.patch(
                "features.build_feature_store",
                return_value=mock.MagicMock(df=player_df.copy()),
            ),
            mock.patch(
                "services.production_predictor.run_production_predictions",
                side_effect=_fail_on_persist,
            ),
            mock.patch.object(engine, "evaluate_squad", return_value=_make_squad_eval()),
            mock.patch.object(engine, "generate_transfer_recommendations", return_value=mock.Mock(transfers=[], action="hold")),
            mock.patch.object(engine, "analyze_hit", side_effect=lambda plan, _: plan),
            mock.patch.object(engine, "evaluate_chips", return_value=[]),
            mock.patch.object(engine, "plan_future", return_value=None),
            mock.patch.object(engine, "generate_executive_summary", return_value=""),
            mock.patch.object(engine, "get_chip_states", return_value={}),
            mock.patch.object(engine, "log_recommendation", return_value=None),
        ):
            report = engine.run_assistant(db, team_id=1, current_gameweek=1)

        assert report is not None

        # Session must be usable — the engine.py catch-all rollback recovered it
        rows = db.query(ChipState).filter_by(team_id=1).all()
        assert len(rows) == 1


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _synthetic_players(n=5):
    import pandas as pd
    return pd.DataFrame({
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


def _make_squad_eval():
    from services.assistant_manager.models import PlayerAssessment, SquadEvaluation
    out = PlayerAssessment(
        player_id=1, web_name="Test", team_id=2, team_short="T2",
        position="FWD", price=15.0, total_points=30, form=1.0,
        xgi_per_90=1.0, value_score=5.0, minutes_played=90,
        minutes_fraction=1.0, status="a", news="",
        selected_by_percent=50.0, cost_change_start=0,
        avg_difficulty_3gw=2.5, weakness_flags=[],
    )
    return SquadEvaluation(
        overall_rating=70.0, total_value=100.0, bank=0.0,
        free_transfers=1, saved_transfers=0, players=[out],
    )
