"""Research program configuration (read-only — production config is never touched).

Everything here lives under data_research/ (gitignored). The research data
store is separate from the production DB (data/moneyball.db).
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VAASTAV_DIR = REPO_ROOT / "data_research" / "vaastav" / "data"
STORE_DIR = REPO_ROOT / "data_research" / "store"
RESULTS_DIR = REPO_ROOT / "data_research" / "results"
REPORT_DIR = REPO_ROOT / "reports"

SOURCE_PIN = "8c97b2adb123863c3dd581e730f1360e89815ac2"  # vaastav master @ 2026-08-04

# Seasons with real per-GW `starts` AND FPL xG/xA/xGC (faithful full-V3 backtest).
FAITHFUL_SEASONS = ["2022-23", "2023-24", "2024-25"]
# Earlier seasons: minutes/price/ownership/transfers/BPS present, but NO per-GW
# starts and NO xG -> engines must run on proxy (documented) inputs.
PROXY_SEASONS = ["2019-20", "2020-21", "2021-22"]
BACKTEST_SEASONS = FAITHFUL_SEASONS + PROXY_SEASONS
ALL_SEASONS = [
    "2016-17", "2017-18", "2018-19", "2019-20", "2020-21", "2021-22",
    "2022-23", "2023-24", "2024-25", "2025-26", "2026-27",
]

# Minimum history required before the first backtest prediction. We need at
# least 2 finished gameweeks to compute cumulative + snapshot features.
MIN_HISTORY_GWS = 2
FIRST_PREDICT_GW = MIN_HISTORY_GWS + 1  # predict from GW 3 onwards

POSITION_MAP = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}

# Per-GW snapshot columns taken from the most recent gameweek < N (leakage-safe:
# they are the values managers saw before the GW N deadline).
SNAPSHOT_COLS = ["value", "selected", "transfers_in", "transfers_out"]

# Columns summed cumulatively over rounds < N.
CUMULATIVE_COLS = [
    "minutes", "goals_scored", "assists", "total_points", "bonus", "bps",
    "influence", "creativity", "threat", "ict_index", "clean_sheets",
    "yellow_cards", "red_cards", "saves",
]
# xG-based rates exist only in faithful seasons; loader zero-fills otherwise.
XG_COLS = [
    "expected_goals", "expected_assists", "expected_goal_involvements",
    "expected_goals_conceded",
]
STARTS_COL = "starts"

FORM_WINDOW = 5  # FPL form = avg points over the last 5 gameweeks
