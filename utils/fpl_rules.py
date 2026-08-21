"""FPL Rules — single source of truth for all squad constraints.

Every module that enforces FPL rules must import from here.  No other file
should define its own copy of these values.

This module is deterministic, stateless, and has zero side effects.  It
defines constants and pure functions — nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Squad composition ────────────────────────────────────────────────────────

SQUAD_SIZE: int = 15
BUDGET: float = 100.0  # £100m
MAX_PER_TEAM: int = 3

POSITION_SLOTS: dict[str, int] = {
    "GKP": 2,
    "DEF": 5,
    "MID": 5,
    "FWD": 3,
}

# ── Starting XI constraints ──────────────────────────────────────────────────

STARTING_XI_SIZE: int = 11
BENCH_SIZE: int = 4  # SQUAD_SIZE - STARTING_XI_SIZE

STARTING_MINIMUMS: dict[str, int] = {
    "GKP": 1,
    "DEF": 3,
    "MID": 2,
    "FWD": 1,
}

# ── Formations ───────────────────────────────────────────────────────────────
# Each formation defines (DEF, MID, FWD) counts for the starting outfield.
# GKP is always 1.  Total must equal STARTING_XI_SIZE.

FORMATIONS: dict[str, dict[str, int]] = {
    "3-4-3": {"GKP": 1, "DEF": 3, "MID": 4, "FWD": 3},
    "3-5-2": {"GKP": 1, "DEF": 3, "MID": 5, "FWD": 2},
    "4-3-3": {"GKP": 1, "DEF": 4, "MID": 3, "FWD": 3},
    "4-4-2": {"GKP": 1, "DEF": 4, "MID": 4, "FWD": 2},
    "4-5-1": {"GKP": 1, "DEF": 4, "MID": 5, "FWD": 1},
    "5-4-1": {"GKP": 1, "DEF": 5, "MID": 4, "FWD": 1},
    "5-3-2": {"GKP": 1, "DEF": 5, "MID": 3, "FWD": 2},
}

# ── Transfer rules ───────────────────────────────────────────────────────────

HIT_COST_PER_TRANSFER: int = 4
MAX_FREE_TRANSFERS: int = 1  # per gameweek baseline
MAX_SAVED_TRANSFERS: int = 5

# ── Chip rules ───────────────────────────────────────────────────────────────
# One chip per gameweek — no exceptions.  Free Hit cannot be played in GW1.

CHIP_NAMES: tuple[str, ...] = ("wildcard", "free_hit", "bboost", "3xc")
FIRST_HALF_CHIP_DEADLINE_GW: int = 19

# ── FPL element_type → position label ───────────────────────────────────────

ELEMENT_TYPE_TO_POSITION: dict[int, str] = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
POSITION_TO_ELEMENT_TYPE: dict[str, int] = {v: k for k, v in ELEMENT_TYPE_TO_POSITION.items()}

# ── Validation error codes ───────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationError:
    """A single validation failure."""

    code: str
    message: str


# ── Pure validation functions ────────────────────────────────────────────────


def validate_squad_composition(player_ids: list[int], positions: dict[int, str]) -> list[ValidationError]:
    """Validate that a list of player IDs forms a legal FPL squad.

    Parameters
    ----------
    player_ids : list of exactly 15 player IDs
    positions : mapping of player_id → position label ("GKP"/"DEF"/"MID"/"FWD")

    Returns
    -------
    Empty list if valid; list of ValidationError otherwise.
    """
    errors: list[ValidationError] = []

    if len(player_ids) != SQUAD_SIZE:
        errors.append(ValidationError(
            "INVALID_SQUAD_SIZE",
            f"Squad has {len(player_ids)} players, must have exactly {SQUAD_SIZE}.",
        ))

    if len(set(player_ids)) != len(player_ids):
        errors.append(ValidationError(
            "INVALID_DUPLICATE_PLAYER",
            "Squad contains duplicate players.",
        ))

    for pid in player_ids:
        if pid not in positions:
            errors.append(ValidationError(
                "INVALID_PLAYER_POSITION",
                f"Player {pid} has no known position.",
            ))

    # Count by position
    pos_counts: dict[str, int] = {}
    for pid in player_ids:
        pos = positions.get(pid, "UNK")
        pos_counts[pos] = pos_counts.get(pos, 0) + 1

    for pos, required in POSITION_SLOTS.items():
        actual = pos_counts.get(pos, 0)
        if actual != required:
            errors.append(ValidationError(
                "INVALID_POSITION_COUNTS",
                f"{pos}: {actual} players, must have exactly {required}.",
            ))

    return errors


def validate_budget(total_cost: float, budget: float = BUDGET) -> list[ValidationError]:
    """Validate that total squad cost is within budget."""
    errors: list[ValidationError] = []
    if total_cost > budget + 1e-6:
        errors.append(ValidationError(
            "OVER_BUDGET",
            f"Squad costs £{total_cost:.1f}m, budget is £{budget:.1f}m.",
        ))
    return errors


def validate_starting_xi(
    starter_ids: list[int],
    bench_ids: list[int],
    squad_ids: list[int],
    positions: dict[int, str],
) -> list[ValidationError]:
    """Validate that a starting XI and bench partition the squad legally.

    Parameters
    ----------
    starter_ids : exactly 11 player IDs in the starting XI
    bench_ids : exactly 4 player IDs on the bench
    squad_ids : the full 15-player squad
    positions : mapping of player_id → position label

    Returns
    -------
    Empty list if valid; list of ValidationError otherwise.
    """
    errors: list[ValidationError] = []

    squad_set = set(squad_ids)
    starter_set = set(starter_ids)
    bench_set = set(bench_ids)

    if len(starter_ids) != STARTING_XI_SIZE:
        errors.append(ValidationError(
            "INVALID_STARTING_XI",
            f"Starting XI has {len(starter_ids)} players, must have exactly {STARTING_XI_SIZE}.",
        ))

    if len(bench_ids) != BENCH_SIZE:
        errors.append(ValidationError(
            "INVALID_BENCH",
            f"Bench has {len(bench_ids)} players, must have exactly {BENCH_SIZE}.",
        ))

    if starter_set & bench_set:
        errors.append(ValidationError(
            "INVALID_OVERLAP",
            f"Players appear in both starting XI and bench: {starter_set & bench_set}.",
        ))

    if starter_set | bench_set != squad_set:
        missing = squad_set - (starter_set | bench_set)
        extra = (starter_set | bench_set) - squad_set
        parts = []
        if missing:
            parts.append(f"missing from both: {missing}")
        if extra:
            parts.append(f"not in squad: {extra}")
        errors.append(ValidationError(
            "INVALID_PARTITION",
            f"Starting XI + bench must equal squad. {'; '.join(parts)}.",
        ))

    # Check starting XI formation legality
    starter_positions: dict[str, int] = {}
    for pid in starter_ids:
        pos = positions.get(pid, "UNK")
        starter_positions[pos] = starter_positions.get(pos, 0) + 1

    for pos, min_count in STARTING_MINIMUMS.items():
        actual = starter_positions.get(pos, 0)
        if actual < min_count:
            errors.append(ValidationError(
                "INVALID_FORMATION",
                f"Starting XI has {actual} {pos}, minimum is {min_count}.",
            ))

    return errors


def find_valid_formations(starter_positions: dict[str, int]) -> list[str]:
    """Given a starting XI's position counts, return matching formation names."""
    matches = []
    for name, formation in FORMATIONS.items():
        if all(starter_positions.get(pos, 0) == count for pos, count in formation.items()):
            matches.append(name)
    return matches


