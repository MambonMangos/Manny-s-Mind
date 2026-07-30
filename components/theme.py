"""Global theme – CSS overrides and Plotly dark template for Manny's FPL House."""

from __future__ import annotations

import streamlit as st
import plotly.io as pio

# ---------------------------------------------------------------------------
# Semantic color roles
#   - Market:  indigo/purple (transfers, ownership)
#   - Risk:    amber gradient (risk severity)
#   - Quality: emerald gradient (accuracy, performance)
#   - Fixture: green -> red (difficulty)
# ---------------------------------------------------------------------------

COLOR_MARKET_BUY = "#818cf8"    # indigo-400
COLOR_MARKET_SELL = "#a78bfa"   # violet-400
COLOR_MARKET_RISER = "#34d399"  # emerald-400
COLOR_MARKET_FALLER = "#fb7185" # rose-400

COLOR_RISK_LOW = "#34d399"
COLOR_RISK_MED = "#fbbf24"
COLOR_RISK_HIGH = "#f87171"

COLOR_QUALITY_GOOD = "#34d399"
COLOR_QUALITY_FAIR = "#fbbf24"
COLOR_QUALITY_POOR = "#f87171"

COLOR_ACCENT_INDIGO = "#6366f1"
COLOR_ACCENT_CYAN = "#06b6d4"
COLOR_ACCENT_AMBER = "#f59e0b"

# ---------------------------------------------------------------------------
# Plotly dark template matching our color scheme
# ---------------------------------------------------------------------------

_MANNYS_TEMPLATE = {
    "layout": {
        "paper_bgcolor": "#18181b",
        "plot_bgcolor": "#18181b",
        "font": {"family": "-apple-system, BlinkMacSystemFont, Inter, sans-serif", "color": "#a1a1aa", "size": 12},
        "title": {"font": {"size": 15, "color": "#fafafa", "family": "-apple-system, BlinkMacSystemFont, Inter, sans-serif"}, "x": 0.02, "y": 0.97},
        "xaxis": {
            "gridcolor": "#27272a",
            "zerolinecolor": "#27272a",
            "linecolor": "#3f3f46",
            "tickfont": {"size": 11, "color": "#71717a"},
            "title": {"font": {"size": 12, "color": "#a1a1aa"}},
        },
        "yaxis": {
            "gridcolor": "#27272a",
            "zerolinecolor": "#27272a",
            "linecolor": "#3f3f46",
            "tickfont": {"size": 11, "color": "#71717a"},
            "title": {"font": {"size": 12, "color": "#a1a1aa"}},
        },
        "legend": {
            "bgcolor": "rgba(0,0,0,0)",
            "font": {"size": 11, "color": "#a1a1aa"},
            "orientation": "h",
            "y": -0.15,
        },
        "margin": {"l": 50, "r": 20, "t": 40, "b": 50},
        "hoverlabel": {
            "bgcolor": "#27272a",
            "bordercolor": "#3f3f46",
            "font": {"size": 12, "color": "#fafafa", "family": "-apple-system, BlinkMacSystemFont, Inter, sans-serif"},
        },
        "colorway": ["#6366f1", "#06b6d4", "#34d399", "#fbbf24", "#f87171", "#8b5cf6", "#ec4899"],
    }
}

pio.templates["mannys_dark"] = _MANNYS_TEMPLATE  # type: ignore[assignment]
pio.templates.default = "mannys_dark"


# ---------------------------------------------------------------------------
# Global CSS - injected once per page
# ---------------------------------------------------------------------------

_GLOBAL_CSS = """
<style>
/* ── Base ────────────────────────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-primary: #09090b;
    --bg-secondary: #18181b;
    --bg-tertiary: #27272a;
    --bg-elevated: #1c1c24;
    --border: #3f3f46;
    --border-subtle: #27272a;
    --text-primary: #fafafa;
    --text-secondary: #a1a1aa;
    --text-muted: #71717a;

    /* Semantic colors */
    --color-market-buy: #818cf8;
    --color-market-sell: #a78bfa;
    --color-market-riser: #34d399;
    --color-market-faller: #fb7185;
    --color-risk-low: #34d399;
    --color-risk-med: #fbbf24;
    --color-risk-high: #f87171;
    --color-quality-good: #34d399;
    --color-quality-fair: #fbbf24;
    --color-quality-poor: #f87171;
    --color-accent-indigo: #6366f1;
    --color-accent-cyan: #06b6d4;
    --color-accent-amber: #f59e0b;

    --radius: 12px;
    --radius-sm: 8px;
}

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


def inject_theme() -> None:
    """Inject global CSS into the current Streamlit page. Call once per page."""
    st.markdown(_GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Reusable HTML helpers
# ---------------------------------------------------------------------------


def page_header(title: str, subtitle: str = "") -> None:
    """Render a consistent page header with title and optional subtitle."""
    st.markdown(f'<div class="page-title fade-in">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.markdown(f'<div class="page-subtitle fade-in fade-in-delay-1">{subtitle}</div>', unsafe_allow_html=True)


def section_label(text: str) -> None:
    """Render an uppercase section label."""
    st.markdown(f'<div class="section-label">{text}</div>', unsafe_allow_html=True)


def section_title(text: str) -> None:
    """Render a section title."""
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def divider() -> None:
    """Render a subtle horizontal divider."""
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)


def position_tag(pos: str) -> str:
    """Return an HTML badge for a player position."""
    css_class = f"tag-{pos.lower()}"
    return f'<span class="tag {css_class}">{pos}</span>'


# ---------------------------------------------------------------------------
# Issue 3: Empty state component
# ---------------------------------------------------------------------------


def render_empty_state(
    icon: str = "",
    title: str = "No data available",
    message: str = "",
    action_label: str | None = None,
    action_key: str | None = None,
) -> None:
    """Render a consistent empty state with optional action button."""
    html = f"""
    <div class="empty-state fade-in">
        <div class="empty-state-icon">{icon}</div>
        <div class="empty-state-title">{title}</div>
        <div class="empty-state-message">{message}</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
    if action_label and action_key:
        st.button(action_label, key=action_key, use_container_width=False)


# ---------------------------------------------------------------------------
# Issue 9: Responsive metric grid
# ---------------------------------------------------------------------------


def render_metric_grid(columns: int = 4) -> str:
    """Return the CSS class for a responsive metric grid."""
    return f"metric-grid-{columns}"


# ---------------------------------------------------------------------------
# Issue 5: Chart styling helper — apply consistent layout to any figure
# ---------------------------------------------------------------------------


def style_chart(fig, height: int = 380, margin: dict | None = None) -> None:
    """Apply consistent mannys_dark styling to a plotly figure.

    Mutates the figure in place; no return value needed.
    """
    fig.update_layout(
        height=height,
        margin=margin or dict(l=10, r=20, t=10, b=10),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="#27272a", zerolinecolor="#27272a")
    fig.update_yaxes(gridcolor="#27272a", zerolinecolor="#27272a")


def style_px_chart(fig, height: int = 380, **extra) -> None:
    """Apply consistent styling to a plotly express figure (px.*)."""
    fig.update_layout(
        height=height,
        margin=dict(l=10, r=20, t=30, b=10),
        hovermode="x unified",
        **extra,
    )
    fig.update_xaxes(gridcolor="#27272a", zerolinecolor="#27272a")
    fig.update_yaxes(gridcolor="#27272a", zerolinecolor="#27272a")
