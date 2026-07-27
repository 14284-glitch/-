
import numpy as np
import pandas as pd
import pytest

from backtest.backtester import (
    BacktestConfig,
    position_size,
    run_backtest,
    transaction_cost,
)
from backtest.performance import calculate_metrics
from backtest.strategy import generate_signals


def market_frame(rows=160, pattern="trend"):
    index = np.arange(rows)
    if pattern == "wave":
        close = 100 + np.sin(index / 5) * 12 + index * 0.02
    else:
        close = 100 + index * 0.5
    return pd.DataFrame({
        "trade_date": pd.bdate_range("2025-01-01", periods=rows),
        "open": close * 1.001, "high": close * 1.02, "low": close * 0.98,
        "close": close, "volume": 1_000_000 + index * 100,
    })


def test_ma_cross_and_death_cross_are_point_in_time():
    data = market_frame(pattern="wave")
    result = generate_signals(data, "均線交叉", {"short_ma": 5, "long_ma": 20})
    assert result["entry_signal"].any()
    assert result["exit_signal"].any()
    first = result.index[result["entry_signal"]][0]
    assert first >= 20


def test_rsi_and_macd_generate_real_signals():
    data = market_frame(pattern="wave")
    rsi = generate_signals(data, "RSI反轉", {"rsi_period": 14, "oversold": 40, "overbought": 60})
    macd = generate_signals(data, "MACD交叉", {"macd_fast": 5, "macd_slow": 15, "macd_signal": 5})
    assert rsi["entry_signal"].any() and rsi["exit_signal"].any()
    assert macd["entry_signal"].any() and macd["exit_signal"].any()


def test_signal_executes_at_next_session_open():
    data = market_frame(40)
    config = BacktestConfig("2330.TW", allow_odd_lots=True, slippage_rate=0)
    result = run_backtest(data, "買進持有", {}, config)
    buy = result.trades.iloc[0]
    assert buy["execution_date"] == data.iloc[1]["trade_date"]
    assert buy["price"] == pytest.approx(data.iloc[1]["open"])


def test_whole_lot_and_odd_lot_position_sizing():
    whole = BacktestConfig("2330.TW", initial_capital=100_000, allow_odd_lots=False, commission_rate=0, slippage_rate=0)
    odd = BacktestConfig("2330.TW", initial_capital=100_000, allow_odd_lots=True, commission_rate=0, slippage_rate=0)
    assert position_size(100_000, 60, whole) == 1000
    assert position_size(100_000, 60, odd) == 1666


def test_transaction_cost_minimum_and_rate():
    assert transaction_cost(1000, 0.001425, 20) == 20
    assert transaction_cost(100_000, 0.001425, 20) == pytest.approx(142.5)


def test_costs_tax_slippage_and_cash_never_negative():
    data = market_frame(80)
    config = BacktestConfig("2330.TW", commission_rate=0.001425, transaction_tax_rate=0.003, slippage_rate=0.001, allow_odd_lots=True)
    result = run_backtest(data, "買進持有", {}, config)
    assert result.trades["commission"].sum() > 0
    assert result.trades.loc[result.trades["side"] == "賣出", "tax"].sum() > 0
    assert result.trades["total_cost"].sum() > result.trades["commission"].sum()
    assert result.equity["cash"].min() >= 0


def test_stop_loss_and_take_profit_priority_generate_exit():
    falling = market_frame(50)
    falling.loc[2:, ["open", "high", "low", "close"]] *= 0.7
    loss = run_backtest(falling, "買進持有", {}, BacktestConfig("x", allow_odd_lots=True, stop_loss=0.08, take_profit=0))
    assert "停損" in set(loss.trades["reason"])
    rising = market_frame(50)
    profit = run_backtest(rising, "買進持有", {}, BacktestConfig("x", allow_odd_lots=True, stop_loss=0, take_profit=0.05))
    assert "停利" in set(profit.trades["reason"])


def test_metrics_cover_return_drawdown_winrate_profit_factor_and_zero_cases():
    equity = pd.DataFrame({"date": pd.date_range("2025-01-01", periods=4), "total_equity": [100, 120, 90, 130]})
    trades = pd.DataFrame({"side": ["賣出", "賣出"], "realized_profit": [20, -10], "return_percent": [.2, -.1], "total_cost": [1, 1]})
    metrics = calculate_metrics(equity, trades, 100)
    assert metrics["total_return"] == pytest.approx(.3)
    assert metrics["max_drawdown"] == pytest.approx(-.25)
    assert metrics["win_rate"] == pytest.approx(.5)
    assert metrics["profit_factor"] == pytest.approx(2)
    empty = calculate_metrics(pd.DataFrame({"date": pd.date_range("2025-01-01", periods=2), "total_equity": [100, 100]}), pd.DataFrame(), 100)
    assert all(np.isfinite(value) for value in empty.values())


def test_invalid_parameters_are_rejected_in_traditional_chinese():
    with pytest.raises(ValueError, match="短期均線"):
        generate_signals(market_frame(), "均線交叉", {"short_ma": 20, "long_ma": 5})
    with pytest.raises(ValueError, match="初始本金"):
        run_backtest(market_frame(), "買進持有", {}, BacktestConfig("x", initial_capital=0))
