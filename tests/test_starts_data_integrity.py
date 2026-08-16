"""Data-integrity tests for the real FPL ``starts`` field.

Regression guard for the Phase 1 data-foundation fix:
- ``starts`` must be ingested from the API, never fabricated as
  ``round(minutes / 90)``.
- Zero starts must remain zero.
- Sub-only players (starts=0, minutes>0) must not be converted into starters.
- The Feature Store must preserve starts/minutes as separate, truthful values.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from synthetic import create_synthetic_players

from database.crud import get_players_dataframe
from database.models import Base, Player, Team
from features import build_feature_store
from services.data_loader import _PLAYER_FIELDS, DataLoader


def test_player_fields_include_starts():
    assert "starts" in _PLAYER_FIELDS


def test_parse_player_preserves_real_starts():
    loader = DataLoader()
    rec = loader._parse_player(
        {"id": 1, "team": 1, "element_type": 3, "web_name": "X", "starts": 38}
    )
    assert rec["starts"] == 38


def test_parse_player_defaults_zero_when_missing():
    loader = DataLoader()
    rec = loader._parse_player(
        {"id": 1, "team": 1, "element_type": 3, "web_name": "X", "starts": None}
    )
    assert rec["starts"] == 0


def test_feature_store_never_fabricates_starts():
    """A DataFrame without starts must not invent starts from minutes."""
    df = create_synthetic_players(n=5, seed=3)
    df = df.drop(columns=["starts"])
    df.loc[0, "minutes"] = 900  # would have been "10 starts" if fabricated
    store = build_feature_store(players_df=df, gameweek_id=1)
    assert (store.df["starts"] == 0).all(), "starts must not be derived from minutes"


def test_feature_store_preserves_real_starts():
    df = create_synthetic_players(n=5, seed=3)
    df["starts"] = [38, 0, 1, 12, 30]
    store = build_feature_store(players_df=df, gameweek_id=1)
    assert store.df["starts"].tolist() == [38, 0, 1, 12, 30]


def test_zero_starts_remain_zero():
    df = create_synthetic_players(n=2, seed=1)
    df["starts"] = [0, 0]
    df["minutes"] = [900, 49]
    store = build_feature_store(players_df=df, gameweek_id=1)
    feats = store.minutes_features()
    assert feats["starts"].tolist() == [0, 0]
    assert feats["starts_rate"].tolist() == [0.0, 0.0]


def test_sub_only_player_is_not_converted_to_starter():
    """0 starts + 49 sub minutes must yield starts_rate 0, not 1.0."""
    df = create_synthetic_players(n=2, seed=1)
    df["starts"] = [0, 30]
    df["minutes"] = [49, 2700]
    store = build_feature_store(players_df=df, gameweek_id=1)
    feats = store.minutes_features()
    sub_only, regular = feats["starts_rate"].tolist()
    assert sub_only == 0.0
    assert regular == 1.0


def test_starts_rate_uses_real_starts():
    """starts_rate must separate a sub-heavy player from an ever-present one."""
    df = create_synthetic_players(n=2, seed=1)
    # 5 starts / 2000 min (many sub appearances) vs 30 starts / 2700 min
    df["starts"] = [5, 30]
    df["minutes"] = [2000, 2700]
    store = build_feature_store(players_df=df, gameweek_id=1)
    feats = store.minutes_features()
    sub_heavy, ever_present = feats["starts_rate"].tolist()
    assert sub_heavy < 0.5 < ever_present <= 1.0


def test_minutes_per_game_capped_at_90():
    """A few starts + many sub minutes must not inflate minutes_per_game."""
    df = create_synthetic_players(n=2, seed=1)
    df["starts"] = [1, 30]
    df["minutes"] = [900, 2700]
    store = build_feature_store(players_df=df, gameweek_id=1)
    feats = store.minutes_features()
    assert feats["minutes_per_game"].tolist() == [90.0, 90.0]


def test_dataframe_exposes_starts_column():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        session.add(
            Team(id=1, name="Arsenal", short_name="ARS",
                 strength_overall_home=1200, strength_overall_away=1100)
        )
        session.add(
            Player(id=7, web_name="Saka", team_id=1, element_type=3,
                   minutes=2700, starts=31)
        )
        session.commit()
        df = get_players_dataframe(session)
        assert "starts" in df.columns
        assert df.iloc[0]["starts"] == 31
    finally:
        session.close()


def test_v3_distinguishes_sub_from_starter():
    """Same minutes, different real starts -> V3 expected minutes must differ.

    This is the core behavioural regression the data fix unlocks: with real
    starts, a 30-start ever-present gets a materially higher expected minutes
    than a 1-start player who accumulated the same minutes from the bench.
    """
    from engines.expected_minutes_engine import project_expected_minutes

    df = create_synthetic_players(n=2, seed=1)
    df["starts"] = [1, 30]
    df["minutes"] = [900, 900]
    df["chance_of_playing_next_round"] = [100, 100]
    df["status"] = ["a", "a"]
    store = build_feature_store(players_df=df, gameweek_id=1)
    projections = project_expected_minutes(store, gameweek_id=1)
    by_id = {p.player_id: p for p in projections}
    sub_heavy = by_id[int(df.iloc[0]["player_id"])]
    ever_present = by_id[int(df.iloc[1]["player_id"])]
    assert ever_present.start_probability > sub_heavy.start_probability
    assert ever_present.expected_minutes > sub_heavy.expected_minutes
