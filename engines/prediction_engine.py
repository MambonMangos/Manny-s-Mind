"""Prediction Engine – single source of truth for projected points, minutes projection, risk classification.

Consolidates:
  - project_minutes (from transfer_engine.py)
  - project_points_gain (from transfer_engine.py)
  - classify_risk (from transfer_engine.py)
  - compute_confidence (from transfer_engine.py)
"""

from __future__ import annotations

import pandas as pd


def project_minutes(row: pd.Series) -> float:
    """Project future minutes based on recent playing time.

    This is the SINGLE implementation — never compute minutes projection inline.
    """
    minutes = float(row.get("minutes", 0) or 0)
    if minutes == 0:
        return 60.0
    if minutes >= 270:
        return 85.0
    if minutes >= 180:
        return 70.0
    if minutes >= 90:
        return 55.0
    return 30.0


def project_points_gain(
    out_assessment,
    in_row: pd.Series,
    in_avg_diff_3: float,
) -> float:
    """Estimate expected points gained over the next 3 GWs from a swap.

    This is the SINGLE implementation — never compute expected gain inline.
    """
    out_proj = out_assessment.form * 3 * (out_assessment.minutes_fraction / 100.0)

    in_form = float(in_row.get("form", 0) or 0)
    in_minutes = project_minutes(in_row)
    in_minutes_factor = in_minutes / 90.0
    fixture_adj = (5 - in_avg_diff_3) / 4.0

    in_proj = in_form * 3 * in_minutes_factor * max(fixture_adj, 0.5)

    return round(in_proj - out_proj, 2)


def classify_risk(row: pd.Series, avg_diff_3: float) -> str:
    """Classify risk level for a player.

    This is the SINGLE implementation — never classify risk inline.
    """
    risk_score = 0
    minutes = float(row.get("minutes", 0) or 0)
    status = str(row.get("status", "a") or "a")

    if status != "a":
        risk_score += 3
    if minutes < 180:
        risk_score += 2
    if avg_diff_3 >= 4.0:
        risk_score += 1
    if float(row.get("form", 0) or 0) < 2.0:
        risk_score += 1

    if risk_score >= 4:
        return "High"
    if risk_score >= 2:
        return "Medium"
    return "Low"


def compute_confidence(
    expected_gain: float,
    risk_level: str,
    minutes_projection: float,
    form: float,
) -> float:
    """Compute a 0-100 confidence rating.

    This is the SINGLE implementation — never compute confidence inline.
    """
    base = 50.0

    # Positive expected gain increases confidence
    base += min(expected_gain * 3, 25)

    # Low risk adds confidence
    if risk_level == "Low":
        base += 10
    elif risk_level == "High":
        base -= 15

    # High minutes reliability adds confidence
    if minutes_projection >= 80:
        base += 10
    elif minutes_projection < 50:
        base -= 10

    # Good form adds confidence
    if form >= 5:
        base += 5

    return round(max(min(base, 95), 10), 1)
