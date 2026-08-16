"""Backtest evaluation metrics for the V3 baseline.

Includes the error metrics, bias, calibration, and minutes-accuracy requested in
the brief, computed from the predictions CSV produced by research/backtest.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _aligned(y_true: pd.Series, y_pred: pd.Series) -> tuple[pd.Series, pd.Series]:
    m = pd.concat([y_true, y_pred], axis=1)
    m.columns = ["y", "p"]
    m = m.dropna()
    return m["y"], m["p"]


def mae(y_true: pd.Series, y_pred: pd.Series) -> float:
    y, p = _aligned(y_true, y_pred)
    if y.empty:
        return float("nan")
    return float(np.mean(np.abs(y - p)))


def rmse(y_true: pd.Series, y_pred: pd.Series) -> float:
    y, p = _aligned(y_true, y_pred)
    if y.empty:
        return float("nan")
    return float(np.sqrt(np.mean((y - p) ** 2)))


def bias(y_true: pd.Series, y_pred: pd.Series) -> float:
    """Positive = model over-predicts on average."""
    y, p = _aligned(y_true, y_pred)
    if y.empty:
        return float("nan")
    return float(np.mean(p - y))


def correlation(y_true: pd.Series, y_pred: pd.Series) -> float:
    y, p = _aligned(y_true, y_pred)
    if len(y) < 2 or y.std() == 0 or p.std() == 0:
        return float("nan")
    return float(np.corrcoef(y, p)[0, 1])


def calibration_buckets(
    df: pd.DataFrame, n_buckets: int = 5,
) -> pd.DataFrame:
    """Predicted-points buckets vs mean actual points (calibration check)."""
    d = df[["predicted_points", "actual_points"]].dropna().copy()
    if d.empty:
        return pd.DataFrame()
    d["bucket"] = pd.qcut(d["predicted_points"], n_buckets, duplicates="drop")
    return (
        d.groupby("bucket", observed=True)
        .agg(n=("actual_points", "size"),
             mean_predicted=("predicted_points", "mean"),
             mean_actual=("actual_points", "mean"),
             mae=("actual_points", lambda s: float(
                 np.mean(np.abs(s - d.loc[s.index, "predicted_points"])))))
        .reset_index()
    )


def _summarise_group(g: pd.DataFrame) -> pd.Series:
    return pd.Series({
        "n": len(g),
        "mae_points": mae(g["actual_points"], g["predicted_points"]),
        "rmse_points": rmse(g["actual_points"], g["predicted_points"]),
        "bias_points": bias(g["actual_points"], g["predicted_points"]),
        "corr_points": correlation(g["actual_points"], g["predicted_points"]),
        "actual_mean": float(g["actual_points"].mean()),
        "predicted_mean": float(g["predicted_points"].mean()),
        "mae_minutes": mae(g["actual_minutes"], g["expected_minutes"]),
        "corr_minutes": correlation(g["actual_minutes"], g["expected_minutes"]),
        "actual_starts_mean": float(g["actual_starts"].mean()),
        "expected_minutes_mean": float(g["expected_minutes"].mean()),
    })


def summarise(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    """Overall and grouped error summary (points and minutes)."""
    if not group_cols:
        return _summarise_group(df).to_frame().T
    records = []
    for _, g in df.groupby(group_cols, dropna=False):
        row = {}
        for c, val in zip(group_cols, g.iloc[0][group_cols]):
            row[c] = val
        row.update(_summarise_group(g).to_dict())
        records.append(row)
    return pd.DataFrame(records)
