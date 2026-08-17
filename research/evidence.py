"""Evidence layer — blends historical priors with current-season evidence.

Phase 3 of the evidence-framework program. The evidence layer is NOT a second
prediction engine. It decides, per player and per feature group, how much trust
to place in current-season evidence versus the historical prior, where current
influence is driven by ACCUMULATED EVIDENCE VOLUME (effective minutes), not by
arbitrary gameweek decay::

    effective_minutes = w_minutes*minutes + w_starts*starts + w_app*appearances
    strength  = floor + (1 - floor) * (1 - exp(-effective_minutes / saturation))
    weight_g  = min(strength ** transition_exponent_g, 1.0)     # per feature group
    value     = weight_g * current_value + (1 - weight_g) * historical_value

Feature groups and their transition exponents (config/evidence/evidence_v1.yaml):
    rate_attack  2.0  slow:    xG+xA per 90
    starting     0.6  fast:    starts rate
    minutes      0.8  fast:    minutes per start
    bonus        2.5  slowest: BPS per 90
    team         0.7  fast:    team attack/defense adjustment

The V3 engines consume the resulting ``ev_*`` columns ONLY when they are
present in the player frame. The production pipeline never injects them, so
production behaviour is byte-for-byte unchanged. Everything here is
leakage-safe: only rounds < gw_n and the fully completed previous season.

New / sparse players have no reliable personal prior; they get a
position-average prior (players with >= ``position_prior_min_games`` previous
season games) and are flagged ``ev_prior_type`` = "position" (or "none" when
even that is missing). Personal priors are only trusted once the player has
>= ``personal_prior_min_games`` previous season games AND
>= ``personal_prior_min_minutes`` minutes.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from research import config
from research.identity import previous_season, previous_season_prior
from research.loader import SeasonData
from utils.config import load_config

logger = logging.getLogger(__name__)

DEFAULT_EVIDENCE_VERSION = "evidence_v1"

# Groups blended per player. Key = config section key.
GROUPS = ("rate_attack", "starting", "minutes", "bonus", "team")

_PRIOR_COLS = [
    "prev_minutes",
    "prev_games",
    "prev_starts",
    "prev_xg_per_90",
    "prev_xa_per_90",
    "prev_xgi_per_90",
    "prev_points_per_90",
    "prev_bps_per_90",
    "prev_bonus_per_90",
    "prev_starts_rate",
    "prev_minutes_per_90",
    "prev_position",
]

# Cached previous-season material per target season: (player prior, team frame).
_prev_cache: dict[str, tuple[pd.DataFrame, pd.DataFrame]] = {}


def load_evidence_config(version: str = DEFAULT_EVIDENCE_VERSION) -> dict:
    """Load the versioned evidence config.

    The evidence category is intentionally NOT listed in ``config/active.yaml``;
    an explicit version is always required so production config resolution is
    unaffected.
    """
    return load_config("evidence", version)


# ---------------------------------------------------------------------------
# Strength + weights
# ---------------------------------------------------------------------------


def evidence_strength(
    minutes: pd.Series,
    starts: pd.Series,
    appearances: pd.Series,
    cfg: dict | None = None,
) -> pd.Series:
    """Current-season evidence strength in [floor, max] from effective minutes."""
    cfg = cfg or load_evidence_config()
    acc = cfg["accumulation"]
    effective = (
        acc["weight_minutes"] * pd.to_numeric(minutes, errors="coerce").fillna(0.0)
        + acc["weight_starts"] * pd.to_numeric(starts, errors="coerce").fillna(0.0)
        + acc["weight_appearances"]
        * pd.to_numeric(appearances, errors="coerce").fillna(0.0)
    )
    floor = float(acc["strength_floor"])
    sat = float(acc["saturation_minutes"])
    strength = floor + (1.0 - floor) * (1.0 - np.exp(-effective / sat))
    return np.minimum(strength, float(acc["max_strength"]))


def current_weight(
    strength: pd.Series,
    group: str,
    cfg: dict | None = None,
) -> pd.Series:
    """Current-season trust weight for one feature group.

    ``w = clip(strength ** transition_exponent, min_current_weight, 1.0)``.
    ``min_current_weight`` guarantees the historical prior never dominates the
    current-season estimator (its exact share proved harmful in the fold1
    ablation — see the walk-forward grid notes), while the exponent controls
    how quickly evidence accumulates.
    """
    cfg = cfg or load_evidence_config()
    g = cfg["feature_groups"][group]
    expo = float(g["transition_exponent"])
    min_w = float(g.get("min_current_weight", 0.0))
    return np.minimum(
        np.power(np.clip(strength, 0.0, 1.0), expo),
        1.0,
    ).clip(lower=min_w)


def blend(hist: pd.Series, current: pd.Series, weight: pd.Series) -> pd.Series:
    """Blend historical prior with current-season value at ``weight`` current."""
    return weight * current + (1.0 - weight) * hist


# ---------------------------------------------------------------------------
# Previous-season material (cached per target season)
# ---------------------------------------------------------------------------


def _per_90(num: pd.Series, minutes: pd.Series) -> pd.Series:
    return (
        (num / (minutes / 90)).replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    )


def _safe_rate(num: pd.Series, den: pd.Series) -> pd.Series:
    out = pd.to_numeric(num, errors="coerce") / pd.to_numeric(
        den, errors="coerce"
    ).replace(0, np.nan)
    return out.fillna(0.0).replace([float("inf"), float("-inf")], 0.0).clip(0.0, 1.0)


def _safe_ratio(
    num: pd.Series, den: pd.Series, clip_max: float | None = None
) -> pd.Series:
    """Unbounded safe ratio (0 when denominator is 0/missing), optionally capped."""
    out = pd.to_numeric(num, errors="coerce") / pd.to_numeric(
        den, errors="coerce"
    ).replace(0, np.nan)
    out = out.fillna(0.0).replace([float("inf"), float("-inf")], 0.0)
    if clip_max is not None:
        out = out.clip(0.0, clip_max)
    return out


def _position_averages(prev_prior: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Per-position prior averages over players with enough history. Index: position."""
    min_games = int(cfg["new_player"]["position_prior_min_games"])
    p = prev_prior[prev_prior["prev_games"] >= min_games]
    p = p[p["prev_minutes"] > 0]
    if p.empty:
        return pd.DataFrame()
    p = p.copy()
    p["_mps"] = _safe_ratio(p["prev_minutes"], p["prev_starts"], clip_max=90.0)
    avg_cols = [
        "prev_xg_per_90",
        "prev_xa_per_90",
        "prev_xgi_per_90",
        "prev_points_per_90",
        "prev_bps_per_90",
        "prev_bonus_per_90",
        "prev_starts_rate",
        "_mps",
    ]
    return p.groupby("prev_position")[avg_cols].mean()


