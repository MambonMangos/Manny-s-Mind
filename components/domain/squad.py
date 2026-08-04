"""Squad-level presenters — overall rating gauge and summary metrics."""

from __future__ import annotations

import streamlit as st

from components.ui.base import div, esc, span
from components.ui.metrics import render_metric_grid


def squad_rating_html(overall_rating: float) -> str:
    """Present the 0-100 squad rating as a big coloured gauge."""
    rating = float(overall_rating)
    css = "rating-good" if rating >= 75 else "rating-fair" if rating >= 55 else "rating-poor"
    return div(
        span(esc("Squad Rating"), classes="metric-label")
        + f'<div class="metric-value {css}">{esc(f"{rating:.0f}")}<span class="caption-text">/100</span></div>',
        classes="card metric-card fade-in",
    )


def render_squad_rating(overall_rating: float) -> None:
    """Render the squad rating gauge."""
    st.markdown(squad_rating_html(overall_rating), unsafe_allow_html=True)


def render_squad_summary_cards(
    total_value: float,
    bank: float,
    free_transfers: int,
    saved_transfers: int,
) -> None:
    """Render the squad's headline numbers as a metric grid."""
    render_metric_grid(
        [
            {"label": "Squad Value", "value": f"£{total_value:.1f}m", "delay": 0},
            {"label": "Bank", "value": f"£{bank:.1f}m", "delay": 1},
            {"label": "Free Transfers", "value": str(free_transfers), "delay": 2},
            {"label": "Saved Transfers", "value": str(saved_transfers), "delay": 3},
        ],
        columns=4,
    )
