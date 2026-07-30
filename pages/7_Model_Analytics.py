"""Model Analytics Dashboard — validation infrastructure for prediction quality.

Engineering dashboard showing scatter plots, calibration curves, engine scorecard,
weekly reports, and version comparison.

This page is read-only for model behavior — no retraining, no config changes.
All config changes require human approval and are tracked in the Decision Log.
"""

from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from components.theme import inject_theme, page_header, section_label, divider
from database.crud import (
    get_error_classifications,
    get_engine_accuracy,
    get_prediction_versions,
    get_projections,
    get_validation_metrics,
)
from database.database import get_session
from services.error_classifier import get_error_summary
from services.learning_service import (
    generate_weekly_report,
    get_model_health,
    get_evidence_level,
    get_evidence_description,
)
from services.result_ingestion_service import (
    detect_finished_gameweeks,
    get_ingestion_status,
    ingest_gameweek_results,
)

st.set_page_config(page_title="Model Analytics", layout="wide")
inject_theme()
page_header("Model Analytics", "Prediction quality dashboard — validate, don't retrain.")


# ------------------------------------------------------------------
# Metric Explanations (Executive-Friendly)
# ------------------------------------------------------------------

METRIC_EXPLANATIONS = {
    "MAE": {
        "name": "Mean Absolute Error (MAE)",
        "description": "Average distance between predicted and actual points, regardless of direction.",
        "interpretation": "Lower is better. MAE of 2.0 means predictions are off by 2 points on average.",
        "good": "< 2.0",
        "acceptable": "2.0 - 4.0",
        "poor": "> 4.0",
    },
    "RMSE": {
        "name": "Root Mean Squared Error (RMSE)",
        "description": "Like MAE but penalizes large errors more heavily.",
        "interpretation": "Lower is better. RMSE > MAE means there are some large misses.",
        "good": "< 2.5",
        "acceptable": "2.5 - 5.0",
        "poor": "> 5.0",
    },
    "Bias": {
        "name": "Prediction Bias",
        "description": "Whether predictions are systematically too high or too low.",
        "interpretation": "Positive = underpredicting (actual > predicted). Negative = overpredicting.",
        "good": "Between -0.5 and +0.5",
        "acceptable": "Between -1.0 and +1.0",
        "poor": "Outside -1.0 to +1.0",
    },
    "CI80": {
        "name": "80% Confidence Interval Coverage",
        "description": "What percentage of actual results fell within the 80% confidence interval.",
        "interpretation": "Should be close to 80%. Lower = intervals too narrow. Higher = intervals too wide.",
        "good": "75% - 85%",
        "acceptable": "65% - 95%",
        "poor": "Outside 65% - 95%",
    },
    "CI95": {
        "name": "95% Confidence Interval Coverage",
        "description": "What percentage of actual results fell within the 95% confidence interval.",
        "interpretation": "Should be close to 95%. Lower = intervals too narrow. Higher = intervals too wide.",
        "good": "90% - 98%",
        "acceptable": "80% - 100%",
        "poor": "Outside 80% - 100%",
    },
}


def show_metric_explanation(metric_key: str):
    """Display an expandable metric explanation."""
    if metric_key in METRIC_EXPLANATIONS:
        info = METRIC_EXPLANATIONS[metric_key]
        with st.expander(f"ℹ️ What is {info['name']}?", expanded=False):
            st.markdown(f"**{info['description']}**")
            st.markdown(f"**Interpretation:** {info['interpretation']}")
            st.markdown("**Benchmarks:**")
            st.markdown(f"- 🟢 Good: {info['good']}")
            st.markdown(f"- 🟡 Acceptable: {info['acceptable']}")
            st.markdown(f"- 🔴 Poor: {info['poor']}")


# ------------------------------------------------------------------
# Evidence Level Display
# ------------------------------------------------------------------

def show_evidence_level(level: str, description: str):
    """Display evidence level with appropriate styling."""
    colors = {
        "weak": "🔴",
        "needs_more_data": "🟡",
        "moderate": "🟠",
        "strong": "🟢",
        "statistically_significant": "✅",
    }
    icon = colors.get(level, "⚪")
    st.markdown(f"**Evidence Level:** {icon} {level.replace('_', ' ').title()}")
    st.caption(description)


