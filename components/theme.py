"""Global theme – CSS overrides and Plotly dark template for Manny's FPL House.

Colours, typography, spacing, radii and breakpoints are defined once in
``components/design_tokens.py``. This module converts those tokens into the
CSS custom properties injected on every page and keeps the legacy public API
(colour constants + helpers) so existing pages and components keep working.

The ``:root`` custom-property block is generated from tokens via
``build_css_variables()``; the generated values are byte-identical to the
pre-refactor hardcoded block (asserted in tests/test_ui_components.py).
"""

from __future__ import annotations

from html import escape

import plotly.io as pio
import streamlit as st

from components import ui as _ui
from components.design_tokens import (
    COLOR_ACCENT_AMBER,
    COLOR_ACCENT_CYAN,
    COLOR_ACCENT_INDIGO,
    COLOR_MARKET_BUY,
    COLOR_MARKET_FALLER,
    COLOR_MARKET_RISER,
    COLOR_MARKET_SELL,
    COLOR_QUALITY_FAIR,
    COLOR_QUALITY_GOOD,
    COLOR_QUALITY_POOR,
    COLOR_RISK_HIGH,
    COLOR_RISK_LOW,
    COLOR_RISK_MED,
    FONT_FAMILY,
    build_css_variables,
    color,
)

# ---------------------------------------------------------------------------
# Semantic color roles (re-exported from design tokens)
#   - Market:  indigo/purple (transfers, ownership)
#   - Risk:    amber gradient (risk severity)
#   - Quality: emerald gradient (accuracy, performance)
#   - Fixture: green -> red (difficulty)
# ---------------------------------------------------------------------------

__all__ = [
    "COLOR_ACCENT_AMBER",
    "COLOR_ACCENT_CYAN",
    "COLOR_ACCENT_INDIGO",
    "COLOR_MARKET_BUY",
    "COLOR_MARKET_FALLER",
    "COLOR_MARKET_RISER",
    "COLOR_MARKET_SELL",
    "COLOR_QUALITY_FAIR",
    "COLOR_QUALITY_GOOD",
    "COLOR_QUALITY_POOR",
    "COLOR_RISK_HIGH",
    "COLOR_RISK_LOW",
    "COLOR_RISK_MED",
]

# ---------------------------------------------------------------------------
# Plotly dark template matching our color scheme
# ---------------------------------------------------------------------------

_MANNYS_TEMPLATE = {
    "layout": {
        "paper_bgcolor": color("surface_card"),
        "plot_bgcolor": color("surface_card"),
        "font": {"family": FONT_FAMILY, "color": color("text_secondary"), "size": 12},
        "title": {"font": {"size": 15, "color": color("text_primary"), "family": FONT_FAMILY}, "x": 0.02, "y": 0.97},
        "xaxis": {
            "gridcolor": color("surface_input"),
            "zerolinecolor": color("surface_input"),
            "linecolor": color("border"),
            "tickfont": {"size": 11, "color": color("text_muted")},
            "title": {"font": {"size": 12, "color": color("text_secondary")}},
        },
        "yaxis": {
            "gridcolor": color("surface_input"),
            "zerolinecolor": color("surface_input"),
            "linecolor": color("border"),
            "tickfont": {"size": 11, "color": color("text_muted")},
            "title": {"font": {"size": 12, "color": color("text_secondary")}},
        },
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"size": 11, "color": color("text_secondary")},
            "orientation": "h",
            "y": -0.15,
        },
        "margin": {"l": 50, "r": 20, "t": 40, "b": 50},
        "hoverlabel": {
            "bgcolor": color("surface_input"),
            "bordercolor": color("border"),
            "font": {"size": 12, "color": color("text_primary"), "family": FONT_FAMILY},
        },
        "colorway": [
            color("trust_primary"),
            color("accent_cyan"),
            color("success"),
            color("warning"),
            color("danger"),
            color("evidence"),
            color("pink_500"),
        ],
    }
}

pio.templates["mannys_dark"] = _MANNYS_TEMPLATE  # type: ignore[assignment]
pio.templates.default = "mannys_dark"


# ---------------------------------------------------------------------------
# Global CSS - injected once per page
# ---------------------------------------------------------------------------

