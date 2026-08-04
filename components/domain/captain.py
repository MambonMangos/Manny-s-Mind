"""Captain card — presents a captaincy recommendation."""

from __future__ import annotations

import streamlit as st

from components.domain.evidence import render_trust_section
from components.domain.models import CaptainCard
from components.ui import badges
from components.ui.base import div, esc, span


def captain_card_html(card: CaptainCard) -> str:
    """Present a captaincy card as HTML."""
    header = (
        span(esc(card.player.web_name), classes="card-title")
        + " "
        + badges.badge_position(card.player.position)
        + span(esc(card.player.team_short), classes="caption-text")
    )
    opponent = ""
    if card.next_opponent:
        diff = ""
        if card.next_opponent_difficulty is not None:
            level = (
                "easy" if card.next_opponent_difficulty <= 2
                else "hard" if card.next_opponent_difficulty >= 4
                else "medium"
            )
            diff = " " + badges.badge_fixture(level)
        opponent = div(
            span(esc("Next: "), classes="caption-text")
            + span(esc(card.next_opponent), classes="body-text")
            + diff,
            classes="trust-note",
        )
    rationale = ""
    if card.rationale:
        rationale = div(
            span(esc("Why: "), classes="caption-text")
            + span(esc(card.rationale), classes="body-text"),
            classes="trust-note",
        )
    main = (
        f'<div class="projection-points">{esc(f"{card.projected_points:.1f}")} '
        f'<span class="caption-text">xPts</span></div>'
        + opponent
        + rationale
    )
    return div(header + main, classes="card captain-card fade-in")


def render_captain_card(card: CaptainCard) -> None:
    """Render a captaincy card, then its trust section."""
    st.markdown(captain_card_html(card), unsafe_allow_html=True)
    render_trust_section(card.trust)
