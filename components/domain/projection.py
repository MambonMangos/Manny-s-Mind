"""Projection card — presents a gameweek xPts projection with its uncertainty
and explainability trail.
"""

from __future__ import annotations

import streamlit as st

from components.domain.evidence import render_trust_section
from components.domain.models import ProjectionCard
from components.ui import badges
from components.ui.base import div, esc, span

_FACTOR_LABELS = {
    "xpts_per_90": "xPts/90",
    "expected_minutes": "Expected minutes",
    "start_probability": "Start probability",
    "minutes_factor": "Minutes factor",
    "rotation_risk": "Rotation risk",
    "data_quality_rate": "Rate data quality",
    "data_quality_minutes": "Minutes data quality",
}


def format_contributing_factors(factors: dict) -> list[str]:
    """Humanise the projection engine's contributing_factors dict."""
    rows: list[str] = []
    for key, value in factors.items():
        label = _FACTOR_LABELS.get(str(key), str(key).replace("_", " ").title())
        if isinstance(value, bool):
            rendered = "yes" if value else "no"
        elif isinstance(value, (int, float)):
            rendered = f"{value:g}" if abs(value) >= 1 else f"{value:.2f}"
        else:
            rendered = str(value)
        rows.append(f"{label}: {rendered}")
    return rows


def projection_card_html(card: ProjectionCard) -> str:
    """Present a projection card as HTML."""
    header = (
        span(esc(card.player.web_name), classes="card-title")
        + " "
        + badges.badge_position(card.player.position)
        + span(esc(card.player.team_short), classes="caption-text")
    )
    main = (
        f'<div class="projection-points">{esc(f"{card.projected_points:.1f}")} '
        f'<span class="caption-text">xPts</span></div>'
        f'<div class="projection-ci caption-text">'
        f'80% CI {esc(f"{card.ci_80_low:.1f}")}–{esc(f"{card.ci_80_high:.1f}")}'
        f" &middot; 95% CI {esc(f'{card.ci_95_low:.1f}')}–{esc(f'{card.ci_95_high:.1f}')}"
        f"</div>"
    )
    body = header + main
    if card.contributing_factors:
        factors = format_contributing_factors(card.contributing_factors)
        body += div(
            span(esc("Drivers: "), classes="caption-text")
            + span(esc(" · ".join(factors[:3])), classes="body-text"),
            classes="trust-note",
        )
    return div(body, classes="card projection-card fade-in")


def render_projection_card(card: ProjectionCard) -> None:
    """Render a projection card, then its trust section."""
    st.markdown(projection_card_html(card), unsafe_allow_html=True)
    render_trust_section(card.trust)
