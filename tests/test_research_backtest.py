"""Backtest runner smoke tests (single gameweek — fast)."""


from research.backtest import predict_gameweek
from research.loader import SeasonData


def test_predict_gameweek_schema_faithful():
    sd = SeasonData.load("2023-24")
    out = predict_gameweek(sd, 10)
    for col in ["player_id", "season", "round", "xpts_per_90",
                "expected_minutes", "predicted_points", "actual_points",
                "actual_minutes", "actual_starts", "data_quality",
                "data_quality_minutes", "season_mode"]:
        assert col in out.columns, f"missing {col}"
    assert len(out) > 500
    assert out["predicted_points"].between(0, 25).all()


def test_predict_gameweek_actuals_match_source():
    sd = SeasonData.load("2023-24")
    out = predict_gameweek(sd, 10)
    expected = sd.gw[sd.gw["round"] == 10].groupby("element")["total_points"].sum()
    joined = out.merge(expected.rename("expected_actual"), left_on="player_id",
                       right_index=True, how="inner")
    assert (joined["actual_points"] == joined["expected_actual"]).all()


def test_predict_gameweek_proxy_marked_and_starts_zero():
    sd = SeasonData.load("2021-22")
    out = predict_gameweek(sd, 10)
    assert (out["season_mode"] == "proxy").all()
    assert (out["actual_starts"].isna() | (out["actual_starts"] == 0)).all()


def test_predictions_reproducible():
    sd = SeasonData.load("2023-24")
    a = predict_gameweek(sd, 12)
    b = predict_gameweek(sd, 12)
    assert a["predicted_points"].equals(b["predicted_points"])
