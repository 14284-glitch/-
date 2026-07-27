"""Numerically safe performance calculations."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def calculate_metrics(equity: pd.DataFrame, trades: pd.DataFrame, initial_capital: float, risk_free_rate: float = 0.0) -> dict[str, float]:
    values = pd.to_numeric(equity["total_equity"], errors="coerce").dropna()
    returns = values.pct_change().dropna()
    final = float(values.iloc[-1]) if not values.empty else float(initial_capital)
    total_return = final / initial_capital - 1 if initial_capital > 0 else 0.0
    days = max(1, (pd.to_datetime(equity["date"]).max() - pd.to_datetime(equity["date"]).min()).days)
    cagr = (final / initial_capital) ** (365 / days) - 1 if initial_capital > 0 and final > 0 else 0.0
    drawdown = values / values.cummax() - 1 if not values.empty else pd.Series(dtype=float)
    volatility = float(returns.std(ddof=0) * np.sqrt(252)) if len(returns) > 1 else 0.0
    excess = returns - risk_free_rate / 252
    sharpe = float(excess.mean() / excess.std(ddof=0) * np.sqrt(252)) if len(excess) > 1 and excess.std(ddof=0) > 0 else 0.0
    downside = returns[returns < 0]
    downside_dev = float(downside.std(ddof=0) * np.sqrt(252)) if len(downside) > 1 else 0.0
    sortino = float((returns.mean() * 252 - risk_free_rate) / downside_dev) if downside_dev > 0 else 0.0
    completed = trades[trades["side"] == "賣出"] if not trades.empty else pd.DataFrame()
    profits = pd.to_numeric(completed.get("realized_profit", pd.Series(dtype=float)), errors="coerce").fillna(0)
    wins, losses = profits[profits > 0], profits[profits < 0]
    profit_factor = float(wins.sum() / abs(losses.sum())) if not losses.empty else (float(wins.sum()) if not wins.empty else 0.0)
    win_rate = float((profits > 0).mean()) if len(profits) else 0.0
    max_dd = float(drawdown.min()) if not drawdown.empty else 0.0
    result = {
        "initial_capital": initial_capital, "final_equity": final, "total_profit": final - initial_capital,
        "total_return": total_return, "annualized_return": cagr, "max_drawdown": max_dd,
        "annualized_volatility": volatility, "sharpe_ratio": sharpe, "sortino_ratio": sortino,
        "calmar_ratio": cagr / abs(max_dd) if max_dd < 0 else 0.0,
        "completed_trades": float(len(completed)), "win_rate": win_rate, "profit_factor": profit_factor,
        "average_trade_return": float(pd.to_numeric(completed.get("return_percent", pd.Series(dtype=float)), errors="coerce").mean()) if len(completed) else 0.0,
        "total_transaction_costs": float(pd.to_numeric(trades.get("total_cost", pd.Series(dtype=float)), errors="coerce").sum()) if not trades.empty else 0.0,
    }
    return {key: (value if math.isfinite(float(value)) else 0.0) for key, value in result.items()}


def monthly_returns(equity: pd.DataFrame) -> pd.DataFrame:
    series = equity.set_index(pd.to_datetime(equity["date"]))["total_equity"].resample("ME").last().pct_change()
    return pd.DataFrame({"月份": series.index.strftime("%Y-%m"), "報酬率": series.fillna(0).values})
