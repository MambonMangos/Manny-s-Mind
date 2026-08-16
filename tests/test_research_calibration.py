"""Empirical calibration tests (research/calibration.py)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from research.calibration import (
    POSITIONS,
    CalibrationParams,
    build_minutes_config,
    build_points_config,
    fit_params,
    load_params,
    save_params,
    write_config_yaml,
)


def test_fit_params_structure():
    params = fit_params(["2022-23"])
    assert params.seasons == ["2022-23"]
    assert params.n_matches > 300
    assert set(params.finishing) == set(POSITIONS)
    assert set(params.creative) == set(POSITIONS)
    assert set(params.bonus) == set(POSITIONS)
    assert set(params.clean_sheet) == set(POSITIONS)
    assert set(params.minutes) == set(POSITIONS)
    for pos in POSITIONS:
        m = params.minutes[pos]
        for col in ["start_rate_prior", "min_if_start", "min_if_sub",
                    "sub_rate_given_not_start", "alpha", "beta"]:
            assert col in m, f"{pos} missing {col}"
        assert 0.0 < m["start_rate_prior"] < 1.0
        assert 0.0 < m["min_if_start"] <= 90.0


def test_finishing_creative_plausible_bounds():
    params = fit_params(["2022-23", "2023-24"])
    for pos in POSITIONS:
        assert 0.7 <= params.finishing[pos] <= 1.3
        assert 0.5 <= params.creative[pos] <= 1.6


def test_bonus_slope_non_negative():
    params = fit_params(["2022-23"])
    for pos in POSITIONS:
        assert params.bonus[pos]["slope"] >= 0.0


def test_save_load_roundtrip():
    params = fit_params(["2022-23"])
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "params.json"
        save_params(params, path)
        loaded = load_params(path)
    assert loaded.to_dict() == params.to_dict()


def test_build_points_config():
    params = fit_params(["2022-23"])
    cfg = build_points_config(params)
    assert cfg["version"] == "hist-1.0.0"
    assert "2022-23" in cfg["description"]
    assert cfg["empirical"]["finishing"] == params.finishing
    assert cfg["empirical"]["prev_season"]["min_current_games"] == 3
    assert cfg["empirical"]["historical_team"]["attack_weight"] == 0.5


def test_build_minutes_config():
    params = fit_params(["2022-23"])
    cfg = build_minutes_config(params)
    assert cfg["historical_minutes"]["enabled"] is True
    assert cfg["historical_minutes"]["positional"] == params.minutes
    assert cfg["historical_minutes"]["start_prior_weight"] == 0.8


def test_write_config_yaml_never_overwrites():
    params = fit_params(["2022-23"])
    with tempfile.TemporaryDirectory() as td:
        cfg_dir = Path(td)
        write_config_yaml("expected_points", "test_cfg", build_points_config(params), cfg_dir)
        p = cfg_dir / "expected_points" / "test_cfg.yaml"
        assert p.exists()
        first = p.read_text()
        write_config_yaml("expected_points", "test_cfg", build_points_config(params), cfg_dir)
        assert p.read_text() == first, "existing config must never be overwritten"


def test_params_dataclass_serialization():
    params = fit_params(["2022-23"])
    data = params.to_dict()
    assert data["source_pin"]
    assert CalibrationParams.from_dict(data).source_pin == data["source_pin"]
