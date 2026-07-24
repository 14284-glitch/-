from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models.research_forecaster import attach_external_market_features, forecast_from_price_history
from pages.prediction_dashboard import load_prediction_data
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs


def test_missing_prediction_file_is_handled(tmp_path: Path):
    frame, error = load_prediction_data(tmp_path / "missing.csv")
    assert frame.empty
    assert "尚未產生" in error


def test_invalid_prediction_date_is_rejected(tmp_path: Path):
    path = tmp_path / "prediction.csv"
    path.write_text("trade_date,probability_up_1d\nnot-a-date,0.7\n", encoding="utf-8")
    frame, error = load_prediction_data(path)
    assert frame.empty
    assert "有效的交易日期" in error


def test_prediction_universes_have_fifty_items():
    assert len(TAIWAN_50_CONSTITUENTS) == 50
    assert len(load_popular_etfs()) == 50


def _write_forecast_history(path: Path, rows: int = 520) -> None:
    index = np.arange(rows)
    close = 100 + index * 0.08 + np.sin(index / 7) * 2
    pd.DataFrame({
        "trade_date": pd.bdate_range("2024-01-01", periods=rows),
        "open": close * (1 + np.sin(index) * 0.002),
        "high": close * 1.012,
        "low": close * 0.988,
        "close": close,
        "adjusted_close": close,
        "volume": 1_000_000 + (index % 30) * 15_000,
    }).to_csv(path, index=False)


def test_research_forecaster_outputs_separate_1_5_20_day_models(tmp_path: Path):
    path = tmp_path / "2330_TW.csv"
    _write_forecast_history(path)
    result = forecast_from_price_history(path, as_of="2026-12-31")

    assert [item.horizon for item in result["forecasts"]] == [1, 5, 20]
    assert [item.input_window for item in result["forecasts"]] == [20, 60, 250]
    for item in result["forecasts"]:
        assert item.probability_up + item.probability_down + item.probability_sideways == pytest.approx(1)
        assert item.price_lower <= item.expected_price <= item.price_upper
        assert item.risk_level in {"低", "中", "高"}


def test_research_forecaster_does_not_use_rows_after_cutoff(tmp_path: Path):
    base_path = tmp_path / "base.csv"
    extended_path = tmp_path / "extended.csv"
    _write_forecast_history(base_path, 500)
    base = pd.read_csv(base_path)
    future = base.tail(20).copy()
    start = pd.Timestamp(base["trade_date"].iloc[-1]).to_pydatetime() + timedelta(days=1)
    future["trade_date"] = pd.bdate_range(start, periods=20)
    future["close"] = 99999
    future["open"] = future["high"] = future["low"] = 99999
    pd.concat([base, future], ignore_index=True).to_csv(extended_path, index=False)
    cutoff = base["trade_date"].iloc[-1]

    original = forecast_from_price_history(base_path, as_of=cutoff)
    extended = forecast_from_price_history(extended_path, as_of=cutoff)

    for left, right in zip(original["forecasts"], extended["forecasts"]):
        assert left.expected_return == pytest.approx(right.expected_return)
        assert left.probability_up == pytest.approx(right.probability_up)


def test_us_market_features_use_strictly_previous_us_session(tmp_path: Path):
    raw = tmp_path / "raw"
    (raw / "us").mkdir(parents=True)
    tw = pd.DataFrame({
        "trade_date": pd.to_datetime(["2026-07-15", "2026-07-16"]),
        "close": [100.0, 101.0],
    })
    pd.DataFrame({
        "us_trade_date": ["2026-07-13", "2026-07-14", "2026-07-15"],
        "close": [100.0, 110.0, 220.0],
    }).to_csv(raw / "us" / "INDEX_GSPC.csv", index=False)

    joined = attach_external_market_features(tw, raw)

    # Taiwan 7/15 receives US 7/14 return (+10%), never the same-date US 7/15 close.
    assert joined.loc[0, "sp500_prev_return"] == pytest.approx(0.10)
    # Taiwan 7/16 can then receive the completed US 7/15 return (+100%).
    assert joined.loc[1, "sp500_prev_return"] == pytest.approx(1.00)