# ------------------------------------------------------------------
# Tabs — Guided 5-Step Validation Workflow
# ------------------------------------------------------------------

st.markdown("---")
st.markdown("### Weekly Validation Workflow")
st.markdown("*Follow these steps after each gameweek finishes to validate and improve the model.*")

tab_workflow, tab_scatter, tab_calibration, tab_errors, tab_engines, tab_versions, tab_report = st.tabs([
    "1️⃣ Result Ingestion",
    "2️⃣ Scatter Plot",
    "3️⃣ Calibration & Health",
    "4️⃣ Error Analysis",
    "5️⃣ Engine Scorecard",
    "6️⃣ Version Comparison",
    "7️⃣ Weekly Report",
])


# ------------------------------------------------------------------
# Tab 1: Result Ingestion (Step 1 of Workflow)
# ------------------------------------------------------------------

with tab_workflow:
    section_label("Step 1: Ingest Actual Results")
    st.markdown("*Retrieve official GW results and attach actual outcomes to every stored prediction.*")

    session = get_session()
    try:
        # Show ingestion status
        status = get_ingestion_status(session)

        if status:
            st.markdown("**Gameweek Ingestion Status**")
            for s in status:
                icon = "🟢" if s["status"] == "ingested" else "🟡" if s["status"] == "pending" else "⚪"
                st.markdown(
                    f"{icon} **GW{s['gameweek_id']}**: {s['total_projections']} projections, "
                    f"{s['ingested']} ingested, {s['pending']} pending"
                )
        else:
            st.info("No predictions found in the ledger. Run the V2 pipeline first.")

        # Finished GWs needing ingestion
        pending = detect_finished_gameweeks(session)
        if pending:
            st.markdown("---")
            st.markdown("**Ready to Ingest**")
            for gw_id in pending:
                if st.button(f"Ingest GW{gw_id} Results", key=f"ingest_{gw_id}"):
                    with st.spinner(f"Ingesting GW{gw_id} results..."):
                        report = ingest_gameweek_results(session, gw_id)
                        session.commit()
                    if report.status == "ok":
                        st.success(
                            f"GW{gw_id}: {report.n_actuals} actuals, "
                            f"{report.n_projections_updated} projections updated, "
                            f"{report.duration_ms:.0f}ms"
                        )
                        st.rerun()
                    else:
                        st.error(f"Failed: {report.error_message}")
        elif status:
            st.success("All finished gameweeks have been ingested.")
    finally:
        session.close()

    # Manual trigger for validation cycle
    section_label("Step 2: Run Validation Cycle")
    st.markdown("*Calculate all metrics automatically — no manual calculations needed.*")

    session2 = get_session()
    try:
        versions = get_prediction_versions(session2)
        if versions:
            gw_options = sorted(set(
                p.gameweek_id for pv in versions
                for p in get_projections(session2, pv.id)
                if p.actual_points is not None
            ))

            if gw_options:
                selected_gw = st.selectbox("Gameweek to validate", gw_options)
                if st.button("Run Validation Cycle"):
                    from services.learning_service import run_validation_cycle
                    with st.spinner("Running validation..."):
                        result = run_validation_cycle(session2, selected_gw)
                        session2.commit()
                    st.json(result)
            else:
                st.info("No gameweeks with actuals available for validation.")
        else:
            st.info("No prediction versions found.")
    finally:
        session2.close()


# ------------------------------------------------------------------
# Tab 2: Scatter Plot (Step 2 of Workflow)
# ------------------------------------------------------------------

