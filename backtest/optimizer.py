"""Bounded parameter search with chronological training/validation splits."""

from __future__ import annotations

import itertools

import pandas as pd

from backtest.backtester import BacktestConfig, run_backtest

OBJECTIVES = {
    "年化報酬率最高": ("annualized_return", False),
    "Sharpe Ratio最高": ("sharpe_ratio", False),
    "Sortino Ratio最高": ("sortino_ratio", False),
    "最大回撤最低": ("max_drawdown", False),
    "Calmar Ratio最高": ("calmar_ratio", False),
    "Profit Factor最高": ("profit_factor", False),
}


def optimize_ma(
    frame: pd.DataFrame,
    config: BacktestConfig,
    short_values: list[int],
    long_values: list[int],
    objective: str,
    max_combinations: int = 100,
) -> pd.DataFrame:
    combinations = [(short, long) for short, long in itertools.product(short_values, long_values) if short < long]
    if len(combinations) > max_combinations:
        raise ValueError(f"參數組合共{len(combinations)}組，超過上限{max_combinations}組，請縮小範圍")
    rows = []
    for short, long in combinations:
        result = run_backtest(frame, "均線交叉", {"short_ma": short, "long_ma": long}, config)
        rows.append({"短期均線": short, "長期均線": long, **result.metrics})
    result_frame = pd.DataFrame(rows)
    key, ascending = OBJECTIVES.get(objective, ("sharpe_ratio", False))
    if not result_frame.empty:
        result_frame = result_frame.sort_values(key, ascending=ascending).reset_index(drop=True)
        result_frame.insert(0, "排名", result_frame.index + 1)
    return result_frame


def training_validation_analysis(
    frame: pd.DataFrame,
    strategy: str,
    parameters: dict,
    config: BacktestConfig,
    training_ratio: float = 0.7,
) -> dict[str, object]:
    split = max(2, min(len(frame) - 2, int(len(frame) * training_ratio)))
    training = run_backtest(frame.iloc[:split].copy(), strategy, parameters, config)
    validation = run_backtest(frame.iloc[split:].copy(), strategy, parameters, config)
    deterioration = validation.metrics["sharpe_ratio"] < training.metrics["sharpe_ratio"] * 0.5
    return {"training": training.metrics, "validation": validation.metrics, "split_date": frame.iloc[split]["trade_date"], "overfit_risk": deterioration}


def walk_forward_analysis(
    frame: pd.DataFrame,
    strategy: str,
    parameters: dict,
    config: BacktestConfig,
    folds: int = 3,
) -> pd.DataFrame:
    fold_size = len(frame) // (folds + 1)
    rows = []
    for fold in range(folds):
        start, end = fold_size * (fold + 1), fold_size * (fold + 2)
        validation = frame.iloc[start:end].copy()
        if len(validation) < 2:
            continue
        result = run_backtest(validation, strategy, parameters, config)
        rows.append({
            "折次": fold + 1, "驗證起日": validation["trade_date"].min(),
            "驗證迄日": validation["trade_date"].max(),
            "總報酬率": result.metrics["total_return"],
            "Sharpe Ratio": result.metrics["sharpe_ratio"],
            "最大回撤": result.metrics["max_drawdown"],
        })
    return pd.DataFrame(rows)
