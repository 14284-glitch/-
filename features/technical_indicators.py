"""Backward-looking technical indicators; every row uses only current and past observations."""

import numpy as np
import pandas as pd


def add_technical_indicators(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.sort_values("trade_date").copy()
    close = pd.to_numeric(frame["close"], errors="coerce")
    high = pd.to_numeric(frame["high"], errors="coerce")
    low = pd.to_numeric(frame["low"], errors="coerce")
    volume = pd.to_numeric(frame["volume"], errors="coerce")

    for window in (5, 10, 20, 60, 120, 240):
        frame[f"ma{window}"] = close.rolling(window, min_periods=window).mean()

    middle = frame["ma20"]
    standard_deviation = close.rolling(20, min_periods=20).std(ddof=0)
    frame["bollinger_middle"] = middle
    frame["bollinger_upper"] = middle + 2 * standard_deviation
    frame["bollinger_lower"] = middle - 2 * standard_deviation

    lowest = low.rolling(9, min_periods=9).min()
    highest = high.rolling(9, min_periods=9).max()
    rsv = ((close - lowest) / (highest - lowest).replace(0, np.nan) * 100).clip(0, 100)
    frame["kd_k"] = rsv.ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()
    frame["kd_d"] = frame["kd_k"].ewm(alpha=1 / 3, adjust=False, min_periods=1).mean()

    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    frame["macd"] = ema12 - ema26
    frame["macd_signal"] = frame["macd"].ewm(span=9, adjust=False, min_periods=9).mean()
    frame["macd_histogram"] = frame["macd"] - frame["macd_signal"]

    change = close.diff()
    average_gain = change.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    average_loss = (-change.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    frame["rsi14"] = 100 - (100 / (1 + relative_strength))
    frame["volume_ma20"] = volume.rolling(20, min_periods=20).mean()
    return frame