with tab_scatter:
    section_label("Step 2: Review Prediction Accuracy")
    st.markdown("*Visualize how well predictions match reality. Points near the diagonal line are accurate predictions.*")

    session = get_session()
    try:
        versions = get_prediction_versions(session)
        if not versions:
            st.info("No prediction versions found. Run the V2 pipeline first.")
        else:
            version_options = {pv.version_tag: pv.id for pv in versions}
            selected_tag = st.selectbox("Prediction Version", list(version_options.keys()))
            version_id = version_options[selected_tag]

            projections = get_projections(session, version_id)
            with_actuals = [p for p in projections if p.actual_points is not None]

            if not with_actuals:
                st.info("No predictions with actuals for this version. Ingest results first.")
            else:
                predicted = [p.projected_points for p in with_actuals]
                actual = [p.actual_points for p in with_actuals]

                fig = go.Figure()

                # Scatter points
                fig.add_trace(go.Scatter(
                    x=predicted, y=actual,
                    mode="markers",
                    marker=dict(
                        size=8, opacity=0.6,
                        color=np.abs(np.array(predicted) - np.array(actual)),
                        colorscale="RdYlGn_r",
                        colorbar=dict(title="|Error|"),
                    ),
                    text=[f"Player {p.player_id}" for p in with_actuals],
                    hovertemplate="Predicted: %{x:.1f}<br>Actual: %{y}<br>%{text}<extra></extra>",
                ))

                # Perfect prediction line
                max_val = max(max(predicted), max(actual))
                fig.add_trace(go.Scatter(
                    x=[0, max_val], y=[0, max_val],
                    mode="lines",
                    line=dict(color="gray", dash="dash", width=1),
                    name="Perfect Prediction",
                ))

                # MAE line
                errors = np.array(actual) - np.array(predicted)
                mae = np.mean(np.abs(errors))
                fig.add_trace(go.Scatter(
                    x=[0, max_val], y=[mae, max_val + mae],
                    mode="lines",
                    line=dict(color="orange", dash="dot", width=1),
                    name=f"MAE = {mae:.2f}",
                ))

                fig.update_layout(
                    xaxis_title="Predicted Points",
                    yaxis_title="Actual Points",
                    height=500,

                )
                st.plotly_chart(fig, use_container_width=True)

                # Stats with explanations
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("MAE", f"{mae:.2f}")
                    show_metric_explanation("MAE")
                with col2:
                    rmse = np.sqrt(np.mean(errors**2))
                    st.metric("RMSE", f"{rmse:.2f}")
                    show_metric_explanation("RMSE")
                with col3:
                    bias = np.mean(errors)
                    st.metric("Bias", f"{bias:+.2f}")
                    show_metric_explanation("Bias")
                with col4:
                    r_squared = 1 - np.sum(errors**2) / np.sum((np.array(actual) - np.mean(actual))**2)
                    st.metric("R²", f"{r_squared:.3f}")
                    st.caption("Proportion of variance explained (1.0 = perfect)")
    finally:
        session.close()


# ------------------------------------------------------------------
# Tab 3: Calibration & Health (Step 3 of Workflow)
# ------------------------------------------------------------------

