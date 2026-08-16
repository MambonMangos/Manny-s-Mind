"""Cross-season player identity tests (research/identity.py)."""

from __future__ import annotations

import pandas as pd

from research.identity import (
    player_codes,
    previous_season,
    previous_season_prior,
)


def test_previous_season_bounds():
    assert previous_season("2016-17") is None
    assert previous_season("2023-24") == "2022-23"
    assert previous_season("2024-25") == "2023-24"
    assert previous_season("1999-00") is None


def test_previous_season_prior_leakage_safe():
    prior = previous_season_prior("2023-24")
    assert isinstance(prior, pd.DataFrame)
    assert not prior.empty
    assert "code" in prior.columns
    assert prior["code"].notna().all()
    assert "prev_position" in prior.columns


def test_previous_season_prior_none_for_first_season():
    assert previous_season_prior("2016-17").empty


def test_player_codes_stable_identity():
    """The FPL `code` must be stable across seasons for known players."""
    codes = player_codes(["2022-23", "2023-24", "2024-25"])
    assert "code" in codes.columns
    assert codes["code"].notna().all()
    assert "element" in codes.columns

    def element_for(season, code):
        rows = codes[(codes["season"] == season) & (codes["code"] == code)]
        assert len(rows) == 1, f"code {code} {season}: {len(rows)} rows"
        return int(rows.iloc[0]["element"])

    # Verified-stable FPL codes (Salah=118748, Saka=223340).
    for code in [118748, 223340]:
        elems = {element_for(s, code) for s in ["2022-23", "2023-24", "2024-25"]}
        assert len(elems) >= 2, f"code {code} should map to (season-dependent) elements across seasons"
    assert element_for("2023-24", 118748) != element_for("2024-25", 118748)


def test_player_codes_positions():
    codes = player_codes(["2023-24"])
    assert set(codes["position"].dropna().unique()) <= {"GKP", "DEF", "MID", "FWD"}
