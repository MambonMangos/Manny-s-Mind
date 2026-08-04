"""Card primitives — HTML presenters plus thin Streamlit renderers.

Replaces ad-hoc ``st.markdown`` cards across pages with one implementation.
All dynamic values are escaped in the presenters.
"""

from __future__ import annotations

import streamlit as st

from components.ui.base import class_attr, esc

# ---------------------------------------------------------------------------
# Presenters
# ---------------------------------------------------------------------------


def metric_card_html(
    label: str,
    value: str,
    delta: str = "",
    positive: bool = True,
    delay: int = 0,
) -> str:
    """Return the HTML for a single metric card (backed by .metric-card CSS)."""
    delay_class = f" fade-in-delay-{delay}" if delay else ""
    delta_html = ""
    if delta:
        css = "positive" if positive else "negative"
        arrow = "+" if positive and not delta.startswith(("-", "+")) else ""
        delta_html = f'<div class="metric-delta {css}">{arrow}{esc(delta)}</div>'
    return (
        f'<div class="metric-card fade-in{delay_class}">'
        f'<div class="metric-label">{esc(label)}</div>'
        f'<div class="metric-value">{esc(value)}</div>'
        f"{delta_html}"
        f"</div>"
    )


def card_html(children: str, classes: str = "") -> str:
    """Wrap child HTML in a `.card` container."""
    return f'<div class="{class_attr("card", classes)}">{children}</div>'


def card_header_html(title: str, subtitle: str = "") -> str:
    """Return the header block used inside cards."""
    subtitle_html = f'<div class="caption-text">{esc(subtitle)}</div>' if subtitle else ""
    return f'<div class="card-title">{esc(title)}</div>{subtitle_html}'


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def render_metric_card(
    label: str,
    value: str,
    delta: str = "",
    positive: bool = True,
    delay: int = 0,
) -> None:
    """Render a single styled metric card (matches legacy signature)."""
    st.markdown(metric_card_html(label, value, delta, positive, delay), unsafe_allow_html=True)


def render_card(children: str, classes: str = "") -> None:
    """Render a card containing already-built HTML children."""
    st.markdown(card_html(children, classes), unsafe_allow_html=True)