def validate_transfers(
    current_squad_ids: list[int],
    sold_ids: list[int],
    bought_ids: list[int],
    current_positions: dict[int, str],
    current_prices: dict[int, float],
    bought_prices: dict[int, float],
    bought_positions: dict[int, str],
    bank: float,
    protected_ids: set[int] | None = None,
) -> list[ValidationError]:
    """Validate a proposed set of transfers against the full squad.

    Constructs the resulting squad and validates it holistically.
    Does NOT validate individual transfers in isolation.

    Parameters
    ----------
    current_squad_ids : the 15 player IDs currently owned
    sold_ids : player IDs being sold
    bought_ids : player IDs being bought
    current_positions : current squad player_id → position
    current_prices : current squad player_id → price
    bought_prices : bought player_id → price
    bought_positions : bought player_id → position
    bank : current bank balance
    protected_ids : player IDs that cannot be sold (e.g. Bruno, Haaland)

    Returns
    -------
    Empty list if valid; list of ValidationError otherwise.
    """
    errors: list[ValidationError] = []

    # 1. Protected players cannot be sold
    if protected_ids:
        sold_protected = set(sold_ids) & protected_ids
        if sold_protected:
            errors.append(ValidationError(
                "INVALID_TRANSFER",
                f"Protected player(s) cannot be sold: {sold_protected}.",
            ))

    # 2. Cannot buy a player already in the squad (after sales)
    remaining_after_sales = set(current_squad_ids) - set(sold_ids)
    already_owned = set(bought_ids) & remaining_after_sales
    if already_owned:
        errors.append(ValidationError(
            "INVALID_TRANSFER",
            f"Already own player(s) being bought: {already_owned}.",
        ))

    # 3. Cannot sell a player not in the squad
    not_owned = set(sold_ids) - set(current_squad_ids)
    if not_owned:
        errors.append(ValidationError(
            "INVALID_TRANSFER",
            f"Trying to sell player(s) not in squad: {not_owned}.",
        ))

    # 4. Must sell and buy the same number (to maintain 15)
    if len(sold_ids) != len(bought_ids):
        errors.append(ValidationError(
            "INVALID_TRANSFER",
            f"Selling {len(sold_ids)} but buying {len(bought_ids)} — squad size must stay at 15.",
        ))

    # 5. Construct resulting squad
    resulting_ids = list(remaining_after_sales) + list(bought_ids)

    # 6. Budget check
    total_in = sum(bought_prices.get(pid, 0) for pid in bought_ids)
    total_out = sum(current_prices.get(pid, 0) for pid in sold_ids)
    errors.extend(validate_budget(100.0 - (100.0 - bank - total_out + total_in)))

    # More precise: total squad cost = current_total - sold + bought
    current_total = sum(current_prices.get(pid, 0) for pid in current_squad_ids)
    new_total = current_total - total_out + total_in
    errors.extend(validate_budget(new_total))

    # 7. Position counts
    resulting_positions: dict[int, str] = {}
    for pid in remaining_after_sales:
        if pid in current_positions:
            resulting_positions[pid] = current_positions[pid]
    for pid in bought_ids:
        if pid in bought_positions:
            resulting_positions[pid] = bought_positions[pid]

    errors.extend(validate_squad_composition(resulting_ids, resulting_positions))

    return errors


