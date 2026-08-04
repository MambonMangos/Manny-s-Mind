"""Badges and tags — presenters return HTML, renderers wrap them in Streamlit.

Badge levels are derived from the design-system state tokens
(:mod:`components.design_tokens`) so colours and labels stay in one place.
"""

from __future__ import annotations

import streamlit as st

from components.design_tokens import (
    CONFIDENCE_LEVELS,
    EVIDENCE_LEVELS,
    FIXTURE_LEVELS,
    RISK_LEVELS,
    color,
    confidence_level_for,
)
from components.ui.base import esc

# ---------------------------------------------------------------------------
# Presenters (pure HTML)
# ---------------------------------------------------------------------------


def badge_position(position: str) -> str:
    """Return an HTML badge for a player position (GKP/DEF/MID/FWD)."""
    pos = str(position).upper()
    css_class = f"tag tag-{pos.lower()}" if pos in ("GKP", "DEF", "MID", "FWD") else "tag"
    return f'<span class="{css_class}">{esc(pos)}</span>'


def badge_risk(level: str) -> str:
    """Return an HTML badge for a risk level (low/medium/high)."""
    key = str(level).lower()
    info = RISK_LEVELS.get(key, RISK_LEVELS["medium"])
    return f'<span class="risk-label risk-{key if key in RISK_LEVELS else "med"}">{esc(info["label"])}</span>'


def badge_evidence(level: str) -> str:
    """Return an HTML badge for an evidence level (design-system names)."""
    key = str(level).lower()
    info = EVIDENCE_LEVELS.get(key)
    if info is None:
        return f'<span class="risk-label risk-med">{esc(key)}</span>'
    style = f'color: {color(info["color_key"])};'
    return (
        f'<span class="risk-label" style="{style}">'
        f'{info["icon"]} {esc(info["label"])}'
        f"</span>"
    )


def badge_confidence(confidence_pct: float | None) -> str:
    """Return an HTML badge for a 0-100 confidence percentage."""
    if confidence_pct is None:
        return badge_evidence("needs_more_data")
    pct = float(confidence_pct)
    level = confidence_level_for(pct)
    label = CONFIDENCE_LEVELS[level]["label"]
    style = f'color: {color(CONFIDENCE_LEVELS[level]["color_key"])};'
    return f'<span class="risk-label" style="{style}">{esc(label)} {esc(f"{pct:.0f}%")}</span>'


def badge_fixture(difficulty: str) -> str:
    """Return an HTML badge for a fixture difficulty (easy/medium/hard)."""
    key = str(difficulty).lower()
    info = FIXTURE_LEVELS.get(key)
    if info is None:
        return badge_fixture("medium")
    style = f'color: {color(info["color_key"])};'
    return f'<span class="risk-label" style="{style}">{info["icon"]} {esc(info["label"])}</span>'


def badge_model_agreement(rate: float | None) -> str:
    """Return an HTML badge for a V3-vs-V2 agreement rate.

    ``rate`` is a 0-1 proportion (as produced by
    :func:`services.comparison_reports.compute_agreement`), or None when no
    comparison exists.
    """
    if rate is None:
        return badge_evidence("needs_more_data")
    pct = max(0.0, min(100.0, float(rate) * 100.0))
    return badge_confidence(pct)


def badge_delta(value: float, invert: bool = False) -> str:
    """Return a colored +/- delta badge for a signed numeric change."""
    value = float(value)
    if abs(value) < 1e-9:
        return f'<span class="metric-delta">{esc("0")}</span>'
    positive = (value > 0) != invert
    css = "positive" if positive else "negative"
    sign = "+" if value > 0 else "-"
    return f'<span class="metric-delta {css}">{sign}{esc(f"{abs(value):.1f}")}</span>'


# ---------------------------------------------------------------------------
# Renderers (thin Streamlit wrappers)
# ---------------------------------------------------------------------------


def render_html(html: str) -> None:
    """Render a presenter-produced HTML fragment. Single markdown entry point."""
    st.markdown(html, unsafe_allow_html=True)


def render_badges(badge_htmls: list[str], separator: str = " ") -> None:
    """Render a run of badges inline."""
    if not badge_htmls:
        return
    render_html(separator.join(badge_htmls))


def render_position_badge(position: str) -> None:
    render_html(badge_position(position))


def render_risk_badge(level: str) -> None:
    render_html(badge_risk(level))


def render_evidence_badge(level: str) -> None:
    render_html(badge_evidence(level))


def render_confidence_badge(confidence_pct: float | None) -> None:
    render_html(badge_confidence(confidence_pct))


def render_fixture_badge(difficulty: str) -> None:
    render_html(badge_fixture(difficulty))
