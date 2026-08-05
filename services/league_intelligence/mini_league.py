"""Mini-League Analyzer — analytical view of the user's mini-league (Phase 3).

Computes facts about squad overlap, differentials, captain overlap, ownership
overlap, risk profile, squad similarity and competitive threats.

STRICTLY ANALYTICAL: this module produces a ``MiniLeagueAnalysis`` report and
nothing else. It never recommends transfers, never changes the user's team and
never modifies prediction values.
"""

from __future__ import annotations

import logging
from collections import Counter

from services.league_intelligence.models import MiniLeagueAnalysis
from utils.config import load_config

logger = logging.getLogger(__name__)


def _squads_as_sets(squads: dict) -> list[set[int]]:
    """Normalise {entry_id: {player_id, ...}} (or {player_id: mult}) to a list of sets."""
    result = []
    for value in squads.values():
        if isinstance(value, dict):
            result.append(set(value.keys()))
        else:
            result.append(set(value))
    return result


def _jaccard(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 0.0
    return round(len(a & b) / len(a | b), 4)


class MiniLeagueAnalyzer:
    """Analyzes a mini-league snapshot for overlap, differentials and threats.

    Inputs:
      league_id, position, gameweek_id
      user_squad: set[int] of the user's player ids
      squads: {entry_id: {player_id, ...}} for every league team (incl. user)
      captains: {entry_id: player_id} captain per team (optional)
      n_teams: total teams in the league

    All optional data is tolerated: missing captain data skips captain overlap.
    """

    def __init__(self, config: dict | None = None):
        self._config = config or load_config("league_intelligence")
        ml = self._config.get("mini_league", {})
        self._common_min = float(ml.get("common_ownership_min", 0.60))
        self._similarity_threshold = float(ml.get("squad_similarity_threshold", 0.5))
        self._threat_overlap = float(ml.get("threat_overlap_threshold", 0.55))
        self._top_diff = int(ml.get("top_differentials", 5))

    def analyze(
        self,
        user_squad: set[int],
        squads: dict,
        league_id: int | None = None,
        position: int | None = None,
        gameweek_id: int = 0,
        captains: dict[int, int] | None = None,
        all_players: dict[int, str] | None = None,
    ) -> MiniLeagueAnalysis:
        """Build the mini-league analysis report."""
        squads_list = _squads_as_sets(squads)
        n_teams = max(len(squads_list), 1)
        user_set = set(user_squad)
        all_players = all_players or {}

        report = MiniLeagueAnalysis(
            gameweek_id=gameweek_id,
            league_id=league_id,
            n_teams=n_teams,
            position=position,
        )
        if not squads_list:
            report.notes.append("No league squad data available — analysis skipped.")
            return report

        # League-wide ownership counts (exclude the user to measure league peer exposure).
        peer_squads = [s for s in squads_list if s != user_set]
        peer_count = len(peer_squads) or 1
        owner_count: Counter = Counter()
        for s in peer_squads:
            owner_count.update(s)

        # --- Common players -------------------------------------------------
        common = []
        for pid, count in owner_count.items():
            if count / peer_count >= self._common_min and pid in user_set:
                common.append({
                    "player_id": pid,
                    "web_name": all_players.get(pid, f"P{pid}"),
                    "league_ownership": round(100.0 * count / peer_count, 1),
                })
        common.sort(key=lambda c: c["league_ownership"], reverse=True)
        report.common_players = common

        # --- Differentials (user owns, league mostly does not) --------------
        diffs = []
        for pid in user_set:
            count = owner_count.get(pid, 0)
            ownership = round(100.0 * count / peer_count, 1)
            if ownership <= (self._common_min * 100.0) * 0.5:  # owned by <30% of peers
                diffs.append({
                    "player_id": pid,
                    "web_name": all_players.get(pid, f"P{pid}"),
                    "league_ownership": ownership,
                })
        diffs.sort(key=lambda d: d["league_ownership"])
        report.league_differentials = diffs[: self._top_diff]

        # --- Captain overlap ------------------------------------------------
        if captains:
            user_cap = captains.get(0)
            peer_caps = [c for eid, c in captains.items() if eid != 0]
            if user_cap is not None:
                cap_counter = Counter(peer_caps)
                report.captain_overlap = {
                    "user_captain": user_cap,
                    "n_peers_captaining_same": cap_counter.get(user_cap, 0),
                    "peers_sharing_captain_pct": round(
                        100.0 * cap_counter.get(user_cap, 0) / max(len(peer_caps), 1), 1
                    ),
                    "most_captained_by_peers": [
                        {"player_id": pid, "count": c}
                        for pid, c in cap_counter.most_common(3)
                    ],
                }
            else:
                report.notes.append("User captain unknown — captain overlap skipped.")

        # --- Ownership overlap / risk profile --------------------------------
        user_sizes = [len(s) for s in squads_list]
        report.ownership_overlap = {
            "avg_league_team_size": round(sum(user_sizes) / n_teams, 2),
            "user_squad_size": len(user_set),
        }
        shared_with_any = sum(1 for s in squads_list if s != user_set and (s & user_set))
        report.risk_profile = {
            "n_peers_sharing_any_player": shared_with_any,
            "peers_sharing_any_pct": round(100.0 * shared_with_any / max(n_teams - 1, 1), 1),
            "n_common_players": len(common),
            "n_differentials": len(diffs),
        }
        if len(common) >= 5:
            report.notes.append(
                f"{len(common)} common players — your squad heavily overlaps the league. "
                "Differential upside is limited unless you break ranks."
            )

        # --- Squad similarity + threats --------------------------------------
        similarities = {}
        for eid, raw in squads.items():
            squad = set(raw.keys()) if isinstance(raw, dict) else set(raw)
            if squad == user_set:
                continue
            similarities[eid] = _jaccard(user_set, squad)
        report.squad_similarity = {
            "mean": round(sum(similarities.values()) / max(len(similarities), 1), 4),
            "max": round(max(similarities.values()), 4) if similarities else 0.0,
            "by_entry": dict(sorted(similarities.items(), key=lambda kv: -kv[1])[:5]),
        }
        report.threats = [
            {
                "entry_id": eid,
                "similarity": sim,
                "shared_players": sorted(user_set & (set(squads[eid].keys()) if isinstance(squads[eid], dict) else set(squads[eid]))),
            }
            for eid, sim in sorted(similarities.items(), key=lambda kv: -kv[1])
            if sim >= self._threat_overlap
        ][:5]
        if report.threats:
            top = report.threats[0]
            report.notes.append(
                f"Highest-similarity rival entry {top['entry_id']} shares "
                f"{top['similarity']:.0%} of your squad — matches matter more here."
            )
        return report
