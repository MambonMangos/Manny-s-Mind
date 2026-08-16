"""Tests for the GW1 picker (research/gw1_picker.py).

Uses synthetic player data — no DB, no network — to verify the invariants
(budget, position slots, club limit) and the research-informed behaviours
(shrinkage, fixture factor, set-piece bonus).
"""

import numpy as np
import pandas as pd
import pytest

from research import gw1_picker as gp


def _synthetic_players(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pos_ids = [1, 2, 3, 4]  # GKP, DEF, MID, FWD
    params = {
        "GKP": {"xgi_base": 0.01},
        "DEF": {"xgi_base": 0.25, "alpha": 2.6, "beta": 5.0},
        "MID": {"xgi_base": 0.45, "alpha": 3.1, "beta": 3.8},
        "FWD": {"xgi_base": 0.60, "alpha": 2.4, "beta": 5.5},
    }
    rows = []
    for i in range(n):
        label = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}[pos_ids[i % 4]]
        mins = float(rng.uniform(0, 3200))
        games = max(mins / 90, 0.0)
        xgi90 = params[label]["xgi_base"] * rng.uniform(0.3, 1.8)
        if label == "GKP":
            pp90 = float(rng.uniform(3.5, 5.5))
        else:
            pp90 = float(np.clip(
                params[label]["alpha"] + params[label]["beta"] * xgi90
                + rng.normal(0, 0.4), 1.5, 7.5))
        rows.append({
            "id": i,
            "web_name": f"P{i}",
            "team_id": (i % 20) + 1,
            "team_name": f"T{(i % 20) + 1}",
            "position": label,
            "price": round(rng.uniform(4.0, 12.0), 1),
            "minutes": mins,
            "starts": float(np.clip(np.round(games * rng.uniform(0.6, 1.0)), 0, 38)),
            "total_points": games * pp90,
            "goals_scored": games * xgi90 * rng.uniform(0.5, 0.8),
            "assists": games * xgi90 * rng.uniform(0.2, 0.5),
            "expected_goal_involvements": games * xgi90,
            "penalties_order": int(rng.integers(0, 4)),
            "direct_freekicks_order": int(rng.integers(0, 4)),
            "corners_and_indirect_freekicks_order": int(rng.integers(0, 4)),
        })
    df = pd.DataFrame(rows)
    # at least a few genuinely cheap players per position
    for label in gp.POSITION_SLOTS:
        idx = df.index[df["position"] == label][:3]
        df.loc[idx, "price"] = 4.0
    return df


def _synthetic_gw1() -> pd.DataFrame:
    rows = [{
        "team_id": t,
        "opponent_id": 21 - t if t != 20 else 1,
        "home": t % 2 == 0,
        "difficulty": (t % 5) + 1,
        "fixture_score": gp.compute_fixture_score((t % 5) + 1),
    } for t in range(1, 21)]
    return pd.DataFrame(rows)


def _synthetic_gw_frames(events=(1, 2, 3, 4, 5)) -> dict[int, pd.DataFrame]:
    """Per-GW frames with a rotating difficulty so fixture factors differ."""
    return {
        ev: pd.DataFrame([{
            "team_id": t,
            "opponent_id": 21 - t if t != 20 else 1,
            "home": (t + ev) % 2 == 0,
            "difficulty": ((t + ev) % 5) + 1,
            "fixture_score": gp.compute_fixture_score(((t + ev) % 5) + 1),
        } for t in range(1, 21)])
        for ev in events
    }


@pytest.fixture(scope="module")
def scored() -> pd.DataFrame:
    d = gp.add_features(_synthetic_players(), _synthetic_gw1())
    m = gp.calibrate_position_model(d)
    return gp.project_points(d, m)


def test_position_slots_and_budget(scored):
    sq = gp.select_squad(scored)
    assert sq.players["position"].value_counts().to_dict() == gp.POSITION_SLOTS
    assert sq.cost <= gp.BUDGET + 1e-6
    assert sq.cost >= gp.BUDGET - 30  # not absurdly under budget


def test_club_limit(scored):
    sq = gp.select_squad(scored)
    counts = sq.players.groupby("team_id").size()
    assert counts.max() <= gp.MAX_PER_CLUB


def test_all_slots_filled(scored):
    sq = gp.select_squad(scored)
    assert len(sq.players) == 15


