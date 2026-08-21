"""Squad Validator — deterministic FPL squad legality checker.

This is a pure, stateless service that receives squad state and returns
structured validation results.  It never calls the LLM, the database,
or any external service.

The validator answers one question: "Is this proposed squad legal under
FPL rules?"  It does not optimise, rank, or recommend — it validates.

Design principle:
    The LLM should never be the final authority on squad legality.
    This module is.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from utils.fpl_rules import (
    BUDGET,
    MAX_PER_TEAM,
    ValidationError,
    find_valid_formations,
    validate_budget,
    validate_squad_composition,
    validate_starting_xi,
)

# ── Squad representation ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Player:
    """Minimal player representation for validation.

    Only the fields needed for squad legality are required.
    Team data is included for the max-per-team constraint.
    """

    player_id: int
    web_name: str
    position: str  # "GKP", "DEF", "MID", "FWD"
    team_id: int
    price: float  # in millions (e.g. 9.5)


@dataclass(frozen=True)
class Squad:
    """A complete 15-player FPL squad with optional XI/bench assignment."""

    players: tuple[Player, ...]  # exactly 15

    @property
    def player_ids(self) -> list[int]:
        return [p.player_id for p in self.players]

    @property
    def positions(self) -> dict[int, str]:
        return {p.player_id: p.position for p in self.players}

    @property
    def prices(self) -> dict[int, float]:
        return {p.player_id: p.price for p in self.players}

    @property
    def team_ids(self) -> dict[int, int]:
        return {p.player_id: p.team_id for p in self.players}

    @property
    def total_cost(self) -> float:
        return round(sum(p.price for p in self.players), 1)

    @property
    def bank(self) -> float:
        return round(BUDGET - self.total_cost, 1)

    @property
    def position_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for p in self.players:
            counts[p.position] = counts.get(p.position, 0) + 1
        return counts

    @property
    def team_counts(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for p in self.players:
            counts[p.team_id] = counts.get(p.team_id, 0) + 1
        return counts


@dataclass(frozen=True)
class Lineup:
    """A starting XI + bench assignment within a squad."""

    starter_ids: tuple[int, ...]  # exactly 11
    bench_ids: tuple[int, ...]  # exactly 4

    @property
    def starter_set(self) -> set[int]:
        return set(self.starter_ids)

    @property
    def bench_set(self) -> set[int]:
        return set(self.bench_ids)


# ── Validation results ───────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Structured result of a squad validation check."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    squad_size: int = 0
    total_cost: float = 0.0
    bank: float = 0.0
    position_counts: dict[str, int] = field(default_factory=dict)
    team_counts: dict[int, int] = field(default_factory=dict)
    formation: str = ""

    def to_dict(self) -> dict:
        """Serialize for LLM consumption."""
        return {
            "valid": self.valid,
            "squad_size": self.squad_size,
            "total_cost": self.total_cost,
            "bank": self.bank,
            "position_counts": self.position_counts,
            "formation": self.formation,
            "errors": [{"code": e.code, "message": e.message} for e in self.errors],
        }


@dataclass
class TransferValidationResult:
    """Result of validating a complete transfer proposal."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    resulting_squad: Squad | None = None
    resulting_bank: float = 0.0
    transfers_in: int = 0
    transfers_out: int = 0
    cost_change: float = 0.0

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "transfers_in": self.transfers_in,
            "transfers_out": self.transfers_out,
            "resulting_bank": self.resulting_bank,
            "cost_change": self.cost_change,
            "errors": [{"code": e.code, "message": e.message} for e in self.errors],
        }


# ── Core validation functions ────────────────────────────────────────────────


def validate_squad(squad: Squad) -> ValidationResult:
    """Validate a complete squad against all FPL composition rules.

    Checks:
    - Exactly 15 players
    - No duplicate players
    - Position counts: 2 GKP, 5 DEF, 5 MID, 3 FWD
    - Budget: total cost <= £100m
    - Max 3 players per team

    Does NOT check starting XI (use validate_lineup for that).
    """
    errors: list[ValidationError] = []

    # Squad size and composition
    errors.extend(validate_squad_composition(squad.player_ids, squad.positions))

    # Budget
    errors.extend(validate_budget(squad.total_cost))

    # Max per team
    for team_id, count in squad.team_counts.items():
        if count > MAX_PER_TEAM:
            errors.append(ValidationError(
                "INVALID_MAX_PER_TEAM",
                f"Team {team_id} has {count} players, maximum is {MAX_PER_TEAM}.",
            ))

    # Detect formation
    formation = ""
    if not errors:
        # If squad is valid, detect which formations the starting XI could use
        # (actual formation depends on lineup selection)
        pc = squad.position_counts
        formation_options = find_valid_formations(pc)
        if formation_options:
            formation = formation_options[0]

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        squad_size=len(squad.players),
        total_cost=squad.total_cost,
        bank=squad.bank,
        position_counts=squad.position_counts,
        team_counts=squad.team_counts,
        formation=formation,
    )


