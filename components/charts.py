"""Reusable chart components for the Streamlit dashboard.

Consolidates repeated chart patterns into single functions:
  - render_horizontal_bar: replaces 4 identical chart blocks in 2_Player_Rankings.py
  - render_vertical_bar: replaces 9 similar chart blocks across pages
"""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from components.theme import style_chart


def render_horizontal_bar(
    labels: list[str],
    values: list[float | int],
    title: str = "",
    color: str = "",
    height: int | None = None,
    x_title: str = "",
    y_title: str = "",
    text_format: str = "{:,.0f}",
    hover_template: str = "",
) -> None:
    """Render a horizontal bar chart with dark theme styling.

    This is the SINGLE implementation — never build horizontal bar charts inline.
    """
    if not labels or not values:
        st.info("No data to display.")
        return

    if height is None:
        height = max(250, len(labels) * 36 + 60)

    formatted_text = [text_format.format(v) for v in values]

    if not hover_template:
        hover_template = "<b>%{y}</b><br>%{x:,.0f}<extra></extra>"

    fig = go.Figure(go.Bar(
        y=labels,
        x=values,
        orientation="h",
        marker_color=color,
        text=formatted_text,
        textposition="outside",
        hovertemplate=hover_template,
    ))

    style_chart(fig, height=height, margin={"l": 10, "r": 60, "t": 10, "b": 10})
    fig.update_xaxes(title=x_title)  # set after style_chart to avoid override

    st.plotly_chart(fig, use_container_width=True)


def render_vertical_bar(
    df,
    x: str,
    y: str,
    title: str = "",
    height: int = 380,
    x_title: str = "",
    y_title: str = "",
    text_position: str = "outside",
    color: str | None = None,
) -> None:
    """Render a vertical bar chart with dark theme styling.

    This is the SINGLE implementation — never build vertical bar charts inline.
    """
    import plotly.express as px

    if df.empty:
        st.info("No data to display.")
        return

    fig = px.bar(
        df,
        x=x,
        y=y,
        title=title,
        labels={x: x_title or x, y: y_title or y},
        color_discrete_sequence=[color] if color else None,
    )
    fig.update_layout(xaxis_tickangle=-45)
    style_chart(fig, height=height)
    st.plotly_chart(fig, use_container_width=True)
