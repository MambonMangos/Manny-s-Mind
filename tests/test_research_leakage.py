"""Leakage-safety + state reconstruction tests.

THE critical requirement of the research program: a prediction for GW N must
be able to see nothing from GW N or later. These tests prove it.
"""

import pytest

from research.loader import SeasonData
from research.state import OUTPUT_COLUMNS, build_state


@pytest.fixture(scope="module")
def sd():
    return SeasonData.load("2023-24")


def test_state_has_expected_columns(sd):
    players, _, _ = build_state(sd, 5)
    for col in OUTPUT_COLUMNS:
        assert col in players.columns, f"missing {col}"


def test_no_future_results_in_state(sd):
    # Inject an absurd future score into gw5; state for gw5 must not see it.
    tampered = sd.gw.copy()
    tampered.loc[tampered["round"] == 5, "total_points"] = 999
    tampered.loc[tampered["round"] == 6, "total_points"] = 998
    tampered_sd = SeasonData(
        season=sd.season, gw=tampered, players_raw=sd.players_raw,
        fixtures=sd.fixtures, teams=sd.teams,
        total_managers=sd.total_managers,
    )
    players, _, _ = build_state(tampered_sd, 5)
    assert (players["total_points"] < 999).all()


def test_no_future_snapshots_in_state(sd):
    # Price/ownership snapshot must come from round < N, never N or later.
    tampered = sd.gw.copy()
    tampered.loc[tampered["round"] == 5, "value"] = 99999
    tampered.loc[tampered["round"] == 5, "selected"] = 999999999
    tampered_sd = SeasonData(
        season=sd.season, gw=tampered, players_raw=sd.players_raw,
        fixtures=sd.fixtures, teams=sd.teams,
        total_managers=sd.total_managers,
    )
    players, _, _ = build_state(tampered_sd, 5)
    assert (players["price"] < 99).all()
    assert (players["selected_by_percent"] < 101).all()


def test_cumulative_stats_are_strictly_past(sd):
    for gw_n in [5, 10, 20]:
        players, _, _ = build_state(sd, gw_n)
        actual_before = (
            sd.gw[sd.gw["round"] < gw_n].groupby("element")["total_points"].sum()
        )
        for el in players["id"].values[:20]:
            if el in actual_before.index:
                assert players.loc[players["id"] == el, "total_points"].iloc[0] == actual_before[el]


def test_fixture_map_contains_only_upcoming_fixtures(sd):
    _, fixture_map, _ = build_state(sd, 10)
    for fixtures in fixture_map.values():
        assert all(f["gameweek"] >= 10 for f in fixtures)


def test_fixture_map_sorted_by_gameweek(sd):
    _, fixture_map, _ = build_state(sd, 3)
    for fixtures in fixture_map.values():
        gws = [f["gameweek"] for f in fixtures]
        assert gws == sorted(gws)


def test_proxy_seasons_have_no_fabricated_starts():
    sd = SeasonData.load("2021-22")
    players, _, _ = build_state(sd, 10)
    assert (players["starts"] == 0).all()  # never fabricated


def test_position_map_valid(sd):
    players, _, _ = build_state(sd, 5)
    assert set(players["position"].unique()) <= {"GKP", "DEF", "MID", "FWD"}


def test_price_is_millions():
    sd2 = SeasonData.load("2019-20")
    players, _, _ = build_state(sd2, 5)
    assert players["price"].between(3.5, 15.0).all()


def test_state_size_matches_roster(sd):
    players, _, _ = build_state(sd, 5)
    assert len(players) > 500


def test_form_is_bounded_and_finite(sd):
    players, _, _ = build_state(sd, 10)
    assert players["form"].between(-15, 35).all()
    assert players["form"].notna().all()
