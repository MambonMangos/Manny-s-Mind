"""Metrics unit tests for the research backtest evaluation module."""

import pandas as pd
import pytest

from research import metrics


@pytest.fixture
def df():
    return pd.DataFrame({
        "season": ["2023-24"] * 5,
        "season_mode": ["faithful"] * 5,
        "predicted_points": [1.0, 2.0, 3.0, 4.0, 5.0],
        "actual_points": [1.0, 2.5, 3.0, 3.5, 6.0],
        "expected_minutes": [50, 60, 70, 80, 90],
        "actual_minutes": [45, 90, 70, 90, 90],
        "actual_starts": [0, 1, 1, 1, 1],
    })


def test_mae(df):
    # errors: 0, .5, 0, .5, 1 -> mean absolute error = 2.0/5 = 0.4
    assert metrics.mae(df["actual_points"], df["predicted_points"]) == pytest.approx(0.4)


def test_rmse(df):
    # errors: 0, .5, 0, .5, 1  -> mse .3 -> rmse ~.5477
    assert metrics.rmse(df["actual_points"], df["predicted_points"]) == pytest.approx(0.54772, abs=1e-3)


def test_bias(df):
    # mean pred 3.0, mean actual 3.2 -> bias -0.2 (under-predicts)
    assert metrics.bias(df["actual_points"], df["predicted_points"]) == pytest.approx(-0.2)


def test_correlation_perfect():
    y = pd.Series([1.0, 2.0, 3.0])
    p = pd.Series([1.0, 2.0, 3.0])
    assert metrics.correlation(y, p) == pytest.approx(1.0)


def test_mae_ignores_nan():
    y = pd.Series([1.0, None, 3.0])
    p = pd.Series([2.0, 5.0, 3.0])
    assert metrics.mae(y, p) == pytest.approx(0.5)


def test_calibration_buckets(df):
    cal = metrics.calibration_buckets(df, n_buckets=2)
    assert len(cal) >= 1
    assert {"n", "mean_predicted", "mean_actual", "mae"} <= set(cal.columns)


def test_summarise_groups(df):
    s = metrics.summarise(df, group_cols=[])
    assert "mae_points" in s.columns
    assert "bias_points" in s.columns
    assert "mae_minutes" in s.columns
