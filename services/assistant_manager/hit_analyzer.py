"""Hit Analyzer — Section 3 of the Assistant Manager.

Evaluates whether taking a points deduction (-4, -8, etc.) is justified by
comparing expected points gained against the hit cost.
"""

from __future__ import annotations

from services.assistant_manager.models import (
    SquadEvaluation,
    TransferPlan,
    TransferRecommendation,
)

HIT_COST_PER_TRANSFER = 4


def analyze_hit(
    transfer_plan: TransferPlan,
    squad_eval: SquadEvaluation,
) -> TransferPlan:
    """Analyze whether hits are worthwhile and adjust the transfer plan.

    Logic:
    - If free transfers available → no hit needed for the first transfer
    - If no free transfers, compare expected gain vs -4 cost
    - For multiple transfers, each additional one costs -4
    - A hit is worthwhile if expected gain > hit cost + safety margin
    """
    if not transfer_plan.transfers or transfer_plan.action == "hold":
        return transfer_plan

    free_tfers = squad_eval.free_transfers
    n_transfers = len(transfer_plan.transfers)

    # If we have free transfers, use them first
    if free_tfers >= n_transfers:
        transfer_plan.total_hit_cost = 0
        transfer_plan.net_expected_gain = transfer_plan.total_expected_gain
        transfer_plan.reasoning += (
            f" Using {n_transfers} free transfer(s) — no points deduction."
        )
        return transfer_plan

    # Need hits for excess transfers
    excess = n_transfers - free_tfers
    excess * HIT_COST_PER_TRANSFER

    # Evaluate each recommended transfer individually
    worthwhile: list[TransferRecommendation] = []
    cumulative_gain = 0.0

    for rec in transfer_plan.transfers:
        marginal_gain = rec.expected_points_gained

        # For the marginal transfer, check if it justifies the -4
        if marginal_gain > HIT_COST_PER_TRANSFER + 1.0:
            # Worth it: gain exceeds cost with safety margin
            worthwhile.append(rec)
            cumulative_gain += marginal_gain
        else:
            # Not worth a hit — stop adding transfers
            break

    if not worthwhile:
        return TransferPlan(
            action="hold",
            reasoning=(
                f"No transfer justifies a -4 hit. The best available move "
                f"gains only {transfer_plan.transfers[0].expected_points_gained:+.1f} "
                f"points, which does not outweigh the 4-point deduction."
            ),
        )

    # Recalculate with only worthwhile transfers
    actual_hits = max(0, len(worthwhile) - free_tfers) * HIT_COST_PER_TRANSFER
    net_gain = round(cumulative_gain - actual_hits, 1)

    action = "free_transfer" if actual_hits == 0 else f"hit_{actual_hits}"

    reasoning_parts = [
        f"Recommended {len(worthwhile)} transfer(s) for a net expected gain of {net_gain:+.1f} points.",
    ]

    if actual_hits > 0:
        reasoning_parts.append(
            f"This requires a -{actual_hits} point deduction "
            f"({len(worthwhile)} transfers, {free_tfers} free)."
        )
        reasoning_parts.append(
            f"The expected gain of {cumulative_gain:+.1f} points exceeds the "
            f"{actual_hits}-point cost by {net_gain:+.1f} points."
        )
    else:
        reasoning_parts.append(
            f"All {len(worthwhile)} transfers fit within your {free_tfers} free transfer(s)."
        )

    return TransferPlan(
        action=action,
        transfers=worthwhile,
        total_expected_gain=round(cumulative_gain, 1),
        total_hit_cost=actual_hits,
        net_expected_gain=net_gain,
        reasoning=" ".join(reasoning_parts),
    )
