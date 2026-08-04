"""Chip card — presents a chip strategy recommendation."""

from __future__ import annotations

import streamlit as st

from components.domain.models import ChipCard
from components.ui import badges
from components.ui.base import div, esc, span

_CHIP_ICONS = {
    "wildcard": "🃏",
    "free_hit": "🎯",
    "bboost": "🪙",
    "3xc": "👑",
}


def chip_card_html(card: ChipCard) -> str:
    """Present a chip recommendation as HTML."""
    icon = _CHIP_ICONS.get(card.chip_name, "🎴")
    status = ""
    if card.used:
        status = span(esc("Used"), classes="risk-label risk-med")
    elif not card.available:
        status = span(esc("Unavailable"), classes="risk-label risk-med")

    body = (
        div(
            f'<span class="chip-icon">{icon}</span> '
            + span(esc(card.chip_label), classes="card-title")
            + " "
            + status,
        )
        + div(
            badges.badge_confidence(card.confidence_pct)
            + " "
            + span(
                esc("Play" if card.should_play else "Hold"),
                classes="chip-action body-text",
            ),
            classes="trust-badges",
        )
    )
    if card.should_play:
        if card.best_gameweek is not None:
            body += div(
                span(esc(f"Best gameweek: GW{card.best_gameweek}"), classes="body-text"),
                classes="trust-note",
            )
        if card.projected_gain:
            body += div(
                span(esc(f"Projected gain: {card.projected_gain:+.1f} pts"), classes="body-text"),
                classes="trust-note",
            )
    if card.reasoning:
        body += div(
            span(esc("Why: "), classes="caption-text")
            + span(esc(card.reasoning), classes="body-text"),
            classes="trust-note",
        )
    return div(body, classes="card chip-card fade-in")


def render_chip_card(card: ChipCard) -> None:
    """Render a chip recommendation."""
    st.markdown(chip_card_html(card), unsafe_allow_html=True)
