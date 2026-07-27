
import numpy as np
import pandas as pd
import pytest

from backtest.backtester import (
    BacktestConfig,
    position_size,
    run_backtest,
    transaction_cost,
)
from backtest.optimizer import (
    optimize_ma,
    training_validation_analysis,
    walk_forward_analysis,
)
from backtest.performance import calculate_metrics
from backtest.storage import delete_strategy, load_strategies, save_strategy
from backtest.strategy import evaluate_condition, generate_signals


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


@pytest.mark.parametrize(
    ("strategy", "parameters"),
    [
        ("KD交叉", {"kd_period": 9, "kd_low": 40, "kd_high": 60}),
        ("布林均值回歸", {"bollinger_period": 20, "bollinger_std": 1.5}),
        ("布林突破", {"bollinger_period": 20, "bollinger_std": 1.0, "volume_multiple": 1.0}),
        ("成交量突破", {"breakout_high": 10, "breakout_low": 5, "volume_period": 10, "volume_multiple": 1.0}),
    ],
)
def test_second_stage_strategies_produce_boolean_signals(strategy, parameters):
    result = generate_signals(market_frame(pattern="wave"), strategy, parameters)
    assert result["entry_signal"].dtype == bool
    assert result["exit_signal"].dtype == bool
    assert len(result) == 160


def test_custom_condition_and_or_and_cross_operators():
    left = pd.Series([1, 2, 4, 2])
    assert evaluate_condition(left, "向上突破", 3).tolist() == [False, False, True, False]
    data = market_frame(pattern="wave")
    parameters = {
        "entry_conditions": [
            {"left": "RSI", "operator": "小於", "value": 55},
            {"left": "成交量倍數", "operator": "大於", "value": 0.9},
        ],
        "exit_conditions": [{"left": "RSI", "operator": "大於", "value": 60}],
        "entry_connector": "AND", "exit_connector": "OR",
    }
    result = generate_signals(data, "自訂條件", parameters)
    assert result["entry_signal"].any()


def test_ai_strategy_refuses_latest_only_prediction_data():
    with pytest.raises(ValueError, match="缺少歷史AI預測訊號"):
        generate_signals(market_frame(), "AI歷史訊號", {})


def test_cash_dividend_and_reinvestment_use_real_event_date():
    data = market_frame(50)
    payment_date = data.iloc[10]["trade_date"]
    dividends = pd.DataFrame({"cash_payment_date": [payment_date], "cash_dividend": [2.0]})
    config = BacktestConfig("x", allow_odd_lots=True, include_dividends=True)
    result = run_backtest(data, "買進持有", {}, config, dividends)
    assert result.metrics["total_dividends"] > 0
    assert result.equity.loc[result.equity["date"] == payment_date, "dividend_income"].iloc[0] > 0
    reinvest = run_backtest(data, "買進持有", {}, BacktestConfig("x", allow_odd_lots=True, include_dividends=True, reinvest_dividends=True), dividends)
    assert reinvest.metrics["total_dividends"] > 0


def test_optimizer_limits_combinations_and_returns_ranked_results():
    data = market_frame(pattern="wave")
    config = BacktestConfig("x", allow_odd_lots=True)
    optimized = optimize_ma(data, config, [5, 10], [20, 30], "Sharpe Ratio最高")
    assert len(optimized) == 4
    assert optimized.iloc[0]["排名"] == 1
    with pytest.raises(ValueError, match="超過上限"):
        optimize_ma(data, config, list(range(2, 30)), list(range(31, 80)), "Sharpe Ratio最高", max_combinations=10)


def test_training_validation_walk_forward_and_storage(tmp_path):
    data = market_frame(240, pattern="wave")
    config = BacktestConfig("x", allow_odd_lots=True)
    analysis = training_validation_analysis(data, "均線交叉", {"short_ma": 5, "long_ma": 20}, config)
    assert {"training", "validation", "overfit_risk"} <= analysis.keys()
    walk = walk_forward_analysis(data, "均線交叉", {"short_ma": 5, "long_ma": 20}, config)
    assert len(walk) == 3
    path = tmp_path / "strategies.json"
    save_strategy(path, {"name": "測試策略", "strategy": "均線交叉"})
    assert load_strategies(path)[0]["name"] == "測試策略"
    assert delete_strategy(path, "測試策略") == []
