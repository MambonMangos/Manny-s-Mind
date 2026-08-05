"""Chip Strategist — Section 4 of the Assistant Manager.

Tracks chip availability, identifies optimal windows (DGW, BGW, fixture
swings), and recommends when to play each chip.
"""

from __future__ import annotations

import pandas as pd

from services.assistant_manager.models import (
    ChipRecommendation,
    PlayerAssessment,
    SquadEvaluation,
)
from engines.fixture_engine import DIFFICULTY_LABELS


def _check_double_gameweeks(
    fixtures: list[dict], team_id: int, gameweeks: list[int]
) -> list[int]:
    """Identify gameweeks where a team plays twice (DGW)."""
    gw_fixture_count: dict[int, int] = {}
    for f in fixtures:
        if f["event"] not in gameweeks:
            continue
        if f["team_h"] == team_id or f["team_a"] == team_id:
            gw_fixture_count[f["event"]] = gw_fixture_count.get(f["event"], 0) + 1
    return [gw for gw, count in gw_fixture_count.items() if count >= 2]


def _check_blank_gameweeks(
    fixtures: list[dict], team_id: int, gameweeks: list[int]
) -> list[int]:
    """Identify gameweeks where a team plays zero times (BGW)."""
    team_gws: set[int] = set()
    for f in fixtures:
        if f["event"] in gameweeks:
            if f["team_h"] == team_id or f["team_a"] == team_id:
                team_gws.add(f["event"])

    return [gw for gw in gameweeks if gw not in team_gws]


