"""About page – Manny's FPL House."""

from __future__ import annotations

import streamlit as st

from components.theme import inject_theme, divider
from components.sidebar import render_refresh_button
from utils.helpers import ensure_data_loaded

st.set_page_config(
    page_title="About",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

# ── Hero section ────────────────────────────────────────────────────────────

st.markdown(
    '<div style="text-align:center; padding: 3rem 0 1rem 0;">'
    '<div class="hero-title">Manny&rsquo;s FPL House</div>'
    '<div style="font-size:1.1rem; font-weight:500; color:#6366f1; '
    'letter-spacing:0.06em; text-transform:uppercase; margin-top:0.5rem;">'
    'Data-Driven FPL Analytics</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ── Icon row ────────────────────────────────────────────────────────────────

st.markdown(
    """
    <div style="display:flex; justify-content:center; gap:3rem;
                font-size:2.2rem; margin-bottom:2.5rem; opacity:0.7;">
        <span>⚽</span>
        <span>🧠</span>
        <span>📊</span>
        <span>🏆</span>
        <span>📈</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ── Intro text ──────────────────────────────────────────────────────────────

st.markdown(
    """
    <div style="max-width:720px; margin:0 auto 3rem auto; text-align:center;
                font-size:1.05rem; line-height:1.8; color:#a1a1aa;">
        This is a personal project I built for fun to explore Fantasy Premier
        League analytics. I have very little coding experience, but I was able
        to create this entire application using Language Models and Open Code.
        It is a work in progress and I am constantly adding new features and
        refining the design.
    </div>
    """,
    unsafe_allow_html=True,
)

divider()

# ── Feature cards ───────────────────────────────────────────────────────────

st.markdown(
    '<div class="section-label" style="text-align:center; margin-top:1.5rem;">'
    "What's Inside"
    "</div>",
    unsafe_allow_html=True,
)

c1, c2, c3, c4 = st.columns(4)

features = [
    ("⚽", "Player Rankings", "Filter, sort, and rank every FPL player by custom value scores."),
    ("📊", "Team Analysis", "Aggregate stats across all 20 Premier League clubs."),
    ("📈", "Player Comparison", "Head-to-head radar charts, fixture difficulty, and efficiency metrics."),
    ("🏆", "Team History", "Season-by-season performance and gameweek breakdowns."),
]

for col, (icon, title, desc) in zip([c1, c2, c3, c4], features):
    with col:
        st.markdown(
            f"""
            <div class="card" style="text-align:center; height:220px;
                        display:flex; flex-direction:column; justify-content:center;">
                <div style="font-size:2rem; margin-bottom:0.75rem;">{icon}</div>
                <div style="font-size:1rem; font-weight:700; color:#fafafa;
                            margin-bottom:0.5rem;">{title}</div>
                <div style="font-size:0.82rem; color:#71717a; line-height:1.5;">{desc}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ── Data bootstrap ──────────────────────────────────────────────────────────

divider()

ensure_data_loaded()
render_refresh_button()

st.markdown(
    """
    <div style="text-align:center; padding:1rem 0 2rem 0;">
        <div style="display:inline-block; background:rgba(16,185,129,0.1);
                    color:#10b981; padding:0.4rem 1rem; border-radius:8px;
                    font-size:0.8rem; font-weight:600;">
            &#10003; Data loaded &amp; ready
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