def test_projection_nonnegative(scored):
    assert (scored["projected_points"] >= 0).all()


def test_shrinkage_reduces_single_game_star():
    df = _synthetic_players(60, seed=3)
    fwd_idx = df.index[df["position"] == "FWD"][:2]
    # one player with a monster single game must NOT outscore a full-season star
    star_idx, single_idx = fwd_idx[0], fwd_idx[1]
    df.loc[star_idx, ["minutes", "starts", "total_points", "expected_goal_involvements"]] = (
        3000.0, 33.0, 210.0, 27.0)  # 6.3 pts / 0.81 xGI per 90 across a full season
    df.loc[single_idx, ["minutes", "starts", "total_points", "expected_goal_involvements"]] = (
        90.0, 1.0, 15.0, 1.0)  # 15 pts per 90 from one game
    feats = gp.add_features(df, _synthetic_gw1())
    scored = gp.project_points(feats, gp.calibrate_position_model(feats))
    assert scored.loc[single_idx, "projected_points"] < scored.loc[star_idx, "projected_points"]


def test_fixture_factor_range(scored):
    assert scored["fixture_factor"].between(0.85, 1.15).all()


def test_set_piece_bonus_added(scored):
    d = scored
    pen = d[d["penalties_order"] == 1]
    assert len(pen) > 0
    # penalty takers carry at least +0.4 vs the same player without the bonus
    assert pen["set_piece_bonus"].max() >= 0.4


def test_format_squad_renders(scored):
    sq = gp.select_squad(scored)
    text = gp.format_squad(sq, team_names=dict(
        scored.groupby("team_id")["team_name"].first()))
    assert "position | player | club" in text
    assert "100.0m" in text


@pytest.fixture(scope="module")
def multi_scored() -> pd.DataFrame:
    events = [1, 2, 3, 4, 5]
    d = gp.add_features(_synthetic_players(), _synthetic_gw_frames(events)[1])
    d = gp.add_multi_gw_fixtures(d, _synthetic_gw_frames(events), events)
    m = gp.calibrate_position_model(d)
    return gp.project_points_multi_gw(d, m, events)


def test_multi_gw_total_is_sum_of_per_gw(multi_scored):
    events = [1, 2, 3, 4, 5]
    cols = [f"projected_points_gw{ev}" for ev in events]
    assert np.allclose(multi_scored[cols].sum(axis=1), multi_scored["projected_points"], rtol=1e-9)


def test_multi_gw_fixture_factors_in_range(multi_scored):
    for ev in [1, 2, 3, 4, 5]:
        assert multi_scored[f"fixture_factor_gw{ev}"].between(0.85, 1.15).all()


def test_multi_gw_window_changes_preference():
    # same player, easy vs hard window: the easy-window copy must project higher
    players = _synthetic_players(300, seed=11)
    base = players.iloc[0].to_dict()
    easy, hard = base.copy(), base.copy()
    easy["id"], hard["id"] = 9000, 9001
    easy["team_id"], hard["team_id"] = 1, 2
    easy["web_name"], hard["web_name"] = "EasyPlayer", "HardPlayer"
    hard["minutes"] = easy["minutes"] = 3000.0
    hard["starts"] = easy["starts"] = 33.0
    hard["total_points"] = easy["total_points"] = 200.0
    df = pd.concat([players, pd.DataFrame([easy, hard])], ignore_index=True)

    def frame_for(team_diff: dict[int, int]) -> pd.DataFrame:
        return pd.DataFrame([{
            "team_id": t, "opponent_id": 20, "home": True,
            "difficulty": team_diff.get(t, 3),
            "fixture_score": gp.compute_fixture_score(team_diff.get(t, 3)),
        } for t in range(1, 21)])

    events = [1, 2, 3, 4, 5]
    frames = {
        ev: frame_for({1: 1 if ev in (1, 3) else 5, 2: 5})
        for ev in events
    }
    feats = gp.add_features(df, frames[1])
    feats = gp.add_multi_gw_fixtures(feats, frames, events)
    scored = gp.project_points_multi_gw(feats, gp.calibrate_position_model(feats), events)
    easy_pts = scored.loc[scored["web_name"] == "EasyPlayer", "projected_points"].iloc[0]
    hard_pts = scored.loc[scored["web_name"] == "HardPlayer", "projected_points"].iloc[0]
    assert easy_pts > hard_pts


