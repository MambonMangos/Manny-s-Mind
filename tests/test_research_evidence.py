"""Evidence-layer tests (research/evidence.py + config/evidence)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.evidence import (
    GROUPS,
    add_evidence_features,
    blend,
    current_weight,
    evidence_breakdown,
    evidence_strength,
    load_evidence_config,
)
from research.loader import SeasonData
from research.state import build_state


def _cfg():
    return load_evidence_config()


def _fixture_state(season: str = "2023-24", gw: int = 3):
    sd = SeasonData.load(season)
    players, _, _ = build_state(sd, gw)
    return sd, players, gw


# ---------------------------------------------------------------------------
# Strength / weights / blend math
# ---------------------------------------------------------------------------


def test_evidence_strength_doc_examples():
    cfg = _cfg()
    # Player A: 4 starts, 360 min, 4 appearances -> strength ~0.74
    s_a = float(
        evidence_strength(
            pd.Series([360.0]),
            pd.Series([4.0]),
            pd.Series([4.0]),
            cfg,
        ).iloc[0]
    )
    assert s_a == pytest.approx(0.74, abs=0.02)
    # Player B: 38 min, 0 starts, 1 appearance -> strength ~0.21
    s_b = float(
        evidence_strength(
            pd.Series([38.0]),
            pd.Series([0.0]),
            pd.Series([1.0]),
            cfg,
        ).iloc[0]
    )
    assert s_b == pytest.approx(0.21, abs=0.02)


def test_evidence_strength_monotonic_and_bounded():
    cfg = _cfg()
    eff = [0.0, 100.0, 300.0, 600.0, 10000.0]
    zeros = pd.Series([0.0] * len(eff))
    s = evidence_strength(pd.Series(eff), zeros, zeros, cfg)
    vals = s.tolist()
    assert vals == sorted(vals)
    assert all(0.0 <= v <= cfg["accumulation"]["max_strength"] for v in vals)
    assert float(s.iloc[0]) == pytest.approx(cfg["accumulation"]["strength_floor"])


def test_current_weight_floor_and_exponent():
    cfg = _cfg()
    # starting: exp 0.6, floor 0.85 -> low strength hits the floor
    w = float(current_weight(pd.Series([0.2]), "starting", cfg).iloc[0])
    assert w == pytest.approx(0.85)
    # rate_attack: exp 2.0, floor 0.60 -> strong evidence passes the floor
    w_high = float(current_weight(pd.Series([0.9]), "rate_attack", cfg).iloc[0])
    assert w_high == pytest.approx(0.9**2.0, abs=1e-6)
    assert w_high >= 0.60
    # never exceeds 1.0
    w_max = float(current_weight(pd.Series([1.0]), "bonus", cfg).iloc[0])
    assert w_max == 1.0


def test_blend_formula():
    hist = pd.Series([0.5, 1.0])
    current = pd.Series([1.0, 0.0])
    w = pd.Series([0.0, 1.0])
    out = blend(hist, current, w)
    assert out.iloc[0] == pytest.approx(0.5)
    assert out.iloc[1] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Feature frame
# ---------------------------------------------------------------------------


def test_add_evidence_features_columns_and_sanity():
    sd, players, gw = _fixture_state()
    ev = add_evidence_features(players, sd, gw)
    assert ev.shape[0] == len(players)
    expected = {
        "ev_strength",
        "ev_has_prior",
        "ev_prior_type",
        "ev_w_rate_attack",
        "ev_w_starting",
        "ev_w_minutes",
        "ev_w_bonus",
        "ev_w_team",
        "ev_xg_per_90",
        "ev_xa_per_90",
        "ev_xgi_per_90",
        "ev_bps_per_90",
        "ev_prior_starts_rate",
        "ev_minutes_per_start",
        "ev_team_attack_mult",
        "ev_team_defense_mult",
    }
    assert expected <= set(ev.columns)
    for col in expected - {"ev_prior_type", "ev_has_prior"}:
        assert ev[col].notna().all(), f"NaN in {col}"
    assert ev["ev_strength"].between(0.0, 1.0).all()
    assert set(ev["ev_prior_type"].unique()) <= {"personal", "position", "none"}
    assert ev["ev_minutes_per_start"].between(0.0, 90.0).all()
    assert ev["ev_team_attack_mult"].gt(0.4).all()


def test_personal_prior_for_salah():
    sd, players, gw = _fixture_state()
    codes = sd.players_raw.set_index("element")["code"]
    ev = add_evidence_features(players, sd, gw).assign(_code=players["id"].map(codes))
    salah = ev[ev["_code"] == 118748].iloc[0]
    assert salah["ev_prior_type"] == "personal"
    assert salah["ev_has_prior"] == 1


def test_position_or_none_prior_for_unknown_players():
    sd, players, gw = _fixture_state()
    ev = add_evidence_features(players, sd, gw)
    # position-average fallback covers players without a reliable personal prior
    covered = ev[ev["ev_prior_starts_rate"].notna()]
    assert len(covered) == len(ev)
    assert (ev["ev_prior_type"] != "none").any()


def test_new_player_no_prior_frame():
    sd, players, _ = _fixture_state()
    # a synthetic element id absent from players_raw must not crash and yields
    # no personal prior (NaN personal columns, no look-ahead by name)
    from research.evidence import _map_personal_prior

    fake = players.copy()
    fake["id"] = 999999
    prior = _map_personal_prior(fake, sd, None)
    assert prior["p_prev_games"].isna().all()


def test_no_history_before_gw_raises():
    sd, players, _ = _fixture_state()
    with pytest.raises(ValueError):
        add_evidence_features(players, sd, 1)


def test_temporal_integrity_uses_only_past_rounds():
    # ev_cur starts rate = starts / games featured, using rounds < gw_n only.
    sd, players, gw = _fixture_state(gw=8)
    ev = add_evidence_features(players, sd, gw)
    past = sd.gw[sd.gw["round"] < gw]
    appeared = past[past["minutes"] > 0].groupby("element").size()
    appeared = (
        appeared.reindex(players["id"].values)
        .set_axis(players.index, axis=0)
        .fillna(0.0)
    )
    expected = (players["starts"] / appeared).fillna(0.0)
    assert (ev["ev_cur_starts_rate"] - expected.round(4)).abs().max() < 1e-9
    assert (ev["ev_cur_mps"] > 0).sum() > 0


def test_evidence_breakdown_structure():
    sd, players, gw = _fixture_state()
    ev = add_evidence_features(players, sd, gw)
    pid = int(ev["id"].iloc[0])
    bd = evidence_breakdown(pid, ev, sd, gw)
    assert bd["player_id"] == pid
    assert set(bd["groups"]) == set(GROUPS)
    g = bd["groups"]["rate_attack"]
    assert {
        "current_value",
        "historical_value",
        "blended_value",
        "weight_current",
    } <= set(g)
    assert 0.0 <= g["weight_current"] <= 1.0
    with pytest.raises(KeyError):
        evidence_breakdown(999999, ev, sd, gw)


def test_evidence_breakdown_builds_frame_on_demand():
    sd, players, gw = _fixture_state()
    bd = evidence_breakdown(int(players["id"].iloc[0]), players, sd, gw)
    assert bd["evidence_strength"] > 0


def test_leakage_audit_future_rounds_do_not_influence_evidence():
    """Corrupting every round >= gw_n must not change the ev_* columns."""
    from dataclasses import replace

    sd, players, gw = _fixture_state(gw=8)
    ev = add_evidence_features(players, sd, gw)
    corrupted = replace(
        sd,
        gw=sd.gw.assign(
            minutes=np.where(sd.gw["round"] >= gw, -99999, sd.gw["minutes"]),
            starts=np.where(sd.gw["round"] >= gw, -1, sd.gw["starts"]),
            bps=np.where(sd.gw["round"] >= gw, -1, sd.gw["bps"]),
            total_points=np.where(sd.gw["round"] >= gw, -1, sd.gw["total_points"]),
        ),
    )
    ev_future = add_evidence_features(players, corrupted, gw)
    ev_cols = [c for c in ev.columns if c.startswith("ev_")]
    pd.testing.assert_frame_equal(
        ev[ev_cols], ev_future[ev_cols],
        check_like=True, check_dtype=False,
    )


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def test_evidence_config_not_in_active_map():
    from utils.config import load_active_versions

    active = load_active_versions()
    assert "evidence" not in active, "evidence must never be in active.yaml"


def test_evidence_config_groups_have_required_keys():
    cfg = _cfg()
    for group in GROUPS:
        g = cfg["feature_groups"][group]
        assert "transition_exponent" in g
        assert "min_current_weight" in g
        assert 0.0 <= g["min_current_weight"] <= 1.0
    acc = cfg["accumulation"]
    assert 0.0 < acc["saturation_minutes"]
    assert 0.0 < acc["strength_floor"] < acc["max_strength"] < 1.0


# ---------------------------------------------------------------------------
# Engine integration
# ---------------------------------------------------------------------------


def test_evidence_changes_points_and_minutes_predictions():
    from research.backtest import predict_gameweek

    sd = SeasonData.load("2023-24")
    base = predict_gameweek(
        sd,
        5,
        points_version="expected_points_v1_hist",
        minutes_version="expected_minutes_v1_hist",
        hist_features=("player",),
    )
    ev = predict_gameweek(
        sd,
        5,
        points_version="expected_points_v1_hist",
        minutes_version="expected_minutes_v1_hist",
        hist_features=("player",),
        evidence_version="evidence_v1",
    )
    assert len(ev) == len(base)
    assert (
        ev["expected_minutes"].fillna(0) != base["expected_minutes"].fillna(0)
    ).any()
    assert (
        ev["predicted_points"].fillna(0) != base["predicted_points"].fillna(0)
    ).any()
    assert ev["predicted_points"].notna().all()
    assert ev["expected_minutes"].notna().all()


def test_production_path_has_no_evidence_columns():
    """Production (no evidence_version) must never touch the evidence path."""
    from research.backtest import predict_gameweek

    sd = SeasonData.load("2023-24")
    out = predict_gameweek(sd, 5)
    assert not any(c.startswith("ev_") for c in out.columns)
    assert not any(c.startswith("hist_") for c in out.columns)


def test_evidence_minutes_never_negative_and_bounded():
    from research.backtest import predict_gameweek

    sd = SeasonData.load("2023-24")
    ev = predict_gameweek(
        sd,
        6,
        points_version="expected_points_v1_hist",
        minutes_version="expected_minutes_v1_hist",
        hist_features=("player",),
        evidence_version="evidence_v1",
    )
    assert ev["expected_minutes"].ge(0).all()
    assert ev["start_probability"].between(0, 1).all()
    assert ev["minutes_if_starting"].le(90.0).all()
