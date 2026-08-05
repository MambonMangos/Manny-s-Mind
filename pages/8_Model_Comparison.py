"""Model Comparison Dashboard — V3 production vs V2 shadow (control group).

Scientific validation + explainability layer for the prediction models:

  - Alignment summary metrics (correlation, mean diff, agreement).
  - V2-vs-V3 scatter plot and largest-disagreement table.
  - Per-player explainability panel (component breakdown + contributing factors).
  - Captaincy / transfer / undervalued recommendation differences.
  - Evidence-threshold status (weak → statistically_significant).

Version 3 (xPts) is the primary production model. V1 (value-score engines) and
V2 (projection_v2) run as *shadow / control* models: they are validated against
V3 over time (accuracy, calibration, bias, drift) and are never removed.
Shadow models are evaluated here; no single gameweek drives any change.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.sidebar import render_refresh_button
from components.theme import (
    COLOR_ACCENT_INDIGO,
    COLOR_QUALITY_GOOD,
    COLOR_QUALITY_POOR,
    COLOR_RISK_HIGH,
    divider,
    inject_theme,
    page_header,
    section_label,
    section_title,
    style_chart,
)
from database.crud import get_players_dataframe
from database.database import get_session
from database.models import Gameweek, PredictionVersion
from engines.fixture_engine import build_fixture_map
from features import build_feature_store
from services.comparison_reports import (
    build_comparison_report,
    disagreements_to_dataframe,
)
from services.fixture_service import fetch_fixtures
from services.player_service import get_scored_players
from utils.config import get_config_hash
from utils.constants import get_active_team_id
from utils.helpers import ensure_data_loaded

st.set_page_config(page_title="Model Comparison", layout="wide")
inject_theme()
page_header(
    "Model Comparison",
    "V3 production vs V2 shadow model — validate the control group, don't regress.",
)
ensure_data_loaded()
render_refresh_button()


# ------------------------------------------------------------------
# Small display helpers
# ------------------------------------------------------------------

def _captain_rows(ranking: dict) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "Rank": r["rank"],
            "Player": r["web_name"],
            "Pos": r["position"],
            "Team": r.get("team_short", ""),
            "Pts": f"{r['projected_points']:.1f}",
        }
        for r in ranking.get("ranked", [])
    ])


def _transfer_rows(items: list) -> pd.DataFrame:
    return pd.DataFrame([
        {"In": r["player_in_name"], "Out": r["player_out_name"],
         "Gain": f"{r['gain']:+.2f}", "Type": r["type"]}
        for r in items
    ])


def _undervalued_rows(items: list) -> pd.DataFrame:
    return pd.DataFrame([
        {"Player": r["web_name"], "Pos": r["position"],
         "1GW Pts": f"{r['points']:.1f}", "Score": f"{r['score']:.0f}"}
        for r in items
    ])


def _render_evidence_level(evidence: dict) -> None:
    """Render the evidence-level status banner."""
    level = evidence.get("level", "weak")
    icons = {
        "weak": "🔴",
        "needs_more_data": "🟡",
        "moderate": "🟠",
        "strong": "🟢",
        "statistically_significant": "✅",
    }
    colors = {
        "weak": "#f87171",
        "needs_more_data": "#fbbf24",
        "moderate": "#fb923c",
        "strong": "#34d399",
        "statistically_significant": "#34d399",
    }
    icon = icons.get(level, "⚪")
    color = colors.get(level, "#a1a1aa")
    n = evidence.get("n_validated_gameweeks", 0)
    next_tier = ""
    if evidence.get("next_level"):
        next_tier = (
            f"<div class='caption-text' style='margin-top:0.25rem;'>Next tier: "
            f"<b>{evidence.get('next_level')}</b> in "
            f"{evidence.get('gameweeks_to_next_level', 0)} more gameweek(s).</div>"
        )
    st.markdown(
        f"""
        <div class="card fade-in" style="border-left: 3px solid {color};">
            <div class="metric-label">Evidence Level · V3 vs V2</div>
            <div style="font-size:1.1rem; font-weight:700; color:#fafafa;">
                {icon} {level.replace('_', ' ').title()}
                <span style="color:#71717a; font-weight:400; font-size:0.85rem;">
                    · {n} validated gameweek{'s' if n != 1 else ''}
                </span>
            </div>
            <div class="caption-text" style="margin-top:0.4rem;">
                {evidence.get('description', '')}
            </div>
            {next_tier}
        </div>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------
