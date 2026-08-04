"""Evidence and trust-section rendering.

Implements the Trust Layer rule of the design system: every recommendation is
shown together with a trust block (evidence level, confidence, data quality,
model agreement, and the reasoning trail). Nothing is fabricated — when a
measure has never been recorded the corresponding slot is omitted, never
invented.
"""

from __future__ import annotations

from components.domain.models import Evidence, TrustSection
from components.ui import badges
from components.ui.base import div, esc, span
from services.learning_service import (
    get_evidence_description,
    get_evidence_level,
)

# Evidence level min-gameweek thresholds (single source mirrored from the
# learning service so the UI can map counts without importing the backend).
EVIDENCE_LEVEL_ORDER = (
    "weak",
    "needs_more_data",
    "moderate",
    "strong",
    "statistically_significant",
)


def evidence_from_gameweeks(n_gameweeks: int, consistency_score: float = 0.0) -> Evidence:
    """Build an :class:`Evidence` from the raw observation count."""
    level = get_evidence_level(n_gameweeks, consistency_score)
    return Evidence(
        level=level,
        n_gameweeks=n_gameweeks,
        description=get_evidence_description(level),
        consistency_score=consistency_score,
    )


def has_any_trust_data(ts: TrustSection) -> bool:
    """True when at least one trust slot has data worth rendering."""
    return bool(
        ts.evidence is not None
        or ts.confidence_pct is not None
        or ts.reasoning
        or ts.model_agreement is not None
        or ts.historical_accuracy is not None
        or ts.data_quality
    )


def data_quality_badge(data_quality: str) -> str:
    """Return an HTML badge for a data-quality label (high/medium/low)."""
    key = str(data_quality).strip().lower()
    if key == "high":
        return badges.badge_evidence("strong")
    if key == "medium":
        return badges.badge_evidence("moderate")
    if key == "low":
        return badges.badge_evidence("weak")
    return badges.badge_evidence("needs_more_data")


def _accuracy_badge(accuracy: float) -> str:
    """Return an HTML badge for a 0-1 historical accuracy rate."""
    pct = max(0.0, min(100.0, float(accuracy) * 100.0))
    return badges.badge_confidence(pct)


def trust_section_html(ts: TrustSection) -> str:
    """Present a trust section as HTML.

    Returns an empty string when there is no trust data at all, so callers can
    simply skip rendering.
    """
    if not has_any_trust_data(ts):
        return ""

    badge_htmls: list[str] = []
    if ts.evidence is not None:
        badge_htmls.append(badges.badge_evidence(ts.evidence.level))
    if ts.confidence_pct is not None:
        badge_htmls.append(badges.badge_confidence(ts.confidence_pct))
    if ts.data_quality:
        badge_htmls.append(data_quality_badge(ts.data_quality))
    if ts.model_agreement is not None:
        badge_htmls.append(badges.badge_model_agreement(ts.model_agreement))
    if ts.historical_accuracy is not None:
        badge_htmls.append(_accuracy_badge(ts.historical_accuracy))

    rows: list[str] = []
    if ts.evidence is not None and ts.evidence.description:
        rows.append(
            div(
                span(esc("Evidence: "), classes="caption-text")
                + span(esc(ts.evidence.description), classes="body-text"),
                classes="trust-note",
            )
        )
    if ts.reasoning:
        items = "".join(
            f"<li>{esc(r)}</li>" for r in ts.reasoning if str(r).strip()
        )
        if items:
            rows.append(
                div(
                    span(esc("Why: "), classes="caption-text")
                    + f'<ul class="trust-reasons">{items}</ul>',
                    classes="trust-note",
                )
            )

    inner = (
        f'<div class="trust-badges">{" ".join(badge_htmls)}</div>'
        + "".join(rows)
    )
    return div(inner, classes="trust-section")


def render_trust_section(ts: TrustSection | None) -> None:
    """Render a trust section below a recommendation (skips when empty)."""
    if ts is None:
        return
    import streamlit as st

    html = trust_section_html(ts)
    if html:
        st.markdown(html, unsafe_allow_html=True)
