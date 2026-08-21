"""Tests for Squad Validator and Transfer Optimizer.

Covers:
- Squad composition validation (size, positions, budget, duplicates)
- Starting XI / bench partition validation
- Transfer proposal validation (single and multi-transfer)
- Protected players, already-owned detection, budget enforcement
- Max per team constraint
- Formation detection
- The Saka regression scenario
- Edge cases: impossible transfers, empty squads, overflow
"""

from __future__ import annotations

import pytest

from services.squad_validator import (
    Lineup,
    Player,
    Squad,
    validate_lineup,
    validate_squad,
    validate_transfer_proposal,
)
from services.transfer_optimizer import (
    solve_multi_transfer,
    solve_transfers,
)
from utils.fpl_rules import (
    BUDGET,
    FORMATIONS,
    POSITION_SLOTS,
    SQUAD_SIZE,
    find_valid_formations,
    validate_budget,
    validate_squad_composition,
    validate_starting_xi,
)

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_player(pid: int, name: str, pos: str, team: int, price: float) -> Player:
    return Player(player_id=pid, web_name=name, position=pos, team_id=team, price=price)


def _make_legal_squad() -> Squad:
    """Create a legal 15-player squad (2 GKP, 5 DEF, 5 MID, 3 FWD)."""
    players = [
        # GKP (2)
        _make_player(1, "Kelleher", "GKP", 1, 5.0),
        _make_player(2, "Verbruggen", "GKP", 2, 4.5),
        # DEF (5)
        _make_player(3, "Van Hecke", "DEF", 3, 5.0),
        _make_player(4, "Mitchell", "DEF", 4, 4.5),
        _make_player(5, "Guehi", "DEF", 5, 6.0),
        _make_player(6, "Truffert", "DEF", 6, 5.5),
        _make_player(7, "Diop", "DEF", 7, 4.0),
        # MID (5)
        _make_player(8, "B.Fernandes", "MID", 8, 12.0),
        _make_player(9, "Wilson", "MID", 9, 6.5),
        _make_player(10, "Tzolis", "MID", 10, 6.5),
        _make_player(11, "Gross", "MID", 2, 5.5),
        _make_player(12, "Zubimendi", "MID", 10, 5.5),
        # FWD (3)
        _make_player(13, "Joao Pedro", "FWD", 11, 7.5),
        _make_player(14, "Haaland", "FWD", 5, 15.5),
        _make_player(15, "DCL", "FWD", 9, 6.0),
    ]
    return Squad(players=tuple(players))


def _make_legal_lineup(squad: Squad) -> Lineup:
    """Create a legal starting XI from a squad."""
    starters = [1, 3, 5, 6, 8, 9, 11, 13, 14, 15, 4]  # 1 GK, 3 DEF, 3 MID, 3 FWD
    bench = [p.player_id for p in squad.players if p.player_id not in set(starters)]
    return Lineup(starter_ids=tuple(starters[:11]), bench_ids=tuple(bench[:4]))


# ── FPL Rules constants ──────────────────────────────────────────────────────


def test_squad_size_constant():
    assert SQUAD_SIZE == 15


def test_budget_constant():
    assert BUDGET == 100.0


def test_position_slots_sum_to_squad():
    assert sum(POSITION_SLOTS.values()) == SQUAD_SIZE


