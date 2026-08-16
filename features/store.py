"""FeatureStore — centralised, structured access to all player features.

The store is built once per snapshot cycle. Engines never compute features
directly — they call store methods to get pre-computed columns or slices.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FeatureStore:
    """Immutable snapshot of all derived features for the current gameweek.

    Built by ``build_feature_store()``.  Provides typed accessors so
    engines never touch raw columns directly — they get clean, named
    DataFrames or Series.
    """

    # The enriched DataFrame (all raw + derived columns)
    df: pd.DataFrame

    # Context objects stored at build time
    fixture_map: dict[int, list[dict]] = field(default_factory=dict)
    team_name_map: dict[int, str] = field(default_factory=dict)
    gameweek_id: int = 0
    config_hash: str = ""

    # Cached snapshots (lazily computed)
    _minutes_features: pd.DataFrame | None = field(default=None, repr=False)
    _xgi_features: pd.DataFrame | None = field(default=None, repr=False)
    _fixture_features: pd.DataFrame | None = field(default=None, repr=False)
    _value_features: pd.DataFrame | None = field(default=None, repr=False)
    _market_features: pd.DataFrame | None = field(default=None, repr=False)
    _availability_features: pd.DataFrame | None = field(default=None, repr=False)
    _set_piece_features: pd.DataFrame | None = field(default=None, repr=False)
    _trend_features: pd.DataFrame | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Core accessors — one per feature category
    # ------------------------------------------------------------------

    def player_ids(self) -> pd.Series:
        return self.df["player_id"]

    def position(self) -> pd.Series:
        return self.df["position"]

    def team_id(self) -> pd.Series:
        return self.df["team_id"]

    def minutes_features(self) -> pd.DataFrame:
        """Minutes reliability features: total, recent, trend, projected."""
        if self._minutes_features is None:
            self._minutes_features = self._build_minutes_features()
        return self._minutes_features

    def xgi_features(self) -> pd.DataFrame:
        """Expected goal involvement features: raw, per-90, trend, finishing ratio."""
        if self._xgi_features is None:
            self._xgi_features = self._build_xgi_features()
        return self._xgi_features

    def fixture_features(self, gameweek: int | None = None) -> pd.DataFrame:
        """Fixture difficulty features: next 1/3/6 GW windows, home/away split."""
        if self._fixture_features is None:
            self._fixture_features = self._build_fixture_features()
        return self._fixture_features

    def value_features(self) -> pd.DataFrame:
        """Value metrics: price, points_per_million, cost_change, value_season."""
        if self._value_features is None:
            self._value_features = self._build_value_features()
        return self._value_features

    def market_features(self) -> pd.DataFrame:
        """Market dynamics: ownership, transfers in/out, velocity, price direction."""
        if self._market_features is None:
            self._market_features = self._build_market_features()
        return self._market_features

    def availability_features(self) -> pd.DataFrame:
        """Availability: status, chance of playing, news flags."""
        if self._availability_features is None:
            self._availability_features = self._build_availability_features()
        return self._availability_features

    def set_piece_features(self) -> pd.DataFrame:
        """Set-piece duties: penalties, FKs, corners, composite set-piece score."""
        if self._set_piece_features is None:
            self._set_piece_features = self._build_set_piece_features()
        return self._set_piece_features

    def trend_features(self) -> pd.DataFrame:
        """Form trends: rolling form, momentum, xGI trend direction."""
        if self._trend_features is None:
            self._trend_features = self._build_trend_features()
        return self._trend_features

    # ------------------------------------------------------------------
    # Convenience: all features as a single wide DataFrame
    # ------------------------------------------------------------------

    def all_features(self) -> pd.DataFrame:
        """Return a single DataFrame with all feature columns merged.

        Columns are prefixed by category: ``minutes_*``, ``xgi_*``, etc.
        """
        parts = [
            self._base_cols(),
            self.minutes_features(),
            self.xgi_features(),
            self.fixture_features(),
            self.value_features(),
            self.market_features(),
            self.availability_features(),
            self.set_piece_features(),
            self.trend_features(),
        ]
        return pd.concat(parts, axis=1)

    def summary(self) -> dict[str, Any]:
        """Return a metadata summary of this feature snapshot."""
        return {
            "gameweek_id": self.gameweek_id,
            "n_players": len(self.df),
            "config_hash": self.config_hash,
            "feature_categories": [
                "minutes", "xgi", "fixture", "value",
                "market", "availability", "set_piece", "trend",
            ],
            "total_features": sum(
                getattr(self, f"_{cat}_features", None) is not None
                for cat in [
                    "minutes", "xgi", "fixture", "value",
                    "market", "availability", "set_piece", "trend",
                ]
            ),
        }

    # ------------------------------------------------------------------
    # Private: base columns that every engine needs
    # ------------------------------------------------------------------

    def _base_cols(self) -> pd.DataFrame:
        base = pd.DataFrame(index=self.df.index)
        base["player_id"] = self.df["player_id"]
        base["web_name"] = self.df["web_name"]
        base["position"] = self.df["position"]
        base["team_id"] = self.df["team_id"]
        base["price"] = self.df["price"]
        base["total_points"] = self.df["total_points"]
        base["form"] = self.df["form"]
        return base

    # ------------------------------------------------------------------
    # Private: feature builders
    # ------------------------------------------------------------------

    def _build_minutes_features(self) -> pd.DataFrame:
        """Minutes reliability: season total, recent form, projected, reliability."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["minutes_season"] = df["minutes"].fillna(0)
        # Minutes per start, capped at 90 (a starter cannot earn more than 90
        # minutes). Uncapped, a few starts + many sub minutes yields absurd
        # values (e.g. 1 start / 900 min -> 900.0).
        f["minutes_per_game"] = np.minimum(
            np.where(
                df["starts"].fillna(0) > 0,
                f["minutes_season"] / df["starts"].fillna(1),
                0.0,
            ),
            90.0,
        )
        f["minutes_fraction"] = df["minutes_fraction"].fillna(0)
        # Observed starts / games played (games ~ minutes/90). Truthful only
        # because `starts` is the real FPL value, not a minutes-derived proxy.
        f["starts_rate"] = np.where(
            f["minutes_season"] > 0,
            df["starts"].fillna(0) / np.maximum(f["minutes_season"] / 90, 1),
            0.0,
        )
        # Preserve the raw starts count for engines and diagnostics.
        f["starts"] = df["starts"].fillna(0).astype(int)
        f["minutes_reliable"] = (f["minutes_fraction"] >= 60).astype(float)
        f["minutes_projected"] = df["minutes_projected"].fillna(60)

        return f

    def _build_xgi_features(self) -> pd.DataFrame:
        """xGI features: raw totals, per-90 rates, trend, finishing ratio."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["xg_raw"] = df["expected_goals"].fillna(0)
        f["xa_raw"] = df["expected_assists"].fillna(0)
        f["xgi_raw"] = df["expected_goal_involvements"].fillna(0)
        f["xgc_raw"] = df["expected_goals_conceded"].fillna(0)

        f["xgi_per_90"] = df["xgi_per_90"].fillna(0)

        # Finishing ratio: actual goals / xG (regression signal)
        f["finishing_ratio"] = np.where(
            f["xg_raw"] > 0,
            df["goals_scored"].fillna(0) / f["xg_raw"],
            1.0,
        )
        # Creative ratio: actual assists / xA
        f["creative_ratio"] = np.where(
            f["xa_raw"] > 0,
            df["assists"].fillna(0) / f["xa_raw"],
            1.0,
        )

        # Write canonical versions to self.df so engines read from SSOT
        self.df["finishing_ratio"] = f["finishing_ratio"]
        self.df["creative_ratio"] = f["creative_ratio"]

        return f

    def _build_fixture_features(self) -> pd.DataFrame:
        """Fixture features: next 1/3/6 GW difficulty averages, home/away, swings."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        # Use pre-computed fixture score if available
        f["fixture_score_3gw"] = df["fixture_score_raw"].fillna(50)
        f["team_strength"] = df["team_strength_raw"].fillna(100)

        # Per-GW fixture breakdowns from fixture_map
        if self.fixture_map:
            avg_1 = []
            avg_3 = []
            avg_6 = []
            home_count_3 = []
            diff_counts = []  # easy(<=2), mid(3), hard(>=4) counts for 6-GW

            for _, row in df.iterrows():
                team_id = int(row.get("team_id", 0) or 0)
                fixtures = self.fixture_map.get(team_id, [])

                diffs_1 = [fx["difficulty"] for fx in fixtures[:1]]
                diffs_3 = [fx["difficulty"] for fx in fixtures[:3]]
                diffs_6 = [fx["difficulty"] for fx in fixtures[:6]]

                home_3 = sum(1 for fx in fixtures[:3] if fx.get("home", False))

                avg_1.append(np.mean(diffs_1) if diffs_1 else 3.0)
                avg_3.append(np.mean(diffs_3) if diffs_3 else 3.0)
                avg_6.append(np.mean(diffs_6) if diffs_6 else 3.0)
                home_count_3.append(home_3)

                easy = sum(1 for d in diffs_6 if d <= 2)
                mid = sum(1 for d in diffs_6 if d == 3)
                hard = sum(1 for d in diffs_6 if d >= 4)
                diff_counts.append({"easy": easy, "mid": mid, "hard": hard})

            f["fixture_avg_1gw"] = avg_1
            f["fixture_avg_3gw"] = avg_3
            f["fixture_avg_6gw"] = avg_6
            f["home_count_next_3"] = home_count_3
            f["fixture_easy_count"] = [d["easy"] for d in diff_counts]
            f["fixture_hard_count"] = [d["hard"] for d in diff_counts]

            # Fixture swing: first 3 vs next 3
            swings = []
            for _, row in df.iterrows():
                team_id = int(row.get("team_id", 0) or 0)
                fixtures = self.fixture_map.get(team_id, [])
                first_3 = [fx["difficulty"] for fx in fixtures[:3]]
                second_3 = [fx["difficulty"] for fx in fixtures[3:6]]
                if first_3 and second_3:
                    swings.append(np.mean(first_3) - np.mean(second_3))
                else:
                    swings.append(0.0)
            f["fixture_swing"] = swings
        else:
            f["fixture_avg_1gw"] = 3.0
            f["fixture_avg_3gw"] = 3.0
            f["fixture_avg_6gw"] = 3.0
            f["home_count_next_3"] = 1
            f["fixture_easy_count"] = 2
            f["fixture_hard_count"] = 2
            f["fixture_swing"] = 0.0

        return f

    def _build_value_features(self) -> pd.DataFrame:
        """Value metrics: price efficiency, cost trajectory, PPM."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["price"] = df["price"].fillna(0)
        f["points_per_million"] = df["points_per_million"].fillna(0)
        f["cost_change_start"] = df["cost_change_start"].fillna(0)
        f["cost_change_event"] = df["cost_change_event"].fillna(0)
        f["value_form"] = df["value_form"].fillna(0)
        f["value_season"] = df["value_season"].fillna(0)

        # Price direction: rising (+1), stable (0), falling (-1)
        f["price_direction"] = np.sign(f["cost_change_start"])

        # String label for engine consumption (canonical from cost_change_event)
        self.df["price_direction_label"] = np.where(
            df["cost_change_event"].fillna(0) > 0, "rising",
            np.where(df["cost_change_event"].fillna(0) < 0, "falling", "stable"),
        )

        return f

    def _build_market_features(self) -> pd.DataFrame:
        """Market dynamics: ownership, transfer activity, momentum."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["selected_by_percent"] = df["selected_by_percent"].fillna(0)
        f["transfers_in_event"] = df["transfers_in_event"].fillna(0)
        f["transfers_out_event"] = df["transfers_out_event"].fillna(0)
        f["net_transfers"] = f["transfers_in_event"] - f["transfers_out_event"]

        # Ownership tier: differential (<5%), mid (5-20%), template (>20%)
        f["ownership_tier"] = np.where(
            f["selected_by_percent"] < 5, "differential",
            np.where(f["selected_by_percent"] < 20, "mid", "template"),
        )

        # Transfer velocity: net transfers as % of owners
        f["transfer_velocity"] = np.where(
            f["selected_by_percent"] > 0,
            f["net_transfers"] / (f["selected_by_percent"] / 100 * 1_000_000) * 100,
            0.0,
        )

        # Write canonical versions to self.df so engines read from SSOT
        self.df["net_transfers"] = f["net_transfers"]
        self.df["ownership_tier"] = f["ownership_tier"]
        self.df["transfer_velocity"] = f["transfer_velocity"]

        return f

    def _build_availability_features(self) -> pd.DataFrame:
        """Availability flags: fit, doubtful, injured, suspended."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["status"] = df["status"].fillna("a")
        f["is_fit"] = (f["status"] == "a").astype(float)
        f["is_doubtful"] = (f["status"] == "d").astype(float)
        f["is_injured"] = (f["status"] == "i").astype(float)
        f["is_suspended"] = (f["status"] == "s").astype(float)
        f["is_unavailable"] = f["is_injured"] + f["is_suspended"]
        f["chance_next"] = df["chance_of_playing_next_round"].fillna(100) / 100.0
        f["chance_this"] = df["chance_of_playing_this_round"].fillna(100) / 100.0
        f["has_news"] = (~df["news"].fillna("").eq("")).astype(float)

        return f

    def _build_set_piece_features(self) -> pd.DataFrame:
        """Set-piece duties: penalties, FKs, corners, composite score."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["penalties_order"] = df["penalties_order"].fillna(99)
        f["fk_order"] = df["direct_freekicks_order"].fillna(99)
        f["corners_order"] = df["corners_and_indirect_freekicks_order"].fillna(99)
        f["set_piece_raw"] = df["set_piece_raw"].fillna(50)

        # Binary flags for key taker roles
        f["is_penalty_taker"] = (f["penalties_order"] == 1).astype(float)
        f["is_fk_taker"] = (f["fk_order"] == 1).astype(float)
        f["is_corner_taker"] = (f["corners_order"] == 1).astype(float)

        return f

    def _build_trend_features(self) -> pd.DataFrame:
        """Form trends: recent form, momentum, ICT direction."""
        f = pd.DataFrame(index=self.df.index)
        df = self.df

        f["form"] = df["form"].fillna(0)
        f["influence"] = df["influence"].fillna(0)
        f["creativity"] = df["creativity"].fillna(0)
        f["threat"] = df["threat"].fillna(0)
        f["ict_index"] = df["ict_index"].fillna(0)

        # Form tier: cold (<2), warm (2-5), hot (>5)
        f["form_tier"] = np.where(
            f["form"] < 2, "cold",
            np.where(f["form"] < 5, "warm", "hot"),
        )

        # Momentum: form change (if we have event_points vs form)
        f["event_points"] = df["event_points"].fillna(0)
        f["form_momentum"] = f["event_points"] - f["form"]

        return f


