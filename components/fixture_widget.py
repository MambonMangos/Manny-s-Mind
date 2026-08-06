"""Reusable fixture visualization components."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st


def render_fixture_score_bar(
    player_fixture_scores: list[dict],
    title: str = "Average Fixture Score",
    gw_range: tuple[int, int] | None = None,
) -> None:
    """Render a horizontal bar chart of player fixture scores.

    This is the SINGLE implementation — never build fixture score charts inline.
    """
    if not player_fixture_scores:
        st.info("No fixture data available.")
        return

    import pandas as pd
    pf_df = pd.DataFrame(player_fixture_scores).sort_values("score", ascending=False)

    colors = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#f43f5e"]

    fig = go.Figure()
    for i, (_, row) in enumerate(pf_df.iterrows()):
        fig.add_trace(go.Bar(
            x=[f"{row['player']}\n({row['team']})"],
            y=[row["score"]],
            text=[str(row["score"])],
            textposition="outside",
            marker_color=colors[i % len(colors)],
            name=row["player"],
            showlegend=False,
        ))

    if gw_range:
        title = f"{title} (GW{gw_range[0]}–{gw_range[1]})"

    fig.update_layout(
        title=title,
        yaxis_title="Fixture Score",
        yaxis={"range": [0, 110]},
        height=350,
    )
    st.plotly_chart(fig, use_container_width=True)


def render_fixture_heatmap(
    pivot_diff,
    text_labels,
) -> None:
    """Render a fixture difficulty heatmap.

    This is the SINGLE implementation — never build fixture heatmaps inline.
    """
    if pivot_diff.empty:
        st.info("No fixture data available.")
        return

    fig = go.Figure(data=go.Heatmap(
        z=pivot_diff.values,
        x=pivot_diff.columns.tolist(),
        y=[f"GW{gw}" for gw in pivot_diff.index],
        colorscale=[
            [0.0, "#10b981"],
            [0.25, "#34d399"],
            [0.5, "#f59e0b"],
            [0.75, "#f97316"],
            [1.0, "#ef4444"],
        ],
        text=text_labels.values,
        texttemplate="%{text}",
        textfont={"size": 11, "color": "#fafafa"},
        showscale=True,
        colorbar={"title": "Difficulty", "tickfont": {"color": "#a1a1aa"}},
        zmin=1,
        zmax=5,
    ))
    fig.update_layout(
        height=max(300, len(pivot_diff) * 40 + 100),
        xaxis_title="Team",
        yaxis={"autorange": "reversed"},
    )
    st.plotly_chart(fig, use_container_width=True)
