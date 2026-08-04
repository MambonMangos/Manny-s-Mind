"""Transfer card — presents a single transfer recommendation (out -> in)."""

from __future__ import annotations

import streamlit as st

from components.domain.evidence import render_trust_section
from components.domain.models import TransferCard
from components.ui import badges
from components.ui.base import div, esc, span


def transfer_card_html(card: TransferCard) -> str:
    """Present a transfer recommendation as HTML."""
    out = (
        span(esc(card.out.web_name), classes="body-text")
        + badges.badge_position(card.out.position)
        + span(esc(card.out.team_short), classes="caption-text")
    )
    in_ = (
        span(esc(card.in_.web_name), classes="card-title")
        + badges.badge_position(card.in_.position)
        + span(esc(card.in_.team_short), classes="caption-text")
    )
    rows: list[str] = []
    rows.append(div('&#8595;', classes="transfer-arrow"))
    gain = badges.badge_delta(card.expected_points_gained)
    rows.append(
        div(
            span(esc("Expected gain: "), classes="caption-text")
            + gain
            + span(esc(f" {card.expected_points_gained:+.1f} pts"), classes="body-text"),
            classes="trust-note",
        )
    )
    details: list[str] = []
    if card.price_difference:
        details.append(f"Price: {card.price_difference:+.1f}m")
    if card.fixture_improvement:
        details.append(f"Fixtures: {card.fixture_improvement:+.1f}")
    if card.minutes_projection:
        details.append(f"Minutes: {card.minutes_projection:.0f}")
    if details:
        rows.append(div(span(esc(" · ".join(details)), classes="caption-text")))
    if card.reasoning:
        rows.append(
            div(
                span(esc("Why: "), classes="caption-text")
                + span(esc(card.reasoning), classes="body-text"),
                classes="trust-note",
            )
        )
    badges_html = (
        badges.badge_risk(card.risk_level)
        + " "
        + (badges.badge_confidence(card.confidence_pct) if card.confidence_pct is not None else "")
    ).rstrip()
    rows.append(div(badges_html, classes="trust-badges"))
    return div(out + div(in_, classes="transfer-in") + "".join(rows), classes="card transfer-card fade-in")


def render_transfer_card(card: TransferCard) -> None:
    """Render a transfer recommendation, then its trust section."""
    st.markdown(transfer_card_html(card), unsafe_allow_html=True)
    render_trust_section(card.trust)