_BASE_CSS = """
<style>
/* ── Base ────────────────────────────────────────────────────────────── */
/* Fonts fall back to system stacks — no external font CDN dependency
   (privacy: no third-party requests from visitors' browsers). */

__DESIGN_TOKENS__

/* Fix Streamlit defaults */
.stApp {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

section[data-testid="stSidebar"] {
    background-color: #0f0f14;
    border-right: 1px solid #1e1e28;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3 {
    color: var(--text-primary) !important;
    font-weight: 600;
}

/* ── Typography - single type ramp ────────────────────────────────── */
.hero-title {
    font-size: 3rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    color: var(--text-primary);
    line-height: 1.1;
}

.page-title {
    font-size: 1.75rem;
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.025em;
    margin-bottom: 0.25rem;
}

.page-subtitle {
    font-size: 0.9rem;
    color: var(--text-muted);
    font-weight: 400;
    margin-bottom: 1.5rem;
}

.section-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 0.75rem;
}

.section-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.01em;
    margin-bottom: 0.75rem;
}

.card-title {
    font-size: 1rem;
    font-weight: 700;
    color: var(--text-primary);
}

.body-text {
    font-size: 0.875rem;
    color: var(--text-secondary);
    line-height: 1.6;
}

.caption-text {
    font-size: 0.75rem;
    color: var(--text-muted);
}

/* ── Cards ───────────────────────────────────────────────────────────── */
.card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 1.25rem 1.5rem;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
    border-color: var(--color-accent-indigo);
    box-shadow: 0 0 0 1px rgba(99, 102, 241, 0.1);
}

.card-sm {
    padding: 0.875rem 1rem;
    border-radius: var(--radius-sm);
}

/* ── Metric cards ────────────────────────────────────────────────────── */
.metric-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius);
    padding: 1.25rem 1.5rem;
    transition: border-color 0.2s ease;
}

.metric-card:hover {
    border-color: var(--color-accent-indigo);
}

.metric-label {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
}

.metric-value {
    font-size: 1.75rem;
    font-weight: 700;
    color: var(--text-primary);
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    line-height: 1.1;
}

.metric-delta {
    font-size: 0.8rem;
    font-weight: 500;
    margin-top: 0.25rem;
}

.metric-delta.positive { color: var(--color-quality-good); }
.metric-delta.negative { color: var(--color-quality-poor); }

.metric-value.rating-good { color: var(--color-quality-good); }
.metric-value.rating-fair { color: var(--color-quality-fair); }
.metric-value.rating-poor { color: var(--color-quality-poor); }

/* ── Tags / badges ──────────────────────────────────────────────────── */
.tag {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 6px;
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

.tag-gkp { background: rgba(245, 158, 11, 0.15); color: #f59e0b; }
.tag-def { background: rgba(6, 182, 212, 0.15); color: #06b6d4; }
.tag-mid { background: rgba(99, 102, 241, 0.15); color: #6366f1; }
.tag-fwd { background: rgba(244, 63, 94, 0.15); color: #f43f5e; }

/* ── Risk badges ────────────────────────────────────────────────────── */
.risk-label {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
}

.risk-low { background: rgba(52, 211, 153, 0.15); color: var(--color-risk-low); }
.risk-med { background: rgba(251, 191, 36, 0.15); color: var(--color-risk-med); }
.risk-high { background: rgba(248, 113, 113, 0.15); color: var(--color-risk-high); }

/* ── Divider ─────────────────────────────────────────────────────────── */
.divider {
    height: 1px;
    background: var(--border-subtle);
    margin: 1.5rem 0;
}

/* ── Empty state ─────────────────────────────────────────────────────── */
.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem 2rem;
    text-align: center;
    color: var(--text-muted);
}

.empty-state-icon {
    font-size: 2.5rem;
    margin-bottom: 0.75rem;
    opacity: 0.4;
}

.empty-state-title {
    font-size: 1rem;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 0.3rem;
}

.empty-state-message {
    font-size: 0.85rem;
    color: var(--text-muted);
    max-width: 400px;
    line-height: 1.5;
}

/* ── Responsive metric grid ──────────────────────────────────────────── */
.metric-grid-4 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
}

.metric-grid-2 {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 1rem;
    margin-bottom: 1rem;
}

@media (max-width: 768px) {
    .metric-grid-4 {
        grid-template-columns: repeat(2, 1fr);
    }
}

/* ── Domain components ───────────────────────────────────────────────── */
.projection-points {
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 2rem;
    font-weight: 700;
    color: var(--text-primary);
    line-height: 1.1;
    margin: 0.5rem 0 0.25rem;
}

.projection-ci {
    margin-bottom: 0.75rem;
}

.trust-section {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border-subtle);
}

.trust-badges {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.4rem;
}

.trust-note {
    margin-top: 0.35rem;
    line-height: 1.5;
}

.trust-reasons {
    margin: 0.25rem 0 0;
    padding-left: 1.25rem;
}

.transfer-arrow {
    color: var(--text-muted);
    font-size: 1.1rem;
    margin: 0.5rem 0;
    text-align: center;
}

.transfer-in {
    margin-top: 0.15rem;
}

.chip-icon {
    font-size: 1.1rem;
}

.chip-action {
    font-weight: 600;
}

/* ── Scrollbar ───────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #3f3f46; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #52525b; }

/* ── Plotly chart containers ─────────────────────────────────────────── */
.js-plotly-plot .plotly {
    border-radius: var(--radius) !important;
}

/* ── Data table styling ──────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    overflow: hidden;
}

/* ── Streamlit metric overrides ──────────────────────────────────────── */
[data-testid="stMetric"] {
    background: var(--bg-secondary);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    padding: 1rem;
}

[data-testid="stMetricValue"] {
    font-family: 'JetBrains Mono', 'Fira Code', monospace !important;
    font-weight: 700 !important;
}

/* ── Multiselect / selectbox dark overrides ──────────────────────────── */
.stMultiSelect [data-baseweb="tag"],
.stSelectbox [data-baseweb="select"] {
    background-color: var(--bg-tertiary) !important;
}

/* ── Fade-in animation ───────────────────────────────────────────────── */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(12px); }
    to { opacity: 1; transform: translateY(0); }
}

.fade-in {
    animation: fadeInUp 0.4s ease-out both;
}

.fade-in-delay-1 { animation-delay: 0.05s; }
.fade-in-delay-2 { animation-delay: 0.10s; }
.fade-in-delay-3 { animation-delay: 0.15s; }
.fade-in-delay-4 { animation-delay: 0.20s; }
</style>
"""

