"""Fixture card — presents a single fixture's difficulty."""

from __future__ import annotations

import streamlit as st

from components.domain.models import FixtureCard
from components.ui import badges
from components.ui.base import div, esc, span


def fixture_level(difficulty: int) -> str:
    """Map a 1-5 FPL difficulty rating to easy/medium/hard."""
    if difficulty <= 2:
        return "easy"
    if difficulty >= 4:
        return "hard"
    return "medium"


def fixture_card_html(fx: FixtureCard) -> str:
    """Present a fixture as HTML."""
    venue = "H" if fx.home else "A"
    header = (
        span(esc(f"GW{fx.gameweek}"), classes="body-text")
        + " "
        + span(esc(f"({venue})"), classes="caption-text")
    )
    opponent = span(esc(fx.opponent), classes="card-title")
    level = fixture_level(fx.difficulty)
    label = fx.difficulty_label or str(fx.difficulty)
    note = ""
    if fx.note:
        note = div(span(esc(fx.note), classes="caption-text"), classes="trust-note")
    return div(
        header + div(opponent + " " + badges.badge_fixture(level))
        + div(span(esc(label), classes="caption-text"))
        + note,
        classes="card card-sm fixture-card fade-in",
    )


def render_fixture_card(fx: FixtureCard) -> None:
    """Render a single fixture card."""
    st.markdown(fixture_card_html(fx), unsafe_allow_html=True)