def _prev_season_has_xg(prev_prior: pd.DataFrame) -> bool:
    """True when the previous season carried real FPL xG (faithful seasons)."""
    if prev_prior is None or prev_prior.empty or "prev_xg" not in prev_prior.columns:
        return False
    return bool(
        pd.to_numeric(prev_prior["prev_xg"], errors="coerce").fillna(0.0).abs().sum()
        > 0
    )


def _prev_season_team_strength(season: str) -> pd.DataFrame:
    """Previous-season per-team xG/xGC strength. Indexed by FPL team id.

    Leakage-safe: the previous season is fully completed before the target
    season begins. Proxy seasons (no xG) yield an empty frame — callers treat
    it as "no historical team signal" (no adjustment).
    """
    prev = None
    try:
        prev = SeasonData.load(season)
    except (AssertionError, FileNotFoundError, ValueError) as exc:
        logger.warning("cannot load previous season %s: %s", season, exc)
        return pd.DataFrame()
    if (
        prev is None
        or prev.players_raw is None
        or config.XG_COLS[0] not in prev.gw.columns
    ):
        return pd.DataFrame()

    elem_team = prev.players_raw.set_index("element")["team"]
    gw = prev.gw.assign(_team=prev.gw["element"].map(elem_team))
    active = gw[gw["_team"].notna()]
    team_games = active[active["minutes"] > 0].groupby("_team")["round"].nunique()
    if team_games.empty:
        return pd.DataFrame()
    xg = active.groupby("_team")["expected_goals"].sum()
    xgc = active.groupby("_team")["expected_goals_conceded"].sum()

    out = pd.DataFrame(index=team_games.index)
    out["prev_team_xg_per_game"] = (xg / team_games).fillna(0.0)
    out["prev_team_xgc_per_game"] = (xgc / team_games).fillna(0.0)
    lg_xg = out["prev_team_xg_per_game"].mean()
    lg_xgc = out["prev_team_xgc_per_game"].mean()
    out["prev_team_attack_adj"] = (
        (out["prev_team_xg_per_game"] / lg_xg).fillna(1.0) if lg_xg > 0 else 1.0
    )
    out["prev_team_defense_adj"] = (
        (out["prev_team_xgc_per_game"] / lg_xgc).fillna(1.0) if lg_xgc > 0 else 1.0
    )
    return out


