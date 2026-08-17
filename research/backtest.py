"""Historical V3 baseline backtest.

Runs the production V3 engines (expected_points_v1 + expected_minutes_v1)
READ-ONLY against leakage-safe reconstructed historical states, and records
predicted vs actual points/minutes per (season, round, player).

No production code is imported for modification; engines are used exactly as
the production pipeline uses them (build_feature_store -> project_*).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from research import config
from research.loader import SeasonData
from research.state import build_state

logger = logging.getLogger(__name__)


def _capture_features(
    store, sd: SeasonData, gw_n: int, out: pd.DataFrame
) -> pd.DataFrame:
    """Capture the full Feature Store matrix for a gameweek (leakage-safe)."""
    import pandas as pd

    feats = {}
    for prefix, frame in [
        ("minutes_", store.minutes_features()),
        ("xgi_", store.xgi_features()),
        ("fixture_", store.fixture_features()),
        ("value_", store.value_features()),
        ("market_", store.market_features()),
        ("availability_", store.availability_features()),
        ("set_piece_", store.set_piece_features()),
        ("trend_", store.trend_features()),
    ]:
        f = frame.add_prefix(prefix)
        feats.update(f.to_dict("series"))

    feat = pd.DataFrame(feats)
    feat["player_id"] = store.df["player_id"].values
    feat["season"] = sd.season
    feat["round"] = gw_n

    raw_cols = [
        "web_name",
        "position",
        "team_id",
        "price",
        "minutes",
        "starts",
        "goals_scored",
        "assists",
        "total_points",
        "bonus",
        "bps",
        "influence",
        "creativity",
        "threat",
        "ict_index",
        "form",
        "event_points",
        "clean_sheets",
        "yellow_cards",
        "red_cards",
        "saves",
    ]
    for c in raw_cols:
        if c in store.df.columns:
            feat["raw_" + c] = store.df[c].values

    feat = feat.merge(
        out[
            [
                "player_id",
                "actual_points",
                "actual_minutes",
                "actual_starts",
                "data_quality",
                "data_quality_minutes",
                "predicted_points",
                "expected_minutes",
                "xpts_per_90",
                "start_probability",
                "minutes_if_starting",
                "substitution_risk",
            ]
        ],
        on="player_id",
        how="left",
    )
    return feat


def predict_gameweek(
    sd: SeasonData,
    gw_n: int,
    with_features: bool = False,
    points_version: str | None = None,
    minutes_version: str | None = None,
    hist_features: tuple[str, ...] = (),
    evidence_version: str | None = None,
    evidence_cfg: dict | None = None,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    """Build the pre-gw_n state, run V3 engines, return predictions + actuals.

    ``points_version`` / ``minutes_version`` select optional config versions
    for the two engines (None = active/production configs). ``hist_features``
    injects ``hist_*`` columns (player/team/prev) from the historical feature
    store before the engines run — leakage-safe (rounds < gw_n only).
    ``evidence_version`` additionally injects ``ev_*`` columns from the
    evidence layer (current-season evidence weights), which the engines consume
    only when present. ``evidence_cfg`` overrides the evidence parameters in
    memory (parameter grid); None loads ``evidence_version`` from disk.

    If ``with_features`` is True, returns ``(out, features)`` where features is
    the full Feature Store matrix for the gameweek.
    """
    from engines.expected_minutes_engine import project_expected_minutes
    from engines.expected_points_engine import project_expected_points
    from features import build_feature_store
    from research.historical_features import add_historical_features

    players_df, fixture_map, team_name_map = build_state(sd, gw_n)
    if hist_features:
        players_df = add_historical_features(
            players_df, sd, gw_n, include=hist_features
        )
    if evidence_version:
        from research.evidence import add_evidence_features

        players_df = add_evidence_features(
            players_df,
            sd,
            gw_n,
            evidence_version=evidence_version,
            cfg=evidence_cfg,
        )
    store = build_feature_store(
        players_df=players_df,
        fixture_map=fixture_map,
        team_name_map=team_name_map,
        gameweek_id=gw_n,
    )

    xpts = project_expected_points(store, gw_n, config_version=points_version)
    mins = project_expected_minutes(store, gw_n, config_version=minutes_version)

    xp_df = pd.DataFrame([vars(p) for p in xpts])
    mins_df = pd.DataFrame([vars(p) for p in mins])

    out = xp_df.merge(
        mins_df[
            [
                "player_id",
                "expected_minutes",
                "start_probability",
                "minutes_if_starting",
                "substitution_risk",
                "sub_rate_given_not_start",
            ]
        ],
        on="player_id",
        how="left",
    )
    out = out.merge(
        mins_df[["player_id", "data_quality"]].rename(
            columns={"data_quality": "data_quality_minutes"}
        ),
        on="player_id",
        how="left",
    )
    out["predicted_points"] = out["xpts_per_90"] * out["expected_minutes"] / 90.0
    out["predicted_points"] = out["predicted_points"].fillna(0.0)
    out["season"] = sd.season
    out["round"] = gw_n

    # --- actuals for round gw_n ----------------------------------------------
    act = sd.gw[sd.gw["round"] == gw_n]
    if not act.empty:
        act_cols = [
            c for c in ["total_points", "minutes", "starts"] if c in act.columns
        ]
        act = act.groupby("element")[act_cols].sum()
        rename = {
            "total_points": "actual_points",
            "minutes": "actual_minutes",
            "starts": "actual_starts",
        }
        out = out.merge(
            act.rename(columns=rename),
            left_on="player_id",
            right_index=True,
            how="left",
        )
        for col in ["actual_points", "actual_minutes", "actual_starts"]:
            if col not in out.columns:
                out[col] = np.nan
    else:
        out["actual_points"] = np.nan
        out["actual_minutes"] = np.nan
        out["actual_starts"] = np.nan

    out["season_mode"] = "faithful" if sd.season in config.FAITHFUL_SEASONS else "proxy"
    if with_features:
        return out, _capture_features(store, sd, gw_n, out)
    return out


def run_season_backtest(
    season: str,
    first_gw: int = config.FIRST_PREDICT_GW,
    last_gw: int | None = None,
    use_cache: bool = True,
    progress: bool = True,
    with_features: bool = False,
    points_version: str | None = None,
    minutes_version: str | None = None,
    hist_features: tuple[str, ...] = (),
    evidence_version: str | None = None,
    evidence_cfg: dict | None = None,
    tag: str | None = None,
) -> pd.DataFrame:
    """Run a V3 backtest over every playable round in a season.

    Extra parameters (``points_version``, ``minutes_version``,
    ``hist_features``, ``evidence_version``, ``evidence_cfg``) enable
    experimental model variants; ``tag`` names the output file so different
    models do not overwrite each other.
    """
    sd = SeasonData.load(season, use_cache=use_cache)
    rounds = [
        r for r in sd.rounds if r >= first_gw and (last_gw is None or r <= last_gw)
    ]
    if not rounds:
        return pd.DataFrame()

    frames = []
    feature_frames = []
    for r in rounds:
        result = predict_gameweek(
            sd,
            r,
            with_features=with_features,
            points_version=points_version,
            minutes_version=minutes_version,
            hist_features=hist_features,
            evidence_version=evidence_version,
            evidence_cfg=evidence_cfg,
        )
        if with_features:
            df, feats = result
            feature_frames.append(feats)
        else:
            df = result
        frames.append(df)
        if progress:
            logger.info("[%s] gw %d done (%d players)", season, r, len(df))
    if with_features and feature_frames:
        feats = pd.concat(feature_frames, ignore_index=True)
        fname = f"{season}_features{('_' + tag) if tag else ''}.parquet"
        out_path = config.STORE_DIR / fname
        feats.to_parquet(out_path)
        logger.info("[%s] wrote %d feature rows to %s", season, len(feats), out_path)
    return pd.concat(frames, ignore_index=True)


def run_backtest(
    seasons: list[str] | None = None,
    use_cache: bool = True,
    with_features: bool = False,
    points_version: str | None = None,
    minutes_version: str | None = None,
    hist_features: tuple[str, ...] = (),
    evidence_version: str | None = None,
    tag: str = "baseline",
) -> pd.DataFrame:
    """Run the backtest over the configured seasons; cache result CSV.

    ``tag`` names the output CSV (e.g. "baseline", "v3_hist_fold2"); default
    keeps the original ``v3_baseline_predictions.csv`` filename.
    """
    seasons = seasons or config.BACKTEST_SEASONS
    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    all_frames = []
    for season in seasons:
        df = run_season_backtest(
            season,
            use_cache=use_cache,
            with_features=with_features,
            points_version=points_version,
            minutes_version=minutes_version,
            hist_features=hist_features,
            evidence_version=evidence_version,
        )
        all_frames.append(df)
    res = pd.concat(all_frames, ignore_index=True)
    out_name = (
        "v3_baseline_predictions.csv"
        if tag == "baseline"
        else f"v3_{tag}_predictions.csv"
    )
    res.to_csv(config.RESULTS_DIR / out_name, index=False)
    logger.info(
        "wrote %d prediction rows to %s", len(res), config.RESULTS_DIR / out_name
    )
    return res
