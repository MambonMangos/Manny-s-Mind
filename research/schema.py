"""Per-season schema assertions — every drift fact from the audit, encoded.

These are the machine-checkable version of reports/historical_data_audit.md §3.
The loader refuses to proceed if a season's gw schema does not match what we
expect, so schema drift can never silently corrupt a backtest.
"""

from __future__ import annotations

# Every season since 2016-17 has these per-GW columns (verified on disk).
ALWAYS_PRESENT = [
    "element", "round", "minutes", "total_points", "value", "selected",
    "transfers_in", "transfers_out", "bps", "bonus", "saves", "yellow_cards",
    "red_cards", "goals_scored", "assists", "clean_sheets",
    "influence", "creativity", "threat", "ict_index", "was_home",
    "opponent_team", "fixture", "kickoff_time",
]

# position/team columns exist from 2020-21 onward.
POSITION_COLS = ["position", "team"]
# xP (FPL ep_this, a documented lookahead hazard) exists from 2020-21 onward.
XP_COL = ["xP"]
# starts + FPL xG/xA/xGC exist only from 2022-23 onward.
STARTS_AND_XG = ["starts"] + [
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded",
]

# Season -> which column groups must be present / must be absent.
#   "have":   gw1.csv must contain these columns
#   "lack":   gw1.csv must NOT contain these columns
SEASON_SCHEMA_EXPECTATIONS: dict[str, dict] = {
    "2016-17": {"have": ALWAYS_PRESENT, "lack": POSITION_COLS + XP_COL + STARTS_AND_XG},
    "2017-18": {"have": ALWAYS_PRESENT, "lack": POSITION_COLS + XP_COL + STARTS_AND_XG},
    "2018-19": {"have": ALWAYS_PRESENT, "lack": POSITION_COLS + XP_COL + STARTS_AND_XG},
    "2019-20": {"have": ALWAYS_PRESENT, "lack": POSITION_COLS + XP_COL + STARTS_AND_XG},
    "2020-21": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL, "lack": STARTS_AND_XG},
    "2021-22": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL, "lack": STARTS_AND_XG},
    "2022-23": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL + STARTS_AND_XG, "lack": []},
    "2023-24": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL + STARTS_AND_XG, "lack": []},
    "2024-25": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL + STARTS_AND_XG, "lack": []},
    "2025-26": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL + STARTS_AND_XG, "lack": []},
    "2026-27": {"have": ALWAYS_PRESENT + POSITION_COLS + XP_COL + STARTS_AND_XG, "lack": []},
}


def has_starts(season: str) -> bool:
    return season in ("2022-23", "2023-24", "2024-25", "2025-26", "2026-27")


def has_xg(season: str) -> bool:
    return has_starts(season)


def has_position(season: str) -> bool:
    return season >= "2020-21" if isinstance(season, str) and season else False


def assert_season_schema(season: str, gw_columns: set[str]) -> None:
    """Raise AssertionError if a season's gw columns drift from expectations."""
    assert season in SEASON_SCHEMA_EXPECTATIONS, f"unmapped season: {season}"
    spec = SEASON_SCHEMA_EXPECTATIONS[season]
    for col in spec["have"]:
        assert col in gw_columns, (
            f"[{season}] expected column missing: {col!r} (schema drift)"
        )
    for col in spec["lack"]:
        assert col not in gw_columns, (
            f"[{season}] expected column absent but found: {col!r} (schema drift)"
        )
