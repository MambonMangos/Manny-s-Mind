"""Onboarding — the welcome page where visitors enter their FPL Team ID.

Rendered by :func:`utils.team_context.require_team` whenever the session has
no validated team. Once a Team ID passes :func:`services.team_validation.validate_team_id`
it is stored in ``session_state.team_id`` and the visitor is dropped into the app.

No login, no password, no stored personal data — only a validated Team ID kept
in session memory for the duration of the visit.
"""

from __future__ import annotations

import streamlit as st

from components.theme import divider
from components.ui import render_error, render_success
from services.team_validation import TeamValidationStatus, validate_team_id
from utils.team_context import seed_from_url, set_current_team_id

_INPUT_KEY = "onboarding_team_id_input"


def render_onboarding() -> None:
    """Render the full onboarding / welcome experience."""
    seed = seed_from_url()
    default_value = str(seed) if seed else ""

    # ── Hero ────────────────────────────────────────────────────────────────
    st.markdown(
        '<div style="text-align:center; padding: 3rem 1rem 1rem 1rem;">'
        '<div class="hero-title">Manny&rsquo;s FPL House</div>'
        '<div style="font-size:1rem; font-weight:500; color:#6366f1; '
        'letter-spacing:0.06em; text-transform:uppercase; margin-top:0.5rem;">'
        'Data-Driven FPL Analytics</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div style="max-width:680px; margin:2rem auto 0 auto;">
            <div class="card fade-in" style="text-align:center;">
                <div class="page-title" style="font-size:1.4rem; margin-bottom:0.75rem;">
                    Welcome to Manny's FPL House
                </div>
                <div class="body-text" style="max-width:520px; margin:0 auto;">
                    To personalize your analysis, please enter your
                    Fantasy Premier League Team ID. We will verify it with the
                    official FPL website and then load your squad, history, and
                    recommendations.
                </div>
                <div class="caption-text" style="margin-top:1rem;">
                    No login. No password. Your Team ID stays in your browser
                    for this visit only.
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    divider()

    # ── Team ID form ────────────────────────────────────────────────────────
    _, mid, _ = st.columns([1, 2, 1])
    with mid:
        team_id_input = st.text_input(
            "Your Fantasy Premier League Team ID",
            value=default_value,
            key=_INPUT_KEY,
            placeholder="e.g. 123456",
            help="Find it in the URL when logged in at fantasy.premierleague.com — "
            "it is the number after /entry/.",
        )
        submitted = st.button(
            "Continue",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            with st.spinner("Checking your team with Fantasy Premier League..."):
                result = validate_team_id(team_id_input)

            if result.status == TeamValidationStatus.VALID:
                set_current_team_id(
                    result.team_id,
                    team_name=result.team_name or result.manager_name,
                )
                name = result.team_name or result.manager_name or "your team"
                render_success(f"Team found — {name}. Loading your dashboard...")
                st.rerun()
            else:
                render_error(result.message)

        # ── Help: how to find your Team ID ─────────────────────────────────
        with st.expander("Need help finding your Team ID?"):
            st.markdown(
                """
1. Go to **[fantasy.premierleague.com](https://fantasy.premierleague.com)** and log in.
2. Click **"My Team"** in the top navigation.
3. Look at the web address in your browser. It ends with something like
   `/entry/123456/`.
4. The number after `/entry/` — here `123456` — is your Team ID.
5. Type that number into the box above and click **Continue**.

Your Team ID is public information on the FPL website — anyone can look up
any team by its ID. Sharing it lets us fetch *your* squad and history.
                """,
                unsafe_allow_html=False,
            )

        # ── Trust footer ───────────────────────────────────────────────────
        st.markdown(
            """
            <div style="text-align:center; padding:2rem 0 1rem 0;">
                <div class="caption-text">
                    Made with ⚽ for fantasy football fans.
                    No account, no ads, no personal data stored.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