def test_multi_gw_squad_constraints(multi_scored):
    sq = gp.select_squad(multi_scored)
    assert sq.players["position"].value_counts().to_dict() == gp.POSITION_SLOTS
    assert len(sq.players) == 15
    assert sq.cost <= gp.BUDGET + 1e-6
    assert sq.players.groupby("team_id").size().max() <= gp.MAX_PER_CLUB


def test_format_squad_multi_gw_renders(multi_scored):
    events = [1, 2, 3, 4, 5]
    sq = gp.select_squad(multi_scored)
    sq.gw_frames = _synthetic_gw_frames(events)
    text = gp.format_squad_multi_gw(sq, team_names=dict(
        multi_scored.groupby("team_id")["team_name"].first()))
    assert "GW1" in text and "GW5" in text
    assert "Expected fielded points" in text


def test_calibration_passes_through_weighted_mean():
    d = gp.add_features(_synthetic_players(), _synthetic_gw1())
    model = gp.calibrate_position_model(d)
    for pos in ("DEF", "MID", "FWD"):
        sub = d[d["position"] == pos]
        w = sub["games"]
        wx = (w * sub["xgi_per_90_s"]).sum() / w.sum()
        wy = (w * sub["points_per_90_s"]).sum() / w.sum()
        fitted = model[pos].alpha + model[pos].beta * wx
        assert fitted == pytest.approx(wy, rel=1e-6)
        assert model[pos].alpha > 0  # baseline: appearance/cs/bonus points


def test_high_xgi_no_longer_over_credited():
    d = gp.add_features(_synthetic_players(), _synthetic_gw1())
    model = gp.calibrate_position_model(d)
    for pos in ("DEF", "MID", "FWD"):
        xgi_pts = model[pos].alpha + model[pos].beta * d.loc[d["position"] == pos, "xgi_per_90_s"]
        pp90 = d.loc[d["position"] == pos, "points_per_90_s"]
        # the xGI-driven term must not dwarf the player's own points-per-90
        assert (xgi_pts <= pp90 * 2.0 + 0.5).all()


def test_expected_fielded_uses_legal_xi_and_is_below_squad_value(multi_scored):
    events = [1, 2, 3, 4, 5]
    sq = gp.select_squad(multi_scored)
    fielded, subs, tf, ts = gp.expected_fielded_points(sq.players, events)
    for ev in events:
        xi = gp.best_xi_for_gw(sq.players, ev)
        assert len(xi) == 11
        # fielded XI sum must be less than all-15 sum for that GW
        assert fielded[ev] < sq.players[f"projected_points_gw{ev}"].sum()
        assert fielded[ev] >= 0 and subs[ev] >= 0
    assert tf + ts < sq.projected_points


def test_season_squad_constraints():
    events = list(range(1, 39))
    frames = _synthetic_gw_frames(events)
    d = gp.add_features(_synthetic_players(200, seed=9), frames[1])
    d = gp.add_multi_gw_fixtures(d, frames, events)
    scored = gp.project_points_multi_gw(d, gp.calibrate_position_model(d), events)
    sq = gp.select_squad(scored)
    assert sq.players["position"].value_counts().to_dict() == gp.POSITION_SLOTS
    assert len(sq.players) == 15
    assert sq.cost <= gp.BUDGET + 1e-6
    assert sq.players.groupby("team_id").size().max() <= gp.MAX_PER_CLUB
    _, _, tf, ts = gp.expected_fielded_points(sq.players, events)
    assert tf + ts < sq.projected_points
    assert 0 < tf + ts


def test_format_squad_season_renders():
    events = list(range(1, 39))
    frames = _synthetic_gw_frames(events)
    d = gp.add_features(_synthetic_players(200, seed=9), frames[1])
    d = gp.add_multi_gw_fixtures(d, frames, events)
    scored = gp.project_points_multi_gw(d, gp.calibrate_position_model(d), events)
    sq = gp.select_squad(scored)
    sq.gw_frames = frames
    text = gp.format_squad_season(sq, team_names=dict(
        scored.groupby("team_id")["team_name"].first()))
    assert "GW36-38" in text
    assert "Expected fielded points (season)" in text
    assert "expected | " in text
