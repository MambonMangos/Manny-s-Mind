"""Conversational Assistant — context construction.

Builds a compact, structured context snapshot from the existing
:class:`services.assistant_manager.models.AssistantReport`. This is the chat's
view of the platform: team state, V3 projections, fixtures and league
intelligence. The chatbot never re-derives these numbers — it consumes what
V3 and the Assistant Manager already produced (see directive: the chatbot sits
on top of the intelligence platform).

Every row records a provenance tag (``V3``, ``FPL``, ``LEAGUE``) so each reply
can point at the exact values it used.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from services.assistant_manager.models import AssistantReport

logger = logging.getLogger(__name__)


@dataclass
class ChatContext:
    """Structured, model-ready context for one chat turn."""

    team_id: int
    team_name: str = ""
    gameweek: int | None = None
    bank: float = 0.0
    free_transfers: int = 0
    saved_transfers: int = 0
    squad: list[dict] = field(default_factory=list)
    top_projections: list[dict] = field(default_factory=list)
    top_differentials: list[dict] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    shadow_projections: dict[str, list[dict]] = field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.squad and not self.top_projections


def _fmt_fixtures(fixtures) -> str:
    """Render a player's next fixtures as one compact string."""
    if not fixtures:
        return "no fixtures loaded"
    parts = []
    for f in fixtures[:3]:
        side = "H" if f.home else "A"
        parts.append(f"GW{f.gameweek} {f.opponent_short} ({side}, diff {f.difficulty})")
    return "; ".join(parts)


def _squad_row(player) -> dict:
    """One compact context row for a squad player."""
    row: dict[str, Any] = {
        "player": player.web_name,
        "position": player.position,
        "team": player.team_short,
        "price": round(player.price, 1),
        "form": round(player.form, 2),
        "xgi_per_90": round(player.xgi_per_90, 2),
        "xpts": round(player.projected_points, 1),
        "selected_by": round(player.selected_by_percent, 1),
        "fixtures": _fmt_fixtures(player.next_3_fixtures),
    }
    if player.status and player.status.lower() not in {"a", "available"}:
        row["status"] = player.status
    if player.news:
        row["news"] = player.news[:120]
    if player.risk_flags:
        row["risks"] = player.risk_flags
    return row


def _projection_row(proj) -> dict:
    """One compact context row for a V3 projection."""
    factors = (
        proj.contributing_factors if isinstance(proj.contributing_factors, dict) else {}
    )
    start_prob = factors.get("start_probability", 0.0)
    row: dict[str, Any] = {
        "player": proj.web_name,
        "position": proj.position,
        "xpts": round(float(proj.projected_points), 1),
        "xpts_per_90": round(float(proj.xpts_per_90), 2),
        "expected_minutes": round(float(proj.expected_minutes), 0),
        "start_probability": round(float(start_prob or 0.0), 2),
        "confidence": round(float(proj.confidence), 0),
    }
    return row


def _shadow_projection_row(proj, model_id: str) -> dict:
    """One compact context row for a shadow model projection."""
    factors = (
        proj.contributing_factors if isinstance(proj.contributing_factors, dict) else {}
    )
    start_prob = factors.get("start_probability", 0.0)
    row: dict[str, Any] = {
        "player": proj.web_name,
        "position": proj.position,
        "xpts": round(float(proj.projected_points), 1),
        "expected_minutes": round(float(proj.expected_minutes), 0),
        "start_probability": round(float(start_prob or 0.0), 2),
        "model": model_id,
    }
    return row