# Data bootstrap
# ------------------------------------------------------------------

def _load_squad(session, player_df: pd.DataFrame) -> list[int]:
    """Best-effort fetch of the user's current squad player IDs."""
    try:
        from services.team_service import fetch_team_data, resolve_player_names

        team_data = fetch_team_data(get_active_team_id(), gameweeks=list(range(1, 10)))
        picks_map = team_data.picks
        if not picks_map:
            return []
        latest_gw = max(picks_map.keys())
        squad_df = resolve_player_names(picks_map[latest_gw].picks, player_df)
        if squad_df.empty:
            return []
        return [int(pid) for pid in squad_df["id"].tolist()]
    except Exception:  # noqa: BLE001 - squad is optional for this page
        return []


def _build_store(session, gameweek_id: int):
    """Build the FeatureStore shared by the V2 and V3 engines."""
    player_df = get_scored_players(session)
    if player_df.empty:
        return None, player_df

    team_df = get_players_dataframe(session)
    team_name_map = {}
    if not team_df.empty:
        team_name_map = dict(zip(team_df["team_id"], team_df["team_name"]))

    fixtures_raw = fetch_fixtures()
    fixture_map = build_fixture_map(fixtures_raw)
    config_hash = get_config_hash("prediction")

    store = build_feature_store(
        players_df=player_df,
        fixture_map=fixture_map,
        team_name_map=team_name_map,
        gameweek_id=gameweek_id,
        config_hash=config_hash,
    )
    return store, player_df


def _load_ledger_alignment(session, gameweek_id: int):
    """Fetch stored primary(V3)+shadow(V2) projections for the scatter plot."""
    from database.crud import get_projections
    from utils.config import get_primary_model_id, get_shadow_model_ids

    primary_model = get_primary_model_id()
    shadow_models = get_shadow_model_ids()
    shadow_model = shadow_models[0] if shadow_models else None

    primary_vid = shadow_vid = None
    for pv in session.query(PredictionVersion).all():
        if pv.model_name == primary_model:
            primary_vid = pv.id
        elif shadow_model is not None and pv.model_name == shadow_model:
            shadow_vid = pv.id
    if primary_vid is None or shadow_vid is None:
        return None

    v3_list = get_projections(session, primary_vid, gameweek_id)
    v2_list = get_projections(session, shadow_vid, gameweek_id)
    if not v3_list or not v2_list:
        return None
    return v3_list, v2_list


# ------------------------------------------------------------------
# Controls
# ------------------------------------------------------------------

session = get_session()
try:
    gameweek_ids = [g.id for g in session.query(Gameweek).order_by(Gameweek.id).all()]
    default_gw = max(gameweek_ids) if gameweek_ids else 0
finally:
    session.close()

if not gameweek_ids:
    st.warning("No gameweeks in the database yet. Refresh data first.")
    st.stop()

col_gw, col_persist, col_run = st.columns([2, 2, 1])
with col_gw:
    selected_gw = st.selectbox(
        "Gameweek", gameweek_ids, index=gameweek_ids.index(default_gw),
        help="Run the V3 (production) and V2 (shadow) engines side-by-side for this gameweek.",
    )
with col_persist:
    persist = st.checkbox(
        "Persist V3 version to ledger",
        value=False,
        help="Write the V3 forecast as an append-only prediction version "
             "so it can be validated once actuals arrive.",
    )
with col_run:
    run = st.button("Run Comparison", type="primary", use_container_width=True)

