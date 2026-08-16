"""Historical feature store tests (research/historical_features.py)."""

from __future__ import annotations

import pytest

from research.historical_features import add_historical_features
from research.identity import previous_season_prior
from research.loader import SeasonData
from research.state import build_state


@pytest.fixture(scope="module")
def sd():
    return SeasonData.load("2023-24")


def test_requires_history_before_gw(sd):
    players_df, _, _ = build_state(sd, 2)
    with pytest.raises((ValueError, AssertionError)):
        add_historical_features(players_df, sd, 1, include=("player",))


def test_player_features_leakage_safe(sd):
    players_df, _, _ = build_state(sd, 10)
    out = add_historical_features(players_df, sd, 10, include=("player",))
    for col in ["hist_appearances", "hist_starts", "hist_starts_rate",
                "hist_sub_rate", "hist_minutes_per_start", "hist_xgi_per_90",
                "hist_avg_pts_last_5"]:
        assert col in out.columns, f"missing {col}"
    assert len(out) == len(players_df)
    assert (out["hist_starts"] <= out["hist_appearances"]).all()


def test_team_features(sd):
    players_df, _, _ = build_state(sd, 10)
    out = add_historical_features(players_df, sd, 10, include=("team",))
    for col in ["hist_team_games", "hist_team_attack_adj", "hist_team_defense_adj",
                "hist_team_cs_rate"]:
        assert col in out.columns, f"missing {col}"
    assert out["hist_team_games"].notna().all()


def test_prev_season_features(sd):
    players_df, _, _ = build_state(sd, 10)
    prior = previous_season_prior(sd.season)
    out = add_historical_features(players_df, sd, 10, include=("prev",), prev_prior=prior)
    assert "hist_prev_minutes" in out.columns
    assert "hist_prev_starts_rate" in out.columns
    assert "hist_prev_xg_per_90" in out.columns


def test_no_lookahead_into_current_gw(sd):
    """hist_* aggregates must use rounds < gw_n only (checked against source)."""
    players_df, _, _ = build_state(sd, 10)
    out = add_historical_features(players_df, sd, 10, include=("player",))
    past = sd.gw[sd.gw["round"] < 10]
    starts_by_elem = past.groupby("element")["starts"].sum()
    joined = out[["id", "hist_starts"]].set_index("id").join(starts_by_elem)
    assert (joined["hist_starts"] == joined["starts"]).all()


def test_original_columns_preserved(sd):
    players_df, _, _ = build_state(sd, 10)
    orig = set(players_df.columns)
    out = add_historical_features(players_df, sd, 10, include=("player", "team", "prev"))
    assert orig <= set(out.columns)
    assert not (set(players_df.columns) & set(out.columns) - orig)