def _prev_material(target_season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player prior, team strength) for the season before ``target_season``."""
    if target_season not in _prev_cache:
        prior = previous_season_prior(target_season)
        team = pd.DataFrame()
        prev = previous_season(target_season)
        if prev is not None:
            team = _prev_season_team_strength(prev)
        _prev_cache[target_season] = (prior, team)
    return _prev_cache[target_season]


# ---------------------------------------------------------------------------
# Evidence frame builder
# ---------------------------------------------------------------------------


def build_evidence_frame(
    players_df: pd.DataFrame,
    sd,
    gw_n: int,
    include: tuple[str, ...] = GROUPS,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """Compute the evidence columns; returns a frame indexed like ``players_df``.

    Raises ``ValueError`` when there is no history before ``gw_n`` (mirrors
    ``build_state`` / ``add_historical_features``).
    """
    cfg = cfg or load_evidence_config()
    past = sd.gw[sd.gw["round"] < gw_n]
    if past.empty:
        raise ValueError(f"{sd.season} gw{gw_n}: no history before target round")

    prior, prev_team = _prev_material(sd.season)
    prev_has_xg = _prev_season_has_xg(prior)
    pos_avgs = _position_averages(prior, cfg) if not prior.empty else pd.DataFrame()

    out = pd.DataFrame(index=players_df.index)

    # --- evidence strength -------------------------------------------------
    minutes = pd.to_numeric(players_df["minutes"], errors="coerce").fillna(0.0)
    starts = pd.to_numeric(players_df["starts"], errors="coerce").fillna(0.0)
    appeared = past[past["minutes"] > 0].groupby("element").size()
    appearances = appeared.reindex(players_df["id"].values, fill_value=0).set_axis(
        out.index, axis=0
    )
    strength = evidence_strength(minutes, starts, appearances, cfg)
    out["ev_strength"] = strength.round(4)

    # --- map personal prior (via FPL code) ---------------------------------
    personal = _map_personal_prior(players_df, sd, prior)
    personal["p__mps"] = _safe_ratio(
        personal["p_prev_minutes"], personal["p_prev_starts"], clip_max=90.0
    )

    np_min_games = int(cfg["new_player"]["personal_prior_min_games"])
    np_min_mins = int(cfg["new_player"]["personal_prior_min_minutes"])
    games_ok = personal["p_prev_games"].ge(np_min_games).fillna(False)
    mins_ok = personal["p_prev_minutes"].ge(np_min_mins).fillna(False)
    prior_reliable_rate = games_ok & mins_ok

    def _pick(pcol: str | None, pos_col: str, use: pd.Series) -> pd.Series:
        """Personal prior where reliable, else position average, else NaN."""
        if pcol is not None:
            vals = pd.to_numeric(personal[pcol], errors="coerce")
        else:
            vals = pd.Series(np.nan, index=out.index, dtype=float)
        out_s = vals.where(use, np.nan)
        missing = out_s.isna()
        if missing.any() and not pos_avgs.empty and pos_col in pos_avgs.columns:
            pos_series = players_df["position"].map(pos_avgs[pos_col])
            out_s = out_s.fillna(pos_series)
        return out_s

    prior_type = pd.Series("none", index=out.index, dtype=object)
    prior_type[prior_reliable_rate] = "personal"
    out["ev_has_prior"] = (prior_type != "none").astype(int)

    # --- rate_attack: xG / xA per 90 (slow group) --------------------------
    if "rate_attack" in include:
        cur_xg = _per_90(
            pd.to_numeric(players_df["expected_goals"], errors="coerce").fillna(0.0),
            minutes,
        )
        cur_xa = _per_90(
            pd.to_numeric(players_df["expected_assists"], errors="coerce").fillna(0.0),
            minutes,
        )
        if prev_has_xg:
            p_xg = _pick("p_prev_xg_per_90", "prev_xg_per_90", prior_reliable_rate)
            p_xa = _pick("p_prev_xa_per_90", "prev_xa_per_90", prior_reliable_rate)
        else:
            p_xg = pd.Series(np.nan, index=out.index, dtype=float)
            p_xa = pd.Series(np.nan, index=out.index, dtype=float)

        position_fill = p_xg.notna() & (prior_type == "none")
        prior_type[position_fill] = "position"

        w = current_weight(strength, "rate_attack", cfg)
        out["ev_w_rate_attack"] = w.round(4)
        out["ev_cur_xgi_per_90"] = (cur_xg + cur_xa).round(4)
        out["ev_hist_xgi_per_90"] = (p_xg + p_xa).round(4)
        out["ev_xg_per_90"] = (
            blend(p_xg, cur_xg, w).where(p_xg.notna(), cur_xg).round(4)
        )
        out["ev_xa_per_90"] = (
            blend(p_xa, cur_xa, w).where(p_xa.notna(), cur_xa).round(4)
        )
        out["ev_xgi_per_90"] = (out["ev_xg_per_90"] + out["ev_xa_per_90"]).round(4)

    # --- bonus: BPS per 90 (slowest group) ----------------------------------
    if "bonus" in include:
        cur_bps = _per_90(
            pd.to_numeric(players_df["bps"], errors="coerce").fillna(0.0), minutes
        )
        p_bps = _pick("p_prev_bps_per_90", "prev_bps_per_90", prior_reliable_rate)
        w = current_weight(strength, "bonus", cfg)
        out["ev_w_bonus"] = w.round(4)
        out["ev_cur_bps_per_90"] = cur_bps.round(4)
        out["ev_hist_bps_per_90"] = p_bps.round(4)
        out["ev_bps_per_90"] = (
            blend(p_bps, cur_bps, w).where(p_bps.notna(), cur_bps).round(4)
        )

    # --- starting: starts rate prior (fast group) ---------------------------
    if "starting" in include:
        p_start = _pick("p_prev_starts_rate", "prev_starts_rate", games_ok)
        w = current_weight(strength, "starting", cfg)
        out["ev_w_starting"] = w.round(4)
        out["ev_cur_starts_rate"] = _safe_rate(starts, appearances).round(4)
        out["ev_hist_starts_rate"] = p_start.round(4)
        out["ev_prior_starts_rate"] = p_start.round(4)

    # --- minutes: minutes per start prior (fast group) ----------------------
    if "minutes" in include:
        mps_cur = _safe_ratio(minutes, starts, clip_max=90.0)
        mps_hist = _pick("p__mps", "_mps", games_ok)
        w = current_weight(strength, "minutes", cfg)
        out["ev_w_minutes"] = w.round(4)
        out["ev_cur_mps"] = mps_cur.round(4)
        out["ev_hist_mps"] = mps_hist.round(4)
        out["ev_minutes_per_start"] = (
            blend(mps_hist, mps_cur, w).where(mps_hist.notna(), mps_cur).round(4)
        )

    # --- team: attack/defense adjustment (fast group) -----------------------
    if "team" in include:
        cur_team = _current_team_strength(past, sd)
        w = current_weight(strength, "team", cfg)
        out["ev_w_team"] = w.round(4)
        if prev_team is not None and not prev_team.empty:
            tmap = prev_team.reindex(players_df["team_id"].values)
            p_atk = tmap["prev_team_attack_adj"].set_axis(out.index, axis=0)
            p_def = tmap["prev_team_defense_adj"].set_axis(out.index, axis=0)
        else:
            p_atk = pd.Series(np.nan, index=out.index, dtype=float)
            p_def = pd.Series(np.nan, index=out.index, dtype=float)
        p_atk = p_atk.fillna(1.0)
        p_def = p_def.fillna(1.0)

        cur_atk = (
            cur_team["hist_team_attack_adj"]
            .reindex(players_df["team_id"].values)
            .set_axis(out.index, axis=0)
            .fillna(1.0)
        )
        cur_def = (
            cur_team["hist_team_defense_adj"]
            .reindex(players_df["team_id"].values)
            .set_axis(out.index, axis=0)
            .fillna(1.0)
        )
        out["ev_cur_team_attack_adj"] = cur_atk.round(4)
        out["ev_hist_team_attack_adj"] = p_atk.round(4)
        out["ev_cur_team_defense_adj"] = cur_def.round(4)
        out["ev_hist_team_defense_adj"] = p_def.round(4)
        atk_used = w * cur_atk + (1.0 - w) * p_atk
        def_used = w * cur_def + (1.0 - w) * p_def
        out["ev_team_attack_mult"] = (1.0 - w + w * atk_used).round(4)
        out["ev_team_defense_mult"] = (1.0 - w + w * def_used).round(4)

    out["ev_prior_type"] = prior_type
    return out


def _map_personal_prior(
    players_df: pd.DataFrame,
    sd,
    prev_prior: pd.DataFrame,
) -> pd.DataFrame:
    """Personal prior columns aligned to ``players_df`` rows (NaN where absent)."""
    pcols = [f"p_{c}" for c in _PRIOR_COLS]
    if prev_prior is None or prev_prior.empty or sd.players_raw is None:
        return pd.DataFrame(
            {k: pd.Series(np.nan, index=players_df.index, dtype=float) for k in pcols},
            index=players_df.index,
        )
    code_by_element = sd.players_raw.set_index("element")["code"]
    tmp = pd.DataFrame({"element": players_df["id"].values})
    tmp["code"] = tmp["element"].map(code_by_element)
    prior = prev_prior.drop(columns=["element"], errors="ignore")
    merged = tmp.merge(prior, on="code", how="left")
    merged.index = players_df.index
    out = pd.DataFrame(index=players_df.index)
    for c in _PRIOR_COLS:
        col = f"p_{c}"
        if c in merged.columns:
            out[col] = (
                pd.to_numeric(merged[c], errors="coerce")
                if c != "prev_position"
                else merged[c]
            )
        else:
            out[col] = np.nan
    return out


def _current_team_strength(past: pd.DataFrame, sd) -> pd.DataFrame:
    """Season-to-date team strength (reuses the historical feature store)."""
    from research.historical_features import _team_features

    return _team_features(past, sd)


def add_evidence_features(
    players_df: pd.DataFrame,
    sd,
    gw_n: int,
    include: tuple[str, ...] = GROUPS,
    evidence_version: str = DEFAULT_EVIDENCE_VERSION,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """Return a copy of ``players_df`` with ``ev_*`` columns appended.

    Consumed by the V3 engines only when present; the production path never
    calls this, so production behaviour is unchanged. All inputs are
    leakage-safe (rounds < gw_n and the completed previous season).

    ``cfg`` optionally overrides the evidence parameters in memory (used by the
    walk-forward parameter grid); None loads ``evidence_version`` from disk.
    """
    cfg = cfg or load_evidence_config(evidence_version)
    frame = build_evidence_frame(players_df, sd, gw_n, include=include, cfg=cfg)
    return pd.concat([players_df.copy(), frame], axis=1)


# ---------------------------------------------------------------------------
# Explainability (Assistant Manager metadata — read-only, never used to compute)
# ---------------------------------------------------------------------------


def evidence_breakdown(
    player_id: int,
    players_df: pd.DataFrame,
    sd,
    gw_n: int,
    evidence_version: str = DEFAULT_EVIDENCE_VERSION,
) -> dict:
    """Structured per-group explainability for one player at gameweek gw_n.

    Returns a dict with the evidence strength, prior type, and per-group
    {current, historical, blended, weight_current, unit}. Callers (e.g. the
    Assistant Manager) must treat this as read-only metadata — predictions are
    never recomputed from it.
    """
    if "ev_strength" not in players_df.columns:
        players_df = add_evidence_features(
            players_df, sd, gw_n, evidence_version=evidence_version
        )
    try:
        row = players_df[players_df["id"] == player_id].iloc[0]
    except IndexError:
        raise KeyError(f"player {player_id} not in the gameweek-{gw_n} frame")

    groups = {}
    spec = load_evidence_config(evidence_version)["feature_groups"]
    for group in GROUPS:
        entry = {"label": spec[group]["label"]}
        if group == "rate_attack":
            entry.update(
                {
                    "current_value": float(row.get("ev_cur_xgi_per_90", np.nan)),
                    "historical_value": float(row.get("ev_hist_xgi_per_90", np.nan)),
                    "blended_value": float(row.get("ev_xgi_per_90", np.nan)),
                    "weight_current": float(row.get("ev_w_rate_attack", np.nan)),
                    "unit": "xG+xA per 90",
                }
            )
        elif group == "starting":
            entry.update(
                {
                    "current_value": float(row.get("ev_cur_starts_rate", np.nan)),
                    "historical_value": float(row.get("ev_hist_starts_rate", np.nan)),
                    "blended_value": float(row.get("ev_prior_starts_rate", np.nan)),
                    "weight_current": float(row.get("ev_w_starting", np.nan)),
                    "unit": "starts / appearance",
                }
            )
        elif group == "minutes":
            entry.update(
                {
                    "current_value": float(row.get("ev_cur_mps", np.nan)),
                    "historical_value": float(row.get("ev_hist_mps", np.nan)),
                    "blended_value": float(row.get("ev_minutes_per_start", np.nan)),
                    "weight_current": float(row.get("ev_w_minutes", np.nan)),
                    "unit": "minutes per start",
                }
            )
        elif group == "bonus":
            entry.update(
                {
                    "current_value": float(row.get("ev_cur_bps_per_90", np.nan)),
                    "historical_value": float(row.get("ev_hist_bps_per_90", np.nan)),
                    "blended_value": float(row.get("ev_bps_per_90", np.nan)),
                    "weight_current": float(row.get("ev_w_bonus", np.nan)),
                    "unit": "BPS per 90",
                }
            )
        else:  # team
            entry.update(
                {
                    "current_value": {
                        "attack_adj": float(row.get("ev_cur_team_attack_adj", np.nan)),
                        "defense_adj": float(
                            row.get("ev_cur_team_defense_adj", np.nan)
                        ),
                    },
                    "historical_value": {
                        "attack_adj": float(row.get("ev_hist_team_attack_adj", np.nan)),
                        "defense_adj": float(
                            row.get("ev_hist_team_defense_adj", np.nan)
                        ),
                    },
                    "blended_value": {
                        "attack_mult": float(row.get("ev_team_attack_mult", np.nan)),
                        "defense_mult": float(row.get("ev_team_defense_mult", np.nan)),
                    },
                    "weight_current": float(row.get("ev_w_team", np.nan)),
                    "unit": "relative adjustment (1.0 = league average)",
                }
            )
        groups[group] = entry

    return {
        "player_id": int(player_id),
        "gameweek": int(gw_n),
        "season": sd.season,
        "evidence_strength": float(row.get("ev_strength", np.nan)),
        "has_historical_prior": int(row.get("ev_has_prior", 0)),
        "prior_type": str(row.get("ev_prior_type", "none")),
        "groups": groups,
        "note": (
            "Read-only explainability metadata. Predictions are never "
            "recomputed from this data; see engines for the actual forecast."
        ),
    }
