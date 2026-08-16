"""Preseason prior tests (research/preseason.py, Model E)."""

from __future__ import annotations

import numpy as np

from research.preseason import (
    PRIOR_COLUMNS,
    build_preseason_prior,
    build_preseason_state,
    load_preseason_raw,
    run_preseason_baseline,
    validate_preseason_prior,
)


def test_raw_snapshot_available():
    raw = load_preseason_raw()
    assert len(raw) > 400
    assert "element" in raw.columns
    assert "code" in raw.columns


def test_prior_schema_and_rates():
    prior = build_preseason_prior()
    assert list(prior.columns) == PRIOR_COLUMNS
    assert set(prior["position"].unique()) <= {"GKP", "DEF", "MID", "FWD"}
    meaningful = prior[prior["last_season_minutes"] > 0]
    assert (meaningful["last_season_starts_rate"].between(0, 1)).all()
    assert (meaningful["last_season_minutes_per_start"].between(0, 90)).all()
    assert (prior["price"].between(3.5, 16.0)).all()


def test_prior_elite_signal():
    prior = build_preseason_prior()
    top = prior[prior["last_season_minutes"] >= 2000]
    assert not top.empty
    assert top["last_season_xg_per_90"].max() > 0.3


def test_prior_per90_consistency():
    """points_per_90 = points / (minutes/90) on the same rows."""
    prior = build_preseason_prior()
    mask = prior["last_season_minutes"] > 0
    expected = prior.loc[mask, "last_season_points"] / (prior.loc[mask, "last_season_minutes"] / 90)
    assert np.allclose(prior.loc[mask, "last_season_points_per_90"], expected)


def test_validate_preseason_prior_all_checks():
    prior = build_preseason_prior()
    checks = validate_preseason_prior(prior)
    assert checks["n_players"] == len(prior)
    assert checks["columns_present"]
    assert checks["positions_valid"]
    assert checks["price_bounds"]
    assert checks["statuses_valid"]
    assert checks["rate_bounds"]
    assert checks["set_piece_orders_bounded"]
    assert checks["sane_elite_signal"]


def test_preseason_state_engine_schema():
    state = build_preseason_state()
    for col in ["id", "web_name", "team_id", "position_id", "position", "price",
                "minutes", "starts", "expected_goals", "expected_assists",
                "chance_of_playing_next_round", "status"]:
        assert col in state.columns, f"missing {col}"
    assert (state["id"].nunique() == len(state))


def test_preseason_baseline_runs():
    out = run_preseason_baseline()
    assert "predicted_points" in out.columns
    assert "expected_minutes" in out.columns
    assert (out["predicted_points"] >= 0).all()
    assert (out["expected_minutes"].between(0, 90)).all()
    assert out["predicted_points"].nlargest(1).iloc[0] > 1.0


def test_preseason_baseline_deterministic():
    a = run_preseason_baseline()
    b = run_preseason_baseline()
    assert a["predicted_points"].equals(b["predicted_points"])