def build_chat_context(
    report: AssistantReport,
    *,
    team_name: str = "",
    top_projections: int = 15,
    top_differentials: int = 5,
) -> ChatContext:
    """Assemble a :class:`ChatContext` from an ``AssistantReport``.

    The report already carries V3 projections (``production_pipeline_result``),
    squad evaluation and league intelligence — no engines are re-run here.
    """
    context = ChatContext(
        team_id=report.team_id,
        team_name=team_name,
        gameweek=report.current_gameweek,
    )

    squad_eval = report.squad_evaluation
    if squad_eval is not None:
        context.bank = round(float(squad_eval.bank), 1)
        context.free_transfers = int(squad_eval.free_transfers)
        context.saved_transfers = int(squad_eval.saved_transfers)
        for player in squad_eval.players:
            context.squad.append(_squad_row(player))

    production = report.production_pipeline_result
    if production is not None and production.primary is not None:
        projections = list(production.primary.projections)
        projections.sort(key=lambda p: float(p.projected_points), reverse=True)
        for proj in projections[:top_projections]:
            context.top_projections.append(_projection_row(proj))

    # Shadow model projections (Model D and others)
    if production is not None:
        for shadow in production.shadows:
            if shadow.ok and shadow.projections:
                shadow_rows = []
                for proj in shadow.projections:
                    shadow_rows.append(_shadow_projection_row(proj, shadow.model_id))
                context.shadow_projections[shadow.model_id] = shadow_rows

    league = report.league_intelligence
    if league is not None:
        diffs = sorted(
            (d for d in league.differentials if getattr(d, "xpts", 0)),
            key=lambda d: float(d.xpts),
            reverse=True,
        )
        for d in diffs[:top_differentials]:
            context.top_differentials.append(
                {
                    "player": d.web_name,
                    "position": d.position,
                    "xpts": round(float(d.xpts), 1),
                    "ownership": round(float(d.global_ownership), 1),
                }
            )

    context.fixtures, context.sources = _build_sources(context)
    return context


def _build_sources(context: ChatContext) -> tuple[list[str], list[str]]:
    """Derive traceable source lines from the context.

    Returns ``(fixture_lines, source_lines)``. Every substantive number the
    model may cite appears here so replies can be checked against the source.
    """
    fixture_lines = []
    sources = []
    if context.gameweek:
        fixture_lines.append(
            f"V3 projections and context are for GW{context.gameweek}."
        )

    for row in context.squad:
        sources.append(
            f"V3 xPts GW{context.gameweek or '?'}: {row['player']} {row['xpts']} "
            f"(form {row['form']}, xGI/90 {row['xgi_per_90']}, "
            f"{row['selected_by']}% owned)"
        )
        if row.get("news"):
            sources.append(f"FPL news for {row['player']}: {row['news']}")

    for row in context.top_projections:
        sources.append(
            f"V3 xPts GW{context.gameweek or '?'}: {row['player']} {row['xpts']} "
            f"(xPts/90 {row['xpts_per_90']}, expected mins {row['expected_minutes']:.0f}, "
            f"start {row['start_probability']:.0%}, confidence {row['confidence']:.0f})"
        )

    for row in context.top_differentials:
        sources.append(
            f"League differential: {row['player']} xPts {row['xpts']}, "
            f"{row['ownership']}% owned"
        )

    return fixture_lines, sources


def render_context(context: ChatContext) -> str:
    """Render the context as a compact text block for the model prompt."""
    lines: list[str] = []

    def section(title: str) -> None:
        lines.append(f"## {title}")

    def kv(rows: list[dict]) -> None:
        for row in rows:
            parts = []
            for key, value in row.items():
                if isinstance(value, list):
                    value = ", ".join(str(v) for v in value)
                parts.append(f"{key}={value}")
            lines.append("- " + ", ".join(parts))

    section("User context")
    lines.append(f"- team_id={context.team_id} team={context.team_name or 'unknown'}")
    lines.append(f"- gameweek={context.gameweek or 'unknown'}")
    lines.append(
        f"- bank={context.bank}m free_transfers={context.free_transfers} "
        f"saved_transfers={context.saved_transfers}"
    )
    if context.squad:
        section("User squad (V3 xPts)")
        kv(context.squad)
    if context.top_projections:
        section("Top V3 projections (best legal picks this GW)")
        kv(context.top_projections)
    if context.top_differentials:
        section("League differentials (V3)")
        kv(context.top_differentials)

    for model_id, shadow_rows in context.shadow_projections.items():
        if shadow_rows:
            label = {
                "v3_hist_d_team": "Model D (V3-HIST-01) projections",
            }.get(model_id, f"{model_id} projections")
            section(label)
            kv(shadow_rows)

    return "\n".join(lines)
