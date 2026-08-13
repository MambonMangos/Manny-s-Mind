"""Tests that ``get_players_dataframe`` exposes every column the FeatureStore
and the V2/V3 engines read.

Regression for: a fresh production load crashed in
``features.store.build_feature_store`` with KeyError on ``value_form`` /
``chance_of_playing_next_round`` / ``event_points`` because those columns
were never selected by the DataFrame query.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.crud import get_players_dataframe
from database.models import Base, Player, Team

REQUIRED_COLUMNS = {
    "value_form",
    "value_season",
    "chance_of_playing_next_round",
    "chance_of_playing_this_round",
    "event_points",
}


def _session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed_row(session) -> None:
    team = Team(
        id=1,
        name="Arsenal",
        short_name="ARS",
        strength_overall_home=1200,
        strength_overall_away=1100,
    )
    player = Player(
        id=7,
        web_name="Saka",
        team_id=1,
        element_type=3,
        value_form=4.2,
        value_season=28.5,
        chance_of_playing_next_round=95,
        chance_of_playing_this_round=90,
        event_points=11,
    )
    session.add_all([team, player])
    session.commit()


def test_dataframe_exposes_feature_store_columns():
    session = _session()
    try:
        _seed_row(session)
        df = get_players_dataframe(session)
        assert not df.empty
        assert REQUIRED_COLUMNS.issubset(df.columns), (
            f"missing columns: {REQUIRED_COLUMNS - set(df.columns)}"
        )
        row = df.iloc[0]
        assert row["value_form"] == 4.2
        assert row["value_season"] == 28.5
        assert row["chance_of_playing_next_round"] == 95
        assert row["chance_of_playing_this_round"] == 90
        assert row["event_points"] == 11
    finally:
        session.close()


def test_feature_store_builds_from_dataframe():
    """Full round-trip: the query output feeds build_feature_store uncrashed."""
    from features import build_feature_store

    session = _session()
    try:
        _seed_row(session)
        df = get_players_dataframe(session)
        store = build_feature_store(players_df=df, gameweek_id=1)
        assert len(store.df) == 1
    finally:
        session.close()
