"""Metric grids — responsive CSS-grid layout for metric card runs.

Renders the whole grid as a single HTML fragment so the CSS grid layout
applies (Streamlit renders each ``st.markdown`` in its own block, so a grid
must live inside one element).
"""

from __future__ import annotations

import streamlit as st

from components.ui.base import esc
from components.ui.cards import metric_card_html

_VALID_COLUMNS = (2, 4)


def grid_class(columns: int) -> str:
    """Return the responsive grid CSS class for a column count (2 or 4)."""
    columns = columns if columns in _VALID_COLUMNS else 4
    return f"metric-grid-{columns}"


def metric_grid_html(cards: list[dict], columns: int = 4) -> str:
    """Return the HTML for a responsive grid of metric cards.

    ``cards`` is a list of dicts with the keys of
    :func:`components.ui.cards.metric_card_html`: label, value, delta,
    positive, delay.
    """
    if not cards:
        return ""
    body = "".join(
        metric_card_html(
            label=esc(c.get("label", "")),
            value=esc(str(c.get("value", ""))),
            delta=str(c.get("delta", "")),
            positive=bool(c.get("positive", True)),
            delay=int(c.get("delay", 0)),
        )
        for c in cards
    )
    return f'<div class="{grid_class(columns)}">{body}</div>'


def render_metric_grid(cards: list[dict], columns: int = 4) -> None:
    """Render a responsive grid of metric cards (2 or 4 columns)."""
    html = metric_grid_html(cards, columns)
    if html:
        st.markdown(html, unsafe_allow_html=True)


def render_metric_row(
    label: str,
    value: str,
    columns: int = 4,
) -> None:
    """Render a single full-width metric card inside a grid row wrapper."""
    render_metric_grid([{"label": label, "value": value}], columns=columns)
