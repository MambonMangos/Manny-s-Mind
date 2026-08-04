"""Comparison Reports — scientific validation layer for the V3 xPts shadow model.

Builds the weekly V2-vs-V3 comparison report:

  - Largest disagreements between V2 and V3 projections.
  - Agreement rates (overall and per position).
  - Captaincy, transfer and undervalued-player recommendation differences.
  - Evidence-level status linked to the learning-service threshold framework.

Everything here is *evaluation only*. V3 stays a shadow model: no production
prediction path is modified, and no decision is taken from a single gameweek.

Usage::

    from services.comparison_reports import build_comparison_report

    report = build_comparison_report(
        store=store, gameweek_id=5, session=session, persist=True,
    )
    report.agreement
    report.disagreements[:5]
    report.evidence["level"]
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

logger = logging.getLogger(__name__)

# A V3-vs-V2 difference below this magnitude counts as "in agreement".
DEFAULT_AGREEMENT_THRESHOLD = 0.75


@dataclass
class PlayerDisagreement:
    """A single player where V2 and V3 meaningfully disagree."""

    player_id: int
    web_name: str
    position: str
    v2_points: float
    v3_points: float
    delta: float  # v3 - v2
    direction: str  # "v3_higher" | "v3_lower"
    confidence: float = 0.0
    contributing_factors: dict = field(default_factory=dict)


@dataclass
class ComparisonReport:
    """Full weekly V2-vs-V3 comparison report."""

    gameweek_id: int
    alignment: dict = field(default_factory=dict)
    disagreements: list = field(default_factory=list)
    agreement: dict = field(default_factory=dict)
    captain: dict = field(default_factory=dict)
    transfers: dict = field(default_factory=dict)
    undervalued: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    insights: list = field(default_factory=list)
    persisted: bool = False
    baseline_version_id: int | None = None
    expected_version_id: int | None = None
    computed_at: str = ""

    def summary(self) -> dict:
        """Short dict for logs / UI headers."""
        return {
            "gameweek_id": self.gameweek_id,
            "n_common_players": self.alignment.get("n_common_players", 0),
            "agreement_rate": self.agreement.get("overall_rate"),
            "n_disagreements": len(self.disagreements),
            "correlation": self.alignment.get("correlation"),
            "evidence_level": self.evidence.get("level"),
            "persisted": self.persisted,
        }


def compute_disagreements(
    v3_projections: list,
    v2_projections: list,
    top_n: int = 10,
) -> list[PlayerDisagreement]:
    """Return the players where V3 and V2 differ most (by |delta|).

    Parameters
    ----------
    v3_projections : list[ExpectedPlayerProjection]
        V3 xPts projections.
    v2_projections : list[PlayerProjection]
        V2 baseline projections.
    top_n : int
        Maximum number of disagreements to return.

    Returns
    -------
    list[PlayerDisagreement]
        Sorted by absolute delta, largest first.
    """
    v3_by_id = {p.player_id: p for p in v3_projections}
    v2_by_id = {p.player_id: p for p in v2_projections}
    common = sorted(set(v3_by_id) & set(v2_by_id))
    if not common:
        return []

    rows = []
    for pid in common:
        v3 = v3_by_id[pid]
        v2 = v2_by_id[pid]
        delta = v3.projected_points - v2.projected_points
        rows.append(PlayerDisagreement(
            player_id=pid,
            web_name=v3.web_name or getattr(v2, "web_name", f"P{pid}"),
            position=v3.position or getattr(v2, "position", "UNK"),
            v2_points=round(float(v2.projected_points), 2),
            v3_points=round(float(v3.projected_points), 2),
            delta=round(delta, 2),
            direction="v3_higher" if delta > 0 else "v3_lower",
            confidence=getattr(v3, "confidence", 0.0),
            contributing_factors=getattr(v3, "contributing_factors", {}) or {},
        ))

    rows.sort(key=lambda d: abs(d.delta), reverse=True)
    return rows[:top_n]


def compute_agreement(
    v3_projections: list,
    v2_projections: list,
    threshold: float = DEFAULT_AGREEMENT_THRESHOLD,
) -> dict:
    """Agreement rates between V2 and V3, overall and per position.

    A pair agrees when ``abs(v3 - v2) <= threshold``.

    Returns
    -------
    dict
        With keys: ``threshold``, ``n_common``, ``n_agree``, ``n_disagree``,
        ``overall_rate``, ``by_position`` (pos -> rate/n).
    """
    v3_by_id = {p.player_id: p for p in v3_projections}
    v2_by_id = {p.player_id: p for p in v2_projections}
    common = sorted(set(v3_by_id) & set(v2_by_id))
    if not common:
        return {
            "threshold": threshold, "n_common": 0, "n_agree": 0,
            "n_disagree": 0, "overall_rate": None, "by_position": {},
        }

    by_position: dict[str, dict] = defaultdict(lambda: {"n_agree": 0, "n": 0})
    n_agree = 0
    for pid in common:
        v3 = v3_by_id[pid]
        v2 = v2_by_id[pid]
        pos = v3.position or getattr(v2, "position", "UNK") or "UNK"
        if abs(v3.projected_points - v2.projected_points) <= threshold:
            n_agree += 1
            by_position[pos]["n_agree"] += 1
        by_position[pos]["n"] += 1

    pos_rates = {}
    for pos, counts in by_position.items():
        n = counts["n"]
        pos_rates[pos] = {
            "rate": round(counts["n_agree"] / n, 4) if n else None,
            "n": n,
            "n_agree": counts["n_agree"],
        }

    return {
        "threshold": threshold,
        "n_common": len(common),
        "n_agree": n_agree,
        "n_disagree": len(common) - n_agree,
        "overall_rate": round(n_agree / len(common), 4) if common else None,
        "by_position": pos_rates,
    }


def rank_by_projection(
    store,
    projections: list,
    top_n: int = 3,
    source: str = "V2",
) -> dict:
    """Rank top-N players by projected points (captaincy proxy).

    Builds a squad-style DataFrame from the FeatureStore with ``value_score``
    set to the model's projected points, then delegates to the single captain
    engine so the comparison uses production logic unchanged.
    """
    if not projections:
        return {"source": source, "ranked": [], "top": None}

    df = store.df.copy()
    proj_map = {p.player_id: p for p in projections}

    ranked = []
    for _, row in df.iterrows():
        pid = int(row.get("player_id", 0) or 0)
        proj = proj_map.get(pid)
        if proj is None:
            continue
        ranked.append({
            "player_id": pid,
            "web_name": str(row.get("web_name", "")),
            "team_short": row.get("team_short", ""),
            "position": str(row.get("position", "")),
            "price": float(row.get("price", 0) or 0),
            "projected_points": float(proj.projected_points),
        })

    ranked.sort(key=lambda r: r["projected_points"], reverse=True)
    top = ranked[:top_n]
    for i, r in enumerate(top, 1):
        r["rank"] = i

    return {"source": source, "ranked": top, "top": top[0] if top else None}


def compare_captain_choices(
    store,
    v3_projections: list,
    v2_projections: list,
    top_n: int = 3,
) -> dict:
    """Compare captaincy candidates from each model."""
    v2 = rank_by_projection(store, v2_projections, top_n=top_n, source="V2")
    v3 = rank_by_projection(store, v3_projections, top_n=top_n, source="V3")

    v2_ids = [r["player_id"] for r in v2["ranked"]]
    v3_ids = [r["player_id"] for r in v3["ranked"]]
    v2_cap = v2["top"]["player_id"] if v2["top"] else None
    v3_cap = v3["top"]["player_id"] if v3["top"] else None

    return {
        "v2": v2,
        "v3": v3,
        "v2_captain_id": v2_cap,
        "v3_captain_id": v3_cap,
        "captain_agree": v2_cap is not None and v2_cap == v3_cap,
        "shared_top_n": len(set(v2_ids) & set(v3_ids)),
        "top_n": top_n,
    }


def compare_undervalued(
    store,
    v3_projections: list,
    v2_projections: list,
    market_signals: list | None = None,
    top_n: int = 5,
) -> dict:
    """Compare undervalued-player picks from each model."""
    from engines.opportunity_engine import find_undervalued_players

    v2 = find_undervalued_players(store, v2_projections, market_signals)
    v3 = find_undervalued_players(store, v3_projections, market_signals)

    def top_names(items, n):
        return [{"player_id": p.player_id, "web_name": p.web_name,
                 "position": p.position, "points": p.projected_points_1gw,
                 "score": p.opportunity_score} for p in items[:n]]

    v2_ids = {p.player_id for p in v2[:top_n]}
    v3_ids = {p.player_id for p in v3[:top_n]}
    return {
        "v2": top_names(v2, top_n),
        "v3": top_names(v3, top_n),
        "shared_top_n": len(v2_ids & v3_ids),
        "v2_only": sorted(v2_ids - v3_ids),
        "v3_only": sorted(v3_ids - v2_ids),
        "top_n": top_n,
    }


def compare_transfer_opportunities(
    store,
    v3_projections: list,
    v2_projections: list,
    current_squad: list[int] | None,
    budget: float = 0.0,
    top_n: int = 3,
) -> dict:
    """Compare top transfer recommendations from each model.

    Requires a current squad; returns an empty comparison (not an error) when
    no squad is available.
    """
    if not current_squad:
        return {
            "available": False,
            "message": "No squad data — transfer comparison unavailable.",
        }

    from engines.opportunity_engine import find_transfer_opportunities

    v2 = find_transfer_opportunities(store, v2_projections, current_squad, budget)
    v3 = find_transfer_opportunities(store, v3_projections, current_squad, budget)

    def to_rows(items, n):
        return [{
            "player_in_id": o.player_in_id,
            "player_in_name": o.player_in_name,
            "player_out_id": o.player_out_id,
            "player_out_name": o.player_out_name,
            "gain": o.projected_points_gain,
            "type": o.opportunity_type,
        } for o in items[:n]]

    v2_rows = to_rows(v2, top_n)
    v3_rows = to_rows(v3, top_n)
    v2_keys = {(r["player_in_id"], r["player_out_id"]) for r in v2_rows}
    v3_keys = {(r["player_in_id"], r["player_out_id"]) for r in v3_rows}
    return {
        "available": True,
        "v2": v2_rows,
        "v3": v3_rows,
        "shared_top_n": len(v2_keys & v3_keys),
        "top_n": top_n,
    }


def evidence_status(
    validated_gameweeks: int,
    consistency_score: float = 0.0,
) -> dict:
    """Map validated gameweek count to the evidence-threshold framework.

    This is the single bridge between the comparison layer and the learning
    service thresholds (weak → needs_more_data → moderate → strong →
    statistically_significant).
    """
    from services.learning_service import (
        EVIDENCE_THRESHOLDS,
        get_evidence_description,
        get_evidence_level,
    )

    level = get_evidence_level(validated_gameweeks, consistency_score)
    thresholds = dict(EVIDENCE_THRESHOLDS)

    # Games remaining before the next evidence tier is reached.
    order = ["weak", "needs_more_data", "moderate", "strong", "statistically_significant"]
    next_level = None
    for candidate in order:
        if thresholds[candidate] > validated_gameweeks:
            next_level = candidate
            break

    return {
        "level": level,
        "description": get_evidence_description(level),
        "n_validated_gameweeks": validated_gameweeks,
        "thresholds": thresholds,
        "next_level": next_level,
        "gameweeks_to_next_level": (
            thresholds[next_level] - validated_gameweeks if next_level else 0
        ),
        "promotion_criteria": (
            "V3 may only be considered for promotion after "
            f"≥{thresholds['strong']} gameweeks of superior MAE/RMSE and "
            "CI calibration. No change is ever automatic."
        ),
    }


def build_comparison_report(
    store,
    gameweek_id: int = 0,
    session=None,
    persist: bool = False,
    baseline_result=None,
    current_squad: list[int] | None = None,
    budget: float = 0.0,
    disagreement_threshold: float = DEFAULT_AGREEMENT_THRESHOLD,
    top_n: int = 10,
) -> ComparisonReport:
    """Build the full weekly V2-vs-V3 comparison report.

    Parameters
    ----------
    store : FeatureStore
        Pre-built feature store.
    gameweek_id : int
        Target gameweek.
    session : Session, optional
        SQLAlchemy session. Required when persist=True and for evidence counts.
    persist : bool
        If True, persist both V2 and V3 prediction versions.
    baseline_result : PipelineResult, optional
        Pre-computed V2 baseline result (avoids re-running the V2 pipeline).
    current_squad : list[int], optional
        Player IDs in the user's squad (for transfer differences).
    budget : float
        Remaining budget for transfer recommendations.
    disagreement_threshold : float
        |delta| below which two projections are "in agreement".
    top_n : int
        Number of disagreements to include.

    Returns
    -------
    ComparisonReport
        Full report with alignment, disagreements, agreement, captain/transfer
        differences, evidence status and human-readable insights.
    """
    from services.expected_pipeline import run_expected_points_comparison

    comparison = run_expected_points_comparison(
        store=store,
        gameweek_id=gameweek_id,
        session=session,
        persist=persist,
        baseline_result=baseline_result,
    )

    report = ComparisonReport(
        gameweek_id=gameweek_id,
        alignment=comparison.alignment,
        computed_at=datetime.now(timezone.utc).isoformat(),
        persisted=comparison.persisted,
        baseline_version_id=comparison.baseline_version_id,
        expected_version_id=comparison.expected_version_id,
    )

    report.disagreements = compute_disagreements(
        comparison.expected_projections,
        comparison.baseline_projections,
        top_n=top_n,
    )
    report.agreement = compute_agreement(
        comparison.expected_projections,
        comparison.baseline_projections,
        threshold=disagreement_threshold,
    )
    report.captain = compare_captain_choices(
        store, comparison.expected_projections, comparison.baseline_projections,
    )
    report.undervalued = compare_undervalued(
        store, comparison.expected_projections, comparison.baseline_projections,
    )
    report.transfers = compare_transfer_opportunities(
        store,
        comparison.expected_projections,
        comparison.baseline_projections,
        current_squad,
        budget,
    )

    # Evidence level: number of gameweeks where BOTH versions were validated.
    n_validated = _validated_gameweek_count(
        session, comparison.baseline_version_id, comparison.expected_version_id,
    )
    report.evidence = evidence_status(n_validated)
    report.insights = _generate_insights(report)

    logger.info(
        "Comparison report gw=%d: %d common players, agreement=%s, "
        "evidence=%s",
        gameweek_id,
        report.agreement.get("n_common", 0),
        report.agreement.get("overall_rate"),
        report.evidence.get("level"),
    )

    return report


def disagreements_to_dataframe(disagreements: list[PlayerDisagreement]) -> pd.DataFrame:
    """Convert disagreements to a DataFrame for tabular UI display."""
    if not disagreements:
        return pd.DataFrame(columns=[
            "player_id", "web_name", "position", "v2_points",
            "v3_points", "delta", "direction",
        ])
    rows = [
        {
            "player_id": d.player_id,
            "web_name": d.web_name,
            "position": d.position,
            "v2_points": d.v2_points,
            "v3_points": d.v3_points,
            "delta": d.delta,
            "direction": d.direction,
        }
        for d in disagreements
    ]
    return pd.DataFrame(rows)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _validated_gameweek_count(
    session,
    baseline_version_id: int | None,
    expected_version_id: int | None,
) -> int:
    """Count gameweeks where BOTH versions have persisted validation metrics."""
    if session is None or baseline_version_id is None or expected_version_id is None:
        return 0
    try:
        from database.crud import get_validation_metrics

        gws_a = {m.gameweek_id for m in get_validation_metrics(
            session, version_id=baseline_version_id)}
        gws_b = {m.gameweek_id for m in get_validation_metrics(
            session, version_id=expected_version_id)}
        return len(gws_a & gws_b)
    except Exception:  # evidence is best-effort
        logger.exception("Failed to compute validated gameweek count")
        return 0


def _generate_insights(report: ComparisonReport) -> list[str]:
    """Human-readable insights from alignment + agreement + evidence."""
    insights: list[str] = []
    alignment = report.alignment
    agreement = report.agreement

    if "error" in alignment:
        return [f"Comparison unavailable: {alignment['error']}"]

    corr = alignment.get("correlation")
    if corr is not None:
        if corr >= 0.95:
            insights.append(
                f"V3 xPts ranks players almost identically to V2 "
                f"(correlation {corr:.3f}) — any delta is small."
            )
        elif corr >= 0.8:
            insights.append(
                f"V3 broadly agrees with V2 (correlation {corr:.3f}) — "
                f"differences concentrate in a few players."
            )
        else:
            insights.append(
                f"V3 diverges materially from V2 (correlation {corr:.3f}) — "
                f"re-verify the minutes/rate inputs before trusting either."
            )

    rate = agreement.get("overall_rate")
    if rate is not None:
        insights.append(
            f"V2/V3 agree on {rate:.0%} of players "
            f"(threshold ±{agreement.get('threshold', 0.75):.2f} pts)."
        )
        if rate < 0.7:
            insights.append(
                "Agreement is low — the minutes model is driving large "
                "per-player differences. Investigate before relying on V3."
            )

    if report.disagreements:
        top = report.disagreements[0]
        insights.append(
            f"Largest disagreement: {top.web_name} ({top.position}) — "
            f"V3 projects {top.v3_points:+.1f} vs V2 {top.v2_points:.1f} "
            f"({top.delta:+.2f} pts)."
        )
        higher = sum(1 for d in report.disagreements if d.direction == "v3_higher")
        insights.append(
            f"Among top disagreements, V3 is higher on {higher}/{len(report.disagreements)} "
            f"players (minutes-driven)."
        )

    if report.captain.get("captain_agree") is False and report.captain.get("v2_captain_id"):
        v2_cap = report.captain["v2"]["top"]
        v3_cap = report.captain["v3"]["top"]
        if v2_cap and v3_cap:
            insights.append(
                f"Captaincy differs: V2 picks {v2_cap['web_name']} "
                f"({v2_cap['projected_points']:.1f} pts) vs V3 "
                f"{v3_cap['web_name']} ({v3_cap['projected_points']:.1f} pts)."
            )

    evidence = report.evidence
    insights.append(
        f"Evidence: {evidence.get('level', 'unknown')} — "
        f"{evidence.get('n_validated_gameweeks', 0)} validated gameweeks "
        f"with both versions. {evidence.get('promotion_criteria', '')}"
    )

    return insights
