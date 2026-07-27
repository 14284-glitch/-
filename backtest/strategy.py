"""Signal generators for long-only, point-in-time backtests."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

STRATEGIES = (
    "買進持有", "均線交叉", "RSI反轉", "MACD交叉",
    "KD交叉", "布林均值回歸", "布林突破", "成交量突破", "自訂條件",
)


def generate_signals(frame: pd.DataFrame, strategy: str, parameters: dict[str, Any]) -> pd.DataFrame:
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
    elif strategy == "KD交叉":
        period = int(parameters.get("kd_period", 9))
        low_level, high_level = float(parameters.get("kd_low", 20)), float(parameters.get("kd_high", 80))
        lowest, highest = data["low"].rolling(period).min(), data["high"].rolling(period).max()
        rsv = (close - lowest) / (highest - lowest).replace(0, np.nan) * 100
        k, d = rsv.ewm(alpha=1 / 3, adjust=False).mean(), rsv.ewm(alpha=1 / 3, adjust=False).mean().ewm(alpha=1 / 3, adjust=False).mean()
        entry = (k > d) & (k.shift(1) <= d.shift(1)) & (k.shift(1) < low_level)
        exit_ = (k < d) & (k.shift(1) >= d.shift(1)) & (k.shift(1) > high_level)
        data["K"], data["D"] = k, d
        warmup = period + 3
    elif strategy in {"布林均值回歸", "布林突破"}:
        period = int(parameters.get("bollinger_period", 20))
        std_multiplier = float(parameters.get("bollinger_std", 2.0))
        middle = close.rolling(period).mean()
        std = close.rolling(period).std(ddof=0)
        upper, lower = middle + std_multiplier * std, middle - std_multiplier * std
        if strategy == "布林均值回歸":
            entry = (close > lower) & (close.shift(1) <= lower.shift(1))
            exit_ = close >= upper
        else:
            volume_ma = data["volume"].rolling(period).mean()
            multiple = float(parameters.get("volume_multiple", 1.5))
            entry = (close > upper) & (close.shift(1) <= upper.shift(1)) & (data["volume"] > volume_ma * multiple)
            exit_ = (close < middle) & (close.shift(1) >= middle.shift(1))
            data["成交量均線"] = volume_ma
        data["布林上軌"], data["布林中軌"], data["布林下軌"] = upper, middle, lower
        warmup = period
    elif strategy == "成交量突破":
        high_n = int(parameters.get("breakout_high", 20))
        low_n = int(parameters.get("breakout_low", 10))
        volume_n = int(parameters.get("volume_period", 20))
        multiple = float(parameters.get("volume_multiple", 1.5))
        prior_high = data["high"].shift(1).rolling(high_n).max()
        prior_low = data["low"].shift(1).rolling(low_n).min()
        volume_ma = data["volume"].shift(1).rolling(volume_n).mean()
        entry = (close > prior_high) & (data["volume"] > volume_ma * multiple)
        exit_ = close < prior_low
        data["N日高點"], data["N日低點"], data["成交量均線"] = prior_high, prior_low, volume_ma
        warmup = max(high_n, low_n, volume_n) + 1
    elif strategy == "自訂條件":
        prepared = _custom_indicator_frame(data, parameters)
        raw_entry = parameters.get("entry_conditions", [])
        raw_exit = parameters.get("exit_conditions", [])
        entry_conditions = raw_entry if isinstance(raw_entry, list) else []
        exit_conditions = raw_exit if isinstance(raw_exit, list) else []
        entry = _condition_group(prepared, entry_conditions, str(parameters.get("entry_connector", "AND")))
        exit_ = _condition_group(prepared, exit_conditions, str(parameters.get("exit_connector", "OR")))
        data = prepared
        warmup = int(parameters.get("custom_warmup", 60))
    elif strategy == "AI歷史訊號":
        required = {"ai_probability_up", "ai_probability_down", "ai_confidence"}
        if required - set(data.columns):
            raise ValueError("目前缺少歷史AI預測訊號，無法執行無前視偏誤的AI策略回測")
        entry = (data["ai_probability_up"] >= float(parameters.get("ai_buy", 0.7))) & (
            data["ai_confidence"] >= float(parameters.get("ai_confidence", 0.6))
        )
        exit_ = data["ai_probability_down"] >= float(parameters.get("ai_sell", 0.6))
        warmup = 1
    else:
        raise ValueError("不支援的回測策略")
    data["entry_signal"] = entry.fillna(False)
    data["exit_signal"] = exit_.fillna(False)
    data.attrs["warmup_periods"] = warmup
    return data


def evaluate_condition(left: pd.Series, operator: str, right: pd.Series | float) -> pd.Series:
    right_series = right if isinstance(right, pd.Series) else pd.Series(float(right), index=left.index)
    operations = {
        "大於": left > right_series, "小於": left < right_series,
        "大於等於": left >= right_series, "小於等於": left <= right_series,
        "等於": left == right_series,
        "向上突破": (left > right_series) & (left.shift(1) <= right_series.shift(1)),
        "向下跌破": (left < right_series) & (left.shift(1) >= right_series.shift(1)),
    }
    if operator not in operations:
        raise ValueError("不支援的自訂條件比較方式")
    return operations[operator].fillna(False)


def _custom_indicator_frame(data: pd.DataFrame, parameters: dict[str, Any]) -> pd.DataFrame:
    close = pd.to_numeric(data["close"], errors="coerce")
    for period in (5, 10, 20, 60, 120, 240):
        data[f"MA{period}"] = close.rolling(period).mean()
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    data["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    data["成交量倍數"] = data["volume"] / data["volume"].rolling(20).mean()
    data["漲跌幅"] = close.pct_change() * 100
    return data


def _condition_group(data: pd.DataFrame, conditions: list[dict], connector: str) -> pd.Series:
    if not conditions:
        return pd.Series(False, index=data.index)
    results = []
    for condition in conditions:
        left_name = str(condition.get("left", "close"))
        if left_name not in data:
            raise ValueError(f"自訂條件缺少指標：{left_name}")
        right_name = condition.get("right_indicator")
        right = data[str(right_name)] if right_name and str(right_name) in data else float(condition.get("value", 0))
        results.append(evaluate_condition(data[left_name], str(condition.get("operator", "大於")), right))
    combined = results[0]
    for result in results[1:]:
        combined = combined & result if connector == "AND" else combined | result
    return combined.fillna(False)