with tab_calibration:
    section_label("Step 3: Review Model Health")
    st.markdown("*Check if confidence intervals are well-calibrated and review overall model health.*")

    session = get_session()
    try:
        versions = get_prediction_versions(session)
        if not versions:
            st.info("No prediction versions found.")
        else:
            version_options = {pv.version_tag: pv.id for pv in versions}
            selected_tag = st.selectbox("Version", list(version_options.keys()), key="cal_version")
            version_id = version_options[selected_tag]

            projections = get_projections(session, version_id)
            with_actuals = [p for p in projections if p.actual_points is not None]

            if not with_actuals:
                st.info("No predictions with actuals.")
            else:
                # Compute calibration at different CI widths
                widths = np.arange(0.1, 1.0, 0.05)
                actual_coverage = []
                for w in widths:
                    low_pct = (1 - w) / 2
                    high_pct = 1 - low_pct
                    hits = 0
                    for p in with_actuals:
                        if p.ci_80_low is not None and p.ci_80_high is not None:
                            # Interpolate CI for arbitrary width
                            ci_range = p.ci_80_high - p.ci_80_low
                            center = (p.ci_80_high + p.ci_80_low) / 2
                            adj_low = center - ci_range * w / 0.8
                            adj_high = center + ci_range * w / 0.8
                            if adj_low <= p.actual_points <= adj_high:
                                hits += 1
                    actual_coverage.append(hits / len(with_actuals))

                fig = go.Figure()

                # Actual coverage
                fig.add_trace(go.Scatter(
                    x=widths * 100, y=[c * 100 for c in actual_coverage],
                    mode="lines+markers",
                    name="Actual Coverage",
                    line=dict(color="#10b981", width=2),
                ))

                # Perfect calibration line
                fig.add_trace(go.Scatter(
                    x=widths * 100, y=widths * 100,
                    mode="lines",
                    name="Perfect Calibration",
                    line=dict(color="gray", dash="dash", width=1),
                ))

                fig.update_layout(
                    xaxis_title="CI Width (%)",
                    yaxis_title="Actual Coverage (%)",
                    height=400,

                )
                st.plotly_chart(fig, use_container_width=True)

                # Specific CI metrics with explanations
                metrics = get_validation_metrics(session, version_id=version_id)
                if metrics:
                    latest = metrics[-1]
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("80% CI Coverage", f"{(latest.coverage_80 or 0):.1%}")
                        show_metric_explanation("CI80")
                    with col2:
                        st.metric("95% CI Coverage", f"{(latest.coverage_95 or 0):.1%}")
                        show_metric_explanation("CI95")

                # Model Health Section
                st.markdown("---")
                section_label("Model Health Summary")

                health = get_model_health(session)
                if health["status"] == "ok":
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Gameweeks Tracked", health["n_gameweeks"])
                    with col2:
                        st.metric("Recent Avg MAE", f"{health['avg_mae_recent']:.2f}")
                    with col3:
                        st.metric("Bias Direction", health["bias_direction"].replace("_", " ").title())

                    # Show trend if we have data
                    if health.get("trend") and len(health["trend"]) > 1:
                        st.markdown("**MAE Trend Across Gameweeks**")
                        trend_data = health["trend"]
                        fig_trend = go.Figure()
                        fig_trend.add_trace(go.Scatter(
                            x=[t["gameweek_id"] for t in trend_data],
                            y=[t["mae"] for t in trend_data],
                            mode="lines+markers",
                            name="MAE",
                            line=dict(color="#10b981", width=2),
                        ))
                        fig_trend.update_layout(
                            xaxis_title="Gameweek",
                            yaxis_title="MAE",
                            height=300,
        
                        )
                        st.plotly_chart(fig_trend, use_container_width=True)
                else:
                    st.info("No validation data available yet.")
    finally:
        session.close()


# ------------------------------------------------------------------
# Tab 4: Error Analysis (Step 4 of Workflow)
# ------------------------------------------------------------------

with tab_errors:
    section_label("Step 4: Analyze Prediction Errors")
    st.markdown("*Understand WHY predictions were wrong. This is the key to improving the model.*")

    session = get_session()
    try:
        versions = get_prediction_versions(session)
        if not versions:
            st.info("No prediction versions found.")
        else:
            version_options = {pv.version_tag: pv.id for pv in versions}
            selected_tag = st.selectbox("Version", list(version_options.keys()), key="err_version")
            version_id = version_options[selected_tag]

            error_summary = get_error_summary(session, version_id)

            if error_summary["total_errors"] == 0:
                st.info("No errors classified. Run validation cycle first.")
            else:
                # Summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Total Errors", error_summary["total_errors"])
                    st.caption("Predictions with |error| > 1.5 points")
                with col2:
                    st.metric("Avg |Error|", f"{error_summary['avg_abs_error']:.2f}")
                    st.caption("Average magnitude of prediction misses")
                with col3:
                    over = error_summary['by_direction'].get('over', 0)
                    under = error_summary['by_direction'].get('under', 0)
                    st.metric("Direction", f"Over: {over}, Under: {under}")
                    st.caption("Over = predicted too high, Under = predicted too low")

                # Error type distribution with explanations
                if error_summary["by_type"]:
                    st.markdown("**Error Type Distribution**")
                    st.caption("*What caused the prediction to be wrong?*")

                    error_type_explanations = {
                        "minutes_miss": "Player didn't play despite being projected to",
                        "low_minutes": "Player played significantly fewer minutes than expected",
                        "outlier_performance": "Unusually high or low performance (hat trick, red card, etc.)",
                        "goal_miss": "Predicted goals but player didn't score (or scored more)",
                        "assists_miss": "Predicted assists but player didn't assist (or assisted more)",
                        "clean_sheet_miss": "Defender/GK predicted clean sheet but team conceded",
                        "generic_misprediction": "General under/overperformance without specific cause",
                    }

                    fig = go.Figure(data=[go.Pie(
                        labels=list(error_summary["by_type"].keys()),
                        values=list(error_summary["by_type"].values()),
                        hole=0.3,
                    )])
                    fig.update_layout(
                        title="Error Type Distribution",
                        height=350,
    
                    )
                    st.plotly_chart(fig, use_container_width=True)

                    # Show explanations for each error type
                    for error_type, count in error_summary["by_type"].items():
                        explanation = error_type_explanations.get(error_type, "Unknown error type")
                        st.markdown(f"- **{error_type}** ({count} occurrences): {explanation}")

                # Severity distribution
                if error_summary["by_severity"]:
                    st.markdown("**Error Severity Distribution**")
                    st.caption("*How severe were the prediction misses?*")

                    severity_explanations = {
                        "minor": "1.5-3 points off: within expected variance",
                        "moderate": "3-6 points off: worth investigating",
                        "severe": "6+ points off: significant miss, needs attention",
                    }

                    fig2 = go.Figure(data=[go.Bar(
                        x=list(error_summary["by_severity"].keys()),
                        y=list(error_summary["by_severity"].values()),
                        marker_color=["#10b981", "#f59e0b", "#ef4444"],
                    )])
                    fig2.update_layout(
                        title="Error Severity Distribution",
                        height=300,
    
                    )
                    st.plotly_chart(fig2, use_container_width=True)

                    for severity, count in error_summary["by_severity"].items():
                        explanation = severity_explanations.get(severity, "Unknown severity")
                        st.markdown(f"- **{severity}** ({count} occurrences): {explanation}")
    finally:
        session.close()