def evaluate_chips(
    squad_eval: SquadEvaluation,
    chip_states: dict[str, dict],
    fixtures: list[dict],
    team_id: int,
    upcoming_gameweeks: list[int] | None = None,
) -> list[ChipRecommendation]:
    """Evaluate all four chips and return recommendations.

    Parameters
    ----------
    squad_eval : current squad evaluation
    chip_states : dict of chip_name → {"used": bool, "used_in_gameweek": int|None}
    fixtures : all fixtures
    team_id : user's team ID
    upcoming_gameweeks : list of upcoming GW numbers to analyze
    """
    if upcoming_gameweeks is None:
        upcoming_gameweeks = list(range(1, 39))

    recommendations: list[ChipRecommendation] = []

    # --- Wildcard ---
    wc_used = chip_states.get("wildcard", {}).get("used", False)
    wc_rec = ChipRecommendation(
        chip_name="wildcard",
        chip_label="Wildcard",
        available=not wc_used,
        used=wc_used,
        should_play=False,
        confidence=0,
        reasoning="",
    )

    if wc_used:
        wc_rec.reasoning = "Wildcard already used."
    else:
        # Wildcard recommended if many weaknesses or injuries
        n_weak = len(squad_eval.weaknesses)
        n_injury = len(squad_eval.injuries)
        n_rotation = len(squad_eval.rotation_risks)

        if n_weak >= 4 or n_injury >= 3:
            wc_rec.should_play = True
            wc_rec.confidence = min(50 + n_weak * 5 + n_injury * 8, 90)
            wc_rec.reasoning = (
                f"Wildcard recommended: {n_weak} weaknesses, "
                f"{n_injury} injuries/doubts, {n_rotation} rotation risks. "
                f"A squad overhaul is likely to yield significant gains."
            )
        elif n_weak >= 2 or n_injury >= 2:
            wc_rec.confidence = 35
            wc_rec.reasoning = (
                f"Wildcard not urgent but worth considering: "
                f"{n_weak} weaknesses, {n_injury} injuries. "
                f"Monitor for 1–2 more gameweeks."
            )
        else:
            wc_rec.confidence = 15
            wc_rec.reasoning = (
                "Squad looks solid. No need for a wildcard unless planning "
                "major restructuring for a fixture swing."
            )

    recommendations.append(wc_rec)

    # --- Free Hit ---
    fh_used = chip_states.get("free_hit", {}).get("used", False)
    fh_rec = ChipRecommendation(
        chip_name="free_hit",
        chip_label="Free Hit",
        available=not fh_used,
        used=fh_used,
        should_play=False,
        confidence=0,
        reasoning="",
    )

    if fh_used:
        fh_rec.reasoning = "Free Hit already used."
    else:
        # Free Hit is best in BGW or for a one-week fixture swing
        bgws = _check_blank_gameweeks(fixtures, team_id, upcoming_gameweeks[:10])
        if bgws:
            fh_rec.should_play = True
            fh_rec.best_gameweek = bgws[0]
            fh_rec.confidence = 75
            fh_rec.reasoning = (
                f"Free Hit recommended for GW{bgws[0]} — blank gameweek detected. "
                f"Use it to field a full squad when many teams don't play."
            )
        else:
            fh_rec.confidence = 20
            fh_rec.reasoning = (
                "No blank gameweeks detected in the near future. "
                "Save Free Hit for a BGW or extreme fixture swing."
            )

    recommendations.append(fh_rec)

    # --- Bench Boost ---
    bb_used = chip_states.get("bboost", {}).get("used", False)
    bb_rec = ChipRecommendation(
        chip_name="bboost",
        chip_label="Bench Boost",
        available=not bb_used,
        used=bb_used,
        should_play=False,
        confidence=0,
        reasoning="",
    )

    if bb_used:
        bb_rec.reasoning = "Bench Boost already used."
    else:
        # Bench Boost is best in DGW when bench players also have double fixtures
        dws = _check_double_gameweeks(fixtures, team_id, upcoming_gameweeks[:10])

        bench_players = [p for p in squad_eval.players if p.minutes_played < 90] or []
        if bench_players and all(p.projected_points > 0 for p in bench_players):
            bench_quality = sum(p.projected_points for p in bench_players) / len(bench_players)
        else:
            bench_quality = (
                sum(p.form for p in bench_players) / len(bench_players)
                if bench_players else 0
            )

        if dws:
            bb_rec.should_play = True
            bb_rec.best_gameweek = dws[0]
            bb_rec.confidence = 70
            bb_rec.reasoning = (
                f"Bench Boost recommended for GW{dws[0]} — double gameweek. "
                f"Bench players have extra fixtures, maximizing chip value."
            )
        elif bench_quality >= 3.0:
            bb_rec.confidence = 40
            bb_rec.reasoning = (
                f"Bench is performing well (avg form {bench_quality:.1f}). "
                f"Consider Bench Boost when a DGW arrives."
            )
        else:
            bb_rec.confidence = 15
            bb_rec.reasoning = (
                "Bench is weak — no DGW detected. "
                "Strengthen bench before playing Bench Boost."
            )

    recommendations.append(bb_rec)

    # --- Triple Captain ---
    tc_used = chip_states.get("3xc", {}).get("used", False)
    tc_rec = ChipRecommendation(
        chip_name="3xc",
        chip_label="Triple Captain",
        available=not tc_used,
        used=tc_used,
        should_play=False,
        confidence=0,
        reasoning="",
    )

    if tc_used:
        tc_rec.reasoning = "Triple Captain already used."
    else:
        # Triple Captain is best in DGW with a premium captain option
        dws = _check_double_gameweeks(fixtures, team_id, upcoming_gameweeks[:10])
        top_captains = sorted(squad_eval.players, key=lambda p: p.form, reverse=True)[:3]
        best_form = top_captains[0].form if top_captains else 0

        if dws and best_form >= 6.0:
            tc_rec.should_play = True
            tc_rec.best_gameweek = dws[0]
            tc_rec.confidence = 72
            tc_rec.reasoning = (
                f"Triple Captain recommended for GW{dws[0]} — double gameweek with "
                f"a strong captain candidate ({top_captains[0].web_name}, "
                f"form {best_form}). Three fixtures maximize the chip."
            )
        elif best_form >= 7.0:
            tc_rec.confidence = 40
            tc_rec.reasoning = (
                f"{top_captains[0].web_name} is in exceptional form ({best_form}), "
                f"but no DGW detected. Consider TC if a DGW aligns with their fixtures."
            )
        else:
            tc_rec.confidence = 10
            tc_rec.reasoning = (
                "No exceptional captain candidate or DGW detected. "
                "Save Triple Captain for optimal conditions."
            )

    recommendations.append(tc_rec)

    return recommendations
