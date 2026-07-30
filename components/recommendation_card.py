"""Reusable recommendation card components for Assistant Manager."""

from __future__ import annotations

import streamlit as st


def render_transfer_recommendation(rec) -> None:  # noqa: ANN001
    """Render a single transfer recommendation card.

    This is the SINGLE implementation — never build transfer recommendation UI inline.
    """
    risk_colors = {"Low": "#10b981", "Medium": "#f59e0b", "High": "#ef4444"}
    risk_color = risk_colors.get(rec.risk_level, "#71717a")

    st.markdown(
        f"""
        <div class="card" style="margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
                <div>
                    <span style="font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: #71717a;">
                        Transfer #{rec.rank}
                    </span>
                </div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 6px; background: rgba({risk_color}, 0.15); color: {risk_color};">
                        {rec.risk_level} Risk
                    </span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 700; color: {'#10b981' if rec.expected_points_gained > 0 else '#ef4444'};">
                        {rec.expected_points_gained:+.1f} pts
                    </span>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.75rem;">
                <div style="text-align: right; flex: 1;">
                    <div style="font-size: 1.1rem; font-weight: 700; color: #fafafa;">{rec.player_out.web_name}</div>
                    <div style="font-size: 0.8rem; color: #71717a;">{rec.player_out.team_short} · {rec.player_out.position} · £{rec.player_out.price:.1f}m</div>
                </div>
                <div style="font-size: 1.2rem; color: #71717a;">→</div>
                <div style="flex: 1;">
                    <div style="font-size: 1.1rem; font-weight: 700; color: #fafafa;">{rec.player_in.web_name}</div>
                    <div style="font-size: 0.8rem; color: #71717a;">{rec.player_in.team_short} · {rec.player_in.position} · £{rec.player_in.price:.1f}m</div>
                </div>
            </div>
            <div style="display: flex; gap: 1.5rem; font-size: 0.75rem; color: #a1a1aa; margin-bottom: 0.5rem;">
                <span>Value: {rec.value_score_difference:+.1f}</span>
                <span>Fixture: {rec.fixture_improvement:+.2f}</span>
                <span>Minutes: {rec.minutes_projection:.0f}/90</span>
                <span>Confidence: {rec.confidence_rating:.0f}/100</span>
            </div>
            <div style="font-size: 0.8rem; color: #a1a1aa; line-height: 1.5;">
                {rec.reasoning}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_chip_recommendation(chip) -> None:  # noqa: ANN001
    """Render a single chip recommendation card.

    This is the SINGLE implementation — never build chip recommendation UI inline.
    """
    status_color = "#10b981" if chip.should_play else "#71717a"
    status_text = "PLAY" if chip.should_play else "HOLD"

    st.markdown(
        f"""
        <div class="card" style="margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <div style="font-size: 1rem; font-weight: 700; color: #fafafa;">{chip.chip_label}</div>
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="font-size: 0.7rem; font-weight: 600; padding: 0.2rem 0.6rem; border-radius: 6px; background: rgba({status_color}, 0.15); color: {status_color};">
                        {status_text}
                    </span>
                    <span style="font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 700; color: #fafafa;">
                        {chip.confidence:.0f}/100
                    </span>
                </div>
            </div>
            {"<div style='font-size: 0.8rem; color: #10b981; margin-bottom: 0.5rem;'>Best Gameweek: GW" + str(chip.best_gameweek) + "</div>" if chip.best_gameweek and chip.should_play else ""}
            <div style="font-size: 0.8rem; color: #a1a1aa; line-height: 1.5;">
                {chip.reasoning}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_squad_rating(overall_rating: float) -> None:
    """Render a squad rating gauge."""
    color = "#10b981" if overall_rating >= 75 else "#f59e0b" if overall_rating >= 55 else "#ef4444"

    st.markdown(
        f"""
        <div class="card" style="text-align: center; padding: 2rem;">
            <div style="font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: #71717a; margin-bottom: 0.5rem;">
                Squad Rating
            </div>
            <div style="font-family: 'JetBrains Mono', monospace; font-size: 3rem; font-weight: 700; color: {color};">
                {overall_rating:.0f}/100
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