# ------------------------------------------------------------------
# Tab 5: Engine Scorecard (Step 5 of Workflow)
# ------------------------------------------------------------------

with tab_engines:
    section_label("Step 5: Review Engine Performance")
    st.markdown("*See which analytical engines are contributing most to prediction accuracy.*")

    session = get_session()
    try:
        versions = get_prediction_versions(session)
        if not versions:
            st.info("No prediction versions found.")
        else:
            version_options = {pv.version_tag: pv.id for pv in versions}
            selected_tag = st.selectbox("Version", list(version_options.keys()), key="eng_version")
            version_id = version_options[selected_tag]

            engine_data = get_engine_accuracy(session, version_id=version_id)

            if not engine_data:
                st.info("No engine accuracy data. Run validation cycle first.")
            else:
                # Build scorecard
                engines_by_gw = {}
                for e in engine_data:
                    gw = e.gameweek_id
                    if gw not in engines_by_gw:
                        engines_by_gw[gw] = {}
                    engines_by_gw[gw][e.engine_name] = {
                        "mae": e.mae,
                        "correlation": e.correlation,
                    }

                # Show latest GW scorecard with explanations
                if engines_by_gw:
                    latest_gw = max(engines_by_gw.keys())
                    st.markdown(f"**Gameweek {latest_gw} Scorecard**")

                    engine_explanations = {
                        "minutes_engine": "Projects how many minutes each player will play",
                        "goals_projection": "Projects goals scored based on xG and form",
                        "assists_projection": "Projects assists based on xA and creative stats",
                        "clean_sheet_projection": "Projects clean sheets based on defensive strength",
                    }

                    for eng_name, scores in engines_by_gw[latest_gw].items():
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.markdown(f"**{eng_name.replace('_', ' ').title()}**")
                            explanation = engine_explanations.get(eng_name, "Analytical engine")
                            st.caption(explanation)
                        with col2:
                            st.metric("MAE", f"{scores['mae']:.3f}" if scores["mae"] else "N/A")
                        with col3:
                            st.metric("Correlation", f"{scores['correlation']:.4f}" if scores["correlation"] else "N/A")
                        with col4:
                            if scores["correlation"] is not None:
                                if scores["correlation"] > 0.3:
                                    st.success("Strong signal")
                                elif scores["correlation"] > 0.1:
                                    st.warning("Moderate signal")
                                else:
                                    st.info("Weak signal")

                # Trend across gameweeks
                if len(engines_by_gw) > 1:
                    st.markdown("**Engine Performance Trend**")
                    st.caption("*Track how each engine's accuracy changes over time*")

                    fig = go.Figure()
                    for eng_name in engines_by_gw[list(engines_by_gw.keys())[0]]:
                        gws = sorted(engines_by_gw.keys())
                        maes = [engines_by_gw[gw].get(eng_name, {}).get("mae") for gw in gws]
                        fig.add_trace(go.Scatter(
                            x=gws, y=maes,
                            mode="lines+markers",
                            name=eng_name.replace("_", " ").title(),
                        ))
                    fig.update_layout(
                        title="Engine MAE Trend",
                        xaxis_title="Gameweek",
                        yaxis_title="MAE",
                        height=400,
    
                    )
                    st.plotly_chart(fig, use_container_width=True)
    finally:
        session.close()


