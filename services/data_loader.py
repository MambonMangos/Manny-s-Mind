"""Data loader – fetches bootstrap-static.json from the FPL API and persists to SQLite.

The database is the single source of truth. This module fetches fresh data
from the live API on every load, so prices, points, and form are always current.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database.crud import upsert_gameweeks_bulk, upsert_players_bulk, upsert_teams_bulk
from database.database import get_session, init_db
from services.api_client import fpl_get
from utils.constants import DATA_STALENESS_SECONDS, POSITION_MAP

logger = logging.getLogger(__name__)

# Fields from bootstrap-static.json element object that we store
_PLAYER_FIELDS = (
    "id", "first_name", "second_name", "web_name", "team", "element_type",
    "now_cost", "cost_change_start", "cost_change_event",
    "cost_change_start_fall", "cost_change_event_fall",
    "value_form", "value_season",
    "starts", "minutes", "goals_scored", "assists", "clean_sheets",
    "goals_conceded", "own_goals", "penalties_saved", "penalties_missed",
    "yellow_cards", "red_cards", "saves", "bonus", "bps",
    "influence", "creativity", "threat", "ict_index",
    "expected_goals", "expected_assists",
    "expected_goal_involvements", "expected_goals_conceded",
    "total_points", "event_points",
    "form", "selected_by_percent",
    "transfers_in_event", "transfers_out_event",
    "transfers_in", "transfers_out",
    "status", "news",
    "chance_of_playing_next_round", "chance_of_playing_this_round",
    "news_added",
    "penalties_order", "direct_freekicks_order",
    "corners_and_indirect_freekicks_order",
    "is_locked",
)

_TEAM_FIELDS = (
    "id", "name", "short_name",
    "strength_overall_home", "strength_overall_away",
    "strength_attack_home", "strength_attack_away",
    "strength_defence_home", "strength_defence_away",
    "pulse_id",
)

_GW_FIELDS = (
    "id", "name", "deadline_time", "deadline_time_epoch",
    "deadline_time_game_offset", "finished", "data_checked",
    "is_previous", "is_current", "is_next",
    "most_captained", "most_vice_captained",
    "highest_score", "chip_plays",
)

# Data is considered stale after this many seconds (configurable via
# DATA_STALENESS_SECONDS, default 1 hour).
STALENESS_THRESHOLD_SECONDS: int = DATA_STALENESS_SECONDS


class DataLoader:
    """Fetches bootstrap-static data from the FPL API and upserts into SQLite.

    Usage::

        loader = DataLoader()
        stats = loader.load()
    """

    def load(self, session: Session | None = None) -> dict:
        """Fetch live data from the FPL API and upsert into the database.

        Returns a summary dict with counts.
        """
        raw = fpl_get("/bootstrap-static/")

        teams_raw: list[dict] = raw.get("teams", [])
        players_raw: list[dict] = raw.get("elements", [])
        gameweeks_raw: list[dict] = raw.get("events", [])

        team_records = [self._parse_team(t) for t in teams_raw]
        player_records = [self._parse_player(p) for p in players_raw]
        gw_records = [self._parse_gameweek(g) for g in gameweeks_raw]

        own_session = session is None
        if own_session:
            session = get_session()

        try:
            init_db()
            n_teams = upsert_teams_bulk(session, team_records)
            n_players = upsert_players_bulk(session, player_records)
            n_gws = upsert_gameweeks_bulk(session, gw_records)

            # Record when data was last refreshed
            _set_last_refreshed(session)

            logger.info(
                "Load complete – %d teams, %d players, %d gameweeks",
                n_teams, n_players, n_gws,
            )
            return {"teams": n_teams, "players": n_players, "gameweeks": n_gws}
        finally:
            if own_session:
                session.close()

    # ------------------------------------------------------------------
    # private
    # ------------------------------------------------------------------

    def _parse_team(self, raw: dict) -> dict:
        rec: dict = {}
        for field in _TEAM_FIELDS:
            rec[field] = raw.get(field)
        if rec.get("short_name") is None:
            rec["short_name"] = (rec.get("name") or "")[:3].upper()
        return rec

    def _parse_player(self, raw: dict) -> dict:
        rec: dict = {}
        for field in _PLAYER_FIELDS:
            value = raw.get(field)
            if field == "team":
                rec["team_id"] = value
            elif field == "element_type":
                rec["element_type"] = value
                rec["element_type_str"] = POSITION_MAP.get(value, "UNK")
            elif field == "starts":
                # Preserve the real FPL starts value (matches started). Never
                # derive starts from minutes — the API supplies it directly.
                rec[field] = int(value) if value is not None else 0
            else:
                rec[field] = value
        return rec

    def _parse_gameweek(self, raw: dict) -> dict:
        rec: dict = {}
        for field in _GW_FIELDS:
            rec[field] = raw.get(field)
        if isinstance(rec.get("chip_plays"), list):
            rec["chip_plays"] = json.dumps(rec["chip_plays"])
        return rec


# ------------------------------------------------------------------
# Staleness helpers
# ------------------------------------------------------------------

def _set_last_refreshed(session: Session) -> None:
    """Record the current UTC time as the last refresh timestamp.

    Uses a module-level singleton instead of Streamlit session state,
    so the data layer has zero dependency on any UI framework.
    """
    _staleness_tracker.record_refresh()


def get_data_age_seconds() -> float | None:
    """Return how many seconds since the last data refresh, or None."""
    return _staleness_tracker.get_age_seconds()


def is_data_stale() -> bool:
    """Return True if data needs refreshing."""
    return _staleness_tracker.is_stale()


# ------------------------------------------------------------------
# Staleness tracker (UI-framework-free singleton)
# ------------------------------------------------------------------

class _StalenessTracker:
    """Module-level singleton for tracking data freshness."""

    def __init__(self) -> None:
        self._last_refresh: datetime | None = None

    def record_refresh(self) -> None:
        self._last_refresh = datetime.now(timezone.utc)

    def get_age_seconds(self) -> float | None:
        if self._last_refresh is None:
            return None
        return (datetime.now(timezone.utc) - self._last_refresh).total_seconds()

    def is_stale(self) -> bool:
        age = self.get_age_seconds()
        if age is None:
            return True
        return age > STALENESS_THRESHOLD_SECONDS


_staleness_tracker = _StalenessTracker()
