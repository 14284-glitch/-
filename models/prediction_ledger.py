"""Immutable prediction snapshots and delayed outcome/error reconciliation."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import PROJECT_ROOT
from models.validated_logistic import FLAT_THRESHOLDS, ValidatedForecast


LEDGER_PATH = PROJECT_ROOT / "data" / "processed" / "prediction_history.csv"
LATEST_PATH = PROJECT_ROOT / "data" / "processed" / "latest_validated_predictions.csv"


def record_forecasts(forecasts: list[ValidatedForecast], path: Path = LEDGER_PATH) -> pd.DataFrame:
    incoming = pd.DataFrame([item.__dict__ for item in forecasts])
    incoming["prediction_recorded_at"] = pd.Timestamp.now(tz="Asia/Taipei").isoformat()
    for column in (
        "actual_date", "actual_close", "actual_return", "actual_direction",
        "direction_correct", "absolute_return_error", "absolute_price_error",
        "interval_covered", "brier_score",
    ):
        incoming[column] = pd.NA
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame()
    combined = pd.concat([existing, incoming], ignore_index=True)
    keys = ["model_version", "symbol", "horizon", "data_date"]
    combined = combined.drop_duplicates(keys, keep="first").sort_values(keys)
    _atomic_csv(combined, path)
    return combined


def reconcile_outcomes(
    ledger_path: Path = LEDGER_PATH, raw_root: Path | None = None
) -> pd.DataFrame:
    if not ledger_path.exists():
        return pd.DataFrame()
    ledger = pd.read_csv(ledger_path)
    if "actual_date" in ledger:
        ledger["actual_date"] = ledger["actual_date"].astype("object")
    raw_root = raw_root or PROJECT_ROOT / "data" / "raw" / "tw"
    for index, row in ledger[ledger["actual_return"].isna()].iterrows():
        price_path = raw_root / f"{str(row['symbol']).replace('.', '_')}".replace("_TW", "_TW.csv")
        if not price_path.exists():
            continue
        prices = pd.read_csv(price_path, usecols=["trade_date", "close", "adjusted_close"])
        prices["trade_date"] = pd.to_datetime(
            prices["trade_date"], format="mixed", errors="coerce"
        )
        prices = prices.dropna(subset=["trade_date"]).sort_values("trade_date")
        target = pd.Timestamp(row["target_date"])
        actual = prices[prices["trade_date"] >= target]
        if actual.empty:
            continue
        actual_row = actual.iloc[0]
        actual_close = float(actual_row["close"])
        actual_return = actual_close / float(row["latest_close"]) - 1
        threshold = FLAT_THRESHOLDS[int(row["horizon"])]
        actual_direction = 1 if actual_return > threshold else -1 if actual_return < -threshold else 0
        predicted_direction = int(np.argmax([
            float(row["probability_down"]), float(row["probability_sideways"]), float(row["probability_up"])
        ])) - 1
        probabilities = {
            -1: float(row["probability_down"]), 0: float(row["probability_sideways"]), 1: float(row["probability_up"])
        }
        ledger.loc[index, "actual_date"] = actual_row["trade_date"].strftime("%Y-%m-%d")
        ledger.loc[index, "actual_close"] = actual_close
        ledger.loc[index, "actual_return"] = actual_return
        ledger.loc[index, "actual_direction"] = actual_direction
        ledger.loc[index, "direction_correct"] = int(predicted_direction == actual_direction)
        ledger.loc[index, "absolute_return_error"] = abs(float(row["expected_return"]) - actual_return)
        ledger.loc[index, "absolute_price_error"] = abs(float(row["expected_price"]) - actual_close)
        ledger.loc[index, "interval_covered"] = int(float(row["return_lower"]) <= actual_return <= float(row["return_upper"]))
        ledger.loc[index, "brier_score"] = sum(
            (probabilities[label] - float(label == actual_direction)) ** 2 for label in (-1, 0, 1)
        ) / 3
    _atomic_csv(ledger, ledger_path)
    return ledger


def write_latest(forecasts: list[ValidatedForecast], path: Path = LATEST_PATH) -> None:
    _atomic_csv(pd.DataFrame([item.__dict__ for item in forecasts]), path)


def monitoring_summary(ledger: pd.DataFrame) -> pd.DataFrame:
    mature = ledger.dropna(subset=["actual_return"]).copy()
    if mature.empty:
        return pd.DataFrame()
    return mature.groupby(["model_version", "horizon"], as_index=False).agg(
        已核對預測數=("actual_return", "size"),
        方向命中率=("direction_correct", "mean"),
        平均報酬誤差=("absolute_return_error", "mean"),
        平均價格誤差=("absolute_price_error", "mean"),
        區間涵蓋率=("interval_covered", "mean"),
        Brier分數=("brier_score", "mean"),
    )


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    frame.to_csv(temporary, index=False)
    temporary.replace(path)
