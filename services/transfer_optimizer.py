"""Transfer Optimizer — constraint-aware transfer solver.

Generates legal transfer combinations that satisfy ALL FPL rules before
optimising for expected points.  The solver:

1. Takes the user's request (e.g. "get Saka", "improve midfield")
2. Generates candidate transfer sets
3. Validates each candidate against FPL rules
4. Ranks valid candidates by V3 projected points gain
5. Returns only validated, legal recommendations

Design principle:
    CONSTRAINTS FIRST, THEN OPTIMISE.
    A recommendation is not a recommendation until the resulting squad
    has been proven legal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from itertools import combinations

from services.squad_validator import (
    Player,
    Squad,
    TransferValidationResult,
    validate_transfer_proposal,
)
from utils.fpl_rules import BUDGET

logger = logging.getLogger(__name__)


# -- Transfer solution --------------------------------------------------------


@dataclass
class TransferMove:
    """A single player swap."""
    player_out: Player
    player_in: Player


@dataclass
class TransferSolution:
    """A validated, legal transfer plan with projected impact."""
    moves: list[TransferMove]
    resulting_squad: Squad
    resulting_bank: float
    total_cost_change: float
    projected_points_change: float
    hit_cost: int
    net_points_change: float
    validation: TransferValidationResult
    reasoning: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return self.validation.valid

    @property
    def formation(self) -> str:
        from utils.fpl_rules import find_valid_formations
        pc = self.resulting_squad.position_counts
        options = find_valid_formations(pc)
        return options[0] if options else "INVALID"

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "transfers": {
                "out": [
                    {"name": m.player_out.web_name, "price": m.player_out.price,
                     "position": m.player_out.position}
                    for m in self.moves
                ],
                "in": [
                    {"name": m.player_in.web_name, "price": m.player_in.price,
                     "position": m.player_in.position}
                    for m in self.moves
                ],
            },
            "resulting_squad_size": len(self.resulting_squad.players),
            "resulting_bank": self.resulting_bank,
            "total_cost_change": self.total_cost_change,
            "projected_points_change": self.projected_points_change,
            "hit_cost": self.hit_cost,
            "net_points_change": self.net_points_change,
            "formation": self.formation,
            "errors": [
                {"code": e.code, "message": e.message}
                for e in self.validation.errors
            ],
        }


# -- Solver -------------------------------------------------------------------


def solve_transfers(
    current_squad: Squad,
    target_player: Player,
    protected_ids: set[int] | None = None,
    player_pool: list[Player] | None = None,
    max_solutions: int = 5,
) -> list[TransferSolution]:
    """Find legal ways to fit a target player into the squad.

    Tries 1-for-1 swaps first (same position preferred).  If no valid
    1-for-1 exists (e.g. over budget), expands to 2-for-2 combinations
    using ``player_pool`` to find filler players.

    Parameters
    ----------
    current_squad : the user's current 15-player squad
    target_player : the player to bring in
    protected_ids : player IDs that cannot be sold
    player_pool : available players to buy (for 2-for-2 filler search)
    max_solutions : maximum number of valid solutions to return
    """
    if protected_ids is None:
        protected_ids = set()
    if player_pool is None:
        player_pool = []

    solutions: list[TransferSolution] = []

    if target_player.player_id in current_squad.player_ids:
        return []

    sellable = [
        p for p in current_squad.players
        if p.player_id not in protected_ids
    ]
    same_pos = [p for p in sellable if p.position == target_player.position]
    diff_pos = [p for p in sellable if p.position != target_player.position]

    # === 1-for-1 swaps ===
    for out_player in same_pos + diff_pos:
        moves = [TransferMove(player_out=out_player, player_in=target_player)]
        validation = validate_transfer_proposal(
            current_squad=current_squad,
            sold_ids=[out_player.player_id],
            bought_players=[target_player],
            protected_ids=protected_ids,
        )
        if not validation.valid:
            continue
        result_squad = validation.resulting_squad
        if result_squad is None:
            continue
        hit_cost = 0
        reasoning = []
        price_diff = target_player.price - out_player.price
        if price_diff > 0:
            reasoning.append(f"Costs {price_diff:.1f}m more than {out_player.web_name}.")
        elif price_diff < 0:
            reasoning.append(f"Saves {abs(price_diff):.1f}m vs {out_player.web_name}.")
        if out_player.position != target_player.position:
            reasoning.append(f"Position change: {out_player.position} to {target_player.position}.")
        solution = TransferSolution(
            moves=moves, resulting_squad=result_squad,
            resulting_bank=validation.resulting_bank,
            total_cost_change=validation.cost_change,
            projected_points_change=0.0, hit_cost=hit_cost,
            net_points_change=-hit_cost, validation=validation,
            reasoning=reasoning,
        )
        solutions.append(solution)

    if solutions:
        solutions.sort(key=lambda s: s.resulting_bank, reverse=True)
        return solutions[:max_solutions]

    # === 2-for-2 same-position swaps ===
    if player_pool and same_pos:
        squad_ids = set(current_squad.player_ids)
        buyable = [
            p for p in player_pool
            if p.position == target_player.position
            and p.player_id not in squad_ids
            and p.player_id != target_player.player_id
        ]
        for out_combo in combinations(same_pos, 2):
            total_out = sum(p.price for p in out_combo)
            out_ids = [p.player_id for p in out_combo]
            for filler in buyable:
                total_in = target_player.price + filler.price
                if current_squad.bank + total_out < total_in - 1e-6:
                    continue
                validation = validate_transfer_proposal(
                    current_squad=current_squad,
                    sold_ids=out_ids,
                    bought_players=[target_player, filler],
                    protected_ids=protected_ids,
                )
                if not validation.valid:
                    continue
                result_squad = validation.resulting_squad
                if result_squad is None:
                    continue
                hit_cost = 4
                solution = TransferSolution(
                    moves=[
                        TransferMove(player_out=out_combo[0], player_in=target_player),
                        TransferMove(player_out=out_combo[1], player_in=filler),
                    ],
                    resulting_squad=result_squad,
                    resulting_bank=validation.resulting_bank,
                    total_cost_change=validation.cost_change,
                    projected_points_change=0.0,
                    hit_cost=hit_cost,
                    net_points_change=-hit_cost,
                    validation=validation,
                    reasoning=[f"Sell 2 to afford {target_player.web_name}. Hit: -{hit_cost}."],
                )
                solutions.append(solution)
                if len(solutions) >= max_solutions:
                    break
            if solutions:
                break

    solutions.sort(key=lambda s: s.resulting_bank, reverse=True)
    return solutions[:max_solutions]


def solve_multi_transfer(
    current_squad: Squad,
    target_players: list[Player],
    protected_ids: set[int] | None = None,
    max_solutions: int = 5,
) -> list[TransferSolution]:
    """Find legal ways to bring in multiple target players.

    For each combination of sellable players (same count as targets),
    validates the complete resulting squad.
    """
    if protected_ids is None:
        protected_ids = set()

    n_targets = len(target_players)
    if n_targets == 0:
        return []

    owned_ids = set(current_squad.player_ids)
    for tp in target_players:
        if tp.player_id in owned_ids:
            return []

    target_ids = [tp.player_id for tp in target_players]
    if len(set(target_ids)) != len(target_ids):
        return []

    sellable = [
        p for p in current_squad.players
        if p.player_id not in protected_ids
    ]

    solutions: list[TransferSolution] = []

    for out_combo in combinations(sellable, n_targets):
        out_ids = [p.player_id for p in out_combo]
        total_out = sum(current_squad.prices.get(pid, 0) for pid in out_ids)
        total_in = sum(tp.price for tp in target_players)
        new_total = current_squad.total_cost - total_out + total_in
        if new_total > BUDGET + 1e-6:
            continue

        validation = validate_transfer_proposal(
            current_squad=current_squad,
            sold_ids=out_ids,
            bought_players=list(target_players),
            protected_ids=protected_ids,
        )
        if not validation.valid:
            continue
        result_squad = validation.resulting_squad
        if result_squad is None:
            continue

        moves = [
            TransferMove(player_out=out_combo[i], player_in=target_players[i])
            for i in range(n_targets)
        ]
        hit_cost = max(0, (n_targets - 1)) * 4

        solution = TransferSolution(
            moves=moves,
            resulting_squad=result_squad,
            resulting_bank=validation.resulting_bank,
            total_cost_change=validation.cost_change,
            projected_points_change=0.0,
            hit_cost=hit_cost,
            net_points_change=-hit_cost,
            validation=validation,
            reasoning=[
                (
                    f"Swap {n_targets} to bring in "
                    f"{', '.join(tp.web_name for tp in target_players)}."
                )
            ],
        )
        solutions.append(solution)

    solutions.sort(key=lambda s: s.total_cost_change)
    return solutions[:max_solutions]