# ------------------------------------------------------------------
# Factory function
# ------------------------------------------------------------------

def build_feature_store(
    players_df: pd.DataFrame,
    fixture_map: dict[int, list[dict]] | None = None,
    team_name_map: dict[int, str] | None = None,
    gameweek_id: int = 0,
    config_hash: str = "",
) -> FeatureStore:
    """Build a FeatureStore from a player DataFrame.

    Parameters
    ----------
    players_df : DataFrame
        Enriched player DataFrame (output of ``get_players_dataframe()``).
    fixture_map : dict, optional
        team_id → list of fixture dicts. Used for fixture features.
    team_name_map : dict, optional
        team_id → team_name.
    gameweek_id : int
        Current gameweek identifier.
    config_hash : str
        SHA-256 of the active config for traceability.

    Returns
    -------
    FeatureStore
        Immutable snapshot ready for engine consumption.
    """
    # Ensure the DataFrame has all required derived columns
    from services.scoring import add_derived_columns

    enriched = add_derived_columns(
        players_df,
        fixture_map=fixture_map,
        team_name_map=team_name_map,
    )

    # Canonicalize the player ID column — engines expect "player_id"
    if "player_id" not in enriched.columns and "id" in enriched.columns:
        enriched["player_id"] = enriched["id"]

    # Add minutes_projected if not present (simple heuristic for now)
    if "minutes_projected" not in enriched.columns:
        enriched["minutes_projected"] = enriched["minutes"].apply(
            _project_minutes_heuristic
        )
    # Preserve the real FPL starts value whenever available. Never derive
    # starts from minutes (round(minutes/90)) — that fabrication made every
    # player's starts_rate collapse to 1.0. Missing starts degrade to 0.
    if "starts" not in enriched.columns:
        enriched["starts"] = 0
    enriched["starts"] = enriched["starts"].fillna(0).astype(int)

    store = FeatureStore(
        df=enriched,
        fixture_map=fixture_map or {},
        team_name_map=team_name_map or {},
        gameweek_id=gameweek_id,
        config_hash=config_hash,
    )

    # Eagerly compute canonical columns so engines read from store.df (SSOT)
    store.xgi_features()
    store.market_features()
    store.value_features()

    logger.info(
        "FeatureStore built: %d players, gw=%d, config_hash=%s",
        len(enriched), gameweek_id, config_hash[:12] if config_hash else "none",
    )

    return store


def _project_minutes_heuristic(minutes: float) -> float:
    """Simple minutes projection for FeatureStore bootstrap.

    This is a TEMPORARY fallback until the Minutes Engine (Phase 2A)
    replaces it with a proper projection.
    """
    if minutes == 0:
        return 60.0
    if minutes >= 270:
        return 85.0
    if minutes >= 180:
        return 70.0
    if minutes >= 90:
        return 55.0
    return 30.0
