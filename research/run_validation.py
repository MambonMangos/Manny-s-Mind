"""Entry point: generate empirical configs and run the full validation program.

Usage:
    python -m research.run_validation [--no-cache] [--fold fold1|fold2] [--models A_baseline,...]

Regenerates the fold + final versioned configs from ``research.calibration``
(never overwrites existing YAMLs) and then runs the walk-forward ablation,
writing per-(model, fold) prediction CSVs, the ablation summary table, the
preseason (Model E) GW1 baseline and a plain-text summary under
``data_research/results/``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from research import config as rconfig
from research.calibration import (
    build_minutes_config,
    build_points_config,
    fit_params,
    write_config_yaml,
)
from research.validation import (
    FOLDS,
    build_ablation_table,
    run_fold,
    run_preseason_validation,
)

logger = logging.getLogger(__name__)


def ensure_configs(force: bool = False) -> None:
    """Write the fold + final candidate configs (additive, never overwrite).

    Skipped when the configs already exist (they are deterministic artifacts of
    ``research.calibration``); pass ``force=True`` to regenerate.
    """
    cfg_dir = Path("config")
    combos = [
        ("", ["2022-23", "2023-24", "2024-25"]),          # final candidate
        ("_fold1", ["2022-23"]),
        ("_fold2", ["2022-23", "2023-24"]),
    ]
    if not force:
        existing = all(
            (cfg_dir / "expected_points" / f"expected_points_v1_hist{suffix}.yaml").exists()
            and (cfg_dir / "expected_minutes" / f"expected_minutes_v1_hist{suffix}.yaml").exists()
            for suffix, _ in combos
        )
        if existing:
            logger.info("configs already present; skipping generation")
            return
    for suffix, seasons in combos:
        params = fit_params(seasons)
        write_config_yaml("expected_points", f"expected_points_v1_hist{suffix}",
                          build_points_config(params), cfg_dir)
        write_config_yaml("expected_minutes", f"expected_minutes_v1_hist{suffix}",
                          build_minutes_config(params), cfg_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Historical-data validation program")
    parser.add_argument("--no-cache", action="store_true", help="recompute (ignore cached results)")
    parser.add_argument("--fold", choices=["fold1", "fold2"], default=None, help="run one fold only")
    parser.add_argument("--models", default=None, help="comma-separated model ids to run")
    parser.add_argument("--force-configs", action="store_true", help="regenerate configs even if present")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    logger.info("ensuring empirical configs (fold + final candidates)")
    ensure_configs(force=args.force_configs)

    models = args.models.split(",") if args.models else None
    folds = [f for f in FOLDS if args.fold is None or f["name"] == args.fold]

    results = {}
    for fold in folds:
        logger.info("=== fold %s: train=%s validate=%s ===",
                    fold["name"], fold["train"], fold["validate"])
        results[fold["name"]] = run_fold(fold, models=models, use_cache=not args.no_cache)

    table = build_ablation_table(results)
    rconfig.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    table.to_csv(rconfig.RESULTS_DIR / "ablation_summary.csv", index=False)
    logger.info("ablation table -> %s", rconfig.RESULTS_DIR / "ablation_summary.csv")

    # Model E: preseason structural validation.
    preseason = run_preseason_validation()
    logger.info("preseason checks: %s", preseason["checks"])

    summary = ["", "=== ABLATION SUMMARY ==="]
    summary.append(table.to_string(index=False))
    summary.append("")
    summary.append("=== PRESEASON (MODEL E) ===")
    summary.append(str(preseason["checks"]))
    summary.append("GW1 top-10 xPts:")
    for row in preseason["top_gw1_xpts"]:
        summary.append(f"  {row['web_name']:<20} {row['position']:<4} {row['predicted_points']:.2f}")
    (rconfig.RESULTS_DIR / "validation_summary.txt").write_text("\n".join(summary))
    print("\n".join(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
