"""Tests for the Comparison Reports service (V2 vs V3 scientific validation layer).

Covers disagreement ranking, agreement rates, captaincy/transfer/undervalued
differences, the evidence-threshold bridge, and the full report builder.
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


from sqlalchemy import text
from synthetic import create_synthetic_fixtures, create_synthetic_players

from database.database import engine, get_session
from database.models import Base, Gameweek, Player, Team
from engines.expected_projection_engine import run_expected_projection
from engines.fixture_engine import build_fixture_map
from features import build_feature_store
from services.comparison_reports import (
    DEFAULT_AGREEMENT_THRESHOLD,
    build_comparison_report,
    compare_captain_choices,
    compare_transfer_opportunities,
    compare_undervalued,
    compute_agreement,
    compute_disagreements,
    evidence_status,
    rank_by_projection,
)
from services.pipeline import run_projection_pipeline


def build_store(n=50, seed=42):
    """Build a FeatureStore from synthetic players + fixtures."""
    df = create_synthetic_players(n=n, seed=seed)
    fixture_map = build_fixture_map(create_synthetic_fixtures())
    return build_feature_store(
        players_df=df,
        fixture_map=fixture_map,
        team_name_map={i: f"Team{i}" for i in range(1, 21)},
        gameweek_id=1,
    )


def run_both(n=50, seed=42):
    """Return (store, v3_projections, v2_projections)."""
    store = build_store(n=n, seed=seed)
    v3 = run_expected_projection(store, gameweek_id=1)
    v2 = run_projection_pipeline(store=store, gameweek_id=1).projections
    return store, v3, v2


# ------------------------------------------------------------------
# compute_disagreements
# ------------------------------------------------------------------

def test_disagreements_sorted_and_directional():
    _, v3, v2 = run_both(50)
    dis = compute_disagreements(v3, v2, top_n=10)

    assert 1 <= len(dis) <= 10
    # Sorted by |delta| descending
    deltas = [abs(d.delta) for d in dis]
    assert deltas == sorted(deltas, reverse=True)
    for d in dis:
        assert d.direction in ("v3_higher", "v3_lower")
        assert d.player_id > 0
        assert d.web_name
        assert round(d.v3_points - d.v2_points, 2) == d.delta
        assert isinstance(d.contributing_factors, dict)


def test_disagreements_empty_guards():
    assert compute_disagreements([], []) == []
    _, v3, _ = run_both(5)
    assert compute_disagreements(v3, []) == []
    assert compute_disagreements([], v3) == []


# ------------------------------------------------------------------
# compute_agreement
# ------------------------------------------------------------------

def test_agreement_rates():
    _, v3, v2 = run_both(50)
    agreement = compute_agreement(v3, v2, threshold=DEFAULT_AGREEMENT_THRESHOLD)

    assert agreement["n_common"] == 50
    assert agreement["n_agree"] + agreement["n_disagree"] == 50
    assert agreement["overall_rate"] is not None
    assert 0.0 <= agreement["overall_rate"] <= 1.0
    assert agreement["threshold"] == DEFAULT_AGREEMENT_THRESHOLD
    assert set(agreement["by_position"]) <= {"GKP", "DEF", "MID", "FWD"}
    for pos in agreement["by_position"]:
        assert 0.0 <= agreement["by_position"][pos]["rate"] <= 1.0
        assert agreement["by_position"][pos]["n"] > 0


def test_agreement_strict_threshold_lowers_rate():
    _, v3, v2 = run_both(50)
    loose = compute_agreement(v3, v2, threshold=3.0)["overall_rate"]
    strict = compute_agreement(v3, v2, threshold=0.01)["overall_rate"]
    assert strict <= loose


def test_agreement_empty():
    empty = compute_agreement([], [])
    assert empty["n_common"] == 0
    assert empty["overall_rate"] is None


# ------------------------------------------------------------------
# Captaincy / undervalued / transfer comparisons
# ------------------------------------------------------------------

def test_rank_by_projection_top_pick_is_highest():
    store, v3, _ = run_both(50)
    ranking = rank_by_projection(store, v3, top_n=3, source="V3")
    assert ranking["source"] == "V3"
    assert len(ranking["ranked"]) == 3
    pts = [r["projected_points"] for r in ranking["ranked"]]
    assert pts == sorted(pts, reverse=True)
    assert ranking["top"]["player_id"] == ranking["ranked"][0]["player_id"]


def test_compare_captain_choices():
    store, v3, v2 = run_both(50)
    result = compare_captain_choices(store, v3, v2, top_n=3)
    assert result["top_n"] == 3
    assert result["v2_captain_id"] is not None
    assert result["v3_captain_id"] is not None
    assert result["captain_agree"] in (True, False)
    assert 0 <= result["shared_top_n"] <= 3
    assert len(result["v2"]["ranked"]) == 3
    assert len(result["v3"]["ranked"]) == 3


def test_compare_undervalued():
    store, v3, v2 = run_both(50)
    result = compare_undervalued(store, v3, v2, top_n=5)
    assert 0 <= result["shared_top_n"] <= 5
    assert len(result["v2"]) <= 5
    assert len(result["v3"]) <= 5
    assert result["v2_only"] is not None and result["v3_only"] is not None


def test_compare_transfers_without_squad():
    store, v3, v2 = run_both(50)
    result = compare_transfer_opportunities(store, v3, v2, None)
    assert result["available"] is False


def test_compare_transfers_with_squad():
    store, v3, v2 = run_both(50)
    squad = [int(p) for p in store.df["player_id"].head(5).tolist()]
    result = compare_transfer_opportunities(store, v3, v2, squad, budget=20.0, top_n=3)
    assert result["available"] is True
    assert 0 <= result["shared_top_n"] <= 3
    for row in result["v2"] + result["v3"]:
        assert row["player_in_id"] > 0
        assert row["gain"] > 0


# ------------------------------------------------------------------
# Evidence threshold bridge
# ------------------------------------------------------------------

def test_evidence_status_levels():
    assert evidence_status(0)["level"] == "weak"
    assert evidence_status(1)["level"] == "weak"
    assert evidence_status(2)["level"] == "needs_more_data"
    assert evidence_status(3)["level"] == "moderate"
    assert evidence_status(4)["level"] == "moderate"
    assert evidence_status(5, consistency_score=0.7)["level"] == "strong"
    assert evidence_status(9)["level"] == "moderate"  # 5+ without consistency → moderate
    assert evidence_status(10)["level"] == "statistically_significant"


def test_evidence_status_next_tier():
    ev = evidence_status(1)
    assert ev["next_level"] == "needs_more_data"
    assert ev["gameweeks_to_next_level"] == 1
    ev2 = evidence_status(10)
    assert ev2["next_level"] is None
    assert ev2["gameweeks_to_next_level"] == 0
    assert "promotion_criteria" in ev2


# ------------------------------------------------------------------
# Full report builder (in-memory, no persistence)
# ------------------------------------------------------------------

def test_build_comparison_report_in_memory():
    store, _, _ = run_both(50)
    report = build_comparison_report(store=store, gameweek_id=1, persist=False)

    assert report.gameweek_id == 1
    assert "error" not in report.alignment
    assert report.alignment["n_common_players"] == 50
    assert 0.0 <= report.agreement["overall_rate"] <= 1.0
    assert report.disagreements  # a 50-player field rarely agrees perfectly
    assert report.captain["v2_captain_id"] is not None
    assert report.evidence["n_validated_gameweeks"] == 0
    assert report.evidence["level"] == "weak"
    assert report.persisted is False
    assert report.baseline_version_id is None
    assert report.expected_version_id is None
    assert report.insights  # human-readable insights present
    assert "promotion_criteria" in report.evidence
    assert report.summary()["n_common_players"] == 50


# ------------------------------------------------------------------
# Integration: full report with persistence
# ------------------------------------------------------------------

def reset_db():
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = ON"))

    session = get_session()
    try:
        for i in range(1, 5):
            session.add(Gameweek(id=i, name=f"Gameweek {i}", finished=False, is_next=(i == 1)))
        for i in range(1, 21):
            session.add(Team(id=i, name=f"Team{i}", short_name=f"T{i}"))
        for i in range(1, 60):
            session.add(Player(
                id=i, web_name=f"P{i}", team_id=(i % 20) + 1, element_type=(i % 4) + 1,
            ))
        session.commit()
    finally:
        session.close()


def test_build_comparison_report_persist_idempotent():
    reset_db()
    store, _, _ = run_both(50)

    session = get_session()
    try:
        report = build_comparison_report(
            store=store, gameweek_id=1, session=session, persist=True,
        )
        session.commit()
        assert report.persisted is True
        assert report.baseline_version_id is not None
        assert report.expected_version_id is not None
        assert report.baseline_version_id != report.expected_version_id

        # Idempotency: same version ids on rerun
        report2 = build_comparison_report(
            store=store, gameweek_id=1, session=session, persist=True,
        )
        session.commit()
        assert report2.expected_version_id == report.expected_version_id
        assert report2.baseline_version_id == report.baseline_version_id

        # Inject actuals + validate both → evidence count increments
        from database.models import Projection
        from engines.validation_engine import validate_version

        for version_id in (report.baseline_version_id, report.expected_version_id):
            for p in session.query(Projection).filter_by(version_id=version_id).all():
                p.actual_points = max(0, round(p.projected_points + random.gauss(0, 2.0)))
            validate_version(session, version_id, gameweek_id=1, persist=True)
        session.flush()

        report3 = build_comparison_report(
            store=store, gameweek_id=1, session=session, persist=True,
        )
        session.commit()
        assert report3.evidence["n_validated_gameweeks"] == 1
        assert report3.evidence["level"] in ("weak", "needs_more_data", "moderate")
        session.commit()
    finally:
        session.close()
