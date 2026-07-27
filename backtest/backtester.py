"""Long-only Taiwan stock backtest engine using next-session execution."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from backtest.performance import calculate_metrics
from backtest.strategy import generate_signals


@dataclass(frozen=True)
class BacktestConfig:
    symbol: str
    initial_capital: float = 1_000_000
    commission_rate: float = 0.001425
    minimum_commission: float = 20
    transaction_tax_rate: float = 0.003
    slippage_rate: float = 0.001
    position_fraction: float = 1.0
    allow_odd_lots: bool = False
    stop_loss: float = 0.08
    take_profit: float = 0.20
    risk_free_rate: float = 0.01
    include_dividends: bool = False
    reinvest_dividends: bool = False


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.DataFrame
    trades: pd.DataFrame
    signals: pd.DataFrame
    metrics: dict[str, float]
    warmup_periods: int


def transaction_cost(amount: float, rate: float, minimum: float = 0.0) -> float:
    return max(minimum, amount * max(0.0, rate)) if amount > 0 else 0.0


def position_size(cash: float, price: float, config: BacktestConfig) -> int:
    if cash <= 0 or price <= 0:
        return 0
    budget = cash * min(1.0, max(0.0, config.position_fraction))
    unit_cost = price * (1 + config.slippage_rate + config.commission_rate)
    shares = math.floor(budget / unit_cost)
    return shares if config.allow_odd_lots else shares // 1000 * 1000


def run_backtest(
    frame: pd.DataFrame,
    strategy: str,
    parameters: dict[str, Any],
    config: BacktestConfig,
    dividends: pd.DataFrame | None = None,
) -> BacktestResult:
    if config.initial_capital <= 0:
        raise ValueError("初始本金必須大於0")
    if min(config.commission_rate, config.transaction_tax_rate, config.slippage_rate) < 0:
        raise ValueError("交易成本不可為負數")
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    if required - set(frame.columns):
        raise ValueError("歷史行情缺少必要欄位")
    data = generate_signals(frame, strategy, parameters)
    cash, shares, entry_price, entry_date, entry_cost = config.initial_capital, 0, 0.0, None, 0.0
    pending: tuple[str, str, pd.Timestamp] | None = None
    dividend_by_date = _dividend_schedule(dividends)
    dividend_pool, total_dividends, pending_reinvest = 0.0, 0.0, False
    trades, equity_rows = [], []
    trade_id = 0
    for i, row in data.iterrows():
        date = pd.Timestamp(row["trade_date"])
        open_price, close = float(row["open"]), float(row["close"])
        if pending_reinvest and shares > 0 and dividend_pool > 0:
            execution = open_price * (1 + config.slippage_rate)
            unit_cost = execution * (1 + config.commission_rate)
            added = math.floor(dividend_pool / unit_cost)
            if not config.allow_odd_lots:
                added = added // 1000 * 1000
            if added > 0:
                gross = execution * added
                commission = transaction_cost(gross, config.commission_rate, config.minimum_commission)
                if gross + commission <= cash:
                    cash -= gross + commission
                    shares += added
                    dividend_pool = max(0.0, dividend_pool - gross - commission)
            pending_reinvest = False
        if pending:
            side, reason, signal_date = pending
            pending = None
            if side == "買進" and shares == 0:
                execution_price = open_price * (1 + config.slippage_rate)
                qty = position_size(cash, open_price, config)
                gross = execution_price * qty
                commission = transaction_cost(gross, config.commission_rate, config.minimum_commission)
                if qty > 0 and gross + commission <= cash:
                    cash -= gross + commission
                    shares, entry_price, entry_date, entry_cost = qty, execution_price, date, commission
                    trade_id += 1
                    slip = open_price * config.slippage_rate * qty
                    trades.append(_trade_row(
                        trade_id, config.symbol, signal_date, date, side, execution_price, qty, gross,
                        commission, 0, slip, commission + slip,
                        reason, cash, shares, cash + shares * close,
                    ))
            elif side == "賣出" and shares > 0:
                cash, shares, trade_id = _sell(
                    trades, trade_id, config, signal_date, date, open_price, close, shares,
                    cash, entry_price, entry_date, entry_cost, reason,
                )
        if shares > 0:
            change = close / entry_price - 1
            if config.stop_loss > 0 and change <= -config.stop_loss:
                pending = ("賣出", "停損", date)
            elif config.take_profit > 0 and change >= config.take_profit:
                pending = ("賣出", "停利", date)
            elif bool(row["exit_signal"]):
                pending = ("賣出", "策略出場", date)
        elif bool(row["entry_signal"]):
            pending = ("買進", "策略進場", date)
        dividend_income = 0.0
        if config.include_dividends and shares > 0:
            dividend_income = shares * dividend_by_date.get(date.normalize(), 0.0)
            if dividend_income > 0:
                cash += dividend_income
                total_dividends += dividend_income
                dividend_pool += dividend_income
                pending_reinvest = config.reinvest_dividends
        total = cash + shares * close
        equity_rows.append({
            "date": date, "cash": cash, "position_value": shares * close,
            "total_equity": total, "dividend_income": dividend_income,
        })
    if shares > 0:
        last = data.iloc[-1]
        date, price = pd.Timestamp(last["trade_date"]), float(last["close"])
        cash, shares, trade_id = _sell(
            trades, trade_id, config, date, date, price, price, shares, cash,
            entry_price, entry_date, entry_cost, "回測結束平倉",
        )
        equity_rows[-1].update({"cash": cash, "position_value": 0.0, "total_equity": cash})
    equity, trades_frame = pd.DataFrame(equity_rows), pd.DataFrame(trades)
    if not equity.empty:
        equity["drawdown"] = equity["total_equity"] / equity["total_equity"].cummax() - 1
    metrics = calculate_metrics(equity, trades_frame, config.initial_capital, config.risk_free_rate)
    metrics["total_dividends"] = total_dividends
    return BacktestResult(equity, trades_frame, data, metrics, int(data.attrs.get("warmup_periods", 0)))


def _dividend_schedule(dividends: pd.DataFrame | None) -> dict[pd.Timestamp, float]:
    if dividends is None or dividends.empty:
        return {}
    date_column = "cash_payment_date" if "cash_payment_date" in dividends else "cash_ex_dividend_date"
    if date_column not in dividends or "cash_dividend" not in dividends:
        return {}
    result: dict[pd.Timestamp, float] = {}
    for _, row in dividends.iterrows():
        date = pd.to_datetime(row[date_column], errors="coerce")
        value = pd.to_numeric(row["cash_dividend"], errors="coerce")
        if pd.notna(date) and pd.notna(value) and float(value) > 0:
            normalized = pd.Timestamp(date).normalize()
            result[normalized] = result.get(normalized, 0.0) + float(value)
    return result


def _sell(trades, trade_id, config, signal_date, date, market_price, close, shares, cash, entry_price, entry_date, entry_cost, reason):
    execution = market_price * (1 - config.slippage_rate)
    gross = execution * shares
    commission = transaction_cost(gross, config.commission_rate, config.minimum_commission)
    tax = gross * config.transaction_tax_rate
    slip = market_price * config.slippage_rate * shares
    cash += gross - commission - tax
    profit = (execution - entry_price) * shares - commission - tax - entry_cost
    trade_id += 1
    trades.append(_trade_row(
        trade_id, config.symbol, signal_date, date, "賣出", execution, shares, gross,
        commission, tax, slip, commission + tax + slip, reason, cash, 0, cash,
        entry_date, profit, profit / (entry_price * shares) if entry_price * shares else 0,
    ))
    return cash, 0, trade_id


def _trade_row(trade_id, symbol, signal_date, date, side, price, shares, gross, commission, tax, slippage, total_cost, reason, cash, position, equity, entry_date=None, profit=0.0, return_percent=0.0):
    return {
        "id": trade_id, "signal_date": signal_date, "execution_date": date, "symbol": symbol, "side": side, "price": price,
        "shares": shares, "gross_amount": gross, "commission": commission, "tax": tax,
        "slippage": slippage, "total_cost": total_cost, "reason": reason,
        "holding_periods": (date - entry_date).days if entry_date is not None else 0,
        "realized_profit": profit, "return_percent": return_percent,
        "cash_after": cash, "position_after": position, "equity_after": equity,
    }
