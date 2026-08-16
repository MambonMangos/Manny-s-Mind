"""Deliverable D: Feature analysis — which features actually predict next-GW points.

Uses the captured Feature Store matrix (leakage-safe: every feature is computed
from state before the target gameweek). Faithful seasons only (2022-23..2024-25),
where starts and xG exist.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from research import config

logger = logging.getLogger(__name__)

# Numeric candidate features, grouped by category (columns as captured).
FEATURE_GROUPS: dict[str, list[str]] = {
    "minutes": ["minutes_minutes_season", "minutes_minutes_per_game",
                "minutes_minutes_fraction", "minutes_starts_rate",
                "minutes_starts", "minutes_minutes_projected"],
    "xgi": ["xgi_xg_raw", "xgi_xa_raw", "xgi_xgi_raw", "xgi_xgc_raw",
            "xgi_xgi_per_90", "xgi_finishing_ratio", "xgi_creative_ratio"],
    "fixture": ["fixture_fixture_score_3gw", "fixture_team_strength",
                "fixture_fixture_avg_1gw", "fixture_fixture_avg_3gw",
                "fixture_fixture_avg_6gw", "fixture_home_count_next_3",
                "fixture_fixture_easy_count", "fixture_fixture_hard_count",
                "fixture_fixture_swing"],
    "value": ["value_price", "value_points_per_million", "value_cost_change_start",
              "value_cost_change_event", "value_value_form", "value_value_season",
              "value_price_direction"],
    "market": ["market_selected_by_percent", "market_transfers_in_event",
               "market_transfers_out_event", "market_net_transfers",
               "market_transfer_velocity"],
    "availability": ["availability_chance_next", "availability_chance_this",
                     "availability_is_fit"],
    "set_piece": ["set_piece_penalties_order", "set_piece_fk_order",
                  "set_piece_corners_order", "set_piece_set_piece_raw",
                  "set_piece_is_penalty_taker", "set_piece_is_fk_taker",
                  "set_piece_is_corner_taker"],
    "trend": ["trend_form", "trend_influence", "trend_creativity", "trend_threat",
              "trend_ict_index", "trend_event_points", "trend_form_momentum"],
    "raw": ["raw_minutes", "raw_starts", "raw_goals_scored", "raw_assists",
            "raw_total_points", "raw_bps", "raw_influence", "raw_creativity",
            "raw_threat", "raw_ict_index", "raw_form", "raw_event_points",
            "raw_clean_sheets", "raw_saves"],
    "engine": ["predicted_points", "xpts_per_90", "expected_minutes",
               "start_probability", "minutes_if_starting", "substitution_risk"],
}

ALL_FEATURES = [c for cols in FEATURE_GROUPS.values() for c in cols]


def load_features(seasons: list[str] | None = None) -> pd.DataFrame:
    seasons = seasons or config.FAITHFUL_SEASONS
    frames = []
    for s in seasons:
        p = config.STORE_DIR / f"{s}_features.parquet"
        if not p.exists():
            logger.warning("missing feature file: %s", p)
            continue
        frames.append(pd.read_parquet(p))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _spearman(x: pd.Series, y: pd.Series) -> float:
    d = pd.concat([x, y], axis=1).dropna()
    if len(d) < 30 or d.iloc[:, 0].nunique() < 2 or d.iloc[:, 1].nunique() < 2:
        return float("nan")
    rx = d.iloc[:, 0].rank()
    ry = d.iloc[:, 1].rank()
    if rx.std() == 0 or ry.std() == 0:
        return float("nan")
    return float(np.corrcoef(rx, ry)[0, 1])


def feature_importance(
    df: pd.DataFrame,
    target: str = "actual_points",
    min_rows: int = 200,
) -> pd.DataFrame:
    """Spearman correlation of every candidate feature vs target, per season.

    Returns one row per (feature, season) plus aggregate columns.
    """
    rows = []
    for season, sub in df.groupby("season"):
        for feature in ALL_FEATURES:
            if feature not in sub.columns:
                continue
            if sub[feature].nunique(dropna=False) < 2:
                continue
            r = _spearman(sub[feature], sub[target])
            if np.isnan(r):
                continue
            rows.append({"feature": feature, "season": season, "spearman": r})
    if not rows:
        return pd.DataFrame(columns=["feature", "season", "spearman"])

    imp = pd.DataFrame(rows)
    agg = (
        imp.groupby("feature")["spearman"]
        .agg(median="median", min="min", max="max", n="count")
        .reset_index()
    )
    agg["sign_consistent"] = (agg["min"] * agg["max"] > 0).astype(int)
    agg = agg[agg["n"] >= 2]
    return agg.sort_values("median", key=abs, ascending=False)


def report_table(
    imp: pd.DataFrame,
    group_by: str,
    df: pd.DataFrame,
    target: str = "actual_points",
    top_n: int = 20,
) -> str:
    """Top-N features per position group (median |Spearman| ranking)."""
    out = []
    for group, sub in df.groupby(group_by):
        gimp = feature_importance(sub, target=target)
        gimp["group"] = group
        out.append(gimp)
    if not out:
        return "_no data_"
    combined = pd.concat(out, ignore_index=True)

    top = combined.sort_values("median", key=abs, ascending=False).head(top_n)
    lines = ["| group | feature | n_seasons | median_r | min_r | max_r | sign_consistent |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for _, row in top.iterrows():
        lines.append(
            f"| {row['group']} | {row['feature']} | {int(row['n'])} "
            f"| {row['median']:.4f} | {row['min']:.4f} | {row['max']:.4f} "
            f"| {row['sign_consistent']} |"
        )
    return "\n".join(lines)


def generate_feature_report(df: pd.DataFrame) -> str:
    d = df[df["actual_points"].notna()].copy()
    d = d[~d["raw_position"].isin(["AM", "", "None"])].copy()
    lines = []
    a = lines.append

    a("# Historical Feature Analysis — which features predict next-GW points")
    a("")
    a(f"**Data:** vaastav `{config.SOURCE_PIN}` · faithful seasons only "
      f"({', '.join(sorted(d['season'].unique()))}) · rows: **{len(d)}**")
    a("")
    a("Features are computed from state before the target gameweek "
      "(leakage-safe). Metric: **Spearman rank correlation with the player's "
      "actual points in the next gameweek**, computed per season and reported "
      "as median/min/max across seasons (sign_consistent = same sign in every "
      "season).")
    a("")
    cat = {c: cat for cat, cols in FEATURE_GROUPS.items() for c in cols}
    a("## Overall (all players)")
    imp = feature_importance(d)
    top = imp.head(25)
    a("| feature | category | n_seasons | median_r | min_r | max_r | sign_consistent |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    cat = {c: cat for cat, cols in FEATURE_GROUPS.items() for c in cols}
    for _, row in top.iterrows():
        a(f"| {row['feature']} | {cat.get(row['feature'], '')} | {int(row['n'])} "
          f"| {row['median']:.4f} | {row['min']:.4f} | {row['max']:.4f} "
          f"| {row['sign_consistent']} |")
    a("")
    cat = {c: cat for cat, cols in FEATURE_GROUPS.items() for c in cols}
    a("## Top features by position")
    a(report_table(imp, "raw_position", d))
    a("")
    a("## Conditional: regular players only (minutes_reliable == 1)")
    reg = d[d["minutes_minutes_reliable"] == 1]
    if len(reg):
        a(f"rows: {len(reg)}")
        a(report_table(imp, "raw_position", reg))
    else:
        a("_no regular-player rows_")
    a("")
    a("## Category strength (median |r| of best feature per category, by position)")
    cat_rows = []
    for position, sub in d.groupby("raw_position"):
        imp_pos = feature_importance(sub)
        imp_pos["category"] = imp_pos["feature"].map(cat)
        best = (
            imp_pos.sort_values("median", key=abs, ascending=False)
            .groupby("category")
            .first()
        )
        for cat_name, r in best.iterrows():
            cat_rows.append({"position": position, "category": cat_name,
                             "best_feature": r["feature"], "median_r": r["median"]})
    cdf = pd.DataFrame(cat_rows)
    cdf["abs_r"] = cdf["median_r"].abs()
    cdf = cdf.sort_values(["position", "abs_r"], ascending=[True, False])
    a("| position | category | best_feature | median_r |")
    a("|---|---|---|---:|")
    for _, r in cdf.iterrows():
        a(f"| {r['position']} | {r['category']} | {r['best_feature']} | {r['median_r']:.4f} |")
    a("")
    a("## V3 prediction vs the raw ingredients")
    s = pd.DataFrame([
        {"feature": "predicted_points (V3 output)", "spearman": _spearman(d["predicted_points"], d["actual_points"])},
        {"feature": "xpts_per_90 (V3)", "spearman": _spearman(d["xpts_per_90"], d["actual_points"])},
        {"feature": "expected_minutes (V3)", "spearman": _spearman(d["expected_minutes"], d["actual_points"])},
        {"feature": "form", "spearman": _spearman(d["trend_form"], d["actual_points"])},
        {"feature": "previous GW points (event_points)", "spearman": _spearman(d["trend_event_points"], d["actual_points"])},
        {"feature": "xgi_per_90", "spearman": _spearman(d["xgi_xgi_per_90"], d["actual_points"])},
        {"feature": "raw minutes", "spearman": _spearman(d["raw_minutes"], d["actual_points"])},
    ])
    a("| feature | spearman |")
    a("|---|---:|")
    for _, r in s.iterrows():
        a(f"| {r['feature']} | {r['spearman']:.4f} |")
    a("")
    a("## Notes")
    a("")
    a("- Spearman on single-GW points is inherently noisy (points are sparse "
      "integers 0-15); per-season medians give the *direction* of each feature.")
    a("- Only faithful seasons can rank xG features. Proxy seasons are excluded.")
    a("- 'sign_consistent' flags features whose sign is stable across all three "
      "faithful seasons — the most trustworthy candidates.")

    path = config.REPORT_DIR / "historical_feature_analysis.md"
    path.write_text("\n".join(lines))
    logger.info("wrote %s", path)
    return str(path)
