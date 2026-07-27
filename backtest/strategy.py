"""Signal generators for long-only, point-in-time backtests."""

from __future__ import annotations

import numpy as np
import pandas as pd

STRATEGIES = ("買進持有", "均線交叉", "RSI反轉", "MACD交叉")


def generate_signals(frame: pd.DataFrame, strategy: str, parameters: dict[str, float]) -> pd.DataFrame:
    data = frame.copy().sort_values("trade_date").reset_index(drop=True)
    close = pd.to_numeric(data["close"], errors="coerce")
    entry = pd.Series(False, index=data.index)
    exit_ = pd.Series(False, index=data.index)
    warmup = 1
    if strategy == "買進持有":
        entry.iloc[0] = True
    elif strategy == "均線交叉":
        short, long = int(parameters.get("short_ma", 5)), int(parameters.get("long_ma", 20))
        if short >= long:
            raise ValueError("短期均線期間必須小於長期均線期間")
        fast, slow = close.rolling(short).mean(), close.rolling(long).mean()
        entry = (fast > slow) & (fast.shift(1) <= slow.shift(1))
        exit_ = (fast < slow) & (fast.shift(1) >= slow.shift(1))
        data["短期均線"], data["長期均線"] = fast, slow
        warmup = long
    elif strategy == "RSI反轉":
        period = int(parameters.get("rsi_period", 14))
        oversold, overbought = float(parameters.get("oversold", 30)), float(parameters.get("overbought", 70))
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
        rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        entry = (rsi > oversold) & (rsi.shift(1) <= oversold)
        exit_ = (rsi < overbought) & (rsi.shift(1) >= overbought)
        data["RSI"] = rsi
        warmup = period + 1
    elif strategy == "MACD交叉":
        fast_n = int(parameters.get("macd_fast", 12))
        slow_n = int(parameters.get("macd_slow", 26))
        signal_n = int(parameters.get("macd_signal", 9))
        if fast_n >= slow_n:
            raise ValueError("MACD快速期間必須小於慢速期間")
        dif = close.ewm(span=fast_n, adjust=False, min_periods=slow_n).mean() - close.ewm(
            span=slow_n, adjust=False, min_periods=slow_n
        ).mean()
        signal = dif.ewm(span=signal_n, adjust=False, min_periods=signal_n).mean()
        entry = (dif > signal) & (dif.shift(1) <= signal.shift(1))
        exit_ = (dif < signal) & (dif.shift(1) >= signal.shift(1))
        data["DIF"], data["Signal"] = dif, signal
        warmup = slow_n + signal_n
    else:
        raise ValueError("不支援的回測策略")
    data["entry_signal"] = entry.fillna(False)
    data["exit_signal"] = exit_.fillna(False)
    data.attrs["warmup_periods"] = warmup
    return data
