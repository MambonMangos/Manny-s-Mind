"""Value Engine – single source of truth for value scores and player ratings.

Consolidates:
  - compute_value_score (from scoring.py)
  - add_derived_columns (from scoring.py)
  - compute_player_rating (from squad_evaluator.py)
  - compute_position_averages (from squad_evaluator.py + transfer_engine.py)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from services.scoring import (
    ScoringResult,
    add_derived_columns,
    compute_value_score,
)
from utils.constants import WEIGHTS


def compute_position_averages(player_df: pd.DataFrame) -> dict[str, float]:
    """Compute average value score by position.

    This is the SINGLE implementation — never groupby position for value_score elsewhere.
    """
    if "position" not in player_df.columns or "value_score" not in player_df.columns:
        return {}
    return player_df.groupby("position")["value_score"].mean().to_dict()


def compute_player_rating(row, avg_diff_3: float, position_avg: dict[str, float]) -> float:  # noqa: ANN001
    """Compute a 0-100 squad rating for a single player.

    This is the SINGLE implementation — never compute player rating inline.
    """
    score = 0.0

    # Form (0-25)
    form = float(row.get("form", 0) or 0)
    score += min(form / 8.0, 1.0) * 25.0

    # xGI per 90 (0-25)
    xgi = float(row.get("xgi_per_90", 0) or 0)
    score += min(xgi / 1.0, 1.0) * 25.0

    # Value score (0-20)
    vs = float(row.get("value_score", 0) or 0)
    score += min(vs / 70.0, 1.0) * 20.0

    # Minutes reliability (0-15)
    mf = float(row.get("minutes_fraction", 0) or 0)
    score += min(mf / 80.0, 1.0) * 15.0

    # Fixture quality (0-15): easier = better
    fixture_score = (5 - avg_diff_3) / 4.0
    score += fixture_score * 15.0

    return round(min(score, 100.0), 1)
