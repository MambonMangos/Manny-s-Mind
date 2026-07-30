"""Reusable metric cards for the Streamlit dashboard."""

from __future__ import annotations

import streamlit as st


def render_metric_card(label: str, value: str, delta: str = "", positive: bool = True, delay: int = 0) -> None:
    """Render a single styled metric card via HTML."""
    delay_class = f" fade-in-delay-{delay}" if delay else ""
    delta_html = ""
    if delta:
        css = "positive" if positive else "negative"
        arrow = "+" if positive and not delta.startswith("-") and not delta.startswith("+") else ""
        delta_html = f'<div class="metric-delta {css}">{arrow}{delta}</div>'

    st.markdown(
        f"""
        <div class="metric-card fade-in{delay_class}">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value}</div>
            {delta_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_top_metrics(df) -> None:  # noqa: ANN001
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
