"""Explainer — Section 7 of the Assistant Manager.

Generates natural-language explanations for every recommendation type.
All explanations are data-driven and reference specific metrics.
"""

from __future__ import annotations

from services.assistant_manager.models import (
    ChipRecommendation,
    PlayerAssessment,
    SquadEvaluation,
    TransferPlan,
    TransferRecommendation,
)


def explain_squad_evaluation(squad_eval: SquadEvaluation) -> str:
    """Generate an executive summary of the squad evaluation."""
    if not squad_eval.players:
        return "No squad data available for evaluation."

    parts = [
        f"**Squad Rating: {squad_eval.overall_rating}/100**",
        f"Total value: £{squad_eval.total_value:.1f}m | Bank: £{squad_eval.bank:.1f}m",
        f"Free transfers: {squad_eval.free_transfers} | Saved: {squad_eval.saved_transfers}",
        "",
    ]

    if squad_eval.strengths:
        parts.append("**Strengths:**")
        for s in squad_eval.strengths[:5]:
            parts.append(f"- {s}")
        parts.append("")

    if squad_eval.weaknesses:
        parts.append("**Weaknesses:**")
        for w in squad_eval.weaknesses[:5]:
            parts.append(f"- {w}")
        parts.append("")

    if squad_eval.injuries:
        parts.append("**Injuries/Doubts:**")
        for i in squad_eval.injuries:
            parts.append(f"- {i}")
        parts.append("")

    if squad_eval.rotation_risks:
        parts.append("**Rotation Risks:**")
        for r in squad_eval.rotation_risks:
            parts.append(f"- {r}")
        parts.append("")

    if squad_eval.excellent_fixtures:
        parts.append("**Favorable Fixtures (next 3 GWs):**")
        for f in squad_eval.excellent_fixtures:
            parts.append(f"- {f}")

    if squad_eval.poor_fixtures:
        parts.append("**Difficult Fixtures (next 3 GWs):**")
        for f in squad_eval.poor_fixtures:
            parts.append(f"- {f}")

    return "\n".join(parts)


def explain_transfer_plan(transfer_plan: TransferPlan) -> str:
    """Generate a natural-language explanation for the transfer plan."""
    if transfer_plan.action == "hold":
        return (
            f"**Recommendation: Hold**\n\n{transfer_plan.reasoning}"
        )

    parts = [
        f"**Recommendation: {transfer_plan.action.replace('_', ' ').title()}**",
        "",
    ]

    if transfer_plan.transfers:
        for i, rec in enumerate(transfer_plan.transfers, 1):
            parts.append(f"### Transfer {i}")
            parts.append(f"**OUT:** {rec.player_out.web_name} ({rec.player_out.team_short}, £{rec.player_out.price:.1f}m)")
            parts.append(f"**IN:** {rec.player_in.web_name} ({rec.player_in.team_short}, £{rec.player_in.price:.1f}m)")
            parts.append(f"Price difference: {rec.price_difference:+.1f}m")
            parts.append(f"Expected points gained: {rec.expected_points_gained:+.1f}")
            parts.append(f"Value score change: {rec.value_score_difference:+.1f}")
            parts.append(f"Fixture improvement: {rec.fixture_improvement:+.2f}")
            parts.append(f"Minutes projection: {rec.minutes_projection:.0f}/90")
            parts.append(f"Risk level: {rec.risk_level}")
            parts.append(f"Confidence: {rec.confidence_rating:.0f}/100")
            parts.append(f"\n> {rec.reasoning}")
            parts.append("")

    if transfer_plan.total_hit_cost > 0:
        parts.append(
            f"**Hit cost:** -{transfer_plan.total_hit_cost} | "
            f"**Net expected gain:** {transfer_plan.net_expected_gain:+.1f} points"
        )
    else:
        parts.append(f"**Net expected gain:** {transfer_plan.net_expected_gain:+.1f} points (no hit)")

    parts.append(f"\n{transfer_plan.reasoning}")

    return "\n".join(parts)


def explain_chip_recommendation(rec: ChipRecommendation) -> str:
    """Explain a single chip recommendation."""
    status = "used" if rec.used else ("available" if rec.available else "unavailable")
    recommendation = "PLAY" if rec.should_play else "HOLD"

    parts = [
        f"**{rec.chip_label}** ({status}) — **{recommendation}**",
        f"Confidence: {rec.confidence:.0f}/100",
    ]

    if rec.best_gameweek and rec.should_play:
        parts.append(f"Best gameweek: GW{rec.best_gameweek}")

    parts.append(f"\n{rec.reasoning}")

    return "\n".join(parts)


def explain_player_rankings(players: list[PlayerAssessment]) -> str:
    """Generate a ranked summary of all squad players."""
    if not players:
        return "No players to rank."

    sorted_players = sorted(players, key=lambda p: p.squad_rating, reverse=True)

    parts = ["**Player Rankings (by squad rating):**", ""]
    for i, p in enumerate(sorted_players, 1):
        flags = []
        if p.strength_flags:
            flags.append(f"Strengths: {', '.join(p.strength_flags[:2])}")
        if p.weakness_flags:
            flags.append(f"Weaknesses: {', '.join(p.weakness_flags[:2])}")
        if p.risk_flags:
            flags.append(f"Risks: {', '.join(p.risk_flags[:1])}")

        fixture_str = f"Fixtures: {p.avg_difficulty_3gw:.1f}/5"
        flag_str = f" | {'; '.join(flags)}" if flags else ""

        parts.append(
            f"{i}. **{p.web_name}** ({p.team_short}, {p.position}) — "
            f"Rating: {p.squad_rating:.0f}/100 | Form: {p.form} | "
            f"Value: {p.value_score:.0f} | {fixture_str}{flag_str}"
        )

    return "\n".join(parts)


def generate_executive_summary(
    squad_eval: SquadEvaluation,
    transfer_plan: TransferPlan,
    chip_recs: list[ChipRecommendation],
) -> str:
    """Generate the top-level executive summary."""
    parts = []

    # Overall assessment
    rating = squad_eval.overall_rating
    if rating >= 75:
        parts.append("Your squad is in **strong condition**.")
    elif rating >= 55:
        parts.append("Your squad is in **decent condition** with room for improvement.")
    elif rating >= 35:
        parts.append("Your squad has **significant weaknesses** that need addressing.")
    else:
        parts.append("Your squad is in **poor condition** — major changes recommended.")

    # Transfer recommendation
    if transfer_plan.action == "hold":
        parts.append("No transfers recommended this gameweek.")
    else:
        n = len(transfer_plan.transfers)
        if transfer_plan.total_hit_cost > 0:
            parts.append(
                f"Recommended **{n} transfer(s)** with a **-{transfer_plan.total_hit_cost} hit** "
                f"for a net gain of **{transfer_plan.net_expected_gain:+.1f} points**."
            )
        else:
            parts.append(
                f"Recommended **{n} free transfer(s)** for an expected gain of "
                f"**{transfer_plan.net_expected_gain:+.1f} points**."
            )

    # Chips
    active_chips = [c for c in chip_recs if c.should_play]
    if active_chips:
        for c in active_chips:
            parts.append(f"Consider playing your **{c.chip_label}** in GW{c.best_gameweek}.")

    # Key alerts
    if squad_eval.injuries:
        parts.append(f"**{len(squad_eval.injuries)}** injury concern(s) in your squad.")
    if squad_eval.price_fallers:
        parts.append(f"**{len(squad_eval.price_fallers)}** player(s) at risk of price drops.")

    return " ".join(parts)