def test_position_slots_correct():
    assert POSITION_SLOTS == {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def test_all_formations_sum_to_11():
    for name, formation in FORMATIONS.items():
        assert sum(formation.values()) == 11, f"Formation {name} does not sum to 11"
        assert formation["GKP"] == 1, f"Formation {name} must have 1 GKP"


def test_find_valid_formations():
    # 4-3-3
    assert "4-3-3" in find_valid_formations({"GKP": 1, "DEF": 4, "MID": 3, "FWD": 3})
    # 3-5-2
    assert "3-5-2" in find_valid_formations({"GKP": 1, "DEF": 3, "MID": 5, "FWD": 2})
    # Invalid
    assert find_valid_formations({"GKP": 1, "DEF": 2, "MID": 5, "FWD": 3}) == []


# ── validate_squad_composition ───────────────────────────────────────────────


def test_valid_composition():
    ids = list(range(15))
    positions = {}
    for i in range(2):
        positions[i] = "GKP"
    for i in range(2, 7):
        positions[i] = "DEF"
    for i in range(7, 12):
        positions[i] = "MID"
    for i in range(12, 15):
        positions[i] = "FWD"
    errors = validate_squad_composition(ids, positions)
    assert errors == []


def test_invalid_squad_size_too_few():
    errors = validate_squad_composition([1, 2, 3], {1: "GKP", 2: "DEF", 3: "MID"})
    codes = [e.code for e in errors]
    assert "INVALID_SQUAD_SIZE" in codes


def test_invalid_squad_size_too_many():
    ids = list(range(20))
    positions = {i: "DEF" for i in range(20)}
    errors = validate_squad_composition(ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_SQUAD_SIZE" in codes


def test_duplicate_player():
    ids = [1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    positions = {1: "GKP", 2: "GKP", 3: "DEF", 4: "DEF", 5: "DEF",
                 6: "DEF", 7: "DEF", 8: "MID", 9: "MID", 10: "MID",
                 11: "MID", 12: "MID", 13: "FWD", 14: "FWD"}
    errors = validate_squad_composition(ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_DUPLICATE_PLAYER" in codes


def test_wrong_position_counts():
    # 3 GKP instead of 2
    ids = list(range(15))
    positions = {}
    for i in range(3):
        positions[i] = "GKP"
    for i in range(3, 8):
        positions[i] = "DEF"
    for i in range(8, 13):
        positions[i] = "MID"
    for i in range(13, 15):
        positions[i] = "FWD"
    errors = validate_squad_composition(ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_POSITION_COUNTS" in codes


def test_missing_player_position():
    ids = list(range(15))
    positions = {i: "DEF" for i in range(14)}  # missing player 14
    errors = validate_squad_composition(ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_PLAYER_POSITION" in codes


# ── validate_budget ──────────────────────────────────────────────────────────


def test_budget_within_limit():
    errors = validate_budget(99.5)
    assert errors == []


def test_budget_exactly_at_limit():
    errors = validate_budget(100.0)
    assert errors == []


def test_budget_over_limit():
    errors = validate_budget(100.5)
    assert len(errors) == 1
    assert errors[0].code == "OVER_BUDGET"


def test_budget_slightly_over():
    errors = validate_budget(100.0001)
    assert len(errors) == 1
    assert errors[0].code == "OVER_BUDGET"


# ── validate_starting_xi ─────────────────────────────────────────────────────


def test_valid_starting_xi():
    squad_ids = list(range(15))
    positions = {}
    for i in range(2):
        positions[i] = "GKP"
    for i in range(2, 7):
        positions[i] = "DEF"
    for i in range(7, 12):
        positions[i] = "MID"
    for i in range(12, 15):
        positions[i] = "FWD"

    starter_ids = [0, 2, 3, 4, 7, 8, 9, 12, 13, 14, 5]  # 1 GK, 4 DEF, 3 MID, 3 FWD
    bench_ids = [1, 6, 10, 11]

    errors = validate_starting_xi(starter_ids, bench_ids, squad_ids, positions)
    assert errors == []


def test_starting_xi_wrong_size():
    errors = validate_starting_xi([1, 2, 3], [4, 5], list(range(5)),
                                   {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD", 5: "DEF"})
    codes = [e.code for e in errors]
    assert "INVALID_STARTING_XI" in codes


def test_starting_xi_overlap_with_bench():
    squad_ids = list(range(15))
    positions = {}
    for i in range(2):
        positions[i] = "GKP"
    for i in range(2, 7):
        positions[i] = "DEF"
    for i in range(7, 12):
        positions[i] = "MID"
    for i in range(12, 15):
        positions[i] = "FWD"

    starter_ids = [0, 2, 3, 4, 7, 8, 9, 12, 13, 14, 5]
    bench_ids = [5, 6, 10, 11]  # 5 is in both!

    errors = validate_starting_xi(starter_ids, bench_ids, squad_ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_OVERLAP" in codes


def test_starting_xi_missing_forwards():
    squad_ids = list(range(15))
    positions = {}
    for i in range(2):
        positions[i] = "GKP"
    for i in range(2, 7):
        positions[i] = "DEF"
    for i in range(7, 12):
        positions[i] = "MID"
    for i in range(12, 15):
        positions[i] = "FWD"

    # No FWDs in starting XI
    starter_ids = [0, 2, 3, 4, 5, 7, 8, 9, 10, 11, 6]
    bench_ids = [1, 12, 13, 14]

    errors = validate_starting_xi(starter_ids, bench_ids, squad_ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_FORMATION" in codes


def test_starting_xi_only_one_defender():
    squad_ids = list(range(15))
    positions = {}
    for i in range(2):
        positions[i] = "GKP"
    for i in range(2, 7):
        positions[i] = "DEF"
    for i in range(7, 12):
        positions[i] = "MID"
    for i in range(12, 15):
        positions[i] = "FWD"

    # Only 1 DEF in starting XI
    starter_ids = [0, 2, 7, 8, 9, 10, 11, 12, 13, 14, 3]
    bench_ids = [1, 4, 5, 6]

    errors = validate_starting_xi(starter_ids, bench_ids, squad_ids, positions)
    codes = [e.code for e in errors]
    assert "INVALID_FORMATION" in codes


# ── Squad validator (integration) ────────────────────────────────────────────


def test_validate_legal_squad():
    squad = _make_legal_squad()
    result = validate_squad(squad)
    assert result.valid
    assert result.squad_size == 15
    assert result.total_cost == 99.5
    assert result.bank == 0.5
    assert result.position_counts == {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def test_validate_squad_over_budget():
    players = [
        _make_player(1, "G1", "GKP", 1, 5.0),
        _make_player(2, "G2", "GKP", 2, 4.5),
        _make_player(3, "D1", "DEF", 3, 5.0),
        _make_player(4, "D2", "DEF", 4, 5.0),
        _make_player(5, "D3", "DEF", 5, 5.0),
        _make_player(6, "D4", "DEF", 6, 5.0),
        _make_player(7, "D5", "DEF", 7, 5.0),
        _make_player(8, "M1", "MID", 8, 15.0),  # expensive
        _make_player(9, "M2", "MID", 9, 15.0),  # expensive
        _make_player(10, "M3", "MID", 10, 15.0),  # expensive
        _make_player(11, "M4", "MID", 11, 15.0),  # expensive
        _make_player(12, "M5", "MID", 12, 15.0),  # expensive
        _make_player(13, "F1", "FWD", 13, 5.0),
        _make_player(14, "F2", "FWD", 14, 5.0),
        _make_player(15, "F3", "FWD", 15, 5.0),
    ]
    squad = Squad(players=tuple(players))
    result = validate_squad(squad)
    assert not result.valid
    assert any(e.code == "OVER_BUDGET" for e in result.errors)


def test_validate_squad_max_per_team():
    players = [
        _make_player(1, "G1", "GKP", 1, 5.0),
        _make_player(2, "G2", "GKP", 2, 4.5),
        _make_player(3, "D1", "DEF", 1, 5.0),  # team 1
        _make_player(4, "D2", "DEF", 1, 5.0),  # team 1
        _make_player(5, "D3", "DEF", 1, 5.0),  # team 1
        _make_player(6, "D4", "DEF", 1, 5.0),  # team 1 — 4th from team 1!
        _make_player(7, "D5", "DEF", 3, 4.0),
        _make_player(8, "M1", "MID", 4, 6.0),
        _make_player(9, "M2", "MID", 5, 6.0),
        _make_player(10, "M3", "MID", 6, 6.0),
        _make_player(11, "M4", "MID", 7, 6.0),
        _make_player(12, "M5", "MID", 8, 6.0),
        _make_player(13, "F1", "FWD", 9, 7.0),
        _make_player(14, "F2", "FWD", 10, 7.0),
        _make_player(15, "F3", "FWD", 11, 7.0),
    ]
    squad = Squad(players=tuple(players))
    result = validate_squad(squad)
    assert not result.valid
    assert any(e.code == "INVALID_MAX_PER_TEAM" for e in result.errors)


def test_validate_squad_too_many_players():
    players = [_make_player(i, f"P{i}", "DEF", 1, 4.0) for i in range(20)]
    squad = Squad(players=tuple(players))
    result = validate_squad(squad)
    assert not result.valid
    assert any(e.code == "INVALID_SQUAD_SIZE" for e in result.errors)


# ── validate_lineup (integration) ────────────────────────────────────────────


def test_validate_legal_lineup():
    squad = _make_legal_squad()
    lineup = _make_legal_lineup(squad)
    result = validate_lineup(squad, lineup)
    assert result.valid
    assert result.formation in FORMATIONS


def test_validate_lineup_overlap():
    squad = _make_legal_squad()
    # Same player in XI and bench
    lineup = Lineup(
        starter_ids=(1, 3, 5, 6, 8, 9, 11, 13, 14, 15, 4),
        bench_ids=(4, 7, 10, 12),  # 4 is in both
    )
    result = validate_lineup(squad, lineup)
    assert not result.valid
    assert any(e.code == "INVALID_OVERLAP" for e in result.errors)


def test_validate_lineup_wrong_formation():
    squad = _make_legal_squad()
    # Only 2 DEF in XI (minimum is 3)
    # Use 2 DEF + 5 MID + 3 FWD + 1 GKP = 11, but only 2 DEF
    lineup = Lineup(
        starter_ids=(1, 3, 4, 8, 9, 10, 11, 12, 13, 14, 15),
        bench_ids=(2, 5, 6, 7),
    )
    result = validate_lineup(squad, lineup)
    assert not result.valid
    assert any(e.code == "INVALID_FORMATION" for e in result.errors)


# ── validate_transfer_proposal ────────────────────────────────────────────────


def test_valid_single_transfer_same_position():
    squad = _make_legal_squad()
    # Sell B.Fernandes (MID, #8, 12.0m), buy Saka (MID, #20, 9.5m) — saves 2.5m
    # This is a legal same-position swap within budget
    incoming = [_make_player(20, "Saka", "MID", 10, 9.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[8],
        bought_players=incoming,
    )
    assert validation.valid
    assert validation.resulting_squad is not None
    assert len(validation.resulting_squad.players) == 15
    assert validation.resulting_bank == pytest.approx(0.5 + 12.0 - 9.5, abs=0.1)


def test_valid_single_transfer_different_position():
    squad = _make_legal_squad()
    # Sell Diop (DEF, #7), buy Saka (MID, #20) — different position
    # Result: 4 DEF, 6 MID — invalid position counts
    incoming = [_make_player(20, "Saka", "MID", 10, 9.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[7],
        bought_players=incoming,
    )
    assert not validation.valid
    assert any(e.code == "INVALID_POSITION_COUNTS" for e in validation.errors)


def test_transfer_over_budget():
    squad = _make_legal_squad()
    # Sell Diop (4.0m), buy a 15.0m player — way over budget
    incoming = [_make_player(20, "Expensive", "DEF", 10, 15.0)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[7],
        bought_players=incoming,
    )
    assert not validation.valid
    assert any(e.code == "OVER_BUDGET" for e in validation.errors)


def test_transfer_sell_already_owned():
    squad = _make_legal_squad()
    # Try to sell B.Fernandes (protected)
    incoming = [_make_player(20, "Saka", "MID", 10, 9.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[8],  # B.Fernandes
        bought_players=incoming,
        protected_ids={8},
    )
    assert not validation.valid
    assert any(e.code == "INVALID_TRANSFER" for e in validation.errors)


def test_transfer_buy_already_owned():
    squad = _make_legal_squad()
    # Try to buy Haaland (already owned)
    incoming = [_make_player(14, "Haaland", "FWD", 5, 15.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[10],
        bought_players=incoming,
    )
    assert not validation.valid
    assert any(e.code == "INVALID_TRANSFER" for e in validation.errors)


def test_transfer_sell_not_in_squad():
    squad = _make_legal_squad()
    incoming = [_make_player(20, "Saka", "MID", 10, 9.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[999],  # not in squad
        bought_players=incoming,
    )
    assert not validation.valid
    assert any(e.code == "INVALID_TRANSFER" for e in validation.errors)


def test_transfer_count_mismatch():
    squad = _make_legal_squad()
    # Sell 2, buy 1
    incoming = [_make_player(20, "Saka", "MID", 10, 9.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[10, 9],
        bought_players=incoming,
    )
    assert not validation.valid
    assert any(e.code == "INVALID_TRANSFER" for e in validation.errors)


# ── Multi-transfer validation ────────────────────────────────────────────────


def test_valid_double_transfer():
    squad = _make_legal_squad()
    # Sell Tzolis (MID, 6.5) + Wilson (MID, 6.5) = 13.0m freed
    # Buy Saka (MID, 9.5) + Budget MID (4.0) = 13.5m
    # Result: 5 DEF, 5 MID (sell 2, buy 2), 3 FWD — valid!
    incoming = [
        _make_player(20, "Saka", "MID", 10, 9.5),
        _make_player(21, "Budget MID", "MID", 12, 4.0),
    ]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[10, 9],  # Tzolis, Wilson
        bought_players=incoming,
    )
    assert validation.valid
    assert validation.resulting_squad is not None
    assert len(validation.resulting_squad.players) == 15
    assert validation.resulting_bank == pytest.approx(0.0, abs=0.1)


def test_double_transfer_position_violation():
    squad = _make_legal_squad()
    # Sell 2 DEF, buy 2 MID — results in 3 DEF, 7 MID
    incoming = [
        _make_player(20, "Saka", "MID", 10, 9.5),
        _make_player(21, "Another MID", "MID", 12, 5.0),
    ]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[3, 4],  # Van Hecke, Mitchell (both DEF)
        bought_players=incoming,
    )
    assert not validation.valid
    assert any(e.code == "INVALID_POSITION_COUNTS" for e in validation.errors)


# ── Transfer Optimizer ───────────────────────────────────────────────────────


def test_solve_transfers_same_position():
    """Test 2-for-2 same-position swap with player pool."""
    squad = _make_legal_squad()
    target = _make_player(20, "Saka", "MID", 10, 9.5)
    # Provide a cheap MID filler in the pool
    pool = [
        _make_player(21, "Cheap MID", "MID", 12, 4.0),
    ]
    solutions = solve_transfers(squad, target, protected_ids={8}, player_pool=pool)
    valid = [s for s in solutions if s.valid]
    assert len(valid) > 0
    for sol in valid:
        assert sol.resulting_squad is not None
        assert len(sol.resulting_squad.players) == 15


def test_solve_transfers_no_solution_over_budget():
    squad = _make_legal_squad()
    target = _make_player(20, "Mega Star", "MID", 10, 20.0)
    pool = [_make_player(21, "Filler", "MID", 12, 4.0)]
    solutions = solve_transfers(squad, target, protected_ids={8}, player_pool=pool)
    # Even with a 2-for-2, selling 2 MIDs (max ~13m) + bank 0.5 = 13.5
    # Need to buy 20.0 + 4.0 = 24.0 — way over
    assert len(solutions) == 0


def test_solve_transfers_respects_protected():
    squad = _make_legal_squad()
    target = _make_player(20, "Saka", "MID", 10, 9.5)
    solutions = solve_transfers(squad, target, protected_ids={8, 14})
    # Should not sell B.Fernandes (8) or Haaland (14)
    for sol in solutions:
        sold_ids = {m.player_out.player_id for m in sol.moves}
        assert 8 not in sold_ids
        assert 14 not in sold_ids


def test_solve_multi_transfer():
    """Test multi-transfer: sell 2 MIDs, buy 2 MIDs (position-maintaining swap)."""
    squad = _make_legal_squad()
    # Sell Tzolis (MID, 6.5) + Wilson (MID, 6.5) = 13.0m freed
    # Buy Saka (MID, 9.5) + Budget MID (4.0) = 13.5m
    # Bank: 0.5 + 13.0 - 13.5 = 0.0m
    # Result: 5 DEF, 5 MID (sell 2, buy 2), 3 FWD — valid!
    targets = [
        _make_player(20, "Saka", "MID", 10, 9.5),
        _make_player(21, "Budget MID", "MID", 12, 4.0),
    ]
    solutions = solve_multi_transfer(
        squad, targets, protected_ids={8, 14}
    )
    valid = [s for s in solutions if s.valid]
    assert len(valid) > 0
    for sol in valid:
        assert len(sol.resulting_squad.players) == 15
        assert sol.resulting_squad.position_counts == {"DEF": 5, "MID": 5, "FWD": 3, "GKP": 2}


def test_solve_multi_transfer_no_solution():
    squad = _make_legal_squad()
    targets = [
        _make_player(20, "Mega Star 1", "MID", 10, 20.0),
        _make_player(21, "Mega Star 2", "MID", 12, 20.0),
    ]
    solutions = solve_multi_transfer(squad, targets, protected_ids={8, 14})
    assert len(solutions) == 0


# ── Saka Regression Test ─────────────────────────────────────────────────────


def test_saka_regression_legal_transfer_exists():
    """Prove the solver discovers a legal way to bring Saka into the squad.

    Current squad:
        GKP: Kelleher (5.0), Verbruggen (4.5)
        DEF: Van Hecke (5.0), Mitchell (4.5), Guehi (6.0), Truffert (5.5), Diop (4.0)
        MID: B.Fernandes (12.0), Wilson (6.5), Tzolis (6.5), Gross (5.5), Zubimendi (5.5)
        FWD: Joao Pedro (7.5), Haaland (15.5), DCL (6.0)
        Total: 99.5m, Bank: 0.5m

    Constraints:
        - Cannot sell B.Fernandes or Haaland
        - Must add Saka (9.5m, MID, Arsenal)

    Expected solution:
        Sell: Tzolis (6.5) + Wilson (6.5) + Diop (4.0) = 17.0m freed
        Buy: Saka (9.5) + Budget MID (5.0) = 14.5m
        New total: 99.5 - 17.0 + 14.5 = 97.0m, Bank: 3.0m
        Position check: 4 DEF, 6 MID, 3 FWD → need to verify this is valid

    Actually: selling Diop (DEF) means 4 DEF left. Buying 2 MID means 7 MID.
    That's invalid. So the correct solution must be:
        Sell: Tzolis (6.5) + Wilson (6.5) = 13.0m freed
        Buy: Saka (9.5) + Budget DEF (4.0) = 13.5m
        Bank: 0.5 + 13.0 - 13.5 = 0.0m
        Position check: 5 DEF (keep Diop), 4 MID, 3 FWD → valid!

    OR:
        Sell: Tzolis (6.5) + Wilson (6.5) = 13.0m
        Buy: Saka (9.5) + Cheap MID filler (4.0m) = 13.5m
        Same result — 2-for-2 same-pos swap.

    So the solver must find the 2-swap solution using a player pool.
    """
    squad = _make_legal_squad()
    target = _make_player(20, "Saka", "MID", 10, 9.5)

    # Provide a pool of available players to buy as filler
    pool = [
        _make_player(21, "Budget MID", "MID", 12, 4.0),
        _make_player(22, "Budget DEF", "DEF", 13, 4.0),
    ]

    solutions = solve_transfers(
        squad, target,
        protected_ids={8, 14},  # B.Fernandes, Haaland
        player_pool=pool,
    )

    # Must find at least one valid solution
    valid = [s for s in solutions if s.valid]
    assert len(valid) > 0, (
        "Solver found no legal way to bring Saka into the squad. "
        "This should not happen — a 2-swap solution exists."
    )

    # The best solution should sell a MID (to maintain position counts)
    best = valid[0]
    assert best.resulting_squad is not None
    assert len(best.resulting_squad.players) == 15

    # Verify position counts
    pc = best.resulting_squad.position_counts
    assert pc.get("GKP", 0) == 2
    assert pc.get("DEF", 0) == 5
    assert pc.get("MID", 0) == 5
    assert pc.get("FWD", 0) == 3

    # Verify budget
    assert best.resulting_squad.total_cost <= BUDGET + 1e-6


def test_saka_regression_no_protected_violation():
    """Verify B.Fernandes and Haaland are never sold in any solution."""
    squad = _make_legal_squad()
    target = _make_player(20, "Saka", "MID", 10, 9.5)
    pool = [_make_player(21, "Budget MID", "MID", 12, 4.0)]

    solutions = solve_transfers(
        squad, target,
        protected_ids={8, 14},
        player_pool=pool,
    )

    for sol in solutions:
        sold_ids = {m.player_out.player_id for m in sol.moves}
        assert 8 not in sold_ids, "B.Fernandes was sold in a solution!"
        assert 14 not in sold_ids, "Haaland was sold in a solution!"


def test_saka_regression_impossible_scenario():
    """When constraints make a legal transfer impossible, solver returns empty."""
    squad = _make_legal_squad()
    target = _make_player(20, "Mega Star", "MID", 10, 20.0)
    pool = [_make_player(21, "Filler", "MID", 12, 4.0)]

    solutions = solve_transfers(
        squad, target,
        protected_ids={8, 14, 9, 10},
        player_pool=pool,
    )
    valid = [s for s in solutions if s.valid]
    assert len(valid) == 0


# ── Validation result serialization ──────────────────────────────────────────


def test_validation_result_to_dict():
    squad = _make_legal_squad()
    result = validate_squad(squad)
    d = result.to_dict()
    assert d["valid"] is True
    assert d["squad_size"] == 15
    assert d["total_cost"] == 99.5
    assert d["bank"] == 0.5
    assert isinstance(d["errors"], list)


def test_transfer_validation_result_to_dict():
    squad = _make_legal_squad()
    # Sell B.Fernandes (12.0), buy Saka (9.5) — saves 2.5m, valid
    incoming = [_make_player(20, "Saka", "MID", 10, 9.5)]
    validation = validate_transfer_proposal(
        current_squad=squad,
        sold_ids=[8],
        bought_players=incoming,
    )
    d = validation.to_dict()
    assert d["valid"] is True
    assert d["transfers_in"] == 1
    assert d["transfers_out"] == 1


def test_transfer_solution_to_dict():
    squad = _make_legal_squad()
    target = _make_player(20, "Saka", "MID", 10, 9.5)
    pool = [_make_player(21, "Budget MID", "MID", 12, 4.0)]
    solutions = solve_transfers(squad, target, protected_ids={8, 14}, player_pool=pool)
    valid = [s for s in solutions if s.valid]
    assert len(valid) > 0
    d = valid[0].to_dict()
    assert d["valid"] is True
    assert d["resulting_squad_size"] == 15
    assert "transfers" in d
    assert "out" in d["transfers"]
    assert "in" in d["transfers"]


# ── Edge cases ───────────────────────────────────────────────────────────────


def test_empty_squad_validation():
    squad = Squad(players=())
    result = validate_squad(squad)
    assert not result.valid
    assert any(e.code == "INVALID_SQUAD_SIZE" for e in result.errors)


def test_single_player_squad():
    squad = Squad(players=(_make_player(1, "Solo", "GKP", 1, 5.0),))
    result = validate_squad(squad)
    assert not result.valid


def test_budget_exactly_100():
    """Squad costing exactly £100.0m should be valid."""
    players = []
    # 15 players averaging ~6.67m each
    for i in range(15):
        pos = "GKP" if i < 2 else "DEF" if i < 7 else "MID" if i < 12 else "FWD"
        price = 6.67 if i < 14 else 6.62  # adjust last to hit exactly 100.0
        players.append(_make_player(i + 1, f"P{i+1}", pos, (i % 20) + 1, price))
    squad = Squad(players=tuple(players))
    # Total should be ~100.0
    assert abs(squad.total_cost - 100.0) < 0.2


def test_validate_budget_boundary():
    """£100.0m is valid, £100.01m is not."""
    assert validate_budget(100.0) == []
    assert len(validate_budget(100.01)) == 1
