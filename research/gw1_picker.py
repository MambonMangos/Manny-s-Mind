"""GW1 squad picker — research-informed lineup for the opening gameweek.

Uses the findings from the feature analysis (form / starts reliability / xGI
are the strongest pre-gameweek signals; fixture strength is weak but non-zero)
to score every player in the DB, then assembles a FPL-legal 15-player squad
(2 GKP / 5 DEF / 5 MID / 3 FWD, max 3 per club, budget 100.0m).

The DB holds last-season totals (preseason, no GW1 data yet), so per-90 rates
from last season are used as the best available proxy — no current-season
stats are fabricated.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from database.crud import get_players_dataframe
from database.database import get_session
from engines.fixture_engine import build_fixture_map, compute_fixture_score
from services.fixture_service import fetch_fixtures

logger = logging.getLogger(__name__)

POSITION_SLOTS = {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
POSITION_IDS = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
MAX_PER_CLUB = 3
BUDGET = 100.0

# xGI-weight per position when blending the xGI signal with raw points-per-90.
# GKP/DEF points are driven by clean sheets/saves, not goal involvements.
XGI_WEIGHT = {"GKP": 0.0, "DEF": 0.4, "MID": 0.6, "FWD": 0.6}


@dataclass
class Squad:
    players: pd.DataFrame
    cost: float
    projected_points: float
    team_names: dict[int, str] | None = None
    gw_frames: dict[int, pd.DataFrame] | None = None


@dataclass
class PositionModel:
    """Per-position xGI → points conversion, fit as points_per_90 = a + b·xGI.

    The intercept ``alpha`` captures the appearance/clean-sheet/bonus baseline
    so a player's xGI does not get to scale up those unrelated sources (the
    flaw in a simple points/xGI ratio).
    """

    alpha: float
    beta: float


def load_players() -> pd.DataFrame:
    """Player dataframe from the DB (last-season totals, current prices)."""
    session = get_session()
    try:
        df = get_players_dataframe(session)
    finally:
        session.close()
    df["minutes"] = df["minutes"].fillna(0)
    df["starts"] = df["starts"].fillna(0)
    df["expected_goal_involvements"] = df["expected_goal_involvements"].fillna(0)
    df["total_points"] = df["total_points"].fillna(0)
    df["goals_scored"] = df["goals_scored"].fillna(0)
    df["assists"] = df["assists"].fillna(0)
    return df


def load_gw1_fixture_map() -> tuple[dict[int, dict], pd.DataFrame]:
    """Fetch fixtures, return per-team GW1 fixture info and a frame."""
    fixtures = fetch_fixtures()
    gw1 = [f for f in fixtures if f.event == 1]
    fixture_map = build_fixture_map(gw1)

    rows = []
    for team_id, flist in fixture_map.items():
        first = flist[0]
        rows.append({
            "team_id": team_id,
            "opponent_id": first["opponent_id"],
            "home": first["home"],
            "difficulty": first["difficulty"],
            "fixture_score": compute_fixture_score(first["difficulty"]),
        })
    return fixture_map, pd.DataFrame(rows)


def load_gw_fixture_maps(events: list[int]) -> dict[int, pd.DataFrame]:
    """Fetch fixtures once; return one per-GW frame per requested gameweek.

    Each frame has one row per team: team_id, opponent_id, home, difficulty,
    fixture_score.
    """
    fixtures = fetch_fixtures()
    frames: dict[int, pd.DataFrame] = {}
    for ev in events:
        fixture_map = build_fixture_map([f for f in fixtures if f.event == ev])
        rows = []
        for team_id, flist in fixture_map.items():
            first = flist[0]
            rows.append({
                "team_id": team_id,
                "opponent_id": first["opponent_id"],
                "home": first["home"],
                "difficulty": first["difficulty"],
                "fixture_score": compute_fixture_score(first["difficulty"]),
            })
        frames[ev] = pd.DataFrame(rows)
    return frames


def _games_played(minutes: float) -> float:
    return max(1.0, minutes / 90.0)


def add_features(
    players: pd.DataFrame,
    gw1: pd.DataFrame,
) -> pd.DataFrame:
    """Derive the research-informed GW1 features from last-season totals.

    Per-90 rates from tiny samples are unreliable (a single good game can
    produce a 15-points-per-90 "star"), so raw rates are shrunk toward the
    position mean, weighted by a reliability ramp over the first 450 minutes —
    the same low-history inflation the minutes analysis identified.
    """
    d = players.copy()
    d["games"] = d["minutes"].apply(_games_played)
    d["minutes_per_game"] = d["minutes"] / d["games"]
    # starts_rate: starts / games, capped at 1.0 (starts is the truthful bound)
    d["starts_rate"] = (d["starts"] / d["games"]).clip(0.0, 1.0)
    d["xgi_per_90"] = d["expected_goal_involvements"] / d["games"]
    d["points_per_90"] = d["total_points"] / d["games"]
    d["goals_per_90"] = d["goals_scored"] / d["games"]
    d["assists_per_90"] = d["assists"] / d["games"]
    d["reliability"] = np.clip(d["minutes"] / 450.0, 0.0, 1.0)

    # Shrinkage targets: minutes-weighted position means
    means: dict[str, dict[str, float]] = {}
    for pos in POSITION_SLOTS:
        sub = d[d["position"] == pos]
        w = sub["games"].sum()
        if w <= 0:
            means[pos] = {"points_per_90": 4.0, "xgi_per_90": 0.3,
                          "starts_rate": 0.6, "minutes_per_game": 60.0}
            continue
        means[pos] = {
            "points_per_90": (sub["points_per_90"] * sub["games"]).sum() / w,
            "xgi_per_90": (sub["xgi_per_90"] * sub["games"]).sum() / w,
            "starts_rate": (sub["starts_rate"] * sub["games"]).sum() / w,
            "minutes_per_game": (sub["minutes_per_game"] * sub["games"]).sum() / w,
        }
    d["position_mean_pp90"] = d["position"].map(lambda p: means[p]["points_per_90"])
    d["position_mean_xgi90"] = d["position"].map(lambda p: means[p]["xgi_per_90"])
    d["position_mean_sr"] = d["position"].map(lambda p: means[p]["starts_rate"])
    d["position_mean_mpg"] = d["position"].map(lambda p: means[p]["minutes_per_game"])

    d["points_per_90_s"] = (d["reliability"] * d["points_per_90"]
                            + (1 - d["reliability"]) * d["position_mean_pp90"])
    d["xgi_per_90_s"] = (d["reliability"] * d["xgi_per_90"]
                         + (1 - d["reliability"]) * d["position_mean_xgi90"])
    d["starts_rate_s"] = (d["reliability"] * d["starts_rate"]
                          + (1 - d["reliability"]) * d["position_mean_sr"])
    d["expected_mins_factor"] = d["starts_rate_s"].clip(0.05, 1.0)

    # GW1 fixture strength per team
    fx = gw1[["team_id", "opponent_id", "home", "difficulty", "fixture_score"]]
    d = d.merge(fx, on="team_id", how="left")
    d["fixture_score"] = d["fixture_score"].fillna(50.0)  # unknown opponent = neutral
    d["fixture_factor"] = 0.85 + 0.30 * (d["fixture_score"] / 100.0)  # 0.85-1.15

    # Set-piece orders (small boost per the (weak) research finding)
    d["set_piece_bonus"] = 0.0
    d.loc[d["penalties_order"] == 1, "set_piece_bonus"] += 0.4
    d.loc[d["direct_freekicks_order"] == 1, "set_piece_bonus"] += 0.15
    d.loc[d["corners_and_indirect_freekicks_order"] == 1, "set_piece_bonus"] += 0.15
    return d


def calibrate_position_model(d: pd.DataFrame) -> dict[str, PositionModel]:
    """Fit points_per_90 = alpha + beta * xgi_per_90 per position.

    Minutes-weighted least squares across last season's players. The intercept
    keeps the appearance/clean-sheet/bonus baseline from being scaled up by a
    player's xGI, so high-xGI players are no longer over-credited (the flaw in
    a simple points/xGI ratio).
    """
    models: dict[str, PositionModel] = {}
    for pos in POSITION_SLOTS:
        sub = d[d["position"] == pos]
        if pos == "GKP" or sub.empty or sub["games"].sum() <= 0:
            models[pos] = PositionModel(alpha=0.0, beta=0.0)
            continue
        w = sub["games"].to_numpy(dtype=float)
        x = sub["xgi_per_90_s"].to_numpy(dtype=float)
        y = sub["points_per_90_s"].to_numpy(dtype=float)
        s0, sx, sy = w.sum(), (w * x).sum(), (w * y).sum()
        sxx = (w * x * x).sum()
        sxy = (w * x * y).sum()
        denom = sxx - sx * sx / s0
        if denom <= 1e-9:
            models[pos] = PositionModel(alpha=float(sy / s0), beta=0.0)
            continue
        beta = (sxy - sx * sy / s0) / denom
        alpha = (sy - beta * sx) / s0
        models[pos] = PositionModel(alpha=float(alpha), beta=float(beta))
    return models


def project_points(d: pd.DataFrame, model: dict[str, PositionModel]) -> pd.DataFrame:
    """Project GW1 points: blend xGI-driven and points-driven signals."""
    d = d.copy()
    xgi_w = np.array([XGI_WEIGHT.get(p, 0.5) for p in d["position"]])
    al = np.array([model[p].alpha for p in d["position"]])
    be = np.array([model[p].beta for p in d["position"]])

    xgi_pts = al + be * d["xgi_per_90_s"].values
    raw_pts = d["points_per_90_s"].values
    blended = ((1 - xgi_w) * raw_pts + xgi_w * xgi_pts)
    blended = blended * d["expected_mins_factor"].values
    d["projected_points"] = blended * d["fixture_factor"].values + d["set_piece_bonus"].values
    d["projected_points"] = d["projected_points"].clip(lower=0)
    return d


def add_multi_gw_fixtures(
    d: pd.DataFrame,
    gw_frames: dict[int, pd.DataFrame],
    events: list[int],
) -> pd.DataFrame:
    """Attach per-GW fixture columns (opponent, home, difficulty, factor) and a
    summed ``fixture_factor_total`` across the requested gameweeks.

    ``d`` must already have the base features (``add_features``); this leaves
    the single-GW columns untouched and adds ``*_gw<ev>`` variants.
    """
    d = d.copy()
    total = np.zeros(len(d))
    for ev in events:
        frame = gw_frames[ev][["team_id", "opponent_id", "home", "difficulty", "fixture_score"]]
        frame = frame.rename(columns={
            "opponent_id": f"opponent_id_gw{ev}",
            "home": f"home_gw{ev}",
            "difficulty": f"difficulty_gw{ev}",
            "fixture_score": f"fixture_score_gw{ev}",
        })
        d = d.merge(frame, on="team_id", how="left")
        fs = d[f"fixture_score_gw{ev}"].fillna(50.0)
        ff = 0.85 + 0.30 * (fs / 100.0)  # 0.85-1.15, same scale as GW1 factor
        d[f"fixture_factor_gw{ev}"] = ff
        total = total + ff.to_numpy()
    d["fixture_factor_total"] = total
    return d


def project_points_multi_gw(
    d: pd.DataFrame,
    model: dict[str, PositionModel],
    events: list[int],
) -> pd.DataFrame:
    """Project per-GW points for each requested gameweek and set
    ``projected_points`` to the window total (what the squad optimiser uses).

    The base signal (per-90 rates × starts reliability, blended by position)
    is constant across the window; only the fixture factor changes per GW. The
    set-piece bonus applies per gameweek.
    """
    d = d.copy()
    xgi_w = np.array([XGI_WEIGHT.get(p, 0.5) for p in d["position"]])
    al = np.array([model[p].alpha for p in d["position"]])
    be = np.array([model[p].beta for p in d["position"]])

    blended = ((1 - xgi_w) * d["points_per_90_s"].values
               + xgi_w * (al + be * d["xgi_per_90_s"].values))
    blended = blended * d["expected_mins_factor"].values

    for ev in events:
        d[f"projected_points_gw{ev}"] = np.clip(
            blended * d[f"fixture_factor_gw{ev}"].values + d["set_piece_bonus"].values,
            a_min=0, a_max=None,
        )
    d["projected_points"] = d[[f"projected_points_gw{ev}" for ev in events]].sum(axis=1)
    return d


def _select_greedy(
    d: pd.DataFrame,
    budget: float,
    rng: np.random.Generator,
    pos_by_proj: dict[str, pd.DataFrame],
    pos_by_price: dict[str, pd.DataFrame],
) -> tuple[list[dict], float]:
    """One greedy build over a shuffled player order.

    ``pos_by_proj`` / ``pos_by_price`` are per-position frames pre-sorted by
    projected points (desc) and price (asc) so the reserve scan stays cheap.
    """
    pos_order = list(POSITION_SLOTS)
    rng.shuffle(pos_order)

    def reserve_cost(needed: dict[str, int], used_clubs: set) -> float:
        reserve = 0.0
        for pos, k in needed.items():
            if k <= 0:
                continue
            sub = pos_by_price[pos]
            mask = ~sub["team_id"].isin(used_clubs)
            if not mask.any():
                reserve += k * 4.0
            else:
                reserve += k * sub.loc[mask, "price"].iloc[0]
        return reserve

    needed = dict(POSITION_SLOTS)
    selected: list[dict] = []
    budget_left = budget
    for pos in pos_order:
        for _, p in pos_by_proj[pos].iterrows():
            if needed[pos] <= 0:
                break
            clubs = {x["team_id"] for x in selected}
            if p["team_id"] in clubs and sum(1 for x in selected if x["team_id"] == p["team_id"]) >= MAX_PER_CLUB:
                continue
            new_needed = dict(needed)
            new_needed[pos] -= 1
            needed_clubs = clubs | {p["team_id"]} if p["team_id"] in clubs else clubs
            if budget_left - p["price"] < reserve_cost(new_needed, needed_clubs) - 1e-6:
                continue
            selected.append(p.to_dict() | {"_i": p.name})
            needed[pos] -= 1
            budget_left -= p["price"]
    return selected, budget_left


def _local_swaps(
    d: pd.DataFrame,
    selected: list[dict],
    budget_left: float,
    rng: np.random.Generator,
    pos_by_proj: dict[str, pd.DataFrame],
    n_attempts: int = 150,
) -> tuple[list[dict], float]:
    """Bounded random swap improvements that stay within budget."""
    selected_idx = {x["_i"] for x in selected}
    for _ in range(n_attempts):
        out_pos = rng.choice(list(selected))
        pos = out_pos["position"]
        cand = pos_by_proj[pos]
        in_candidates = cand[~cand.index.isin(selected_idx)]
        if in_candidates.empty:
            continue
        in_pick = in_candidates.iloc[rng.integers(0, len(in_candidates))]
        n_same = sum(1 for x in selected if x["team_id"] == in_pick["team_id"])
        if n_same >= MAX_PER_CLUB and in_pick["team_id"] != out_pos["team_id"]:
            continue
        cost_delta = in_pick["price"] - out_pos["price"]
        pts_delta = in_pick["projected_points"] - out_pos["projected_points"]
        if cost_delta > budget_left + 1e-6:
            continue
        if pts_delta > 0.05:
            selected = [x for x in selected if x is not out_pos]
            selected.append(in_pick.to_dict() | {"_i": in_pick.name})
            selected_idx.discard(out_pos["_i"])
            selected_idx.add(in_pick.name)
            budget_left -= cost_delta
    return selected, budget_left


def select_squad(
    d: pd.DataFrame,
    budget: float = BUDGET,
    restarts: int = 80,
) -> Squad:
    """Multi-restart greedy + local swaps; keep the best feasible squad."""
    d = d.copy().sort_values("projected_points", ascending=False)
    rng = np.random.default_rng(1)

    pos_by_proj = {pos: d[d["position"] == pos]
                   for pos in POSITION_SLOTS}
    pos_by_price = {pos: d[d["position"] == pos].sort_values("price")
                    for pos in POSITION_SLOTS}

    best: tuple[list[dict], float] | None = None
    for _ in range(restarts):
        selected, budget_left = _select_greedy(d, budget, rng, pos_by_proj, pos_by_price)
        if len(selected) != 15:
            continue
        selected, budget_left = _local_swaps(d, selected, budget_left, rng, pos_by_proj)
        total = sum(x["projected_points"] for x in selected)
        if best is None or total > best[0]:
            best = (total, selected, budget_left)
    if best is None:
        raise RuntimeError("no feasible squad found within budget")

    _, selected, budget_left = best
    squad_df = pd.DataFrame(selected).sort_values(
        by=["position", "projected_points"], ascending=[True, False]
    )
    return Squad(
        players=squad_df,
        cost=float(squad_df["price"].sum()),
        projected_points=float(squad_df["projected_points"].sum()),
    )


def build_squad() -> Squad:
    """End-to-end GW1 squad build (fetch fixtures, score, select)."""
    players = load_players()
    _, gw1 = load_gw1_fixture_map()
    feats = add_features(players, gw1)
    model = calibrate_position_model(feats)
    scored = project_points(feats, model)
    team_names = dict(players.groupby("team_id")["team_name"].first())
    squad = select_squad(scored)
    squad.team_names = team_names
    return squad


def build_squad_multi_gw(events: list[int] | None = None) -> Squad:
    """End-to-end squad build for a fixed gameweek window (default GW1-5).

    Every player is scored on their projected points summed across the window
    (per-90 rates × starts reliability × per-GW fixture factor + set-piece
    bonus each GW), then a single fixed squad is selected under the usual
    constraints — i.e. the no-transfers scenario.
    """
    events = list(events or (1, 2, 3, 4, 5))
    players = load_players()
    gw_frames = load_gw_fixture_maps(events)
    feats = add_features(players, gw_frames[events[0]])
    feats = add_multi_gw_fixtures(feats, gw_frames, events)
    model = calibrate_position_model(feats)
    scored = project_points_multi_gw(feats, model, events)
    team_names = dict(players.groupby("team_id")["team_name"].first())
    squad = select_squad(scored)
    squad.team_names = team_names
    squad.gw_frames = gw_frames
    return squad


def _p_at_least(lam: float, k: int) -> float:
    """P(X >= k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 0.0
    p = 0.0
    for j in range(k):
        p += math.exp(-lam) * lam**j / math.factorial(j)
    return 1.0 - p


def best_xi_for_gw(df: pd.DataFrame, gw: int) -> list[int]:
    """Indices of the best legal XI for one gameweek.

    Respects formation bounds: exactly 1 GKP, 3-5 DEF, 3-5 MID, 1-3 FWD.
    Greedy: satisfy the positional minima first, then fill to 11 with the
    highest remaining projections subject to position caps.
    """
    df = df.sort_values(f"projected_points_gw{gw}", ascending=False)
    minima = {"GKP": 1, "DEF": 3, "MID": 2, "FWD": 1}
    cap = {"GKP": 1, "DEF": 5, "MID": 5, "FWD": 3}
    counts = {p: 0 for p in cap}
    picked: list[int] = []

    for _, r in df.iterrows():
        if counts[r["position"]] < minima[r["position"]]:
            picked.append(r.name)
            counts[r["position"]] += 1
    for _, r in df.iterrows():
        if len(picked) >= 11:
            break
        if counts[r["position"]] >= cap[r["position"]]:
            continue
        picked.append(r.name)
        counts[r["position"]] += 1
    return picked


def expected_fielded_points(
    squad_df: pd.DataFrame,
    events: list[int],
) -> tuple[dict[int, float], dict[int, float], float, float]:
    """Expected points actually scored, per GW and across the window.

    For each GW picks the best legal XI and sums their projections, then adds
    the expected auto-sub contribution: if the starting GK misses, the bench GK
    replaces them (probability = 1 - starts reliability); outfield misses are
    modelled as Poisson(lambda) and each bench sub in priority order contributes
    when the corresponding number of starters are out.

    Returns (fielded_per_gw, sub_per_gw, total_fielded, total_subs).
    """
    fielded_per_gw: dict[int, float] = {}
    sub_per_gw: dict[int, float] = {}
    total_fielded = 0.0
    total_subs = 0.0

    for ev in events:
        xi = best_xi_for_gw(squad_df, ev)
        starters = squad_df.loc[xi]
        bench = squad_df.drop(index=xi)
        fielded = float(starters[f"projected_points_gw{ev}"].sum())

        gk = starters[starters["position"] == "GKP"]
        gk_sub = bench[bench["position"] == "GKP"]
        gk_ev = 0.0
        if len(gk) == 1 and len(gk_sub) == 1:
            p_miss = 1.0 - min(gk["expected_mins_factor"].iloc[0], 1.0)
            gk_ev = p_miss * float(gk_sub[f"projected_points_gw{ev}"].iloc[0])

        out_starters = starters[starters["position"] != "GKP"]
        lam = float((1.0 - out_starters["expected_mins_factor"].clip(upper=1.0)).sum())
        out_bench = bench[bench["position"] != "GKP"].sort_values(
            f"projected_points_gw{ev}", ascending=False)
        out_ev = 0.0
        for k, (_, b) in enumerate(out_bench.head(3).iterrows(), start=1):
            out_ev += _p_at_least(lam, k) * float(b[f"projected_points_gw{ev}"])

        fielded_per_gw[ev] = fielded
        sub_per_gw[ev] = gk_ev + out_ev
        total_fielded += fielded
        total_subs += gk_ev + out_ev

    return fielded_per_gw, sub_per_gw, total_fielded, total_subs


def format_squad(squad: Squad, team_names: dict[int, str] | None = None) -> str:
    """Render the squad as a markdown table."""
    df = squad.players
    if team_names is None:
        team_names = squad.team_names or {}
    out = ["| position | player | club | price | proj_pts | GW1 opp | diff |",
           "|---|---|---:|---:|---:|---:|---:|"]
    for _, r in df.iterrows():
        opp = team_names.get(int(r["opponent_id"]), "?")
        hs = "H" if r["home"] else "A"
        out.append(
            f"| {r['position']} | {r['web_name']} | {team_names.get(int(r['team_id']), '?')} "
            f"| {r['price']:.1f}m | {r['projected_points']:.1f} "
            f"| {opp} ({hs}) | {int(r['difficulty'])}/5 |"
        )
    out.append("")
    out.append(f"**Total cost:** {squad.cost:.1f}m / 100.0m · "
               f"**Projected points (GW1):** {squad.projected_points:.1f}")
    return "\n".join(out)


def format_squad_multi_gw(
    squad: Squad,
    events: list[int] | None = None,
    team_names: dict[int, str] | None = None,
) -> str:
    """Render a window squad: per-GW projected points + per-GW opponents."""
    events = list(events or (1, 2, 3, 4, 5))
    df = squad.players
    if team_names is None:
        team_names = squad.team_names or {}

    hdr = ["position", "player", "club", "price"] + [f"GW{ev}" for ev in events] + ["total"]
    rule = ["---"] * 3 + ["---:"] * (len(events) + 2)
    out = ["| " + " | ".join(hdr) + " |",
           "|" + "|".join(rule) + "|"]
    for _, r in df.iterrows():
        cells = [r["position"], r["web_name"], team_names.get(int(r["team_id"]), "?"),
                 f"{r['price']:.1f}m"]
        cells += [f"{r[f'projected_points_gw{ev}']:.1f}" for ev in events]
        cells.append(f"{r['projected_points']:.1f}")
        out.append("| " + " | ".join(cells) + " |")
    out.append("")
    out.append("**Fixtures GW1-5 (opponent + difficulty):**")
    for _, r in df.iterrows():
        cells = [f"{r['web_name']} ({team_names.get(int(r['team_id']), '?')}):"]
        for ev in events:
            opp = team_names.get(int(r[f"opponent_id_gw{ev}"]), "?")
            hs = "H" if r[f"home_gw{ev}"] else "A"
            cells.append(f"GW{ev} {opp} ({hs}) {int(r[f'difficulty_gw{ev}'])}")
        out.append("- " + " · ".join(cells))
    out.append("")
    fielded, subs, tot_f, tot_s = expected_fielded_points(df, events)
    out.append("**Expected points actually scored (best legal XI + auto-subs):**")
    hdr2 = ["GW"] + [f"GW{ev}" for ev in events] + ["total"]
    rule2 = ["---"] + ["---:"] * (len(events) + 1)
    out.append("| " + " | ".join(hdr2) + " |")
    out.append("|" + "|".join(rule2) + "|")
    gws = [f"{fielded[ev] + subs[ev]:.1f}" for ev in events]
    out.append("| expected | " + " | ".join(gws) + " | "
               f"{tot_f + tot_s:.1f} |")
    out.append("| of which auto-subs | " + " | ".join(
        f"+{subs[ev]:.1f}" for ev in events) + " | "
        f"+{tot_s:.1f} |")
    out.append("")
    out.append("_The per-player totals in the squad table sum all 15 players "
               "across the window (the squad's raw value); only the 11 fielded "
               "plus bench auto-subs count towards your actual score._")
    out.append("")
    out.append(f"**Total cost:** {squad.cost:.1f}m / 100.0m · "
               f"**Squad value (all 15, GW1-5):** {squad.projected_points:.1f} · "
               f"**Expected fielded points (GW1-5):** {tot_f + tot_s:.1f}")
    return "\n".join(out)


SEASON_EVENTS = list(range(1, 39))


def _chunk_events(events: list[int], size: int = 5) -> list[list[int]]:
    """Split a GW list into display blocks (e.g. GW1-5, GW6-10, ...)."""
    return [events[i:i + size] for i in range(0, len(events), size)]


def build_squad_season(events: list[int] | None = None) -> Squad:
    """End-to-end no-transfers squad for the whole season (default GW1-38).

    Identical methodology to ``build_squad_multi_gw`` — per-GW fixture factors
    applied to a constant base signal, then a single fixed 15 selected once.
    """
    return build_squad_multi_gw(events or SEASON_EVENTS)


def format_squad_season(
    squad: Squad,
    events: list[int] | None = None,
    team_names: dict[int, str] | None = None,
) -> str:
    """Render a full-season squad: per-player totals by 5-GW blocks, expected
    fielded points by block, and a season fixture summary per player."""
    events = list(events or SEASON_EVENTS)
    df = squad.players
    if team_names is None:
        team_names = squad.team_names or {}
    blocks = _chunk_events(events)

    out = ["| position | player | club | price | " +
           " | ".join(f"GW{b[0]}-{b[-1]}" for b in blocks) +
           " | season |",
           "|---" * 3 + "|---:" * (len(blocks) + 2)]
    for _, r in df.iterrows():
        cells = [r["position"], r["web_name"], team_names.get(int(r["team_id"]), "?"),
                 f"{r['price']:.1f}m"]
        for b in blocks:
            cells.append(f"{sum(r[f'projected_points_gw{ev}'] for ev in b):.0f}")
        cells.append(f"{r['projected_points']:.0f}")
        out.append("| " + " | ".join(cells) + " |")

    out.append("")
    fielded, subs, tot_f, tot_s = expected_fielded_points(df, events)
    out.append("**Expected points actually scored (best legal XI + auto-subs):**")
    hdr2 = ["block"] + [f"GW{b[0]}-{b[-1]}" for b in blocks] + ["season"]
    out.append("| " + " | ".join(hdr2) + " |")
    out.append("|---" + "|---:" * (len(blocks) + 1))
    row = ["expected"]
    for b in blocks:
        row.append(f"{sum(fielded[ev] + subs[ev] for ev in b):.1f}")
    row.append(f"{tot_f + tot_s:.1f}")
    out.append("| " + " | ".join(row) + " |")

    out.append("")
    out.append("**Season fixtures (avg difficulty · easy/H · away):**")
    for _, r in df.iterrows():
        diffs = [r[f"difficulty_gw{ev}"] for ev in events]
        homes = sum(1 for ev in events if r[f"home_gw{ev}"])
        easy = sum(1 for d in diffs if d <= 2)
        out.append(f"- {r['web_name']} ({team_names.get(int(r['team_id']), '?')}): "
                   f"avg diff {np.mean(diffs):.1f} · easy {easy}/38 · home {homes}/38")

    out.append("")
    out.append(f"**Total cost:** {squad.cost:.1f}m / 100.0m · "
               f"**Squad value (all 15):** {squad.projected_points:.1f} · "
               f"**Expected fielded points (season):** {tot_f + tot_s:.1f}")
    return "\n".join(out)
