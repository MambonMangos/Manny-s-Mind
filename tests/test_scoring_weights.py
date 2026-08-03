"""Tests for the value-score weighting system.

Guards the invariant that WEIGHTS always sum to 1.0 (enforced at import time
in utils/constants.py) and that the composite score stays in a sane range.
These tests protect the "one source of truth for weights" principle.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _base_player_df(n=8) -> pd.DataFrame:
    """Deterministic synthetic player frame with all scoring components."""
    price = np.arange(n, dtype=float) + 5.0
    total_points = np.arange(n, dtype=float) * 20.0
    minutes = (np.arange(n, dtype=float) + 1.0) * 300.0
    return pd.DataFrame({
        "id": np.arange(1, n + 1),
        "web_name": [f"P{i}" for i in range(1, n + 1)],
        "price": price,
        "total_points": total_points,
        "minutes": minutes,
        "expected_goal_involvements": np.arange(n, dtype=float) * 2.0,
        "selected_by_percent": np.arange(n, dtype=float) * 5.0,
        "strength_overall_home": np.full(n, 1100.0),
        "strength_overall_away": np.full(n, 1100.0),
        "penalties_order": [1, 2, 3, None, None, None, None, None],
        "direct_freekicks_order": [1, 2, None, None, None, None, None, None],
    })


def test_weights_sum_to_one():
    """WEIGHTS must sum to 1.0 so the composite is a true weighted average."""
    from utils.constants import WEIGHTS

    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-6, f"Weights sum to {total}, expected 1.0"


def test_weights_have_all_components():
    """Every scoring component must have a weight (no silent drops)."""
    from utils.constants import WEIGHTS

    expected = {
        "minutes", "xgi_per_90", "value", "team_strength",
        "fixture", "ownership", "set_pieces",
    }
    assert set(WEIGHTS.keys()) == expected, f"Unexpected weight keys: {set(WEIGHTS) ^ expected}"


def test_active_config_matches_loaded_weights():
    """WEIGHTS (utils/constants.py) must match the active value_score config."""
    from utils.config import load_active_versions, load_config
    from utils.constants import WEIGHTS

    version = load_active_versions()["weights"]
    config = load_config("weights", version)
    for key, value in config["value_score"].items():
        assert WEIGHTS[key] == float(value), (
            f"Weight '{key}' mismatch: code={WEIGHTS[key]} config={value}"
        )


def test_constant_columns_do_not_break_scoring():
    """Constant components (min-max of a flat column) must not break the composite."""
    from services.scoring import compute_value_score

    df = _base_player_df()
    df["strength_overall_home"] = 1100.0
    df["strength_overall_away"] = 1100.0  # team strength is constant → flat 0-100

    result = compute_value_score(df)
    assert np.isfinite(result.composite).all(), "Composite must be finite"


def test_composite_in_range():
    """Composite (0-100 scale) must stay within [0, 100]."""
    from services.scoring import compute_value_score

    result = compute_value_score(_base_player_df())
    assert result.composite.min() >= 0.0, "Composite must not be negative"
    assert result.composite.max() <= 100.0, "Composite must not exceed 100"


def test_high_xgi_outscores_low_xgi():
    """Within one dataset, more xGI/90 (all else equal) must score higher.

    Min-max normalisation is column-relative, so the comparison must be made
    between rows of the same dataset, not across datasets.
    """
    from services.scoring import compute_value_score

    df = _base_player_df()
    # Player A and B identical except for expected_goal_involvements.
    base = df.iloc[[0]].copy()
    low = base.copy()
    high = base.copy()
    high["expected_goal_involvements"] = low["expected_goal_involvements"] + 5.0
    pair = pd.concat([low, high], ignore_index=True)

    res = compute_value_score(pair).composite
    assert res[1] > res[0], "Higher xGI/90 must produce a higher composite score"
