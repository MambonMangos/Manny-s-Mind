"""Reusable metric cards for the Streamlit dashboard.

Legacy facade: delegates to the design-system primitives in
:mod:`components.ui` so there is a single implementation. New code should
import from ``components.ui`` or ``components.domain`` directly.
"""

from __future__ import annotations

import streamlit as st

from components.ui.cards import render_metric_card


def render_top_metrics(df) -> None:
    """Display the top-level KPI cards."""
    if df.empty:
        st.info("No player data available.")
        return

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        render_metric_card("Players", f"{len(df):,}", delay=0)
    with col2:
        render_metric_card("Avg Value Score", f"{df['value_score'].mean():.1f}", delay=1)
    with col3:
        render_metric_card("Highest Value Score", f"{df['value_score'].max():.1f}", delay=2)
    with col4:
        render_metric_card("Avg Ownership", f"{df['selected_by_percent'].mean():.1f}%", delay=3)