if not run:
    st.info(
        "Select a gameweek and press **Run Comparison** to generate the "
        "scientific V2-vs-V3 report. V3 is the production model; V2 is the "
        "shadow/control group, evaluated here and never removed."
    )
    st.stop()

# ------------------------------------------------------------------
# Run comparison
# ------------------------------------------------------------------

with st.spinner("Running V3 + V2 projections and building the comparison report…"):
    session = get_session()
    try:
        store, player_df = _build_store(session, selected_gw)
        if store is None:
            st.warning("No player data found. Refresh data first.")
            st.stop()

        current_squad = _load_squad(session, player_df)

        report = build_comparison_report(
            store=store,
            gameweek_id=selected_gw,
            session=session,
            persist=persist,
            current_squad=current_squad,
        )
        session.commit()
    except Exception as exc:  # noqa: BLE001 - surface failures without crashing
        st.error(f"Comparison failed: {exc}")
        st.stop()
    finally:
        session.close()

if "error" in report.alignment:
    st.warning(report.alignment["error"])
    st.stop()

# ------------------------------------------------------------------
# Evidence banner + summary metrics
# ------------------------------------------------------------------

section_label("Scientific Evidence Status")
_render_evidence_level(report.evidence)
divider()

section_label("Alignment Summary")
alignment = report.alignment
agreement = report.agreement

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("Players Compared", alignment.get("n_common_players", 0))
with c2:
    corr = alignment.get("correlation")
    st.metric("Correlation", f"{corr:.3f}" if corr is not None else "N/A")
    st.caption("How similarly V3 (production) and V2 (shadow) rank players")
with c3:
    mad = alignment.get("mean_abs_diff")
    st.metric("Mean |Δ|", f"{mad:.2f}" if mad is not None else "N/A")
    st.caption("Average absolute V2-vs-V3 difference (pts)")
with c4:
    st.metric("Mean Δ (V3−V2)", f"{alignment.get('mean_diff_v3_minus_v2', 0):+.3f}")
    st.caption("Overall bias direction of V3 vs the V2 control group")
with c5:
    rate = agreement.get("overall_rate")
    st.metric("Agreement Rate", f"{rate:.0%}" if rate is not None else "N/A")
    st.caption(f"±{agreement.get('threshold', 0.75):.2f} pts threshold")

divider()

# ------------------------------------------------------------------
# Scatter plot (from the in-memory ledger pair when available)
# ------------------------------------------------------------------

section_label("Projection Alignment")
section_title("V3 xPts (production) vs V2 Projected Points (shadow)")
st.caption(
    "Each point is one player. Color shows the signed difference (V3 − V2); "
    "players far from the diagonal are where the models disagree."
)

session = get_session()
try:
    ledger_pair = _load_ledger_alignment(session, selected_gw)
finally:
    session.close()

if ledger_pair:
    v3_list, v2_list = ledger_pair
    v3_map = {p.player_id: p.projected_points for p in v3_list}
    v2_map = {p.player_id: p.projected_points for p in v2_list}
    common_ids = sorted(set(v3_map) & set(v2_map))
    x = [v2_map[pid] for pid in common_ids]
    y = [v3_map[pid] for pid in common_ids]
    deltas = [y[i] - x[i] for i in range(len(common_ids))]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="markers",
        marker={
            "size": 9, "opacity": 0.75,
            "color": deltas, "colorscale": "RdYlGn_r", "cmin": -3, "cmax": 3,
            "colorbar": {"title": "Δ (V3−V2)"},
        },
        text=[f"P{pid}" for pid in common_ids],
        hovertemplate="V2: %{x:.1f}<br>V3: %{y:.1f}<br>Δ: %{marker.color:+.2f}<extra></extra>",
    ))
    max_val = max(max(x), max(y)) * 1.05
    fig.add_trace(go.Scatter(
        x=[0, max_val], y=[0, max_val],
        mode="lines", line={"color": "#3f3f46", "dash": "dash", "width": 1},
        name="Perfect agreement",
    ))
    fig.update_layout(
        xaxis_title="V2 Projected Points",
        yaxis_title="V3 xPts",
    )
    style_chart(fig, height=460, margin={"l": 10, "r": 20, "t": 10, "b": 10})
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(
        "No stored V2/V3 ledger pair for this gameweek. Run the comparison "
        "with **Persist V3 version to ledger** checked (or run the Assistant "
        "Manager, which persists both versions), then validate both models in "
        "the Model Analytics page for a scatter plot of stored data."
    )

