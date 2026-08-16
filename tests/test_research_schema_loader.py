"""Schema drift + loader integrity tests for the historical research layer."""

import pytest

from research import config
from research.loader import SeasonData, load_gw_season
from research.schema import has_starts, has_xg


def test_schema_expectations_are_consistent():
    # The audit's key facts, machine-checked from the expectations table.
    assert has_starts("2019-20") is False
    assert has_starts("2021-22") is False
    assert has_starts("2022-23") is True
    assert has_xg("2022-23") is True
    assert has_xg("2021-22") is False


@pytest.mark.parametrize("season", ["2019-20", "2020-21", "2021-22"])
def test_proxy_seasons_lack_starts_and_xg(season):
    gw = load_gw_season(season)
    assert "starts" not in gw.columns
    assert "expected_goals" not in gw.columns


@pytest.mark.parametrize("season", ["2022-23", "2023-24", "2024-25"])
def test_faithful_seasons_have_starts_and_xg(season):
    gw = load_gw_season(season)
    assert "starts" in gw.columns
    assert "expected_goals" in gw.columns


def test_no_blank_gws_loaded():
    # 2019-20 rounds 30-38 were empty files (COVID pause) and must be skipped.
    gw = load_gw_season("2019-20")
    assert 30 not in gw["round"].values
    assert 38 not in gw["round"].values
    assert 39 in gw["round"].values  # restart round present


def test_double_gameweeks_produce_multiple_rows():
    # DGWs legitimately have >1 row per (round, element).
    gw = load_gw_season("2023-24")
    dup = gw.groupby(["round", "element"]).size()
    assert (dup > 1).any()


def test_no_duplicate_player_ids_per_gw_after_aggregation():
    gw = load_gw_season("2023-24")
    single = gw.groupby(["round", "element"])["minutes"].sum()
    assert single.index.is_unique


def test_player_counts_sane():
    for season in config.BACKTEST_SEASONS:
        gw = load_gw_season(season)
        per_round = gw.groupby("round")["element"].nunique()
        assert per_round.median() > 400  # a full FPL squad list is ~500+


def test_players_raw_ids_align_with_gw_elements():
    for season in ["2023-24", "2019-20"]:
        sd = SeasonData.load(season)
        gw_elements = set(sd.gw["element"].unique())
        raw_elements = set(sd.players_raw["element"].unique())
        # Nearly every gw element should resolve in players_raw
        assert len(gw_elements - raw_elements) / len(gw_elements) < 0.05


def test_total_managers_estimate_in_sane_range():
    for season in ["2019-20", "2022-23", "2024-25"]:
        sd = SeasonData.load(season)
        assert 1_000_000 <= sd.total_managers <= 25_000_000


def test_fixtures_available_for_backtest_seasons():
    for season in config.BACKTEST_SEASONS:
        sd = SeasonData.load(season)
        assert sd.fixtures is not None, f"{season} missing fixtures.csv"
