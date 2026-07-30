"""Fixture service – fetches and processes fixture difficulty data from the FPL API."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from services.api_client import fpl_get

logger = logging.getLogger(__name__)


@dataclass
class Fixture:
    """Single fixture between two teams."""

    event: int
    team_h: int
    team_a: int
    team_h_difficulty: int
    team_a_difficulty: int
    started: bool
    finished: bool


def fetch_fixtures() -> list[Fixture]:
    """Fetch all fixtures from the FPL API."""
    raw = fpl_get("/fixtures/")
    return [
        Fixture(
            event=f.get("event", 0),
            team_h=f.get("team_h", 0),
            team_a=f.get("team_a", 0),
            team_h_difficulty=f.get("team_h_difficulty", 3),
            team_a_difficulty=f.get("team_a_difficulty", 3),
            started=f.get("started", False),
            finished=f.get("finished", False),
        )
        for f in raw
    ]


def get_team_fixtures_df(
    fixtures: list[Fixture],
    team_id: int,
    gameweeks: list[int] | None = None,
) -> pd.DataFrame:
    """Return a DataFrame of fixtures for a specific team.

    Each row is a gameweek with opponent and difficulty.
    """
    rows = []
    for fix in fixtures:
        if gameweeks and fix.event not in gameweeks:
            continue

        if fix.team_h == team_id:
            rows.append({
                "gameweek": fix.event,
                "opponent_id": fix.team_a,
                "home": True,
                "difficulty": fix.team_h_difficulty,
                "finished": fix.finished,
            })
        elif fix.team_a == team_id:
            rows.append({
                "gameweek": fix.event,
                "opponent_id": fix.team_h,
                "home": False,
                "difficulty": fix.team_a_difficulty,
                "finished": fix.finished,
            })

    return pd.DataFrame(rows)


def compute_fixture_score(
    fixtures_df: pd.DataFrame,
    team_id: int,
    team_name_map: dict[int, str],
) -> pd.DataFrame:
    """Compute a projected fixture score for a team over a gameweek range.

    Difficulty 1 = easiest (score 100), difficulty 5 = hardest (score 0).
    """
    if fixtures_df.empty:
        return fixtures_df

    df = fixtures_df.copy()
    df["opponent_name"] = df["opponent_id"].map(team_name_map).fillna("TBD")
    df["fixture_score"] = ((5 - df["difficulty"]) / 4) * 100

    # Average fixture score across the range
    avg_score = df["fixture_score"].mean()

    df["team_id"] = team_id
    df["avg_fixture_score"] = avg_score

    return df


def build_fixture_comparison(
    fixtures: list[Fixture],
    team_ids: list[int],
    team_name_map: dict[int, str],
    gameweeks: list[int] | None = None,
) -> pd.DataFrame:
    """Build a combined DataFrame of fixture data for multiple teams.

    Returns a DataFrame with one row per team-gameweek with difficulty and score.
    """
    all_rows = []
    for tid in team_ids:
        team_fix = get_team_fixtures_df(fixtures, tid, gameweeks)
        if team_fix.empty:
            continue
        scored = compute_fixture_score(team_fix, tid, team_name_map)
        all_rows.append(scored)

    if not all_rows:
        return pd.DataFrame()

    return pd.concat(all_rows, ignore_index=True)
