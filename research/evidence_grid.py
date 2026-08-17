"""Evidence-layer parameter grid — Phase 4/6 of the evidence framework.

Runs the evidence model (Model G) over a coarse grid of the two highest-impact
knobs on fold1 (validate 2023-24):

    starting_floor        minimum current-season weight on P(start)
    rate_attack_floor     minimum current-season weight on attack rates

Saturation and exponents are held at their config defaults. Results are cached
per combo under data_research/results/ and summarised to
``evidence_grid_fold1.csv``. The best fold1 combo is then run honestly on
fold2 (2024-25) — the grid is tuned on fold1 only, never on fold2.

Leakage safety is identical to the rest of the research program: each gameweek
uses only rounds < gw_n and the completed previous season.
"""

from __future__ import annotations

import copy
import itertools
import logging

import pandas as pd

from research import config as rconfig
from research.backtest import run_season_backtest
from research.evidence import GROUPS, load_evidence_config
from research.validation import summarize_model

logger = logging.getLogger(__name__)

POINTS = "expected_points_v1_hist"
MINUTES = "expected_minutes_v1_hist"

# Fold1 grid over the two high-impact per-group current-weight floors
# (saturation and exponents held at config defaults). 2 x 2 = 4 combos.
GRID = {
    "starting_floor": [0.70, 0.85],
    "rate_attack_floor": [0.60, 0.75],
}


def _override_cfg(
    base: dict,
    starting_floor: float,
    rate_attack_floor: float,
) -> dict:
    cfg = copy.deepcopy(base)
    cfg["feature_groups"]["starting"]["min_current_weight"] = starting_floor
    cfg["feature_groups"]["rate_attack"]["min_current_weight"] = rate_attack_floor
    return cfg


def _name(starting_floor: float, rate_attack_floor: float) -> str:
    return f"stf{starting_floor:.2f}_raf{rate_attack_floor:.2f}"


def run_grid_fold1(
    use_cache: bool = True,
    progress: bool = True,
) -> pd.DataFrame:
    """Run every grid combo on 2023-24 and return the summarised table."""
    base = load_evidence_config()
    rows = []
    for starting_floor, rate_attack_floor in itertools.product(
        GRID["starting_floor"],
        GRID["rate_attack_floor"],
    ):
        name = _name(starting_floor, rate_attack_floor)
        tag = f"G_evidence_{name}_fold1"
        cache = rconfig.RESULTS_DIR / f"v3_{tag}_predictions.csv"
        if use_cache and cache.exists():
            df = pd.read_csv(cache)
            logger.info("[grid] loaded cached %s", cache.name)
        else:
            cfg = _override_cfg(base, starting_floor, rate_attack_floor)
            df = run_season_backtest(
                "2023-24",
                points_version=POINTS,
                minutes_version=MINUTES,
                hist_features=("player",),
                evidence_version="evidence_v1",
                evidence_cfg=cfg,
                tag=tag,
                progress=progress,
            )
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache, index=False)
        row = {
            "combo": name,
            "starting_floor": starting_floor,
            "rate_attack_floor": rate_attack_floor,
        }
        row.update(summarize_model(df))
        rows.append(row)

    table = pd.DataFrame(rows)
    out = rconfig.RESULTS_DIR / "evidence_grid_fold1.csv"
    table.to_csv(out, index=False)
    logger.info("wrote %d grid rows to %s", len(table), out)
    return table


def best_fold1_combo() -> str:
    """Combo with the lowest pooled RMSE on fold1 (tie-break: MAE)."""
    table = pd.read_csv(rconfig.RESULTS_DIR / "evidence_grid_fold1.csv")
    return table.sort_values(["rmse_points", "mae_points"]).iloc[0]["combo"]


def run_best_on_fold2(combo: str | None = None, use_cache: bool = True) -> dict:
    """Honest fold2 (2024-25) run of the best fold1 combo."""
    combo = combo or best_fold1_combo()
    table = pd.read_csv(rconfig.RESULTS_DIR / "evidence_grid_fold1.csv")
    row = table[table["combo"] == combo].iloc[0]
    base = load_evidence_config()
    cfg = _override_cfg(
        base,
        float(row["starting_floor"]),
        float(row["rate_attack_floor"]),
    )
    tag = f"G_evidence_{combo}_fold2"
    cache = rconfig.RESULTS_DIR / f"v3_{tag}_predictions.csv"
    if use_cache and cache.exists():
        df = pd.read_csv(cache)
    else:
        df = run_season_backtest(
            "2024-25",
            points_version=POINTS,
            minutes_version=MINUTES,
            hist_features=("player",),
            evidence_version="evidence_v1",
            evidence_cfg=cfg,
            tag=tag,
            progress=False,
        )
        cache.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(cache, index=False)
    metrics = summarize_model(df)
    logger.info(
        "[fold2] best combo %s: RMSE=%.3f MAE=%.3f start_acc=%.3f",
        combo,
        metrics["rmse_points"],
        metrics["mae_points"],
        metrics["start_accuracy"],
    )
    return {"combo": combo, "metrics": metrics}


def _disable_cfg(base: dict, group: str | None) -> dict:
    """Copy of the evidence config with one group (or all) at pure current."""
    cfg = copy.deepcopy(base)
    targets = GROUPS if group is None else [group]
    for g in targets:
        cfg["feature_groups"][g]["min_current_weight"] = 1.0
    return cfg


def run_group_disable_fold1(
    use_cache: bool = True,
    progress: bool = True,
) -> pd.DataFrame:
    """Feature-group contribution analysis on fold1.

    Each row disables the blend for one group (``min_current_weight=1.0``,
    pure current-season values) at the validated defaults for the rest, plus
    an ``all_current`` row and the full evidence model. Isolates which
    group's historical-blending costs the most vs D.
    """
    base = load_evidence_config()
    rows = []
    for group in [None, *GROUPS]:
        name = "all_current" if group is None else f"disable_{group}"
        tag = f"G_evidence_{name}_fold1"
        cache = rconfig.RESULTS_DIR / f"v3_{tag}_predictions.csv"
        if use_cache and cache.exists():
            df = pd.read_csv(cache)
        else:
            cfg = _disable_cfg(base, group)
            df = run_season_backtest(
                "2023-24",
                points_version=POINTS,
                minutes_version=MINUTES,
                hist_features=("player",),
                evidence_version="evidence_v1",
                evidence_cfg=cfg,
                tag=tag,
                progress=progress,
            )
            cache.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache, index=False)
        row = {"variant": name}
        row.update(summarize_model(df))
        rows.append(row)

    table = pd.DataFrame(rows)
    out = rconfig.RESULTS_DIR / "evidence_group_analysis_fold1.csv"
    table.to_csv(out, index=False)
    logger.info("wrote %d group-analysis rows to %s", len(table), out)
    return table
