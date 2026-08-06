"""Future Planner — Section 5 of the Assistant Manager.

Looks ahead 3, 6, and 10 gameweeks to identify fixture swings, transfer
targets, captaincy windows, and price movement signals.
"""

from __future__ import annotations

from engines.fixture_engine import (
    build_fixture_map,
    build_fixture_window,
    detect_fixture_swings,
)
from services.assistant_manager.models import (
    FuturePlan,
    SquadEvaluation,
)


def plan_future(
    squad_eval: SquadEvaluation,
    all_player_df,
    fixtures: list[dict],
    team_name_map: dict[int, str],
) -> FuturePlan:
    """Generate forward-looking analysis for the squad.

    Parameters
    ----------
    squad_eval : current squad evaluation
    all_player_df : full player DataFrame with scores
    fixtures : all fixtures
    team_name_map : team_id → name
    """
    plan = FuturePlan()

    if not squad_eval.players:
        return plan

    fixture_map = build_fixture_map(fixtures)

    # ── Fixture Windows ───────────────────────────────────────────────────
    for window_size, attr in [(3, "window_3gw"), (6, "window_6gw"), (10, "window_10gw")]:
        fw = build_fixture_window(squad_eval.players, fixture_map, team_name_map, window_size)
        if fw is not None:
            setattr(plan, attr, fw)

    # ── Fixture Swings ────────────────────────────────────────────────────
    plan.fixture_swings = detect_fixture_swings(squad_eval.players, fixture_map, team_name_map)

    # ── Difficult Runs ────────────────────────────────────────────────────
    for p in squad_eval.players:
        if p.avg_difficulty_3gw >= 4.0:
            plan.upcoming_difficult_runs.append(
                f"{p.web_name} ({p.team_short}): avg difficulty {p.avg_difficulty_3gw} over next 3 GWs"
            )

    # ── Easy Runs ─────────────────────────────────────────────────────────
    for p in squad_eval.players:
        if 0 < p.avg_difficulty_3gw <= 2.0:
            plan.upcoming_easy_runs.append(
                f"{p.web_name} ({p.team_short}): avg difficulty {p.avg_difficulty_3gw} over next 3 GWs"
            )

    # ── Price Rise Targets ────────────────────────────────────────────────
    if not all_player_df.empty and "transfers_in_event" in all_player_df.columns:
        hot = all_player_df[
            (all_player_df["transfers_in_event"] > 5000)
            & (all_player_df["selected_by_percent"] < 20)
        ].nlargest(5, "transfers_in_event")
        for _, row in hot.iterrows():
            plan.price_rise_targets.append(
                f"{row.get('web_name', '?')} ({row.get('team_short', '?')}): "
                f"{int(row.get('transfers_in_event', 0)):,} transfers in, "
                f"likely to rise soon"
            )

    # ── Price Drop Warnings ───────────────────────────────────────────────
    if not all_player_df.empty and "transfers_out_event" in all_player_df.columns:
        dropping = all_player_df[
            all_player_df["transfers_out_event"] > 5000
        ].nlargest(5, "transfers_out_event")
        squad_names = {p.web_name for p in squad_eval.players}
        for _, row in dropping.iterrows():
            name = row.get("web_name", "?")
            if name in squad_names:
                plan.price_drop_warnings.append(
                    f"{name} ({row.get('team_short', '?')}): "
                    f"{int(row.get('transfers_out_event', 0)):,} transfers out, "
                    f"may drop in price"
                )

    # ── Captain Opportunities ─────────────────────────────────────────────
    for p in sorted(squad_eval.players, key=lambda x: x.form, reverse=True)[:5]:
        if p.form >= 4.0 and p.avg_difficulty_3gw <= 3.0:
            plan.captain_opportunities.append(
                f"{p.web_name} ({p.team_short}): form {p.form}, "
                f"avg fixture difficulty {p.avg_difficulty_3gw:.1f}"
            )

    # ── Transfer Suggestions ──────────────────────────────────────────────
    for p in squad_eval.players:
        if p.weakness_flags and p.risk_flags:
            plan.transfer_plan.append(
                f"Consider selling {p.web_name} ({p.team_short}): "
                f"{'; '.join(p.weakness_flags[:2])}"
            )

    return plan
