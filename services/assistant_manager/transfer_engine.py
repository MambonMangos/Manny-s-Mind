"""Transfer Engine — Section 2 of the Assistant Manager.

Generates transfer recommendations by evaluating every possible replacement
for each player in the squad.  Each recommendation is scored, ranked, and
accompanied by reasoning.
"""

from __future__ import annotations

import pandas as pd

from engines.market_engine import classify_demand
from engines.prediction_engine import (
    classify_risk,
    compute_confidence,
    project_minutes,
    project_points_gain,
)
from services.assistant_manager.models import (
    PlayerAssessment,
    SquadEvaluation,
    TransferPlan,
    TransferRecommendation,
)

# Position limits: GKP(1), DEF(2), MID(3), FWD(4) → max in squad
POSITION_LIMITS = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}


def _build_reasoning(
    out_a: PlayerAssessment,
    in_name: str,
    in_team: str,
    expected_gain: float,
    fixture_improvement: float,
    risk_level: str,
    price_diff: float,
    in_form: float,
    in_xgi: float,
    out_weaknesses: list[str],
    in_opportunities: list[str],
) -> str:
    """Build a human-readable explanation for a transfer recommendation."""
    parts = [
        (
            f"{in_name} ({in_team}) projects {expected_gain:+.2f} pts better than "
            f"{out_a.web_name} this gameweek."
        )
    ]
    if fixture_improvement > 0:
        parts.append(
            f"Fixtures improve by {fixture_improvement:+.1f} over the next 3 GWs."
        )
    elif fixture_improvement < 0:
        parts.append(
            f"Fixtures are {abs(fixture_improvement):.1f} points harder over the next 3 GWs."
        )
    if in_form > 0:
        parts.append(f"Strong recent form ({in_form:.2f}).")
    if in_xgi > 0:
        parts.append(f"Attacking threat of {in_xgi:.2f} xGI/90.")
    if price_diff != 0:
        parts.append(f"Price difference of £{price_diff:+.1f}m.")
    if out_weaknesses:
        parts.append(f"{out_a.web_name} concerns: {', '.join(out_weaknesses[:2])}.")
    if in_opportunities:
        parts.append("Opportunity: " + "; ".join(in_opportunities[:2]) + ".")
    parts.append(f"Risk level: {risk_level}.")
    return " ".join(parts)


