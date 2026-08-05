"""Squad Evaluator — Section 1 of the Assistant Manager.

Evaluates the current squad: strengths, weaknesses, injuries, rotation risks,
fixture quality, price changes, form, and per-player ratings.
"""

from __future__ import annotations

import pandas as pd

from services.assistant_manager.models import (
    FixtureInfo,
    PlayerAssessment,
    SquadEvaluation,
)
from engines.fixture_engine import DIFFICULTY_LABELS, get_fixture_info, build_fixture_map
from engines.value_engine import compute_player_rating, compute_position_averages


def _classify_player(
    row: pd.Series,
    avg_diff_3: float,
    avg_diff_6: float,
    position_avg: dict[str, float],
) -> tuple[list[str], list[str], list[str], list[str]]:
    """Return (strengths, weaknesses, risks, opportunities) flags."""
    strengths = []
    weaknesses = []
    risks = []
    opportunities = []

    form = float(row.get("form", 0) or 0)
    xgi = float(row.get("xgi_per_90", 0) or 0)
    vs = float(row.get("value_score", 0) or 0)
    minutes = int(row.get("minutes", 0) or 0)
    price_change = int(row.get("cost_change_start", 0) or 0)
    status = str(row.get("status", "a") or "a")
    news = str(row.get("news", "") or "")
    transfers_in = int(row.get("transfers_in_event", 0) or 0)
    transfers_out = int(row.get("transfers_out_event", 0) or 0)
    selected = float(row.get("selected_by_percent", 0) or 0)
    total_points = int(row.get("total_points", 0) or 0)
    pos = str(row.get("position", "?"))
    pos_avg = position_avg.get(pos, 50.0)

    # Strengths
    if form >= 5.0:
        strengths.append(f"Strong form ({form})")
    if xgi >= 0.5:
        strengths.append(f"Excellent xGI/90 ({xgi:.2f})")
    if vs >= 60:
        strengths.append(f"High value score ({vs:.0f})")
    if avg_diff_3 <= 2.5:
        strengths.append(f"Favorable next 3 GWs (avg difficulty {avg_diff_3:.1f})")
    if total_points > 0 and vs > pos_avg:
        strengths.append("Outperforming positional peers")

    # Weaknesses
    if form <= 1.0 and minutes > 180:
        weaknesses.append(f"Poor form ({form})")
    if xgi < 0.1 and pos in ("MID", "FWD") and minutes > 180:
        weaknesses.append(f"Low attacking threat (xGI/90: {xgi:.2f})")
    if avg_diff_3 >= 4.0:
        weaknesses.append(f"Difficult next 3 GWs (avg difficulty {avg_diff_3:.1f})")
    if minutes < 90:
        weaknesses.append(f"Limited game time ({minutes} mins)")

    # Risks
    if status != "a":
        risk_detail = news if news else f"Status: {status}"
        risks.append(f"Injury doubt — {risk_detail}")
    if transfers_out > transfers_in * 1.5 and transfers_out > 5000:
        risks.append(f"Heavy selling ({transfers_out:,} out vs {transfers_in:,} in)")
    if minutes > 0 and minutes < 270 and minutes >= 90:
        risks.append(f"Rotation risk ({minutes} mins so far)")

    # Opportunities
    if transfers_in > transfers_out * 1.5 and transfers_in > 3000:
        opportunities.append(f"High demand ({transfers_in:,} transfers in)")
    if price_change >= 2:
        opportunities.append(f"Price risen +£{price_change/10:.1f}m — rising further possible")
    if selected < 5.0 and xgi >= 0.4:
        opportunities.append(f"Differential pick ({selected:.1f}% owned, xGI/90: {xgi:.2f})")

    return strengths, weaknesses, risks, opportunities


