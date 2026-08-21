"""Tests for chip-plan validation — one chip per gameweek, enforced.

The chip strategist must never recommend two chips for the same gameweek,
and the Free Hit must never be recommended for GW1.  The rules authority is
``utils.fpl_rules.validate_chip_plan``; the strategist must emit plans that
pass it.
"""

from __future__ import annotations

from services.assistant_manager.chip_strategist import evaluate_chips
from services.assistant_manager.models import PlayerAssessment, SquadEvaluation
from utils.fpl_rules import validate_chip_plan

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_player(
    player_id: int = 1,
    web_name: str = "Bruno",
    form: float = 7.5,
    minutes_played: int = 500,
    projected_points: float = 6.0,
) -> PlayerAssessment:
    return PlayerAssessment(
        player_id=player_id,
        web_name=web_name,
        team_id=16,
        team_short="MUN",
        position="MID",
        price=8.5,
        total_points=150,
        form=form,
        xgi_per_90=0.5,
        value_score=1.0,
        minutes_played=minutes_played,
        minutes_fraction=0.9,
        status="a",
        news="",
        selected_by_percent=25.0,
        cost_change_start=0,
    )


def make_squad(players: list[PlayerAssessment] | None = None) -> SquadEvaluation:
    return SquadEvaluation(
        overall_rating=7.0,
        total_value=99.5,
        bank=1.0,
        free_transfers=1,
        saved_transfers=0,
        players=players or [make_player()],
    )


def dgw_fixtures(team_id: int = 12345, gw: int = 6) -> list[dict]:
    """Two fixtures for the user's team in the same gameweek (a DGW).

    Defaults to GW6 because ``evaluate_chips`` only analyzes the first 10
    gameweeks of its window by default.
    """
    return [
        {"event": gw, "team_h": team_id, "team_a": 1},
        {"event": gw, "team_a": team_id, "team_h": 2},
    ]


def unused_chips() -> dict[str, dict]:
    return {
        "wildcard": {"used": False, "used_in_gameweek": None},
        "free_hit": {"used": False, "used_in_gameweek": None},
        "bboost": {"used": False, "used_in_gameweek": None},
        "3xc": {"used": False, "used_in_gameweek": None},
    }


# ---------------------------------------------------------------------------
# validate_chip_plan (rules authority)
# ---------------------------------------------------------------------------


def test_validate_chip_plan_accepts_legal_plan():
    assert validate_chip_plan({
        "wildcard": 5,
        "bboost": 6,
        "free_hit": 12,
        "3xc": None,
    }) == []


def test_validate_chip_plan_accepts_all_none():
    assert validate_chip_plan({chip: None for chip in (
        "wildcard", "free_hit", "bboost", "3xc")}) == []


def test_validate_chip_plan_rejects_double_booking():
    errors = validate_chip_plan({"bboost": 24, "3xc": 24})
    codes = [e.code for e in errors]
    assert "CHIP_DOUBLE_BOOKED" in codes
    double = next(e for e in errors if e.code == "CHIP_DOUBLE_BOOKED")
    assert "GW24" in double.message
    assert "bboost" in double.message and "3xc" in double.message


def test_validate_chip_plan_rejects_free_hit_in_gw1():
    errors = validate_chip_plan({"free_hit": 1})
    assert any(e.code == "FREE_HIT_GW1_ILLEGAL" for e in errors)


def test_validate_chip_plan_rejects_unknown_chip():
    errors = validate_chip_plan({"mystery_chip": 5})
    assert any(e.code == "UNKNOWN_CHIP" for e in errors)


# ---------------------------------------------------------------------------
# evaluate_chips — the strategist must emit legal plans
# ---------------------------------------------------------------------------


def _active_plans(recommendations):
    return {
        rec.chip_name: rec.best_gameweek
        for rec in recommendations
        if rec.should_play and rec.best_gameweek is not None
    }


def test_chip_plan_never_double_books():
    """DGW present: BB and TC both want it — exactly one may keep it."""
    squad = make_squad([
        make_player(player_id=1, web_name="Bruno", form=7.5),
        make_player(player_id=2, web_name="Hojlund", form=6.0, minutes_played=60),
    ])
    recs = evaluate_chips(squad, unused_chips(), dgw_fixtures(), 12345)

    plans = _active_plans(recs)
    gws = list(plans.values())
    assert len(gws) == len(set(gws)), f"Double-booked plan emitted: {plans}"

    # And the plan passes the rules authority
    assert validate_chip_plan(plans) == []


def test_conflict_keeps_higher_confidence_chip():
    """TC (conf 72) beats BB (conf 70) on the same DGW; loser is demoted."""
    squad = make_squad([
        make_player(player_id=1, web_name="Bruno", form=7.5),
        make_player(player_id=2, web_name="Hojlund", form=6.0, minutes_played=60),
    ])
    recs = evaluate_chips(squad, unused_chips(), dgw_fixtures(), 12345)

    by_name = {rec.chip_name: rec for rec in recs}
    tc, bb = by_name["3xc"], by_name["bboost"]

    assert tc.should_play is True
    assert tc.best_gameweek == 6
    assert bb.should_play is False
    assert "only one chip per gameweek" in bb.reasoning.lower()
    assert "3xc" in bb.reasoning or "Triple Captain" in bb.reasoning


def test_free_hit_never_recommended_for_gw1():
    """Even if a blank GW1 appears in the fixture list, FH must not target it."""
    fixtures = [
        {"event": 1, "team_h": 999, "team_a": 998},  # user's team not involved → BGW
        *dgw_fixtures(gw=24),
    ]
    squad = make_squad()
    recs = evaluate_chips(squad, unused_chips(), fixtures, 12345)

    fh = next(rec for rec in recs if rec.chip_name == "free_hit")
    assert not (fh.should_play and fh.best_gameweek == 1)


def test_no_dgw_produces_no_conflicts():
    """Normal fixture list: nothing to resolve, plan stays valid."""
    fixtures = [{"event": gw, "team_h": 1, "team_a": 2} for gw in range(1, 11)]
    squad = make_squad()
    recs = evaluate_chips(squad, unused_chips(), fixtures, 12345)

    plans = _active_plans(recs)
    assert validate_chip_plan(plans) == []


def test_used_chips_are_never_part_of_the_plan():
    squad = make_squad()
    chips = unused_chips()
    chips["bboost"]["used"] = True
    chips["3xc"]["used"] = True
    recs = evaluate_chips(squad, chips, dgw_fixtures(), 12345)

    by_name = {rec.chip_name: rec for rec in recs}
    assert by_name["bboost"].should_play is False
    assert by_name["3xc"].should_play is False
    assert validate_chip_plan(_active_plans(recs)) == []