_GLOBAL_CSS = _BASE_CSS.replace("__DESIGN_TOKENS__", build_css_variables())


def inject_theme() -> None:
    """Inject global CSS into the current Streamlit page. Call once per page."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Reusable HTML helpers
# ---------------------------------------------------------------------------


def page_header(title: str, subtitle: str = "") -> None:
    """Render a consistent page header with title and optional subtitle."""
    title = escape(str(title))
    st.markdown(f'<div class="page-title fade-in">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        subtitle = escape(str(subtitle))
        st.markdown(f'<div class="page-subtitle fade-in fade-in-delay-1">{subtitle}</div>', unsafe_allow_html=True)


def section_label(text: str) -> None:
    """Render an uppercase section label."""
    st.markdown(f'<div class="section-label">{escape(str(text))}</div>', unsafe_allow_html=True)


def section_title(text: str) -> None:
    """Render a section title."""
    st.markdown(f'<div class="section-title">{escape(str(text))}</div>', unsafe_allow_html=True)


def divider() -> None:
    """Render a subtle horizontal divider."""
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)


def position_tag(pos: str) -> str:
    """Return an HTML badge for a player position.

    Delegates to :func:`components.ui.badges.badge_position` — the single
    implementation of position badges.
    """
    return _ui.badges.badge_position(pos)


# ---------------------------------------------------------------------------
# Empty state component (delegated to the design-system implementation)
# ---------------------------------------------------------------------------


def render_empty_state(
    icon: str = "",
    title: str = "No data available",
    message: str = "",
    action_label: str | None = None,
    action_key: str | None = None,
) -> None:
    """Render a consistent empty state with optional action button."""
    _ui.states.render_empty_state(
        icon=icon,
        title=title,
        message=message,
        action_label=action_label or "",
        action_key=action_key or "",
    )


# ---------------------------------------------------------------------------
# Responsive metric grid
# ---------------------------------------------------------------------------


def render_metric_grid(columns: int = 4) -> str:
    """Return the CSS class for a responsive metric grid."""
    return f"metric-grid-{columns}"


# ---------------------------------------------------------------------------
# Chart styling helper — apply consistent layout to any figure
# ---------------------------------------------------------------------------


def style_chart(fig, height: int = 380, margin: dict | None = None) -> None:
    """Apply consistent mannys_dark styling to a plotly figure.

    Mutates the figure in place; no return value needed.
    """
    fig.update_layout(
        height=height,
        margin=margin or {"l": 10, "r": 20, "t": 10, "b": 10},
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#27272a", zerolinecolor="#27272a")
    fig.update_yaxes(gridcolor="#27272a", zerolinecolor="#27272a")


def style_px_chart(fig, height: int = 380, **extra) -> None:
    """Apply consistent styling to a plotly express figure (px.*)."""
    fig.update_layout(
        height=height,
        margin={"l": 10, "r": 20, "t": 30, "b": 10},
        hovermode="x unified",
        **extra,
    )
    fig.update_xaxes(gridcolor="#27272a", zerolinecolor="#27272a")
    fig.update_yaxes(gridcolor="#27272a", zerolinecolor="#27272a")