def evaluate_squad(
    squad_df: pd.DataFrame,
    player_df: pd.DataFrame,
    fixtures: list[dict],
    team_name_map: dict[int, str],
    bank: float = 0.0,
    free_transfers: int = 1,
    saved_transfers: int = 0,
) -> SquadEvaluation:
    """Run the full squad evaluation.

    Parameters
    ----------
    squad_df : DataFrame of the current 15-man squad (from resolve_player_names)
    player_df : DataFrame of all players with scores (from get_scored_players)
    fixtures : list of fixture dicts from fixture_service
    team_name_map : dict mapping team_id → team_name
    bank : ITB amount
    free_transfers : number of free transfers available
    saved_transfers : number of saved transfers
    """
    if squad_df.empty:
        return SquadEvaluation(
            overall_rating=0,
            total_value=0,
            bank=bank,
            free_transfers=free_transfers,
            saved_transfers=saved_transfers,
        )

    # Build fixture map: team_id → sorted list of upcoming fixtures
    fixture_map = build_fixture_map(fixtures)

    # Position averages for relative comparison
    position_avg = compute_position_averages(player_df)

    total_value = float(squad_df["price"].sum()) if "price" in squad_df.columns else 0.0
    all_strengths: list[str] = []
    all_weaknesses: list[str] = []
    all_injuries: list[str] = []
    all_rotation_risks: list[str] = []
    all_poor_fixtures: list[str] = []
    all_excellent_fixtures: list[str] = []
    all_price_risers: list[str] = []
    all_price_fallers: list[str] = []
    all_underperformers: list[str] = []
    all_bargains: list[str] = []

    player_assessments: list[PlayerAssessment] = []

    for _, row in squad_df.iterrows():
        next_3, next_6 = get_fixture_info(row, fixture_map, team_name_map)
        avg_d3 = sum(f.difficulty for f in next_3) / max(len(next_3), 1)
        avg_d6 = sum(f.difficulty for f in next_6) / max(len(next_6), 1)

        strengths, weaknesses, risks, opportunities = _classify_player(
            row, avg_d3, avg_d6, position_avg
        )
        rating = compute_player_rating(row, avg_d3, position_avg)

        assessment = PlayerAssessment(
            player_id=int(row["id"]),
            web_name=str(row.get("web_name", "?")),
            team_id=int(row.get("team_id", 0) or 0),
            team_short=str(row.get("team_short", "?")),
            position=str(row.get("position", "?")),
            price=float(row.get("price", 0) or 0),
            total_points=int(row.get("total_points", 0) or 0),
            form=float(row.get("form", 0) or 0),
            xgi_per_90=float(row.get("xgi_per_90", 0) or 0),
            value_score=float(row.get("value_score", 0) or 0),
            minutes_played=int(row.get("minutes", 0) or 0),
            minutes_fraction=float(row.get("minutes_fraction", 0) or 0),
            status=str(row.get("status", "a") or "a"),
            news=str(row.get("news", "") or ""),
            selected_by_percent=float(row.get("selected_by_percent", 0) or 0),
            cost_change_start=int(row.get("cost_change_start", 0) or 0),
            next_3_fixtures=next_3,
            next_6_fixtures=next_6,
            avg_difficulty_3gw=round(avg_d3, 2),
            avg_difficulty_6gw=round(avg_d6, 2),
            strength_flags=strengths,
            weakness_flags=weaknesses,
            risk_flags=risks,
            opportunity_flags=opportunities,
            squad_rating=rating,
            projected_points=float(row.get("projected_points", 0) or 0),
        )

        player_assessments.append(assessment)
        name = f"{assessment.web_name} ({assessment.team_short})"

        all_strengths.extend(f"{name}: {s}" for s in strengths)
        all_weaknesses.extend(f"{name}: {w}" for w in weaknesses)
        all_injuries.extend(f"{name}: {r}" for r in risks if "Injury" in r or "doubt" in r.lower())
        all_rotation_risks.extend(f"{name}: {r}" for r in risks if "Rotation" in r)
        all_poor_fixtures.extend(f"{name}: next 3 avg {assessment.avg_difficulty_3gw}" for _ in [1] if assessment.avg_difficulty_3gw >= 4.0)
        all_excellent_fixtures.extend(f"{name}: next 3 avg {assessment.avg_difficulty_3gw}" for _ in [1] if assessment.avg_difficulty_3gw <= 2.0)
        all_price_risers.extend(f"{name}: +£{assessment.cost_change_start/10:.1f}m" for _ in [1] if assessment.cost_change_start >= 2)
        all_price_fallers.extend(f"{name}: -£{abs(assessment.cost_change_start)/10:.1f}m" for _ in [1] if assessment.cost_change_start <= -2)
        all_underperformers.extend(f"{name}: {assessment.total_points} pts, {assessment.form} form" for _ in [1] if assessment.form < 2.0 and assessment.minutes_played > 180)
        all_bargains.extend(f"{name}: {assessment.value_score:.0f} value, £{assessment.price:.1f}m" for _ in [1] if assessment.value_score >= 60 and assessment.price <= 5.5)

    overall = (
        sum(a.squad_rating for a in player_assessments) / len(player_assessments)
        if player_assessments else 0.0
    )

    return SquadEvaluation(
        overall_rating=round(overall, 1),
        total_value=round(total_value, 1),
        bank=bank,
        free_transfers=free_transfers,
        saved_transfers=saved_transfers,
        players=player_assessments,
        strengths=all_strengths,
        weaknesses=all_weaknesses,
        injuries=all_injuries,
        rotation_risks=all_rotation_risks,
        poor_fixtures=all_poor_fixtures,
        excellent_fixtures=all_excellent_fixtures,
        price_risers=all_price_risers,
        price_fallers=all_price_fallers,
        underperformers=all_underperformers,
        emerging_bargains=all_bargains,
    )