# ------------------------------------------------------------------
# Tab 6: Version Comparison
# ------------------------------------------------------------------

with tab_versions:
    section_label("Version Comparison")
    st.markdown("*Compare accuracy of two prediction versions to see which performs better.*")

    session = get_session()
    try:
        versions = get_prediction_versions(session)
        if len(versions) < 2:
            st.info("Need at least 2 prediction versions to compare.")
        else:
            version_options = {pv.version_tag: pv.id for pv in versions}

            col1, col2 = st.columns(2)
            with col1:
                baseline_tag = st.selectbox("Baseline Version", list(version_options.keys()), key="comp_a")
            with col2:
                treatment_tag = st.selectbox("Treatment Version", list(version_options.keys()), key="comp_b")

            if st.button("Compare Versions"):
                from engines.validation_engine import compare_versions
                result = compare_versions(
                    session,
                    version_options[baseline_tag],
                    version_options[treatment_tag],
                )

                if "error" in result:
                    st.warning(result["error"])
                else:
                    # Show evidence level
                    n_gws = result.get("n_gameweeks", 0)
                    evidence_level = get_evidence_level(n_gws, 0.5)
                    evidence_desc = get_evidence_description(evidence_level)

                    st.markdown("**Comparison Results**")
                    show_evidence_level(evidence_level, evidence_desc)

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("MAE Improvement", f"{result['mae_improvement_pct']:+.2f}%")
                    with col2:
                        st.metric("RMSE Improvement", f"{result['rmse_improvement_pct']:+.2f}%")
                    with col3:
                        winner = result["winner"].upper()
                        st.metric("Winner", winner)
                        if winner == "TIE":
                            st.caption("No clear winner")
                        else:
                            st.caption(f"Version {winner} performs better")

                    st.markdown("---")
                    st.json(result)
    finally:
        session.close()


# ------------------------------------------------------------------
# Tab 7: Weekly Report (Step 6 of Workflow)
# ------------------------------------------------------------------

