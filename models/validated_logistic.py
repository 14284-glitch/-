"""Leakage-aware, separately trained 1/5/20-day Logistic baseline models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, balanced_accuracy_score, log_loss, mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit

from features.technical_indicators import add_technical_indicators


MODEL_VERSION = "logistic-pit-v1"
FEATURE_VERSION = "technical-pit-v1"
HORIZONS = (1, 5, 20)
FLAT_THRESHOLDS = {1: 0.003, 5: 0.01, 20: 0.03}
MAX_RETURN_MAE = {1: 0.04, 5: 0.08, 20: 0.15}
FEATURES = (
    "return_1d", "return_3d", "return_5d", "return_10d", "return_20d",
    "log_return", "volume_change", "volume_ratio_20", "volatility_20",
    "close_to_ma5", "close_to_ma20", "ma5_to_ma20", "rsi14",
    "kd_k", "kd_d", "macd", "macd_signal", "macd_histogram",
    "bollinger_position", "gap_return", "amplitude",
)


@dataclass(frozen=True)
class ValidatedForecast:
    symbol: str
    horizon: int
    data_date: str
    latest_close: float
    target_date: str
    probability_up: float
    probability_down: float
    probability_sideways: float
    expected_return: float
    expected_price: float
    return_lower: float
    return_upper: float
    accuracy: float
    balanced_accuracy: float
    log_loss: float
    return_mae: float
    test_samples: int
    baseline_accuracy: float
    production_ready: bool
    walk_forward_accuracy: float
    walk_forward_balanced_accuracy: float
    training_start: str
    training_end: str
    model_version: str = MODEL_VERSION
    feature_version: str = FEATURE_VERSION


def build_model_frame(path: Path, as_of: object | None = None) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame):
        raise ValueError(f"行情欄位不足：{', '.join(sorted(required - set(frame)))}")
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], format="mixed", errors="coerce"
    ).dt.tz_localize(None)
    cutoff = pd.Timestamp(as_of).tz_localize(None) if as_of is not None else pd.Timestamp.now().normalize()
    frame = frame[frame["trade_date"] <= cutoff].sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    for column in ("open", "high", "low", "close", "adjusted_close", "volume"):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["trade_date", "open", "high", "low", "close", "volume"])
    frame = add_technical_indicators(frame)
    close = frame["close"]
    target_price = frame.get("adjusted_close", close).fillna(close)
    volume = frame["volume"]
    for window in (1, 3, 5, 10, 20):
        frame[f"return_{window}d"] = target_price.pct_change(window)
    frame["log_return"] = np.log(target_price / target_price.shift(1))
    frame["volume_change"] = volume.pct_change()
    frame["volume_ratio_20"] = volume / frame["volume_ma20"].replace(0, np.nan)
    frame["volatility_20"] = frame["log_return"].rolling(20).std(ddof=0) * np.sqrt(252)
    frame["close_to_ma5"] = close / frame["ma5"] - 1
    frame["close_to_ma20"] = close / frame["ma20"] - 1
    frame["ma5_to_ma20"] = frame["ma5"] / frame["ma20"] - 1
    width = (frame["bollinger_upper"] - frame["bollinger_lower"]).replace(0, np.nan)
    frame["bollinger_position"] = (close - frame["bollinger_lower"]) / width
    frame["gap_return"] = frame["open"] / close.shift(1) - 1
    frame["amplitude"] = (frame["high"] - frame["low"]) / close.shift(1)
    for horizon in HORIZONS:
        future = target_price.shift(-horizon) / target_price - 1
        threshold = FLAT_THRESHOLDS[horizon]
        frame[f"future_return_{horizon}d"] = future
        frame[f"direction_{horizon}d"] = np.select(
            [future > threshold, future < -threshold], [1, -1], default=0
        ).astype(float)
        frame.loc[future.isna(), f"direction_{horizon}d"] = np.nan
    return frame.replace([np.inf, -np.inf], np.nan)


def train_validated_forecasts(path: Path, as_of: object | None = None) -> list[ValidatedForecast]:
    frame = build_model_frame(path, as_of)
    symbol = path.stem.replace("_TW", ".TW")
    results = [_fit_horizon(frame, symbol, horizon) for horizon in HORIZONS]
    return results


def _classifier() -> Pipeline:
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced", C=0.35)),
    ])


def _regressor() -> TransformedTargetRegressor:
    pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", Ridge(alpha=8.0)),
    ])
    return TransformedTargetRegressor(regressor=pipeline, transformer=StandardScaler())


def _fit_horizon(frame: pd.DataFrame, symbol: str, horizon: int) -> ValidatedForecast:
    target_return = f"future_return_{horizon}d"
    target_direction = f"direction_{horizon}d"
    usable = frame.dropna(subset=[*FEATURES, target_return, target_direction]).copy()
    if len(usable) < 750:
        raise ValueError(f"{horizon}日模型有效樣本不足750筆")
    # Use at most the latest five years, while preserving chronological order.
    usable = usable.tail(1260)
    holdout = max(126, int(len(usable) * 0.20))
    split = len(usable) - holdout
    train_end = max(1, split - horizon)  # purge overlapping forward labels
    train, test = usable.iloc[:train_end], usable.iloc[split:]
    x_train, x_test = train[list(FEATURES)], test[list(FEATURES)]
    y_train = train[target_direction].astype(int)
    y_test = test[target_direction].astype(int)
    if y_train.nunique() < 3:
        raise ValueError(f"{horizon}日模型訓練資料缺少完整漲跌盤整類別")
    calibration_size = max(126, int(len(train) * 0.15))
    core_end = len(train) - calibration_size - horizon
    core_x, core_y = x_train.iloc[:core_end], y_train.iloc[:core_end]
    calibration_x, calibration_y = x_train.iloc[-calibration_size:], y_train.iloc[-calibration_size:]
    classifier = _classifier().fit(core_x, core_y)
    calibrator = LogisticRegression(max_iter=1000, C=0.5).fit(
        _log_probabilities(classifier.predict_proba(calibration_x)), calibration_y
    )
    probabilities = calibrator.predict_proba(
        _log_probabilities(classifier.predict_proba(x_test))
    )
    predictions = calibrator.classes_[np.argmax(probabilities, axis=1)]
    labels = [-1, 0, 1]
    probability_frame = pd.DataFrame(probabilities, columns=calibrator.classes_).reindex(columns=labels, fill_value=0.0)
    classification_loss = float(log_loss(y_test, probability_frame, labels=labels))
    baseline_accuracy = float(y_test.value_counts(normalize=True).max())
    tested_accuracy = float(accuracy_score(y_test, predictions))
    tested_balanced_accuracy = float(balanced_accuracy_score(y_test, predictions))

    regressor = _regressor().fit(x_train, train[target_return].astype(float))
    predicted_returns = regressor.predict(x_test)
    residuals = test[target_return].to_numpy() - predicted_returns
    lower_residual, upper_residual = np.quantile(residuals, [0.10, 0.90])
    wf_accuracy, wf_balanced = _walk_forward_metrics(usable, horizon)
    return_mae = float(mean_absolute_error(test[target_return], predicted_returns))

    # Refit on all mature labels only after the untouched holdout metrics are fixed.
    classifier.fit(usable[list(FEATURES)], usable[target_direction].astype(int))
    regressor.fit(usable[list(FEATURES)], usable[target_return].astype(float))
    latest = frame.iloc[-1]
    latest_x = latest[list(FEATURES)].to_frame().T
    calibrated_latest = calibrator.predict_proba(
        _log_probabilities(classifier.predict_proba(latest_x))
    )[0]
    latest_probabilities = dict(zip(calibrator.classes_, calibrated_latest))
    raw_expected_return = float(regressor.predict(latest_x)[0])
    target_floor, target_ceiling = usable[target_return].quantile([0.05, 0.95])
    expected_return = float(np.clip(raw_expected_return, target_floor, target_ceiling))
    return ValidatedForecast(
        symbol=symbol, horizon=horizon,
        data_date=pd.Timestamp(latest["trade_date"]).strftime("%Y-%m-%d"),
        latest_close=float(latest["close"]),
        target_date=_target_session(latest["trade_date"], horizon),
        probability_up=float(latest_probabilities.get(1, 0.0)),
        probability_down=float(latest_probabilities.get(-1, 0.0)),
        probability_sideways=float(latest_probabilities.get(0, 0.0)),
        expected_return=expected_return,
        expected_price=max(0.0, float(latest["close"]) * (1 + expected_return)),
        return_lower=float(expected_return + lower_residual),
        return_upper=float(expected_return + upper_residual),
        accuracy=tested_accuracy,
        balanced_accuracy=tested_balanced_accuracy,
        log_loss=classification_loss,
        return_mae=return_mae,
        test_samples=len(test),
        baseline_accuracy=baseline_accuracy,
        production_ready=bool(
            tested_accuracy >= baseline_accuracy
            and tested_balanced_accuracy >= 0.36
            and wf_balanced >= 0.35
            and return_mae <= MAX_RETURN_MAE[horizon]
            and len(test) >= 126
        ),
        walk_forward_accuracy=wf_accuracy,
        walk_forward_balanced_accuracy=wf_balanced,
        training_start=pd.Timestamp(usable.iloc[0]["trade_date"]).strftime("%Y-%m-%d"),
        training_end=pd.Timestamp(usable.iloc[-1]["trade_date"]).strftime("%Y-%m-%d"),
    )


def _target_session(value: object, horizon: int) -> str:
    import exchange_calendars as xcals
    calendar = xcals.get_calendar("XTAI")
    session = calendar.date_to_session(pd.Timestamp(value).normalize(), direction="previous")
    for _ in range(horizon):
        session = calendar.next_session(session)
    return pd.Timestamp(session).strftime("%Y-%m-%d")


def _log_probabilities(probabilities: np.ndarray) -> np.ndarray:
    values = np.clip(probabilities, 1e-6, 1 - 1e-6)
    return np.log(values)


def _walk_forward_metrics(frame: pd.DataFrame, horizon: int) -> tuple[float, float]:
    splitter = TimeSeriesSplit(n_splits=3, gap=horizon)
    accuracies, balanced = [], []
    x = frame[list(FEATURES)]
    y = frame[f"direction_{horizon}d"].astype(int)
    for train_index, test_index in splitter.split(x):
        train_y = y.iloc[train_index]
        if train_y.nunique() < 3:
            continue
        model = _classifier().fit(x.iloc[train_index], train_y)
        predicted = model.predict(x.iloc[test_index])
        actual = y.iloc[test_index]
        accuracies.append(accuracy_score(actual, predicted))
        balanced.append(balanced_accuracy_score(actual, predicted))
    if not accuracies:
        return 0.0, 0.0
    return float(np.mean(accuracies)), float(np.mean(balanced))


def forecasts_as_records(forecasts: list[ValidatedForecast]) -> list[dict[str, object]]:
    return [asdict(item) for item in forecasts]
