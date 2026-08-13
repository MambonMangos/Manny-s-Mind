"""Tests for the squad optimizer's legal-squad construction.

Regression for: ``engines/squad_optimizer._generate_candidate_squad`` produced
12-player squads (2 GK + formation outfield) instead of a legal FPL 15
(2 GKP, 5 DEF, 5 MID, 3 FWD).
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from engines.squad_optimizer import (
    FORMATION_LIMITS,
    MAX_PER_TEAM,
    SQUAD_SIZE,
    _generate_candidate_squad,
    optimize_squad,
)


def _realistic_pool(seed: int = 42) -> pd.DataFrame:
    """A player pool with realistic FPL prices and club distribution.

    120 players: 20 GKP, 40 DEF, 40 MID, 20 FWD spread across 20 clubs
    (3 per position per club region), prices 4.0-8.0m (avg ~6m so a random
    15-man squad fits the £100m budget).
    """
    rng = np.random.default_rng(seed)
    rows = []
    n = 120
    pos = ["GKP"] * 20 + ["DEF"] * 40 + ["MID"] * 40 + ["FWD"] * 20
    team_ids = [(i % 20) + 1 for i in range(n)]
    rng.shuffle(team_ids)
    price = rng.uniform(4.0, 8.0, n).round(1)
    xpts = rng.uniform(1.5, 8.0, n).round(2)
    for i in range(n):
        rows.append({
            "player_id": i + 1,
            "web_name": f"P{i + 1}",
            "position": pos[i],
            "team_id": team_ids[i],
            "price": float(price[i]),
        })
    df = pd.DataFrame(rows)
    projections = [
        SimpleNamespace(player_id=int(r.player_id), projected_points=float(xpts[i]),
                        confidence=60.0)
        for i, (_, r) in enumerate(df.iterrows())
    ]
    return df, projections


def _store_and_projections(seed: int = 42):
    df, projections = _realistic_pool(seed)
    store = SimpleNamespace(df=df)
    return store, projections


def test_candidate_squad_is_legal_fifteen():
    """Every generated candidate is a legal 15-man FPL squad."""
    store, projections = _store_and_projections()
    proj_map = {p.player_id: p for p in projections}
    players = _generate_candidate_squad.__globals__["_build_player_lookup"](
        store.df, proj_map
    )

    generated = 0
    for _ in range(500):
        sol = _generate_candidate_squad(players, budget=100.0)
        if sol is None:
            continue
        generated += 1

        squad = sol.gkp + sol.def_ + sol.mid + sol.fwd
        assert len(squad) == SQUAD_SIZE
        assert len(set(squad)) == SQUAD_SIZE, "squad must contain unique players"
        assert len(sol.gkp) == 2
        assert len(sol.def_) == 5
        assert len(sol.mid) == 5
        assert len(sol.fwd) == 3
        assert len(sol.starting_xi) == 11
        assert len(sol.bench) == 4
        assert sol.total_price <= 100.0

        assert sol.formation in FORMATION_LIMITS
        need = FORMATION_LIMITS[sol.formation]
        xi_pos = {}
        for pid in sol.starting_xi:
            p = next(p for p in players["GKP"] + players["DEF"] + players["MID"] + players["FWD"]
                     if p["player_id"] == pid)
            xi_pos[p["position"]] = xi_pos.get(p["position"], 0) + 1
        assert xi_pos["GKP"] == 1
        assert xi_pos["DEF"] == need["DEF"]
        assert xi_pos["MID"] == need["MID"]
        assert xi_pos["FWD"] == need["FWD"]

        team_counts = {}
        for pid in squad:
            p = next(p for p in players["GKP"] + players["DEF"] + players["MID"] + players["FWD"]
                     if p["player_id"] == pid)
            team_counts[p["team_id"]] = team_counts.get(p["team_id"], 0) + 1
        assert all(v <= MAX_PER_TEAM for v in team_counts.values())

        assert sol.captain in sol.starting_xi
        assert sol.vice_captain in sol.starting_xi

    assert generated > 100, "most candidates should be generated with a realistic pool"


def test_optimize_squad_returns_legal_fifteen():
    """``optimize_squad`` must return a full 15-man squad, not 12."""
    store, projections = _store_and_projections()
    sol = optimize_squad(store, projections, n_iterations=500)
    assert sol is not None
    squad = sol.gkp + sol.def_ + sol.mid + sol.fwd
    assert len(squad) == SQUAD_SIZE
    assert len(set(squad)) == SQUAD_SIZE
    assert len(sol.gkp) == 2
    assert len(sol.def_) == 5
    assert len(sol.mid) == 5
    assert len(sol.fwd) == 3
    assert sol.total_price <= 100.0


def test_optimize_squad_includes_budget_headroom():
    """Optimized squads should spend within budget and leave >= 0."""
    store, projections = _store_and_projections(seed=7)
    sol = optimize_squad(store, projections, n_iterations=300)
    assert sol is not None
    assert sol.total_price <= 100.0
    assert sol.remaining_budget == round(100.0 - sol.total_price, 1)
