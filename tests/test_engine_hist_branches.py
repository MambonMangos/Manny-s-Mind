"""Empirical (historical) branch tests for the two V3 engines.

Verifies that the optional ``config_version`` / ``hist_*`` column plumbing
works without disturbing the default (production) behaviour, which is already
covered by the existing engine test suites.
"""

from __future__ import annotations

from synthetic import create_synthetic_players

from engines.expected_minutes_engine import project_expected_minutes
from engines.expected_points_engine import project_expected_points
from features import build_feature_store


def build_store(n=20, seed=11, **kwargs):
    df = create_synthetic_players(n=n, seed=seed)
    for col, val in kwargs.items():
        df[col] = val
    return build_feature_store(players_df=df, gameweek_id=1)


def test_points_default_equals_production_version():
    """With config_version=None the engine uses the active production config."""
    a = {p.player_id: p.xpts_per_90 for p in project_expected_points(build_store(20))}
    b = {p.player_id: p.xpts_per_90 for p in
         project_expected_points(build_store(20), config_version=None)}
    assert a == b


def test_minutes_default_equals_production_version():
    a = {p.player_id: p.expected_minutes for p in project_expected_minutes(build_store(20))}
    b = {p.player_id: p.expected_minutes for p in
         project_expected_minutes(build_store(20), config_version=None)}
    assert a == b


def test_points_empirical_finishing_multiplier():
    """Empirical finishing multiplier must scale xg_90 (FWD, goals/xG<1 shrunk)."""
    store = build_store(1, seed=1, position=["FWD"], expected_goals=[8.0],
                        expected_assists=[0.0], expected_goal_involvements=[8.0])
    base = project_expected_points(store, config_version=None)[0]
    hist = project_expected_points(store, config_version="expected_points_v1_hist")[0]
    assert hist.xg_90 != base.xg_90
    assert hist.xg_90 > base.xg_90, "empirical FWD finishing > 1.0 must raise xg_90"


def test_points_empirical_bonus_and_cs_apply():
    store = build_store(3, seed=2, bps=[800, 20, 5], position=["GKP", "DEF", "MID"])
    base = {p.player_id: p.expected_bonus for p in project_expected_points(store, config_version=None)}
    hist = {p.player_id: p.expected_bonus for p in
            project_expected_points(store, config_version="expected_points_v1_hist")}
    for pid, value in base.items():
        assert hist[pid] != value, "empirical bonus model must differ from divisor model"


def test_points_empirical_team_adjustment():
    """hist_team_attack_adj > 1 must lift xg_90 when empirical config is on."""
    df = create_synthetic_players(1, seed=3)
    df["position"] = ["FWD"]
    df["hist_team_attack_adj"] = [1.6]
    df["hist_team_defense_adj"] = [1.0]
    store = build_feature_store(players_df=df, gameweek_id=1)
    hist = project_expected_points(store, config_version="expected_points_v1_hist")[0]

    df2 = create_synthetic_players(1, seed=3)
    df2["position"] = ["FWD"]
    df2["hist_team_attack_adj"] = [1.0]
    df2["hist_team_defense_adj"] = [1.0]
    store2 = build_feature_store(players_df=df2, gameweek_id=1)
    plain = project_expected_points(store2, config_version="expected_points_v1_hist")[0]
    assert hist.xg_90 > plain.xg_90


def test_points_empirical_prev_season_blend_small_sample():
    """With < min_current_games, hist_prev_* shrinks current-season rates."""
    df = create_synthetic_players(1, seed=4)
    df["position"] = ["FWD"]
    df["minutes"] = [180]          # 2 games -> below min_current_games=3
    df["expected_goals"] = [1.0]
    df["expected_assists"] = [0.0]
    df["expected_goal_involvements"] = [1.0]
    df["hist_prev_xg_per_90"] = [1.2]
    df["hist_prev_xa_per_90"] = [0.4]
    store = build_feature_store(players_df=df, gameweek_id=1)
    hist = project_expected_points(store, config_version="expected_points_v1_hist")[0]
    assert hist.xg_90 > 0.5, "prev-season blend must pull xg_90 up toward 1.2"


def test_minutes_hist_mode_adds_sub_branch():
    """Empirical minutes model must add the P(sub|not start) branch."""
    df = create_synthetic_players(4, seed=5)
    df["hist_appearances"] = [10, 10, 10, 10]
    df["hist_starts"] = [9, 2, 8, 0]
    df["hist_sub_rate"] = [0.1, 0.4, 0.2, 0.5]
    df["starts"] = [9, 2, 8, 0]
    df["minutes"] = [810, 200, 720, 40]
    store = build_feature_store(players_df=df, gameweek_id=1)

    base = {p.player_id: p for p in project_expected_minutes(store, config_version=None)}
    hist = {p.player_id: p for p in
            project_expected_minutes(store, config_version="expected_minutes_v1_hist")}
    for pid, p in hist.items():
        assert p.sub_rate_given_not_start > 0.0, "hist mode must populate sub_rate_given_not_start"
    for pid, p in hist.items():
        if base[pid].start_probability < 0.5:
            # Non-starters gain a bench minutes branch in the empirical model.
            assert p.expected_minutes > base[pid].expected_minutes


def test_minutes_hist_beta_binomial_sample_sensitivity():
    """A 0-starts sample of 10 appearances must have lower P(start) than one of 2."""
    def make(apps, starts):
        df = create_synthetic_players(1, seed=6)
        df["hist_appearances"] = [apps]
        df["hist_starts"] = [starts]
        df["hist_sub_rate"] = [0.1]
        df["starts"] = [starts]
        df["minutes"] = [starts * 90]
        return build_feature_store(players_df=df, gameweek_id=1)

    p_2apps = project_expected_minutes(make(2, 0), config_version="expected_minutes_v1_hist")[0]
    p_10apps = project_expected_minutes(make(10, 0), config_version="expected_minutes_v1_hist")[0]
    assert p_10apps.start_probability < p_2apps.start_probability


def test_minutes_hist_uses_player_sub_rate_blend():
    """hist_sub_rate should raise expected minutes via the bench branch."""
    def make(sub_rate):
        df = create_synthetic_players(1, seed=7)
        df["hist_appearances"] = [10]
        df["hist_starts"] = [0]
        df["hist_sub_rate"] = [sub_rate]
        df["starts"] = [0]
        df["minutes"] = [30]
        return build_feature_store(players_df=df, gameweek_id=1)

    low = project_expected_minutes(make(0.0), config_version="expected_minutes_v1_hist")[0]
    high = project_expected_minutes(make(0.9), config_version="expected_minutes_v1_hist")[0]
    assert high.expected_minutes > low.expected_minutes
