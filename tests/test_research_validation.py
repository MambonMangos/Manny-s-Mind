"""Walk-forward validation tests (research/validation.py)."""

from __future__ import annotations

import pytest

from research.validation import (
    FOLDS,
    MODELS,
    build_ablation_table,
    evaluate_outcome,
    run_fold,
    run_preseason_validation,
    summarize_model,
)


def test_folds_chronological_and_non_overlapping():
    for fold in FOLDS:
        assert set(fold["train"]) <= {"2022-23", "2023-24", "2024-25"}
        assert fold["validate"] and not (set(fold["train"]) & set(fold["validate"]))
    assert FOLDS[0]["validate"] == ["2023-24"]
    assert FOLDS[1]["validate"] == ["2024-25"]


def test_models_definition():
    expected = {"A_baseline", "B_points_hist", "C_minutes_hist", "D_team", "F_full"}
    assert set(MODELS) == expected
    assert MODELS["A_baseline"]["points_version"] is None
    assert MODELS["B_points_hist"]["hist_features"] == ()
    assert MODELS["D_team"]["hist_features"] == ("player", "team")


@pytest.fixture(scope="module")
def fold1_out():
    return run_fold(FOLDS[0], models=["A_baseline"], use_cache=True)


def test_run_fold_cached(fold1_out):
    df = fold1_out["A_baseline"]
    assert len(df) > 20000
    for col in ["predicted_points", "actual_points", "expected_minutes",
                "actual_minutes", "actual_starts", "start_probability",
                "sub_rate_given_not_start"]:
        assert col in df.columns, f"missing {col}"


def test_evaluate_outcome(fold1_out):
    ev = evaluate_outcome(fold1_out["A_baseline"])
    assert "points_error" in ev.columns
    assert "is_non_starter" in ev.columns
    non_starters = ev[ev["is_non_starter"]]
    assert (non_starters["actual_minutes"] == 0).any()
    subs = ev[(ev["is_non_starter"]) & (ev["actual_minutes"] > 0)]
    assert len(subs) > 100, "faithful data must contain bench appearances"


def test_summarize_model_metrics(fold1_out):
    s = summarize_model(fold1_out["A_baseline"])
    assert s["n_predictions"] > 20000
    assert 0 < s["mae_points"] < 3
    assert 0 < s["rmse_points"] < 6
    assert s["corr_points"] > 0
    assert 0 < s["start_accuracy"] < 1
    assert 0 < s["mae_minutes"] < 90
    assert s["top10_overlap_mean"] > 0


def test_build_ablation_table(fold1_out):
    table = build_ablation_table({"fold1": fold1_out})
    assert len(table) == 1
    assert table.iloc[0]["model"] == "A_baseline"
    assert table.iloc[0]["desc"]


def test_preseason_validation_runs():
    report = run_preseason_validation()
    assert report["checks"]["columns_present"]
    assert report["n_players"] > 400
    assert len(report["top_gw1_xpts"]) == 10
