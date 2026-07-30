"""Squad Optimizer — finds optimal squad composition within FPL constraints.

Owns:
  - Budget-constrained squad optimization
  - Formation selection
  - Captain recommendation
  - Chip timing (when to play Wildcard, Free Hit, etc.)

Reads from: FeatureStore, Projection Engine, Opportunity Engine
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# FPL squad constraints
SQUAD_SIZE = 15
BUDGET = 100.0  # £100m
MAX_PER_TEAM = 3
FORMATION_LIMITS = {
    "3-4-3": {"DEF": 3, "MID": 4, "FWD": 3},
    "3-5-2": {"DEF": 3, "MID": 5, "FWD": 2},
    "4-3-3": {"DEF": 4, "MID": 3, "FWD": 3},
    "4-4-2": {"DEF": 4, "MID": 4, "FWD": 2},
    "4-5-1": {"DEF": 4, "MID": 5, "FWD": 1},
    "5-4-1": {"DEF": 5, "MID": 4, "FWD": 1},
    "5-3-2": {"DEF": 5, "MID": 3, "FWD": 2},
}


@dataclass
class SquadSolution:
    """An optimized squad configuration."""

    # Squad composition
    gkp: list[int]  # 2 goalkeepers
    def_: list[int]  # 5 defenders
    mid: list[int]  # 5 midfielders
    fwd: list[int]  # 3 forwards

    # Starting XI
    starting_xi: list[int]
    formation: str
    captain: int
    vice_captain: int

    # Metrics
    total_projected_points: float
    total_price: float
    remaining_budget: float
    avg_confidence: float

    # Bench
    bench: list[int]

    # Optimization details
    optimization_score: float  # composite metric
    iterations: int


@dataclass
class SquadRecommendation:
    """High-level squad recommendation."""

    current_squad_points: float
    optimized_squad_points: float
    improvement: float

    suggested_transfers: list[dict]
    suggested_formation: str
    captain_recommendation: int

    confidence: float
    reasoning: list[str]


def optimize_squad(
    store,  # noqa: ANN001
    projections: list,  # noqa: ANN001
    current_squad: list[int] | None = None,
    budget: float = BUDGET,
    n_iterations: int = 1000,
) -> SquadSolution:
    """Find an optimal squad within FPL constraints.

    Uses a greedy heuristic with random perturbation to find
    a near-optimal squad.

    Parameters
    ----------
    store : FeatureStore
        Feature store with player data.
    projections : list[PlayerProjection]
        Projections for all players.
    current_squad : list[int], optional
        Current squad player_ids (for relative optimization).
    budget : float
        Total budget in millions.
    n_iterations : int
        Number of optimization iterations.

    Returns
    -------
    SquadSolution
        The best squad found.
    """
    proj_map = {p.player_id: p for p in projections}
    df = store.df

    # Build player lookup
    players = _build_player_lookup(df, proj_map)

    best_solution = None
    best_score = -1

    for i in range(n_iterations):
        solution = _generate_candidate_squad(players, budget)
        if solution is None:
            continue

        score = _evaluate_squad(solution, proj_map)
        if score > best_score:
            best_score = score
            best_solution = solution

    if best_solution is None:
        # Fallback: build a simple squad
        best_solution = _build_fallback_squad(players, budget)
        best_score = _evaluate_squad(best_solution, proj_map) if best_solution else 0

    if best_solution:
        best_solution.iterations = n_iterations
        best_solution.optimization_score = round(best_score, 2)

    return best_solution


def get_squad_recommendation(
    store,  # noqa: ANN001
    projections: list,  # noqa: ANN001
    current_squad: list[int] | None = None,
    budget_remaining: float = 0.0,
) -> SquadRecommendation:
    """Generate a high-level squad recommendation.

    Compares current squad projections vs optimized squad projections.
    """
    # Optimize
    optimized = optimize_squad(store, projections, current_squad)

    if optimized is None or current_squad is None:
        return SquadRecommendation(
            current_squad_points=0,
            optimized_squad_points=0,
            improvement=0,
            suggested_transfers=[],
            suggested_formation="4-4-2",
            captain_recommendation=0,
            confidence=30,
            reasoning=["Insufficient data for recommendation"],
        )

    proj_map = {p.player_id: p for p in projections}

    # Current squad points
    current_pts = sum(
        proj_map[sid].projected_points
        for sid in current_squad
        if sid in proj_map
    )

    # Optimized squad points (starting XI)
    optimized_pts = sum(
        proj_map[sid].projected_points
        for sid in optimized.starting_xi
        if sid in proj_map
    )

    # Find transfers
    transfers = []
    out_ids = set(current_squad) - set(optimized.starting_xi + optimized.bench)
    in_ids = set(optimized.starting_xi + optimized.bench) - set(current_squad)

    for out_id in list(out_ids)[:3]:
        for in_id in list(in_ids)[:3]:
            out_proj = proj_map.get(out_id)
            in_proj = proj_map.get(in_id)
            if out_proj and in_proj:
                transfers.append({
                    "out": out_proj.web_name,
                    "in": in_proj.web_name,
                    "gain": round(in_proj.projected_points - out_proj.projected_points, 2),
                })

    reasoning = []
    if optimized_pts > current_pts:
        reasoning.append(f"Optimized squad projects {optimized_pts - current_pts:.1f} more points")
    if transfers:
        reasoning.append(f"Recommended {len(transfers)} transfer(s)")

    return SquadRecommendation(
        current_squad_points=round(current_pts, 2),
        optimized_squad_points=round(optimized_pts, 2),
        improvement=round(optimized_pts - current_pts, 2),
        suggested_transfers=transfers,
        suggested_formation=optimized.formation,
        captain_recommendation=optimized.captain,
        confidence=round(min(50 + len(transfers) * 10, 85), 1),
        reasoning=reasoning,
    )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_player_lookup(df: pd.DataFrame, proj_map: dict) -> dict:
    """Build a structured player lookup for the optimizer."""
    players = []
    for _, row in df.iterrows():
        pid = int(row.get("player_id", 0))
        proj = proj_map.get(pid)
        if proj is None:
            continue

        players.append({
            "player_id": pid,
            "web_name": str(row.get("web_name", "")),
            "position": str(row.get("position", "")),
            "team_id": int(row.get("team_id", 0) or 0),
            "price": float(row.get("price", 0) or 0),
            "projected_points": proj.projected_points,
            "confidence": proj.confidence,
        })

    return {
        "GKP": [p for p in players if p["position"] == "GKP"],
        "DEF": [p for p in players if p["position"] == "DEF"],
        "MID": [p for p in players if p["position"] == "MID"],
        "FWD": [p for p in players if p["position"] == "FWD"],
    }


def _generate_candidate_squad(
    players: dict,
    budget: float,
) -> SquadSolution | None:
    """Generate a random valid squad candidate."""
    import random

    try:
        # Pick formation randomly
        formation_name = random.choice(list(FORMATION_LIMITS.keys()))
        formation = FORMATION_LIMITS[formation_name]

        # Pick players
        gkp = random.sample(players["GKP"], min(2, len(players["GKP"])))
        def_ = random.sample(players["DEF"], min(formation["DEF"], len(players["DEF"])))
        mid = random.sample(players["MID"], min(formation["MID"], len(players["MID"])))
        fwd = random.sample(players["FWD"], min(formation["FWD"], len(players["FWD"])))

        # Check budget
        total_price = sum(p["price"] for p in gkp + def_ + mid + fwd)
        if total_price > budget:
            return None

        # Check team constraint (max 3 per team)
        all_players = gkp + def_ + mid + fwd
        team_counts = {}
        for p in all_players:
            team_counts[p["team_id"]] = team_counts.get(p["team_id"], 0) + 1
        if any(v > MAX_PER_TEAM for v in team_counts.values()):
            return None

        # Starting XI: best projected points per position
        starting_xi = []
        bench = []

        for pos, count in formation.items():
            pos_players = [p for p in all_players if p["position"] == pos]
            pos_players.sort(key=lambda x: x["projected_points"], reverse=True)
            starting_xi.extend([p["player_id"] for p in pos_players[:count]])
            bench.extend([p["player_id"] for p in pos_players[count:]])

        # GKP: best starts
        gkp_sorted = sorted(gkp, key=lambda x: x["projected_points"], reverse=True)
        starting_xi.append(gkp_sorted[0]["player_id"])
        bench.extend([p["player_id"] for p in gkp_sorted[1:]])

        # Captain: highest projected in starting XI
        captain = max(starting_xi, key=lambda pid: next(
            p["projected_points"] for p in all_players if p["player_id"] == pid
        ))
        vice_captain = max(
            [pid for pid in starting_xi if pid != captain],
            key=lambda pid: next(
                p["projected_points"] for p in all_players if p["player_id"] == pid
            ),
        )

        return SquadSolution(
            gkp=[p["player_id"] for p in gkp],
            def_=[p["player_id"] for p in def_],
            mid=[p["player_id"] for p in mid],
            fwd=[p["player_id"] for p in fwd],
            starting_xi=starting_xi,
            formation=formation_name,
            captain=captain,
            vice_captain=vice_captain,
            total_projected_points=0,
            total_price=round(total_price, 1),
            remaining_budget=round(budget - total_price, 1),
            avg_confidence=0,
            bench=bench,
            optimization_score=0,
            iterations=0,
        )
    except (ValueError, IndexError):
        return None


def _evaluate_squad(
    solution: SquadSolution,
    proj_map: dict,
) -> float:
    """Evaluate a squad solution. Higher is better."""
    if solution is None:
        return -1

    # Total projected points
    total_pts = sum(
        proj_map[pid].projected_points
        for pid in solution.starting_xi
        if pid in proj_map
    )

    # Captain multiplier (2x)
    if solution.captain in proj_map:
        total_pts += proj_map[solution.captain].projected_points

    # Budget efficiency
    budget_eff = (BUDGET - solution.total_price) / BUDGET * 10

    # Confidence bonus
    avg_conf = np.mean([
        proj_map[pid].confidence
        for pid in solution.starting_xi
        if pid in proj_map
    ]) if solution.starting_xi else 0

    return total_pts + budget_eff + avg_conf * 0.1


def _build_fallback_squad(
    players: dict,
    budget: float,
) -> SquadSolution | None:
    """Build a simple fallback squad (best per position)."""
    all_players = []
    for pos_list in players.values():
        all_players.extend(pos_list)

    # Sort by projected points, pick top 15 within budget
    all_players.sort(key=lambda x: x["projected_points"], reverse=True)

    squad = []
    total_price = 0
    team_counts = {}

    for p in all_players:
        if len(squad) >= SQUAD_SIZE:
            break
        if total_price + p["price"] > budget:
            continue
        if team_counts.get(p["team_id"], 0) >= MAX_PER_TEAM:
            continue
        squad.append(p)
        total_price += p["price"]
        team_counts[p["team_id"]] = team_counts.get(p["team_id"], 0) + 1

    if len(squad) < 11:
        return None

    gkp = [p["player_id"] for p in squad if p["position"] == "GKP"][:2]
    def_ = [p["player_id"] for p in squad if p["position"] == "DEF"][:5]
    mid = [p["player_id"] for p in squad if p["position"] == "MID"][:5]
    fwd = [p["player_id"] for p in squad if p["position"] == "FWD"][:3]

    starting_xi = gkp[:1] + def_[:4] + mid[:4] + fwd[:2]
    bench = gkp[1:] + def_[4:] + mid[4:] + fwd[2:]

    captain = max(starting_xi, key=lambda pid: next(
        (p["projected_points"] for p in squad if p["player_id"] == pid), 0
    ))

    return SquadSolution(
        gkp=gkp,
        def_=def_,
        mid=mid,
        fwd=fwd,
        starting_xi=starting_xi,
        formation="4-4-2",
        captain=captain,
        vice_captain=starting_xi[0] if starting_xi and starting_xi[0] != captain else captain,
        total_projected_points=0,
        total_price=round(total_price, 1),
        remaining_budget=round(budget - total_price, 1),
        avg_confidence=0,
        bench=bench,
        optimization_score=0,
        iterations=0,
    )
