"""League Intelligence — community data providers.

Provider interfaces (Protocols) decouple the League Intelligence Layer from any
specific external source. The engine depends on these interfaces; concrete
implementations are injected at call time (see ``engine.run_league_intelligence``).

Design contract:
  - No provider is hard-coded into the layer. The FPL-backed implementation is
    one implementation among many (LiveFPL, fantasyfootballpundit, fpl.page…).
  - Providers are best-effort: the engine degrades gracefully when a provider
    has no data for a gameweek (missing figures stay ``None``/0.0 rather than
    failing the run).
  - Never modify projections or the feature store.
"""

from __future__ import annotations

import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class OwnershipProvider(Protocol):
    """Global ownership signal for one gameweek, keyed by player_id."""

    def get_global_ownership(self, gameweek_id: int) -> dict[int, float]:
        """Return {player_id: ownership_pct} for the gameweek."""
        ...

    def get_top10k_ownership(self, gameweek_id: int) -> dict[int, float] | None:
        """Return {player_id: top10k ownership_pct}, or None if unavailable."""
        ...


class CaptainPollProvider(Protocol):
    """Community captaincy polls for one gameweek, keyed by player_id."""

    def get_captain_pct(self, gameweek_id: int) -> dict[int, float]:
        """Return {player_id: % of managers captaining}."""
        ...


class CommunityStatsProvider(Protocol):
    """Net-transfer and price-movement signals for one gameweek."""

    def get_transfer_velocity(self, gameweek_id: int) -> dict[int, float]:
        """Return {player_id: net transfer velocity} (positive = buying)."""
        ...

    def get_price_movement(self, gameweek_id: int) -> dict[int, float]:
        """Return {player_id: cost change this gameweek} (in £0.1 units)."""
        ...


class MiniLeagueProvider(Protocol):
    """Mini-league standings and rival squads (Phase 3/4)."""

    def get_league_standings(
        self, league_id: int, gameweek_id: int
    ) -> list[dict]:
        """Return standings rows with keys: entry_id, team_name, rank.

        Entries are ordered best-to-worst; ``gameweek_id`` lets providers
        filter to a snapshot if they only publish the latest.
        """
        ...

    def get_entry_squad(
        self, entry_id: int, gameweek_id: int
    ) -> dict[int, int]:
        """Return {player_id: multiplier} for a rival's squad that gameweek.

        multiplier 2 = captain, 3 = triple captain. Return {} when unavailable.
        """
        ...


# ---------------------------------------------------------------------------
# Reference implementations
# ---------------------------------------------------------------------------


class FeatureStoreOwnershipProvider:
    """Ownership/transfer signal derived from the local feature store.

    This is the always-available, offline provider: it reads the ownership and
    transfer columns already computed into the FeatureStore (or a plain player
    DataFrame with the same schema). Captain polls and top-10k data are not
    locally available, so those return empty/None.
    """

    def __init__(self, store=None, players_df=None):
        self._store = store
        self._players_df = players_df
        self._cache: dict[int, dict[int, float]] = {}

    def _frame(self):
        if self._players_df is not None:
            return self._players_df
        if self._store is not None and hasattr(self._store, "df"):
            return self._store.df
        return None

    def _ownership_map(self, gameweek_id: int) -> dict[int, float]:
        if gameweek_id in self._cache:
            return self._cache[gameweek_id]
        frame = self._frame()
        result: dict[int, float] = {}
        if frame is not None and "player_id" in frame.columns:
            col = "selected_by_percent" if "selected_by_percent" in frame.columns else None
            if col:
                for _, row in frame.iterrows():
                    result[int(row["player_id"])] = float(row[col] or 0.0)
        self._cache[gameweek_id] = result
        return result

    def get_global_ownership(self, gameweek_id: int) -> dict[int, float]:
        return self._ownership_map(gameweek_id)

    def get_top10k_ownership(self, gameweek_id: int) -> dict[int, float] | None:
        return None

    def get_transfer_velocity(self, gameweek_id: int) -> dict[int, float]:
        frame = self._frame()
        result: dict[int, float] = {}
        if frame is not None and {"player_id", "transfers_in_event", "transfers_out_event"} <= set(frame.columns):
            for _, row in frame.iterrows():
                result[int(row["player_id"])] = float(
                    (row["transfers_in_event"] or 0) - (row["transfers_out_event"] or 0)
                )
        return result

    def get_price_movement(self, gameweek_id: int) -> dict[int, float]:
        frame = self._frame()
        result: dict[int, float] = {}
        if frame is not None and {"player_id", "cost_change_event"} <= set(frame.columns):
            for _, row in frame.iterrows():
                result[int(row["player_id"])] = float(row["cost_change_event"] or 0.0)
        return result


class FPLApiMiniLeagueProvider:
    """Mini-league + rival data from the official FPL API.

    Uses ``services.api_client.fpl_get`` (shared SSL/timeout/retry handling).
    Every call is wrapped so a missing league or network failure yields an
    empty result instead of aborting the run.
    """

    def __init__(self, api_get=None):
        self._api_get = api_get

    def _get(self, endpoint: str):
        if self._api_get is not None:
            return self._api_get(endpoint)
        from services.api_client import fpl_get

        return fpl_get(endpoint)

    def get_league_standings(self, league_id: int, gameweek_id: int) -> list[dict]:
        try:
            data = self._get(f"/leagues-classic/{league_id}/standings/")
        except Exception as exc:  # noqa: BLE001 - external API boundary, degrade
            logger.warning("League standings unavailable (league %s): %s", league_id, exc)
            return []
        rows = []
        for item in (data.get("standings") or {}).get("results", []):
            rows.append({
                "entry_id": int(item.get("entry", 0)),
                "team_name": item.get("entry_name", ""),
                "rank": item.get("rank"),
                "total_points": item.get("total", 0),
            })
        return rows

    def get_entry_squad(self, entry_id: int, gameweek_id: int) -> dict[int, int]:
        try:
            data = self._get(f"/entry/{entry_id}/event/{gameweek_id}/picks/")
        except Exception as exc:  # noqa: BLE001 - external API boundary, degrade
            logger.warning("Entry squad unavailable (entry %s gw %s): %s", entry_id, gameweek_id, exc)
            return {}
        squad: dict[int, int] = {}
        for pick in data.get("picks", []):
            squad[int(pick.get("element", 0))] = int(pick.get("multiplier", 1))
        return squad
