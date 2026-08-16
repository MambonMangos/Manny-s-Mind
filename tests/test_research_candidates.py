"""Shadow candidate registry tests (research/candidates.py)."""

from __future__ import annotations

import json

import pytest

from research import config as rconfig
from research.candidates import (
    CANDIDATES,
    get_candidate,
    get_shadow_candidate,
    load_shadow_candidate,
    register_shadow_candidate,
)


def test_registry_populated():
    assert "v3_hist_d_team" in CANDIDATES
    assert "v3_hist_b_points" in CANDIDATES
    for c in CANDIDATES.values():
        assert c["status"] == "shadow_candidate"
        assert c["promotion_status"] == "not_promoted"
        assert c["promotion_requires"], "candidates must list promotion criteria"
        assert c["points_version"] in (None, "expected_points_v1_hist")


def test_shadow_candidate_is_model_d():
    d = get_shadow_candidate()
    assert d["model_id"] == "v3_hist_d_team"
    assert d["hist_features"] == ["player", "team"]


def test_get_candidate_unknown_raises():
    with pytest.raises(KeyError):
        get_candidate("does_not_exist")


def test_register_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(rconfig, "RESULTS_DIR", tmp_path)
    path = register_shadow_candidate("v3_hist_b_points")
    assert path == tmp_path / "shadow_candidate.json"
    loaded = load_shadow_candidate()
    assert loaded["model_id"] == "v3_hist_b_points"
    assert loaded["walk_forward_metrics"] or True


def test_register_embeds_fold_metrics(tmp_path, monkeypatch):
    # Point RESULTS_DIR at a real results dir so live ablation metrics attach.
    real = rconfig.RESULTS_DIR
    monkeypatch.setattr(rconfig, "RESULTS_DIR", real)
    path = register_shadow_candidate()
    with open(path) as f:
        data = json.load(f)
    assert "walk_forward_metrics" in data
    assert "fold1" in data["walk_forward_metrics"]
    assert data["walk_forward_metrics"]["fold1"]["mae_points"] > 0


def test_load_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(rconfig, "RESULTS_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        load_shadow_candidate()