def generate_transfer_recommendations(
    squad_eval: SquadEvaluation,
    player_df: pd.DataFrame,
    fixture_map: dict[int, list[dict]],
    team_name_map: dict[int, str],
    top_n: int = 10,
) -> TransferPlan:
    """Generate ranked transfer recommendations.

    Parameters
    ----------
    squad_eval : output of evaluate_squad()
    player_df : all players with value scores
    fixture_map : team_id → list of fixture dicts
    team_name_map : team_id → team_name
    top_n : max recommendations to return
    """
    if not squad_eval.players:
        return TransferPlan(action="hold", reasoning="No squad data available.")

    squad_ids = {p.player_id for p in squad_eval.players}
    {p.position for p in squad_eval.players}

    # Position average value scores for relative comparison
    if "position" in player_df.columns and "value_score" in player_df.columns:
        player_df.groupby("position")["value_score"].mean().to_dict()

    recommendations: list[TransferRecommendation] = []

    for out_a in squad_eval.players:
        # Candidates: same position, not in squad
        candidates = player_df[
            (player_df["position"] == out_a.position)
            & (~player_df["id"].isin(squad_ids))
        ].copy()

        if candidates.empty:
            continue

        # Get fixtures for candidate teams
        fixture_map.get(
            int(_squad_df_id := out_a.player_id), []
        )
        out_avg_d3 = out_a.avg_difficulty_3gw

        for _, in_row in candidates.iterrows():
            in_team_id = int(in_row.get("team_id", 0) or 0)
            in_fixtures = fixture_map.get(in_team_id, [])
            in_avg_d3 = (
                sum(f["difficulty"] for f in in_fixtures[:3]) / min(len(in_fixtures), 3)
                if in_fixtures else 3.0
            )

            in_form = float(in_row.get("form", 0) or 0)
            in_xgi = float(in_row.get("xgi_per_90", 0) or 0)
            in_price = float(in_row.get("price", 0) or 0)
            in_vs = float(in_row.get("value_score", 0) or 0)

            price_diff = round(in_price - out_a.price, 1)

            # Expected gain: V3 xPts drive the score when both players have a
            # production projection; otherwise fall back to the legacy engine.
            in_proj = float(in_row.get("projected_points", 0) or 0)
            out_proj = float(getattr(out_a, "projected_points", 0) or 0)
            if in_proj > 0 and out_proj > 0:
                expected_gain = round(in_proj - out_proj, 2)
            else:
                expected_gain = project_points_gain(out_a, in_row, in_avg_d3)

            minutes_proj = project_minutes(in_row)
            risk = classify_risk(in_row, in_avg_d3)
            confidence = compute_confidence(expected_gain, risk, minutes_proj, in_form)
            fixture_imp = out_avg_d3 - in_avg_d3

            in_team_short = str(in_row.get("team_short", "?") or "?")
            in_web_name = str(in_row.get("web_name", "?") or "?")

            # Get opportunity flags for the candidate
            transfers_in = int(in_row.get("transfers_in_event", 0) or 0)
            transfers_out = int(in_row.get("transfers_out_event", 0) or 0)
            selected = float(in_row.get("selected_by_percent", 0) or 0)
            in_opps = classify_demand(transfers_in, transfers_out, selected)

            reasoning = _build_reasoning(
                out_a=out_a,
                in_name=in_web_name,
                in_team=in_team_short,
                expected_gain=expected_gain,
                fixture_improvement=fixture_imp,
                risk_level=risk,
                price_diff=price_diff,
                in_form=in_form,
                in_xgi=in_xgi,
                out_weaknesses=out_a.weakness_flags,
                in_opportunities=in_opps,
            )

            rec = TransferRecommendation(
                player_out=out_a,
                player_in=PlayerAssessment(
                    player_id=int(in_row["id"]),
                    web_name=in_web_name,
                    team_id=in_team_id,
                    team_short=in_team_short,
                    position=str(in_row.get("position", "?") or "?"),
                    price=in_price,
                    total_points=int(in_row.get("total_points", 0) or 0),
                    form=in_form,
                    xgi_per_90=in_xgi,
                    value_score=in_vs,
                    minutes_played=int(in_row.get("minutes", 0) or 0),
                    minutes_fraction=float(in_row.get("minutes_fraction", 0) or 0),
                    status=str(in_row.get("status", "a") or "a"),
                    news=str(in_row.get("news", "") or ""),
                    selected_by_percent=selected,
                    cost_change_start=int(in_row.get("cost_change_start", 0) or 0),
                    projected_points=in_proj,
                ),
                price_difference=price_diff,
                expected_points_gained=expected_gain,
                value_score_difference=round(in_vs - out_a.value_score, 2),
                fixture_improvement=round(fixture_imp, 2),
                minutes_projection=minutes_proj,
                ownership_difference=round(selected - out_a.selected_by_percent, 1),
                risk_level=risk,
                confidence_rating=confidence,
                reasoning=reasoning,
            )

            # Only recommend if expected gain > 0
            if expected_gain > 0:
                recommendations.append(rec)

    # Sort by expected points gained, descending
    recommendations.sort(key=lambda r: r.expected_points_gained, reverse=True)

    # Take top N
    recommendations = recommendations[:top_n]
    for i, rec in enumerate(recommendations):
        rec.rank = i + 1

    # Determine overall action
    if not recommendations:
        return TransferPlan(
            action="hold",
            reasoning="No transfer recommended. Your squad is well-positioned for the upcoming gameweeks.",
        )

    top = recommendations[0]
    if top.expected_points_gained < 2.0:
        return TransferPlan(
            action="hold",
            transfers=recommendations,
            total_expected_gain=top.expected_points_gained,
            reasoning=f"The best available transfer gains only {top.expected_points_gained:+.1f} points — not worth a transfer.",
        )

    if top.expected_points_gained >= 8.0 and squad_eval.free_transfers == 0:
        return TransferPlan(
            action="hit_4",
            transfers=[top],
            total_expected_gain=top.expected_points_gained,
            total_hit_cost=4,
            net_expected_gain=round(top.expected_points_gained - 4, 1),
            reasoning=f"A -4 hit is justified. Expected gain of {top.expected_points_gained:+.1f} points outweighs the 4-point cost.",
        )

    return TransferPlan(
        action="free_transfer" if squad_eval.free_transfers > 0 else "hold",
        transfers=[top] if squad_eval.free_transfers > 0 else recommendations[:1],
        total_expected_gain=top.expected_points_gained,
        net_expected_gain=top.expected_points_gained,
        reasoning=f"Recommended: {top.player_out.web_name} → {top.player_in.web_name} ({top.expected_points_gained:+.1f} pts expected).",
    )