def validate_chip_plan(assignments: dict[str, int | None]) -> list[ValidationError]:
    """Validate a chip schedule: chip_name → target gameweek (or None).

    Enforces the official FPL chip constraints:
    - At most ONE chip per gameweek (CHIP_DOUBLE_BOOKED)
    - Free Hit cannot be played in GW1 (FREE_HIT_GW1_ILLEGAL)

    Parameters
    ----------
    assignments : mapping of chip name to the gameweek it will be played in.
        Chips with a ``None`` target are ignored (not being played).

    Returns
    -------
    Empty list if valid; list of ValidationError otherwise.
    """
    errors: list[ValidationError] = []

    scheduled: dict[int, list[str]] = {}
    for chip, gw in assignments.items():
        if gw is None:
            continue
        if chip not in CHIP_NAMES:
            errors.append(ValidationError(
                "UNKNOWN_CHIP",
                f"Unknown chip name {chip!r}; expected one of {CHIP_NAMES}.",
            ))
            continue
        scheduled.setdefault(gw, []).append(chip)

    for gw, chips in sorted(scheduled.items()):
        if len(chips) > 1:
            errors.append(ValidationError(
                "CHIP_DOUBLE_BOOKED",
                f"GW{gw} has {len(chips)} chips assigned ({', '.join(sorted(chips))}). "
                f"Only one chip can be played per gameweek.",
            ))

    fh_gw = assignments.get("free_hit")
    if fh_gw == 1:
        errors.append(ValidationError(
            "FREE_HIT_GW1_ILLEGAL",
            "Free Hit cannot be played in Gameweek 1.",
        ))

    return errors


def format_validation_errors(errors: list[ValidationError]) -> str:
    """Format validation errors into a user-readable message."""
    if not errors:
        return "All checks passed."
    lines = ["**Squad validation failed:**", ""]
    for err in errors:
        lines.append(f"- {err.message}")
    return "\n".join(lines)