divider()

# ------------------------------------------------------------------
# Largest disagreements
# ------------------------------------------------------------------

section_label("Largest Disagreements")
section_title("Where do the V2 shadow and V3 production models most strongly disagree?")
st.caption(
    "Sorted by absolute difference. Direction shows whether V3 rates the "
    "player higher or lower than V2. Explainable via the panel below."
)

if report.disagreements:
    df_dis = disagreements_to_dataframe(report.disagreements)
    display = df_dis.copy()
    display.columns = ["ID", "Player", "Pos", "V2 Pts", "V3 Pts", "Δ", "Direction"]
    display["Δ"] = display["Δ"].map(lambda v: f"{v:+.2f}")
    display["Direction"] = display["Direction"].map(
        lambda d: "V3 higher" if d == "v3_higher" else "V3 lower"
    )
    st.dataframe(display, use_container_width=True, hide_index=True, height=400)

    fig_bar = go.Figure(go.Bar(
        y=df_dis["web_name"] + " (" + df_dis["position"] + ")",
        x=df_dis["delta"],
        orientation="h",
        marker_color=[
            COLOR_QUALITY_GOOD if d >= 0 else COLOR_QUALITY_POOR
            for d in df_dis["delta"]
        ],
        text=[f"{d:+.2f}" for d in df_dis["delta"]],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>Δ: %{x:+.2f} pts<extra></extra>",
    ))
    fig_bar.update_layout(
        xaxis_title="Δ (V3 − V2, pts)",
        height=max(260, len(df_dis) * 34 + 60),
        margin={"l": 10, "r": 40, "t": 10, "b": 10},
    )
    fig_bar.update_xaxes(gridcolor="#27272a", zerolinecolor="#3f3f46")
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No disagreements above threshold — V2 and V3 are in close agreement.")
divider()

# ------------------------------------------------------------------
# Explainability panel
# ------------------------------------------------------------------

section_label("Explainability Panel")
section_title("Why does V3 project this player's points?")
st.caption(
    "Select a player to see the V3 component breakdown: expected minutes, "
    "xPts/90, start probability, rotation risk, confidence intervals and the "
    "drivers behind their forecast."
)

from engines.expected_projection_engine import run_expected_projection

session = get_session()
try:
    store, _ = _build_store(session, selected_gw)
finally:
    session.close()

