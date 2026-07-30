"""Assistant Manager — intelligent FPL decision-support system."""

from __future__ import annotations

import streamlit as st

from components.theme import inject_theme, page_header, divider, section_label
from components.sidebar import render_refresh_button
from components.recommendation_card import (
    render_transfer_recommendation,
    render_chip_recommendation,
    render_squad_rating,
)
from database.database import get_session
from services.player_service import get_scored_players
from services.assistant_manager.engine import run_assistant
from utils.helpers import ensure_data_loaded
from utils.constants import TEAM_ID

st.set_page_config(page_title="Assistant Manager", layout="wide")
inject_theme()
ensure_data_loaded()
render_refresh_button()

page_header(
    "Assistant Manager",
    "Your FPL decision engine — analyzing your squad for data-driven recommendations on "
    "transfers, captaincy, chip strategy, and long-term planning. It evaluates player value, "
    "fixtures, form, ownership, price changes, and projected points while explaining the "
    "reasoning behind every recommendation. As the season progresses, it continuously compares "
    "predictions to actual outcomes to improve its accuracy over time.",
)

divider()

# ---------------------------------------------------------------------------
# Run the Assistant Engine
# ---------------------------------------------------------------------------

session = get_session()
try:
    with st.spinner("Running Assistant Manager analysis..."):
        report = run_assistant(session, TEAM_ID)
finally:
    session.close()

if report.squad_evaluation is None or not report.squad_evaluation.players:
    st.info(
        "No squad data available yet. "
        "The Assistant Manager needs live gameweek data to analyze your squad. "
        "Once GW1 kicks off and you have registered your team, this page will activate."
    )
    st.stop()

squad_eval = report.squad_evaluation

# ---------------------------------------------------------------------------
# Executive Summary
# ---------------------------------------------------------------------------

section_label("Executive Summary")

col1, col2, col3 = st.columns([1, 2, 1])

with col1:
    render_squad_rating(squad_eval.overall_rating)

with col2:
    st.markdown(report.executive_summary)

with col3:
    st.markdown(
        f"""
        <div class="card" style="text-align: center;">
            <div style="font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #71717a; margin-bottom: 0.5rem;">
                Squad Value
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 1.5rem; font-weight: 700; color: #fafafa;">
                £{squad_eval.total_value:.1f}m
            </div>
            <div style="font-size: 0.8rem; color: #71717a; margin-top: 0.25rem;">
                Bank: £{squad_eval.bank:.1f}m
            </div>
            <div style="font-size: 0.8rem; color: #71717a;">
                Free Transfers: {squad_eval.free_transfers}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

divider()

# ---------------------------------------------------------------------------
# Transfer Recommendations
# ---------------------------------------------------------------------------

section_label("Transfer Recommendations")

if report.transfer_plan and report.transfer_plan.transfers:
    for rec in report.transfer_plan.transfers:
        render_transfer_recommendation(rec)
else:
    st.info("No transfer recommendations at this time.")

divider()

# ---------------------------------------------------------------------------
# Chip Strategy
# ---------------------------------------------------------------------------

section_label("Chip Strategy")

if report.chip_recommendations:
    chip_cols = st.columns(4)
    for i, chip in enumerate(report.chip_recommendations):
        with chip_cols[i]:
            render_chip_recommendation(chip)
else:
    st.info("No chip recommendations available.")

divider()

# ---------------------------------------------------------------------------
# Squad Breakdown
# ---------------------------------------------------------------------------

section_label("Squad Breakdown")

# Player ratings
player_data = []
for p in squad_eval.players:
    player_data.append({
        "Player": p.web_name,
        "Team": p.team_short,
        "Pos": p.position,
        "Price": f"£{p.price:.1f}m",
        "Pts": p.total_points,
        "Form": p.form,
        "xGI/90": f"{p.xgi_per_90:.2f}",
        "Value": f"{p.value_score:.0f}",
        "Rating": f"{p.squad_rating:.0f}/100",
    })

import pandas as pd
player_df = pd.DataFrame(player_data)
st.dataframe(player_df, use_container_width=True, hide_index=True)

# Strengths and Weaknesses
col_strengths, col_weaknesses = st.columns(2)

with col_strengths:
    st.markdown("**Strengths**")
    if squad_eval.strengths:
        for s in squad_eval.strengths[:10]:
            st.markdown(f"- {s}")
    else:
        st.info("No strengths identified.")

with col_weaknesses:
    st.markdown("**Weaknesses**")
    if squad_eval.weaknesses:
        for w in squad_eval.weaknesses[:10]:
            st.markdown(f"- {w}")
    else:
        st.info("No weaknesses identified.")

# Injuries and Risks
if squad_eval.injuries or squad_eval.rotation_risks:
    divider()
    section_label("Alerts")

    if squad_eval.injuries:
        st.markdown("**Injuries/Doubts**")
        for i in squad_eval.injuries:
            st.warning(i)

    if squad_eval.rotation_risks:
        st.markdown("**Rotation Risks**")
        for r in squad_eval.rotation_risks:
            st.warning(r)

# Fixture Analysis
if squad_eval.excellent_fixtures or squad_eval.poor_fixtures:
    divider()
    section_label("Fixture Analysis")

    col_easy, col_hard = st.columns(2)

    with col_easy:
        st.markdown("**Favorable Fixtures**")
        for f in squad_eval.excellent_fixtures:
            st.success(f)

    with col_hard:
        st.markdown("**Difficult Fixtures**")
        for f in squad_eval.poor_fixtures:
            st.error(f)

# Price Movers
if squad_eval.price_risers or squad_eval.price_fallers:
    divider()
    section_label("Price Movements")

    col_risers, col_fallers = st.columns(2)

    with col_risers:
        st.markdown("**Price Rises**")
        for r in squad_eval.price_risers:
            st.success(r)

    with col_fallers:
        st.markdown("**Price Falls**")
        for f in squad_eval.price_fallers:
            st.error(f)
