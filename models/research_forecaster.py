"""Point-in-time historical-analogue forecasts for 1/5/20 trading days."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from features.technical_indicators import add_technical_indicators
from features.point_in_time_integrator import attach_point_in_time_features


HORIZON_CONFIG = {
    1: {"lookback": 20, "flat_threshold": 0.003, "features": ("return_1d", "return_5d", "log_return",
                                                              "volume_change", "volatility_20",
                                                              "close_to_ma20", "rsi14", "macd_histogram",
                                                              "gap_return", "amplitude", "twii_return_1d",
                                                              "sp500_prev_return", "sox_prev_return",
                                                              "vix_prev_change", "foreign_net_5d",
                                                              "news_sentiment_5d")},
    5: {"lookback": 60, "flat_threshold": 0.010, "features": ("return_5d", "return_20d", "volume_ratio_20",
                                                               "volatility_20", "volatility_60",
                                                               "close_to_ma20", "close_to_ma60", "rsi14",
                                                               "macd_histogram", "bollinger_position",
                                                               "twii_return_5d", "nasdaq_prev_return",
                                                               "tsm_prev_return", "twd_prev_change",
                                                               "institutional_net_5d", "margin_change_5d",
                                                               "revenue_yoy", "news_count_5d")},
    20: {"lookback": 250, "flat_threshold": 0.030, "features": ("return_20d", "return_60d", "volume_ratio_20",
                                                                 "volatility_60", "volatility_120",
                                                                 "close_to_ma60", "close_to_ma120",
                                                                 "distance_52w_high", "rsi14",
                                                                 "bollinger_position", "twii_return_20d",
                                                                 "sp500_prev_return_20d",
                                                                 "sox_prev_return_20d",
                                                                 "tnx_prev_change_20d", "short_change_5d",
                                                                 "gross_margin", "eps", "roe",
                                                                 "debt_ratio", "free_cash_flow",
                                                                 "event_risk_20d")},
}


@dataclass(frozen=True)
class HorizonForecast:
    horizon: int
    input_window: int
    probability_up: float
    probability_down: float
    probability_sideways: float
    expected_return: float
    return_lower: float
    return_upper: float
    expected_price: float
    price_lower: float
    price_upper: float
    volatility: float
    risk_level: str
    probability_break_resistance: float
    probability_break_support: float
    expected_return_above_cost: bool
    analogue_count: int


def forecast_from_price_history(
    path: Path,
    transaction_cost: float = 0.00585,
    as_of: str | pd.Timestamp | None = None,
) -> dict[str, object]:
    frame, stage_availability = _prepare_features(path, as_of)
    if len(frame) < 280:
        raise ValueError("有效歷史資料不足280個交易日，無法建立20日研究預測")
    latest = frame.iloc[-1]
    forecasts = [
        _forecast_horizon(frame, horizon, transaction_cost)
        for horizon in (1, 5, 20)
    ]
    history_years = (frame["trade_date"].max() - frame["trade_date"].min()).days / 365.25
    return {
        "data_date": latest["trade_date"],
        "latest_close": float(latest["close"]),
        "support_20": float(latest["support_20"]),
        "resistance_20": float(latest["resistance_20"]),
        "history_years": history_years,
        "formal_training_ready": history_years >= 5,
        "stage_availability": stage_availability,
        "forecasts": forecasts,
    }


def _prepare_features(
    path: Path, as_of: str | pd.Timestamp | None
) -> tuple[pd.DataFrame, dict[str, bool]]:
    if not path.exists():
        raise ValueError("找不到行情資料")
    frame = pd.read_csv(path)
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"行情缺少欄位：{', '.join(sorted(missing))}")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.tz_localize(None)
    cutoff = pd.Timestamp(as_of).tz_localize(None) if as_of is not None else pd.Timestamp.now().normalize()
    frame = frame[frame["trade_date"] <= cutoff].sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=list(required - {"trade_date"}) + ["trade_date"])
    frame = add_technical_indicators(frame)
    close, volume = frame["close"], frame["volume"]
    frame["return_1d"] = close.pct_change()
    for window in (5, 20, 60):
        frame[f"return_{window}d"] = close.pct_change(window)
    frame["log_return"] = np.log(close / close.shift(1))
    frame["volume_change"] = volume.pct_change().replace([np.inf, -np.inf], np.nan)
    frame["volume_ratio_20"] = volume / frame["volume_ma20"].replace(0, np.nan)
    for window in (20, 60, 120, 250):
        frame[f"volatility_{window}"] = frame["log_return"].rolling(window).std(ddof=0) * np.sqrt(252)
    frame["close_to_ma20"] = close / frame["ma20"] - 1
    frame["close_to_ma60"] = close / frame["ma60"] - 1
    frame["close_to_ma120"] = close / frame["ma120"] - 1
    frame["gap_return"] = frame["open"] / frame["close"].shift(1) - 1
    frame["amplitude"] = (frame["high"] - frame["low"]) / frame["close"].shift(1)
    band_width = (frame["bollinger_upper"] - frame["bollinger_lower"]).replace(0, np.nan)
    frame["bollinger_position"] = (close - frame["bollinger_lower"]) / band_width
    high_52w = frame["high"].rolling(250).max()
    frame["distance_52w_high"] = close / high_52w - 1
    frame["support_20"] = frame["low"].rolling(20).min()
    frame["resistance_20"] = frame["high"].rolling(20).max()
    frame = attach_external_market_features(frame, path.parents[1])
    stock_id = path.stem.replace("_TW", ".TW")
    frame, stage_availability = attach_point_in_time_features(
        frame, stock_id, path.parents[1].parent / "processed"
    )
    for horizon in (1, 5, 20):
        frame[f"future_return_{horizon}d"] = close.shift(-horizon) / close - 1
        frame[f"future_high_{horizon}d"] = (
            frame["high"].shift(-1).rolling(horizon).max().shift(-(horizon - 1))
        )
        frame[f"future_low_{horizon}d"] = (
            frame["low"].shift(-1).rolling(horizon).min().shift(-(horizon - 1))
        )
    return frame.replace([np.inf, -np.inf], np.nan), stage_availability


def attach_external_market_features(frame: pd.DataFrame, raw_root: Path) -> pd.DataFrame:
    """Attach TW close data and strictly previous-session US data point in time."""
    result = frame.sort_values("trade_date").copy()
    twii = _read_external_series(raw_root / "tw" / "INDEX_TWII.csv", "trade_date")
    if not twii.empty:
        twii["twii_return_1d"] = twii["close"].pct_change()
        twii["twii_return_5d"] = twii["close"].pct_change(5)
        twii["twii_return_20d"] = twii["close"].pct_change(20)
        result = result.merge(
            twii[["date", "twii_return_1d", "twii_return_5d", "twii_return_20d"]],
            left_on="trade_date", right_on="date", how="left",
        ).drop(columns="date")
    else:
        for column in ("twii_return_1d", "twii_return_5d", "twii_return_20d"):
            result[column] = 0.0

    external = {
        "sp500": raw_root / "us" / "INDEX_GSPC.csv",
        "nasdaq": raw_root / "us" / "INDEX_NDX.csv",
        "sox": raw_root / "us" / "INDEX_SOX.csv",
        "vix": raw_root / "us" / "INDEX_VIX.csv",
        "tsm": raw_root / "us" / "TSM.csv",
        "twd": raw_root / "us" / "TWD_X.csv",
        "tnx": raw_root / "us" / "INDEX_TNX.csv",
    }
    for prefix, series_path in external.items():
        series = _read_external_series(series_path, "us_trade_date")
        one_day = f"{prefix}_prev_{'change' if prefix in {'vix', 'twd', 'tnx'} else 'return'}"
        twenty_day = f"{one_day}_20d"
        if series.empty:
            result[one_day] = 0.0
            result[twenty_day] = 0.0
            continue
        series[one_day] = series["close"].pct_change()
        series[twenty_day] = series["close"].pct_change(20)
        result = pd.merge_asof(
            result.sort_values("trade_date"),
            series[["date", one_day, twenty_day]].sort_values("date"),
            left_on="trade_date",
            right_on="date",
            direction="backward",
            allow_exact_matches=False,
        ).drop(columns="date")
    market_columns = [
        column for column in result.columns
        if column.startswith(("twii_", "sp500_", "nasdaq_", "sox_", "vix_", "tsm_", "twd_", "tnx_"))
    ]
    result[market_columns] = result[market_columns].fillna(0.0)
    return result


def _read_external_series(path: Path, date_column: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["date", "close"])
    try:
        data = pd.read_csv(path, usecols=[date_column, "close"])
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame(columns=["date", "close"])
    data["date"] = pd.to_datetime(data[date_column], errors="coerce").dt.tz_localize(None)
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    return data.dropna().sort_values("date").drop_duplicates("date", keep="last")[["date", "close"]]


def _forecast_horizon(
    frame: pd.DataFrame, horizon: int, transaction_cost: float
) -> HorizonForecast:
    config = HORIZON_CONFIG[horizon]
    features = list(config["features"])
    target = f"future_return_{horizon}d"
    usable = frame.dropna(subset=features + [target]).copy()
    if len(usable) < 60:
        raise ValueError(f"{horizon}日模型有效樣本不足60筆")
    current = frame.iloc[-1]
    if current[features].isna().any():
        raise ValueError(f"{horizon}日模型最新特徵不完整")
    feature_matrix = usable[features].astype(float)
    current_values = pd.to_numeric(current[features], errors="coerce").astype(float)
    means = feature_matrix.mean()
    scales = feature_matrix.std(ddof=0).replace(0, 1)
    squared_distance = (((feature_matrix - current_values) / scales) ** 2).mean(axis=1).astype(float)
    distances = np.sqrt(squared_distance)
    neighbour_count = min(max(40, int(np.sqrt(len(usable)) * 5)), 120, len(usable))
    neighbours = usable.loc[distances.nsmallest(neighbour_count).index].copy()
    neighbour_distances = distances.loc[neighbours.index]
    weights = np.exp(-neighbour_distances.clip(upper=20))
    weights = weights / weights.sum()
    returns = neighbours[target]
    threshold = float(config["flat_threshold"])
    probability_up = float(weights[returns > threshold].sum())
    probability_down = float(weights[returns < -threshold].sum())
    probability_sideways = max(0.0, 1 - probability_up - probability_down)
    expected_return = float(np.average(returns, weights=weights))
    lower, upper = _weighted_quantile(returns.to_numpy(), weights.to_numpy(), (0.10, 0.90))
    latest_close = float(current["close"])
    realized_volatility = float(current[f"volatility_{config['lookback']}"])
    if not np.isfinite(realized_volatility):
        realized_volatility = float(frame["log_return"].tail(config["lookback"]).std(ddof=0) * np.sqrt(252))
    risk_level = "高" if realized_volatility >= 0.35 else "中" if realized_volatility >= 0.20 else "低"
    break_resistance = neighbours[f"future_high_{horizon}d"] > neighbours["resistance_20"]
    break_support = neighbours[f"future_low_{horizon}d"] < neighbours["support_20"]
    return HorizonForecast(
        horizon=horizon,
        input_window=int(config["lookback"]),
        probability_up=probability_up,
        probability_down=probability_down,
        probability_sideways=probability_sideways,
        expected_return=expected_return,
        return_lower=float(lower),
        return_upper=float(upper),
        expected_price=latest_close * (1 + expected_return),
        price_lower=max(0.0, latest_close * (1 + float(lower))),
        price_upper=max(0.0, latest_close * (1 + float(upper))),
        volatility=realized_volatility,
        risk_level=risk_level,
        probability_break_resistance=float(weights[break_resistance.fillna(False)].sum()),
        probability_break_support=float(weights[break_support.fillna(False)].sum()),
        expected_return_above_cost=expected_return > transaction_cost,
        analogue_count=neighbour_count,
    )


def _weighted_quantile(
    values: np.ndarray, weights: np.ndarray, quantiles: tuple[float, float]
) -> tuple[float, float]:
    order = np.argsort(values)
    sorted_values, sorted_weights = values[order], weights[order]
    cumulative = np.cumsum(sorted_weights)
    cumulative = cumulative / cumulative[-1]
    return tuple(float(np.interp(quantile, cumulative, sorted_values)) for quantile in quantiles)