if store is not None:
    with st.spinner("Computing V3 explainability breakdown…"):
        v3_full = run_expected_projection(store, selected_gw)
    v3_full_map = {p.player_id: p for p in v3_full}

    options = {}
    for d in report.disagreements:
        options.setdefault(d.web_name, d.player_id)
    for p in v3_full:
        options.setdefault(p.web_name, p.player_id)

    selected_player = st.selectbox(
        "Player", list(options.keys()), index=0,
        help="Players from the disagreement list appear first.",
    )
    proj = v3_full_map.get(options[selected_player])

    if proj is not None:
        factors = proj.contributing_factors or {}

        col_left, col_right = st.columns([1, 1])
        with col_left:
            st.markdown(
                f'<div class="card">'
                f'<div style="font-size:0.7rem; font-weight:600; text-transform:uppercase; '
                f'letter-spacing:0.08em; color:#71717a;">Projection</div>'
                f'<div style="font-size:2rem; font-weight:800; color:#fafafa; '
                f'font-family: JetBrains Mono, monospace; margin:0.25rem 0;">'
                f'{proj.projected_points:.2f} <span style="font-size:1rem; color:#71717a;">xPts</span></div>'
                f'<div class="caption-text">GW {proj.gameweek_id} · {proj.position} · '
                f'confidence {proj.confidence:.0f}/100</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.markdown("**Contributing factors**")
            st.json(factors)
        with col_right:
            c1e, c2e = st.columns(2)
            with c1e:
                st.metric("xPts / 90", f"{proj.xpts_per_90:.3f}")
                st.metric("Expected Minutes", f"{proj.expected_minutes:.0f}")
                st.metric("Start Probability", f"{factors.get('start_probability', 0):.0%}")
            with c2e:
                st.metric("Minutes Factor", f"{factors.get('minutes_factor', 0):.2f}")
                rotation = factors.get("rotation_risk", "unknown")
                risk_color = {
                    "high": COLOR_RISK_HIGH, "medium": "#fbbf24", "low": COLOR_QUALITY_GOOD,
                }.get(rotation, "#a1a1aa")
                st.markdown(
                    f'<div style="margin-top:1rem;">'
                    f'<div class="metric-label">Rotation Risk</div>'
                    f'<span style="color:{risk_color}; font-weight:700; text-transform:uppercase; '
                    f'font-size:0.9rem;">{rotation}</span></div>',
                    unsafe_allow_html=True,
                )
                st.metric("Data Quality", proj.data_quality.replace("_", " ").title())

        divider()

        section_title("Component Breakdown")
        st.caption(
            "The projected points decomposed into the FPL scoring sources "
            "that drive them (before any clamping)."
        )
        comps = {
            "Goals": proj.goals_proj,
            "Assists": proj.assists_proj,
            "Clean Sheet": proj.clean_sheet_proj,
            "Bonus": proj.bonus_proj,
            "Other (saves/cards/set-piece)": proj.other_proj,
        }
        fig_comp = go.Figure(go.Bar(
            x=[max(v, 0) for v in comps.values()],
            y=list(comps.keys()),
            orientation="h",
            marker_color=COLOR_ACCENT_INDIGO,
            text=[f"{v:.2f}" for v in comps.values()],
            textposition="outside",
        ))
        fig_comp.update_layout(height=280, margin={"l": 10, "r": 40, "t": 10, "b": 10})
        fig_comp.update_xaxes(gridcolor="#27272a")
        st.plotly_chart(fig_comp, use_container_width=True)

        section_title("Confidence Intervals")
        ci1, ci2 = st.columns(2)
        with ci1:
            st.metric(
                "80% CI",
                f"[{proj.ci_80_low:.2f}, {proj.ci_80_high:.2f}]",
                delta=f"±{(proj.ci_80_high - proj.ci_80_low) / 2:.2f}",
            )
        with ci2:
            st.metric(
                "95% CI",
                f"[{proj.ci_95_low:.2f}, {proj.ci_95_high:.2f}]",
                delta=f"±{(proj.ci_95_high - proj.ci_95_low) / 2:.2f}",
            )

divider()

# ------------------------------------------------------------------
# Captaincy, transfers, undervalued differences
# ------------------------------------------------------------------

section_label("Recommendation Differences")
col_cap, col_tx = st.columns(2)

with col_cap:
    section_title("Captaincy")
    cap = report.captain
    if cap.get("v2_captain_id"):
        v2_top = cap["v2"]["top"]
        v3_top = cap["v3"]["top"]
        if cap.get("captain_agree"):
            st.success(
                f"Both models pick **{v2_top['web_name']}** "
                f"({v2_top['projected_points']:.1f} pts)."
            )
        else:
            st.warning(
                f"V2 picks **{v2_top['web_name']}** ({v2_top['projected_points']:.1f} pts) "
                f"but V3 prefers **{v3_top['web_name']}** ({v3_top['projected_points']:.1f} pts)."
            )
        st.markdown("**V2 top 3**")
        st.dataframe(_captain_rows(cap["v2"]), use_container_width=True, hide_index=True, height=180)
        st.markdown("**V3 top 3**")
        st.dataframe(_captain_rows(cap["v3"]), use_container_width=True, hide_index=True, height=180)
    else:
        st.info("No projections available for captaincy comparison.")

with col_tx:
    section_title("Transfers")
    tx = report.transfers
    if tx.get("available"):
        st.markdown(
            f"Shared top-{tx.get('top_n')}: **{tx.get('shared_top_n', 0)}** "
            f"of {tx.get('top_n', 3)} recommendations."
        )
        if tx.get("v2") or tx.get("v3"):
            colv2, colv3 = st.columns(2)
            with colv2:
                st.markdown("**V2 recommendations**")
                st.dataframe(_transfer_rows(tx["v2"]), use_container_width=True, hide_index=True, height=220)
            with colv3:
                st.markdown("**V3 recommendations**")
                st.dataframe(_transfer_rows(tx["v3"]), use_container_width=True, hide_index=True, height=220)
        else:
            st.info("No transfer opportunities found with either model.")
    else:
        st.info(tx.get("message", "Transfer comparison unavailable."))

divider()

section_label("Undervalued Players")
uv = report.undervalued
if uv.get("v2") or uv.get("v3"):
    st.markdown(
        f"Shared top-{uv.get('top_n')}: **{uv.get('shared_top_n', 0)}** "
        f"of {uv.get('top_n', 5)} picks."
    )
    colu2, colu3 = st.columns(2)
    with colu2:
        st.markdown("**V2 undervalued**")
        st.dataframe(_undervalued_rows(uv["v2"]), use_container_width=True, hide_index=True, height=220)
    with colu3:
        st.markdown("**V3 undervalued**")
        st.dataframe(_undervalued_rows(uv["v3"]), use_container_width=True, hide_index=True, height=220)
else:
    st.info("No undervalued player data available.")

divider()

# ------------------------------------------------------------------
# Evidence framework ladder
# ------------------------------------------------------------------

section_label("Evidence Framework")
section_title("What would it take to keep trusting V3?")
st.caption(
    "V3 is the production model; V2 is the shadow/control group. Sustained "
    "multi-gameweek evidence is required before any model change — never a "
    "single result."
)

ladder = [
    ("weak", 1, "Preliminary — 1 gameweek, could be noise. Observe only."),
    ("needs_more_data", 2, "Early signal — 2 gameweeks. Not yet reliable."),
    ("moderate", 3, "Consistent pattern across 3–4 gameweeks. Monitor."),
    ("strong", 5, "Reliable pattern across 5+ gameweeks. Candidate for review."),
    ("statistically_significant", 10, "High confidence across 10+ gameweeks. Actionable."),
]
icons = {"weak": "🔴", "needs_more_data": "🟡", "moderate": "🟠", "strong": "🟢", "statistically_significant": "✅"}
current = report.evidence.get("level", "weak")

for level, gw_count, desc in ladder:
    reached = report.evidence.get("n_validated_gameweeks", 0) >= gw_count
    active = level == current
    color = "#34d399" if reached else "#71717a"
    border = f"3px solid {COLOR_ACCENT_INDIGO}" if active else "1px solid #27272a"
    st.markdown(
        f"""
        <div class="card-sm" style="margin-bottom:0.5rem; border: {border}; opacity: {1 if reached else 0.7};">
            <span style="font-weight:700; color:{color};">{icons[level]} {level.replace('_', ' ').title()}</span>
            <span style="color:#71717a; font-size:0.8rem;"> · ≥{gw_count} GWs</span>
            <span style="color:#a1a1aa; font-size:0.8rem; display:block; margin-top:0.2rem;">{desc}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.markdown(report.evidence.get("promotion_criteria", ""))
if report.insights:
    divider()
    section_label("Key Insights")
    for i, insight in enumerate(report.insights, 1):
        st.markdown(f"**{i}.** {insight}")
