"""Assistant Manager — intelligent FPL decision-support system.

Migrated to the design-system domain components (components/domain). This
page only adapts backend objects into domain dataclasses and calls the
``render_*`` helpers — it never builds recommendation markup by hand.
"""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from components.domain import (
    ChipCard,
    PlayerRef,
    TransferCard,
    TrustSection,
    render_chip_card,
    render_transfer_card,
)
from components.domain.squad import render_squad_rating, render_squad_summary_cards
from components.sidebar import render_refresh_button
from components.theme import divider, inject_theme, page_header, section_label
from components.ui import render_error, render_info, render_success, render_warning
from database.database import get_session
from services.assistant_manager.engine import run_assistant
from utils.constants import TEAM_ID
from utils.helpers import ensure_data_loaded

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
    render_info(
        "No squad data available yet. "
        "The Assistant Manager needs live gameweek data to analyze your squad. "
        "Once GW1 kicks off and you have registered your team, this page will activate."
    )
    st.stop()

squad_eval = report.squad_evaluation


# ---------------------------------------------------------------------------
# Adapters: backend objects -> domain dataclasses
# ---------------------------------------------------------------------------

def _to_player_ref(player) -> PlayerRef:
    return PlayerRef(
        player_id=player.player_id,
        web_name=player.web_name,
        team_short=player.team_short,
        position=player.position,
        price=player.price,
    )


def _to_transfer_card(rec) -> TransferCard:
    return TransferCard(
        out=_to_player_ref(rec.player_out),
        in_=_to_player_ref(rec.player_in),
        price_difference=rec.price_difference,
        expected_points_gained=rec.expected_points_gained,
        value_score_difference=rec.value_score_difference,
        fixture_improvement=rec.fixture_improvement,
        minutes_projection=rec.minutes_projection,
        ownership_difference=rec.ownership_difference,
        risk_level=str(rec.risk_level).lower(),
        confidence_pct=rec.confidence_rating,
        rank=rec.rank,
        reasoning=rec.reasoning,
        trust=TrustSection(
            confidence_pct=rec.confidence_rating,
            reasoning=[rec.reasoning] if rec.reasoning else [],
        ),
    )


def _to_chip_card(chip) -> ChipCard:
    return ChipCard(
        chip_name=chip.chip_name,
        chip_label=chip.chip_label,
        should_play=chip.should_play,
        confidence_pct=chip.confidence,
        best_gameweek=chip.best_gameweek,
        projected_gain=chip.projected_gain,
        reasoning=chip.reasoning,
        available=chip.available,
        used=chip.used,
    )


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
    render_squad_summary_cards(
        total_value=squad_eval.total_value,
        bank=squad_eval.bank,
        free_transfers=squad_eval.free_transfers,
        saved_transfers=squad_eval.saved_transfers,
    )

divider()

# ---------------------------------------------------------------------------
# Transfer Recommendations
# ---------------------------------------------------------------------------

section_label("Transfer Recommendations")

if report.transfer_plan and report.transfer_plan.transfers:
    for rec in report.transfer_plan.transfers:
        render_transfer_card(_to_transfer_card(rec))
else:
    render_info("No transfer recommendations at this time.")

divider()

# ---------------------------------------------------------------------------
# Chip Strategy
# ---------------------------------------------------------------------------

section_label("Chip Strategy")

if report.chip_recommendations:
    chip_cols = st.columns(4)
    for i, chip in enumerate(report.chip_recommendations):
        with chip_cols[i]:
            render_chip_card(_to_chip_card(chip))
else:
    render_info("No chip recommendations available.")

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

player_df = pd.DataFrame(player_data)
st.dataframe(player_df, use_container_width=True, hide_index=True)

# Strengths and Weaknesses
col_strengths, col_weaknesses = st.columns(2)

with col_strengths:
    st.markdown("**Strengths**")
    if squad_eval.strengths:
        for s in squad_eval.strengths[:10]:
            st.markdown(f"- {escape(s)}")
    else:
        render_info("No strengths identified.")

with col_weaknesses:
    st.markdown("**Weaknesses**")
    if squad_eval.weaknesses:
        for w in squad_eval.weaknesses[:10]:
            st.markdown(f"- {escape(w)}")
    else:
        render_info("No weaknesses identified.")

# Injuries and Risks
if squad_eval.injuries or squad_eval.rotation_risks:
    divider()
    section_label("Alerts")

    if squad_eval.injuries:
        st.markdown("**Injuries/Doubts**")
        for i in squad_eval.injuries:
            render_warning(i)

    if squad_eval.rotation_risks:
        st.markdown("**Rotation Risks**")
        for r in squad_eval.rotation_risks:
            render_warning(r)

# Fixture Analysis
if squad_eval.excellent_fixtures or squad_eval.poor_fixtures:
    divider()
    section_label("Fixture Analysis")

    col_easy, col_hard = st.columns(2)

    with col_easy:
        st.markdown("**Favorable Fixtures**")
        for f in squad_eval.excellent_fixtures:
            render_success(f)

    with col_hard:
        st.markdown("**Difficult Fixtures**")
        for f in squad_eval.poor_fixtures:
            render_error(f)

# Price Movers
if squad_eval.price_risers or squad_eval.price_fallers:
    divider()
    section_label("Price Movements")

    col_risers, col_fallers = st.columns(2)

    with col_risers:
        st.markdown("**Price Rises**")
        for r in squad_eval.price_risers:
            render_success(r)

    with col_fallers:
        st.markdown("**Price Falls**")
        for f in squad_eval.price_fallers:
            render_error(f)
