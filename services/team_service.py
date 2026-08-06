"""Team service – fetches and processes the user's FPL team data from the API."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from requests import HTTPError

from services.api_client import fpl_get

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ManagerProfile:
    """High-level manager info."""

    id: int
    name: str
    team_name: str
    region: str
    favourite_team: int | None = None
    years_active: int = 0
    overall_points: int | None = None
    overall_rank: int | None = None
    event_points: int | None = None
    event_rank: int | None = None
    joined_time: str = ""


@dataclass
class SeasonHistory:
    """One row of past-season performance."""

    season_name: str
    total_points: int
    rank: int
    rank_percentage: str


@dataclass
class Pick:
    """A single player pick in the squad."""

    player_id: int
    position: int  # 1–15
    is_captain: bool
    is_vice_captain: bool
    multiplier: int
    did_not_play: bool = False


@dataclass
class Transfer:
    """Record of a single transfer."""

    player_in: int
    player_out: int
    player_in_cost: int
    player_out_cost: int
    event: int
    time: str


@dataclass
class GameweekPicks:
    """Picks for a specific gameweek."""

    event_id: int
    picks: list[Pick]
    active_chip: str | None = None
    auto_sub: list[Any] = field(default_factory=list)


@dataclass
class TeamData:
    """Aggregate of everything fetched for a user's team."""

    profile: ManagerProfile
    history: list[SeasonHistory]
    chips: list[dict]
    current: list[dict]
    transfers: list[Transfer]
    picks: dict[int, GameweekPicks]  # gw_id → picks


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_profile(team_id: int) -> ManagerProfile:
    """Fetch the manager profile."""
    data = fpl_get(f"/entry/{team_id}/")
    return ManagerProfile(
        id=data["id"],
        name=f"{data.get('player_first_name', '')} {data.get('player_last_name', '')}".strip(),
        team_name=data.get("name", ""),
        region=data.get("player_region_name", ""),
        favourite_team=data.get("favourite_team"),
        years_active=data.get("years_active", 0),
        overall_points=data.get("summary_overall_points"),
        overall_rank=data.get("summary_overall_rank"),
        event_points=data.get("summary_event_points"),
        event_rank=data.get("summary_event_rank"),
        joined_time=data.get("joined_time", ""),
    )


def fetch_history(team_id: int) -> tuple[list[SeasonHistory], list[dict], list[dict]]:
    """Fetch gameweek history and chip usage.

    Returns (past_seasons, current_gw_history, chips).
    """
    data = fpl_get(f"/entry/{team_id}/history/")

    past = [
        SeasonHistory(
            season_name=s["season_name"],
            total_points=s["total_points"],
            rank=s["rank"],
            rank_percentage=s.get("rank_percentage", ""),
        )
        for s in data.get("past", [])
    ]

    return past, data.get("current", []), data.get("chips", [])


def fetch_transfers(team_id: int) -> list[Transfer]:
    """Fetch all transfers for the team."""
    data = fpl_get(f"/entry/{team_id}/transfers/")
    return [
        Transfer(
            player_in=t["player_in"],
            player_out=t["player_out"],
            player_in_cost=t.get("player_in_cost", 0),
            player_out_cost=t.get("player_out_cost", 0),
            event=t.get("event", 0),
            time=t.get("time", ""),
        )
        for t in data
    ]


def fetch_picks(team_id: int, event_id: int) -> GameweekPicks | None:
    """Fetch the squad picks for a specific gameweek."""
    try:
        data = fpl_get(f"/entry/{team_id}/event/{event_id}/picks/")
    except HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None
        raise
    picks = [
        Pick(
            player_id=p["element"],
            position=p["position"],
            is_captain=p["is_captain"],
            is_vice_captain=p["is_vice_captain"],
            multiplier=p.get("multiplier", 1),
            did_not_play=p.get("did_not_play", False),
        )
        for p in data.get("picks", [])
    ]
    return GameweekPicks(
        event_id=data["active_chip"] and 0 or event_id,
        picks=picks,
        active_chip=data.get("active_chip"),
        auto_sub=data.get("auto_sub", []),
    )


def fetch_all_picks(team_id: int, gameweeks: list[int]) -> dict[int, GameweekPicks]:
    """Fetch picks for multiple gameweeks."""
    results: dict[int, GameweekPicks] = {}
    for gw in gameweeks:
        result = fetch_picks(team_id, gw)
        if result is not None:
            results[gw] = result
    return results


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------

def fetch_team_data(team_id: int, gameweeks: list[int] | None = None) -> TeamData:
    """Fetch everything for a team in one call.

    If *gameweeks* is None, fetches GWs 1–38.
    """
    if gameweeks is None:
        gameweeks = list(range(1, 39))

    profile = fetch_profile(team_id)
    past, current, chips = fetch_history(team_id)
    transfers = fetch_transfers(team_id)
    picks = fetch_all_picks(team_id, gameweeks)

    return TeamData(
        profile=profile,
        history=past,
        chips=chips,
        current=current,
        transfers=transfers,
        picks=picks,
    )


def resolve_player_names(
    picks: list[Pick], player_df: pd.DataFrame
) -> pd.DataFrame:
    """Merge pick data with the player DataFrame to get names, teams, etc."""
    if player_df.empty:
        return pd.DataFrame()

    pick_ids = [p.player_id for p in picks]
    matched = player_df[player_df["id"].isin(pick_ids)].copy()

    # Add position in squad and captain info
    pick_info = {p.player_id: p for p in picks}
    matched["squad_position"] = matched["id"].map(
        {pid: info.position for pid, info in pick_info.items()}
    )
    matched["is_captain"] = matched["id"].map(
        {pid: info.is_captain for pid, info in pick_info.items()}
    )
    matched["is_vice_captain"] = matched["id"].map(
        {pid: info.is_vice_captain for pid, info in pick_info.items()}
    )
    matched["multiplier"] = matched["id"].map(
        {pid: info.multiplier for pid, info in pick_info.items()}
    )

    matched = matched.sort_values("squad_position")
    return matched


def recommend_captain(squad_df: pd.DataFrame, fixture_map: dict[int, list[dict]] | None = None) -> pd.DataFrame:
    """Pick the top 3 captain candidates from the squad.

    Delegates to captain_engine.rank_captains for the actual calculation.
    """
    from engines.captain_engine import rank_captains
    return rank_captains(squad_df, fixture_map)


def build_transfer_log(
    transfers: list[Transfer], player_df: pd.DataFrame
) -> pd.DataFrame:
    """Build a human-readable transfer log."""
    if not transfers:
        return pd.DataFrame()

    name_map = dict(zip(player_df["id"], player_df["web_name"]))
    team_map = dict(zip(player_df["id"], player_df["team_short"]))
    price_map = dict(zip(player_df["id"], player_df["price"]))

    rows = []
    for t in transfers:
        rows.append({
            "GW": t.event,
            "In": name_map.get(t.player_in, str(t.player_in)),
            "In Team": team_map.get(t.player_in, "?"),
            "In Price": price_map.get(t.player_in, t.player_in_cost / 10.0),
            "Out": name_map.get(t.player_out, str(t.player_out)),
            "Out Team": team_map.get(t.player_out, "?"),
            "Out Price": price_map.get(t.player_out, t.player_out_cost / 10.0),
            "Date": t.time[:10] if t.time else "",
        })

    return pd.DataFrame(rows)
