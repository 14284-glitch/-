from pathlib import Path

import numpy as np
import pandas as pd

from models.prediction_ledger import monitoring_summary, reconcile_outcomes, record_forecasts
from models.validated_logistic import build_model_frame, train_validated_forecasts


def _history(path: Path, rows: int = 1500) -> None:
    index = np.arange(rows)
    close = 100 + index * 0.02 + np.sin(index / 11) * 4 + np.sin(index / 3)
    pd.DataFrame({
        "stock_id": "2330.TW",
        "trade_date": pd.bdate_range("2020-01-01", periods=rows),
        "open": close * (1 + np.sin(index / 5) * 0.002),
        "high": close * 1.012,
        "low": close * 0.988,
        "close": close,
        "adjusted_close": close,
        "volume": 1_000_000 + (index % 40) * 20_000,
    }).to_csv(path, index=False)


def test_targets_use_only_future_rows_and_latest_target_is_unknown(tmp_path: Path):
    path = tmp_path / "2330_TW.csv"
    _history(path)
    frame = build_model_frame(path, as_of="2030-12-31")
    assert pd.isna(frame.iloc[-1]["future_return_1d"])
    expected = frame.iloc[1]["adjusted_close"] / frame.iloc[0]["adjusted_close"] - 1
    assert frame.iloc[0]["future_return_1d"] == expected


def test_three_horizons_are_trained_separately_with_holdout_metrics(tmp_path: Path):
    path = tmp_path / "2330_TW.csv"
    _history(path)
    forecasts = train_validated_forecasts(path, as_of="2030-12-31")
    assert [item.horizon for item in forecasts] == [1, 5, 20]
    for item in forecasts:
        assert 0 <= item.accuracy <= 1
        assert 0 <= item.baseline_accuracy <= 1
        assert item.test_samples >= 126
        assert abs(item.probability_up + item.probability_down + item.probability_sideways - 1) < 1e-8


def test_ledger_is_immutable_and_reconciles_only_mature_predictions(tmp_path: Path):
    price_path = tmp_path / "2330_TW.csv"
    _history(price_path)
    forecast = train_validated_forecasts(price_path, as_of="2025-06-30")[0]
    ledger_path = tmp_path / "ledger.csv"
    first = record_forecasts([forecast], ledger_path)
    second = record_forecasts([forecast], ledger_path)
    assert len(first) == len(second) == 1
    reconciled = reconcile_outcomes(ledger_path, tmp_path)
    assert reconciled.iloc[0]["actual_return"] == reconciled.iloc[0]["actual_return"]
    summary = monitoring_summary(reconciled)
    assert int(summary.iloc[0]["已核對預測數"]) == 1
