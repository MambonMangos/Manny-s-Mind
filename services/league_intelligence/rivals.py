"""Rival Tracker — analytical comparison against specific rivals (Phase 4).

Builds head-to-head comparisons: squads, captains, differential opportunities,
transfer divergence, weak positions and aggregate xPts.

STRICTLY ANALYTICAL: produces a ``RivalAnalysis`` report only. Nothing here
changes the user's team, issues transfers, or touches prediction values.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict

from services.league_intelligence.models import RivalAnalysis
from utils.config import load_config

logger = logging.getLogger(__name__)


class RivalTracker:
    """Compares the user's squad/projections against tracked rivals.

    Inputs:
      user_squad: set[int]
      user_captain: int | None
      projections_by_id: {player_id: ExpectedPlayerProjection}
      rival_squads: {entry_id: {player_id: multiplier}} or {entry_id: set[int]}
      rival_names: {entry_id: str} (optional)
      position_by_id: {player_id: str} (optional, for weak-position analysis)
    """

    def __init__(self, config: dict | None = None):
        self._config = config or load_config("league_intelligence")
        rv = self._config.get("rivals", {})
        self._top_rivals = int(rv.get("top_rivals_n", 5))
        self._weak_gap = float(rv.get("weak_position_gap", 1.5))

    def analyze(
        self,
        user_squad: set[int],
        user_captain: int | None,
        projections_by_id: dict,
        rival_squads: dict,
        rival_names: dict | None = None,
        position_by_id: dict | None = None,
        gameweek_id: int = 0,
    ) -> RivalAnalysis:
        """Build the rival-comparison report."""
        rival_names = rival_names or {}
        position_by_id = position_by_id or {}
        report = RivalAnalysis(gameweek_id=gameweek_id, rival_ids=list(rival_squads.keys()))
        report.rival_names = rival_names

        if not rival_squads:
            report.notes.append("No rival squad data available — comparison skipped.")
            return report

        user_set = set(user_squad)

        # Normalise rival squads: {entry_id: set[player_id]} and captain maps.
        rival_player_sets: dict[int, set[int]] = {}
        rival_captains: dict[int, int] = {}
        for eid, raw in rival_squads.items():
            if isinstance(raw, dict):
                rival_player_sets[eid] = set(raw.keys())
                for pid, mult in raw.items():
                    if mult and mult >= 2:
                        rival_captains[eid] = pid
            else:
                rival_player_sets[eid] = set(raw)

        # --- Squad comparison -------------------------------------------------
        for eid in list(rival_squads.keys())[: self._top_rivals]:
            rs = rival_player_sets.get(eid, set())
            report.squad_comparison.append({
                "entry_id": eid,
                "team_name": rival_names.get(eid, ""),
                "in_both": sorted(user_set & rs),
                "user_only": sorted(user_set - rs),
                "rival_only": sorted(rs - user_set),
                "shared_count": len(user_set & rs),
            })

        # --- Captain comparison ----------------------------------------------
        user_cap = user_captain
        if user_cap is not None and rival_captains:
            cap_counter = Counter(rival_captains.values())
            report.captain_comparison = {
                "user_captain": user_cap,
                "user_captain_xpts": round(float(projections_by_id.get(user_cap).projected_points), 2)
                if user_cap in projections_by_id else None,
                "n_rivals_on_user_captain": cap_counter.get(user_cap, 0),
                "rival_captains": [
                    {"entry_id": eid, "captain": c, "xpts": round(float(projections_by_id.get(c).projected_points), 2)
                     if c in projections_by_id else None}
                    for eid, c in sorted(rival_captains.items())[: self._top_rivals]
                ],
                "best_rival_captain": max(
                    ({"entry_id": eid, "captain": c,
                      "xpts": float(projections_by_id.get(c).projected_points)
                      if c in projections_by_id else 0.0}
                     for eid, c in rival_captains.items()),
                    key=lambda d: d.get("xpts") or 0.0,
                    default=None,
                ),
            }

        # --- Differential opportunities (players no rival owns) --------------
        all_rival_players: Counter = Counter()
        for s in rival_player_sets.values():
            all_rival_players.update(s)
        opps = []
        for pid, proj in projections_by_id.items():
            if pid in user_set:
                continue
            owned_by = all_rival_players.get(pid, 0)
            if owned_by == 0:
                opps.append({
                    "player_id": pid,
                    "web_name": proj.web_name,
                    "position": proj.position,
                    "xpts": round(float(proj.projected_points), 2),
                })
        opps.sort(key=lambda o: o["xpts"], reverse=True)
        report.differential_opportunities = opps[: self._top_rivals]

        # --- Transfer divergence --------------------------------------------
        # Players entering multiple rival squads that the user does not own.
        entering: Counter = Counter()
        for s in rival_player_sets.values():
            entering.update(s)
        divergence = [
            {"player_id": pid, "rival_ownership": count, "count": count}
            for pid, count in entering.most_common()
            if pid not in user_set and count >= max(1, int(len(rival_player_sets) * 0.4))
        ]
        report.transfer_divergence = divergence[: self._top_rivals]

        # --- Weak positions ----------------------------------------------------
        if position_by_id:
            pos_xpts = defaultdict(list)
            for pid in user_set:
                proj = projections_by_id.get(pid)
                if proj is not None:
                    pos_xpts[position_by_id.get(pid, proj.position)].append(float(proj.projected_points))
            rival_pos_xpts = defaultdict(list)
            for s in rival_player_sets.values():
                for pid in s:
                    proj = projections_by_id.get(pid)
                    if proj is not None:
                        rival_pos_xpts[position_by_id.get(pid, proj.position)].append(float(proj.projected_points))
            for pos, vals in pos_xpts.items():
                mine = sum(vals)
                theirs = sum(rival_pos_xpts.get(pos, []))
                if theirs - mine >= self._weak_gap:
                    report.weak_positions.append({
                        "position": pos,
                        "user_xpts": round(mine, 2),
                        "avg_rival_xpts": round(theirs, 2),
                        "gap": round(theirs - mine, 2),
                    })
            report.weak_positions.sort(key=lambda w: w["gap"], reverse=True)

        # --- Aggregate xPts comparison ----------------------------------------
        mine_total = round(sum(
            float(projections_by_id[p].projected_points) for p in user_set if p in projections_by_id
        ), 2)
        totals = {"user_total_xpts": mine_total, "rivals": {}}
        for eid, s in rival_player_sets.items():
            totals["rivals"][eid] = round(sum(
                float(projections_by_id[p].projected_points) for p in s if p in projections_by_id
            ), 2)
        report.xpts_comparison = totals
        if totals["rivals"]:
            avg_rival = sum(totals["rivals"].values()) / len(totals["rivals"])
            report.notes.append(
                f"Your projected total ({mine_total}) is "
                f"{'ahead of' if mine_total >= avg_rival else 'behind'} the rival average "
                f"({avg_rival:.1f}) for GW{gameweek_id}."
            )
        return report