with tab_report:
    section_label("Step 6: Generate Weekly Report")
    st.markdown("*Produce a comprehensive report answering: What happened? Why? Did the model perform as expected?*")

    session = get_session()
    try:
        versions = get_prediction_versions(session)
        if not versions:
            st.info("No prediction versions found.")
        else:
            version_options = {pv.version_tag: pv.id for pv in versions}
            gw_options = sorted(set(
                p.gameweek_id for pv in versions
                for p in get_projections(session, pv.id)
                if p.actual_points is not None
            ))

            if gw_options:
                selected_gw = st.selectbox("Select Gameweek", gw_options, key="report_gw")

                if st.button("Generate Weekly Report"):
                    with st.spinner("Generating comprehensive weekly report..."):
                        report = generate_weekly_report(session, selected_gw)

                    if report.status == "no_data":
                        st.warning("No validation data available for this gameweek.")
                    else:
                        # Report Header
                        st.markdown(f"## Weekly Report: Gameweek {selected_gw}")
                        st.caption(f"Generated at: {report.computed_at}")

                        # Evidence Level
                        show_evidence_level(report.overall_evidence_level, report.evidence_description)

                        # Summary Metrics
                        st.markdown("---")
                        section_label("Summary")
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Versions Evaluated", report.n_versions_evaluated)
                        with col2:
                            st.metric("Predictions with Actuals", report.n_predictions_with_actuals)
                        with col3:
                            st.metric("Errors Classified", report.n_errors_classified)
                        with col4:
                            st.metric("Gameweek", selected_gw)

                        # Key Insights
                        st.markdown("---")
                        section_label("Key Insights")
                        if report.insights:
                            for i, insight in enumerate(report.insights, 1):
                                st.markdown(f"**{i}.** {insight}")
                        else:
                            st.info("No significant insights for this gameweek.")

                        # Error Summary
                        if report.error_summary and report.error_summary.get("total_errors", 0) > 0:
                            st.markdown("---")
                            section_label("Error Analysis")
                            error_summary = report.error_summary

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Total Errors", error_summary["total_errors"])
                            with col2:
                                st.metric("Avg |Error|", f"{error_summary['avg_abs_error']:.2f}")
                            with col3:
                                over = error_summary['by_direction'].get('over', 0)
                                under = error_summary['by_direction'].get('under', 0)
                                st.metric("Direction", f"Over: {over}, Under: {under}")

                        # Candidate Improvements
                        st.markdown("---")
                        section_label("Candidate Improvements")
                        st.markdown("*Evidence-based recommendations for model changes. These are RECOMMENDATIONS ONLY — not automatically applied.*")

                        if report.candidate_improvements:
                            for i, candidate in enumerate(report.candidate_improvements, 1):
                                with st.expander(f"Candidate {i}: {candidate.problem_observed[:80]}...", expanded=True):
                                    st.markdown(f"**Problem Observed:** {candidate.problem_observed}")
                                    st.markdown(f"**Evidence Level:** {candidate.evidence_level.replace('_', ' ').title()}")

                                    if candidate.supporting_metrics:
                                        st.markdown("**Supporting Metrics:**")
                                        for metric, value in candidate.supporting_metrics.items():
                                            st.markdown(f"- {metric}: {value}")

                                    st.markdown(f"**Observations:** {candidate.n_observations}")
                                    st.markdown(f"**Gameweeks Affected:** {', '.join(str(gw) for gw in candidate.gameweeks_affected)}")
                                    st.markdown(f"**Expected Impact:** {candidate.expected_impact}")
                                    st.markdown(f"**Potential Risk:** {candidate.potential_risk}")
                                    st.markdown(f"**Recommended Action:** {candidate.recommended_action}")

                                    st.warning("⚠️ **Status: Recommendation Only** — This change is NOT automatically applied. Human review and approval required.")
                        else:
                            st.info("No candidate improvements identified for this gameweek.")

                        # Version Metrics
                        if report.version_metrics:
                            st.markdown("---")
                            section_label("Version Performance")
                            for m in report.version_metrics:
                                st.markdown(f"**Version ID: {m.version_id}**")
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.metric("MAE", f"{m.mae:.3f}" if m.mae else "N/A")
                                with col2:
                                    st.metric("RMSE", f"{m.rmse:.3f}" if m.rmse else "N/A")
                                with col3:
                                    st.metric("Bias", f"{m.bias:+.3f}" if m.bias else "N/A")
                                with col4:
                                    st.metric("CI80 Coverage", f"{m.coverage_80:.1%}" if m.coverage_80 else "N/A")
            else:
                st.info("No gameweeks with actuals available for reporting.")
    finally:
        session.close()


# ------------------------------------------------------------------
# Model Health Sidebar
# ------------------------------------------------------------------

with st.sidebar:
    st.markdown("---")
    st.markdown("**Model Health**")

    session_h = get_session()
    try:
        health = get_model_health(session_h)
        if health["status"] == "ok":
            st.metric("Gameweeks Tracked", health["n_gameweeks"])
            st.metric("Recent Avg MAE", f"{health['avg_mae_recent']:.2f}")

            # Bias direction with explanation
            bias_dir = health["bias_direction"]
            if bias_dir == "well_calibrated":
                st.success("Bias: Well Calibrated")
                st.caption("Predictions are neither systematically too high nor too low")
            elif bias_dir == "underpredicting":
                st.warning("Bias: Underpredicting")
                st.caption("Actual scores are higher than predicted on average")
            else:
                st.warning("Bias: Overpredicting")
                st.caption("Actual scores are lower than predicted on average")
        else:
            st.info("No validation data yet.")
    finally:
        session_h.close()

    # Quick links
    st.markdown("---")
    st.markdown("**Quick Actions**")
    st.markdown("1. Ingest Results → Tab 1")
    st.markdown("2. Run Validation → Tab 1")
    st.markdown("3. Review Accuracy → Tab 2")
    st.markdown("4. Check Calibration → Tab 3")
    st.markdown("5. Analyze Errors → Tab 4")
    st.markdown("6. Review Engines → Tab 5")
    st.markdown("7. Generate Report → Tab 7")
