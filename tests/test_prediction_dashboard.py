from datetime import timedelta
from pathlib import Path

import pandas as pd
import pytest
import numpy as np

from models.price_average_estimator import estimate_symbol_price, estimate_universe
from models.research_forecaster import forecast_from_price_history
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


def test_average_estimator_calculates_3_7_14_day_ranges(tmp_path: Path):
    path = tmp_path / "2330_TW.csv"
    dates = pd.date_range("2026-07-01", periods=20)
    closes = list(range(100, 120))
    pd.DataFrame({"trade_date": dates, "close": closes}).to_csv(path, index=False)

    result = estimate_symbol_price(path, "2330.TW", "台積電", as_of="2026-07-20")

    assert result["average_3d"] == sum([117, 118, 119]) / 3
    assert result["average_7d"] == sum(range(113, 120)) / 7
    assert result["average_14d"] == sum(range(106, 120)) / 14
    assert result["lower_3d"] == pytest.approx(result["average_3d"] * 0.2)
    assert result["upper_3d"] == pytest.approx(result["average_3d"] * 1.8)


def test_estimator_excludes_rows_after_as_of_date(tmp_path: Path):
    path = tmp_path / "2330_TW.csv"
    dates = pd.date_range("2026-07-01", periods=16)
    closes = [100.0] * 15 + [99999.0]
    pd.DataFrame({"trade_date": dates, "close": closes}).to_csv(path, index=False)

    result = estimate_symbol_price(path, "2330.TW", "台積電", as_of="2026-07-15")

    assert result["latest_close"] == 100.0
    assert result["average_14d"] == 100.0


def test_universe_estimator_handles_missing_symbols(tmp_path: Path):
    pd.DataFrame({
        "trade_date": pd.date_range("2026-07-01", periods=14),
        "close": range(100, 114),
    }).to_csv(tmp_path / "2330_TW.csv", index=False)
    result = estimate_universe(
        {"2330.TW": "台積電", "9999.TW": "缺少資料"},
        tmp_path,
        as_of="2026-07-20",
    )
    assert list(result["symbol"]) == ["2330"]


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