def validate_lineup(squad: Squad, lineup: Lineup) -> ValidationResult:
    """Validate a starting XI and bench assignment within a squad.

    Checks everything validate_squad checks, plus:
    - Starting XI has exactly 11 players
    - Bench has exactly 4 players
    - No overlap between XI and bench
    - XI + bench = full squad
    - Formation legality (min defenders, midfielders, forwards)
    """
    # First validate the squad itself
    result = validate_squad(squad)

    # Then validate the lineup partition
    lineup_errors = validate_starting_xi(
        list(lineup.starter_ids),
        list(lineup.bench_ids),
        squad.player_ids,
        squad.positions,
    )
    result.errors.extend(lineup_errors)

    # Detect formation from starting XI
    if not lineup_errors:
        starter_positions: dict[str, int] = {}
        for pid in lineup.starter_ids:
            pos = squad.positions.get(pid, "UNK")
            starter_positions[pos] = starter_positions.get(pos, 0) + 1
        formation_options = find_valid_formations(starter_positions)
        if formation_options:
            result.formation = formation_options[0]
        else:
            result.formation = "INVALID"

    result.valid = len(result.errors) == 0
    return result


def validate_transfer_proposal(
    current_squad: Squad,
    sold_ids: list[int],
    bought_players: list[Player],
    protected_ids: set[int] | None = None,
) -> TransferValidationResult:
    """Validate a complete transfer proposal by constructing and checking
    the resulting squad.

    This is the most important validation function.  It does NOT validate
    transfers individually — it validates the final state.

    Parameters
    ----------
    current_squad : the user's current 15-player squad
    sold_ids : player IDs being removed
    bought_players : Player objects being added
    protected_ids : player IDs that cannot be sold

    Returns
    -------
    TransferValidationResult with the resulting squad if valid.
    """
    errors: list[ValidationError] = []

    # 1. Protected players
    if protected_ids:
        sold_protected = set(sold_ids) & protected_ids
        if sold_protected:
            errors.append(ValidationError(
                "INVALID_TRANSFER",
                f"Cannot sell protected player(s): "
                f"{', '.join(str(p) for p in sold_protected)}.",
            ))

    # 2. All sold players must be in current squad
    current_ids = set(current_squad.player_ids)
    not_owned = set(sold_ids) - current_ids
    if not_owned:
        errors.append(ValidationError(
            "INVALID_TRANSFER",
            f"Player(s) not in squad: {not_owned}.",
        ))

    # 3. Cannot buy a player already owned (after sales)
    remaining_ids = current_ids - set(sold_ids)
    bought_ids = {p.player_id for p in bought_players}
    already_owned = bought_ids & remaining_ids
    if already_owned:
        errors.append(ValidationError(
            "INVALID_TRANSFER",
            f"Already own player(s) being bought: {already_owned}.",
        ))

    # 4. Must sell and buy the same number
    if len(sold_ids) != len(bought_players):
        errors.append(ValidationError(
            "INVALID_TRANSFER",
            f"Selling {len(sold_ids)} but buying {len(bought_players)} "
            f"players — must be equal to maintain 15-player squad.",
        ))

    # 5. Budget check
    total_out = sum(current_squad.prices.get(pid, 0) for pid in sold_ids)
    total_in = sum(p.price for p in bought_players)
    new_total = current_squad.total_cost - total_out + total_in
    new_bank = BUDGET - new_total

    if new_total > BUDGET + 1e-6:
        errors.append(ValidationError(
            "OVER_BUDGET",
            f"Resulting squad costs £{new_total:.1f}m, budget is £{BUDGET:.1f}m "
            f"(would need £{new_total - BUDGET:.1f}m more).",
        ))

    # 6. Construct resulting squad
    remaining_players = [p for p in current_squad.players if p.player_id not in set(sold_ids)]
    resulting_players = remaining_players + list(bought_players)
    resulting_squad = Squad(players=tuple(resulting_players))

    # 7. Validate resulting squad composition
    composition_errors = validate_squad(resulting_squad)
    errors.extend(composition_errors.errors)

    # 8. Max per team in resulting squad
    for team_id, count in resulting_squad.team_counts.items():
        if count > MAX_PER_TEAM:
            errors.append(ValidationError(
                "INVALID_MAX_PER_TEAM",
                f"Resulting squad has {count} players from team {team_id}, "
                f"maximum is {MAX_PER_TEAM}.",
            ))

    return TransferValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        resulting_squad=resulting_squad if not errors else None,
        resulting_bank=round(new_bank, 1),
        transfers_in=len(bought_players),
        transfers_out=len(sold_ids),
        cost_change=round(total_in - total_out, 1),
    )
