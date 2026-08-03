"""Reusable player card component."""

from __future__ import annotations

from html import escape

import streamlit as st


def render_player_cards(players_df, max_cards: int = 5) -> None:  # noqa: ANN001
    """Render a row of player cards with colored left border.

    This is the SINGLE implementation — never build player cards inline.
    """
    if players_df.empty:
        return

    colors = ["#6366f1", "#06b6d4", "#10b981", "#f59e0b", "#f43f5e"]
    card_cols = st.columns(min(len(players_df), max_cards))

    for i, (_, row) in enumerate(players_df.head(max_cards).iterrows()):
        with card_cols[i]:
            color = colors[i % len(colors)]
            web_name = escape(str(row["web_name"]))
            team_short = escape(str(row["team_short"]))
            position = escape(str(row["position"]))
            st.markdown(
                f"""
                <div class="card" style="border-left: 3px solid {color}; text-align:center;">
                    <div style="font-size:1.1rem; font-weight:700; color:#fafafa;">{web_name}</div>
                    <div style="font-size:0.8rem; color:#71717a; margin-bottom:0.5rem;">{team_short} · {position}</div>
                    <div style="font-family:'JetBrains Mono',monospace; font-size:1.4rem; font-weight:700; color:{color};">
                        £{row['price']:.1f}m
                    </div>
                    <div style="font-size:0.75rem; color:#71717a; margin-top:0.25rem;">
                        {row['total_points']} pts · {row['value_score']:.1f} value
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
