"""Tests for the feature/minutes analysis modules (Deliverables D & E)."""

import numpy as np
import pandas as pd
import pytest

from research import config
from research import features_analysis as fa
from research import minutes_analysis as ma


def _synthetic_features(n: int = 600) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    pos = rng.choice(["GKP", "DEF", "MID", "FWD"], n)
    pos_code = pd.Series(pos).map({"GKP": 2.0, "DEF": 1.0, "MID": 1.5, "FWD": 1.8}).values
    season = rng.choice(["2022-23", "2023-24", "2024-25"], n)
    form = rng.normal(4, 3, n)
    actual = rng.poisson(np.exp(0.08 * form + 0.05 * pos_code + 0.1 * rng.normal(0, 1, n)))
    out = pd.DataFrame({
        "player_id": rng.integers(1, 1000, n),
        "season": season,
        "round": rng.integers(3, 38, n),
        "raw_position": pos,
        "position": pos,
        "raw_form": form,
        "trend_form": form,
        "raw_event_points": rng.integers(0, 15, n),
        "trend_event_points": rng.integers(0, 15, n),
        "minutes_minutes_season": rng.uniform(0, 3000, n),
        "minutes_minutes_reliable": rng.integers(0, 2, n),
        "minutes_minutes_fraction": rng.uniform(0, 1, n),
        "xgi_xgi_raw": rng.uniform(0, 60, n),
        "xgi_xgi_per_90": rng.uniform(0, 2, n),
        "raw_minutes": rng.uniform(0, 3000, n),
        "fixture_fixture_avg_3gw": rng.uniform(0, 10, n),
        "market_selected_by_percent": rng.uniform(0, 30, n),
        "set_piece_set_piece_raw": rng.uniform(0, 30, n),
        "predicted_points": rng.uniform(0, 12, n),
        "xpts_per_90": rng.uniform(0, 8, n),
        "expected_minutes": rng.uniform(0, 90, n),
        "start_probability": rng.uniform(0, 1, n),
        "minutes_if_starting": rng.uniform(50, 90, n),
        "substitution_risk": rng.uniform(0, 0.3, n),
        "actual_points": actual,
        "actual_minutes": rng.integers(0, 90, n),
        "actual_starts": rng.integers(0, 2, n),
        "data_quality_minutes": rng.choice(["good", "moderate"], n),
        "minutes_minutes_per_game": rng.uniform(0, 90, n),
    })
    out["raw_minutes"] = out["minutes_minutes_season"]
    out.loc[out.index % 2 == 1, "raw_minutes"] = rng.uniform(0, 200, (n + 1) // 2)
    return out


# ---------------------------------------------------------------- features


def test_feature_importance_structure_and_ranking():
    d = _synthetic_features()
    imp = fa.feature_importance(d)
    assert {"feature", "median", "min", "max", "n", "sign_consistent"} <= set(imp.columns)
    assert len(imp) >= 10
    assert imp["n"].min() >= 2
    # ranking is by |median| descending
    meds = imp["median"].abs().values
    assert np.all(meds[:-1] >= meds[1:] - 1e-12)


def test_feature_importance_sign_detection():
    d = _synthetic_features()
    imp = fa.feature_importance(d)
    r = imp[imp["feature"] == "raw_form"]
    assert len(r) == 1
    assert r["sign_consistent"].iloc[0] == 1
    assert r["median"].iloc[0] > 0


def test_spearman_matches_ranked_pearson():
    rng = np.random.default_rng(7)
    x = rng.normal(size=200)
    y = 2 * x + rng.normal(size=200)
    got = fa._spearman(pd.Series(x), pd.Series(y))
    expected = np.corrcoef(pd.Series(x).rank(), pd.Series(y).rank())[0, 1]
    assert got == pytest.approx(expected, abs=1e-12)


def test_spearman_rejects_small_constant_series():
    assert np.isnan(fa._spearman(pd.Series(np.arange(20)), pd.Series([1.0] * 20)))
    assert np.isnan(fa._spearman(pd.Series([5] * 40), pd.Series(np.arange(40.0))))


def test_load_features_skips_missing():
    d = fa.load_features(["2099-00", "2000-01"])
    assert d.empty


def test_generate_feature_report_writes_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    d = _synthetic_features(2000)
    path = fa.generate_feature_report(d)
    assert path == str(tmp_path / "historical_feature_analysis.md")
    text = (tmp_path / "historical_feature_analysis.md").read_text()
    assert "## Overall (all players)" in text
    assert "predicted_points (V3 output)" in text


# ---------------------------------------------------------------- minutes


def test_start_probability_calibration_restricts_to_good():
    d = _synthetic_features()
    cal = ma.start_probability_calibration(d)
    assert not cal.empty
    assert cal["n"].sum() == (d["data_quality_minutes"] == "good").sum()


def test_calibration_by_history_splits():
    d = _synthetic_features(4000)
    tab = ma.calibration_by_history(d)
    assert not tab.empty
    assert set(tab["history"]) <= {"established", "marginal"}
    assert set(tab["history"]) == {"established", "marginal"}
    assert tab["observed_starts_rate"].between(0, 1).all()
    assert (tab["n"] >= 50).all()


def test_minutes_if_starting_table_covers_positions():
    d = _synthetic_features()
    t = ma.minutes_if_starting_table(d)
    assert set(t["position"]) == {"GKP", "DEF", "MID", "FWD"}
    assert "implied_sub_rate" in t.columns
    assert "engine_sub_risk_mean" in t.columns


def test_expected_minutes_error_by_tier():
    d = _synthetic_features()
    err = ma.expected_minutes_error_by_tier(d)
    assert set(err["data_quality_minutes"]) <= {"good", "moderate"}
    assert (err["mae"] >= 0).all()


def test_generate_minutes_report_filters_faithful(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPORT_DIR", tmp_path)
    d = _synthetic_features(3000)
    d["season_mode"] = np.where(d["season"].isin(config.FAITHFUL_SEASONS),
                                "faithful", "proxy")
    d["position"] = d["raw_position"]
    ma.generate_minutes_report(d)
    text = (tmp_path / "historical_minutes_analysis.md").read_text()
    assert "## 1. Start-probability calibration" in text
    assert "## 7. Caveat" in text
    assert "substitution_risk" in text
