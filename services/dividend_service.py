"""Dividend history, calculator, and reinvestment services."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math

import pandas as pd

from config.dividend_config import (
    NHI_DIVIDEND_PAYMENT_CAP,
    NHI_DIVIDEND_PAYMENT_THRESHOLD,
    NHI_SUPPLEMENTARY_PREMIUM_RATE,
    SHARES_PER_LOT,
)


def safe_number(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


@dataclass(frozen=True)
class DividendCalculation:
    shares: float
    lots: float
    cash_dividend_per_share: float
    gross_cash_dividend: float
    estimated_income_tax: float
    estimated_nhi_premium: float
    estimated_net_dividend: float
    stock_dividend_new_shares: float
    yield_on_cost: float
    current_yield: float
    quarterly_average: float
    monthly_average: float


def calculate_dividend(
    shares: object,
    cash_dividend_per_share: object,
    stock_dividend_rate: object,
    cost_per_share: object,
    current_price: object,
    income_tax_rate: object,
    include_nhi: bool,
) -> DividendCalculation:
    shares_value = max(0.0, safe_number(shares))
    cash_per_share = max(0.0, safe_number(cash_dividend_per_share))
    stock_rate = max(0.0, safe_number(stock_dividend_rate))
    cost = max(0.0, safe_number(cost_per_share))
    price = max(0.0, safe_number(current_price))
    tax_rate = min(1.0, max(0.0, safe_number(income_tax_rate)))
    gross = shares_value * cash_per_share
    income_tax = gross * tax_rate
    nhi_base = min(gross, NHI_DIVIDEND_PAYMENT_CAP)
    nhi = (
        nhi_base * NHI_SUPPLEMENTARY_PREMIUM_RATE
        if include_nhi and gross >= NHI_DIVIDEND_PAYMENT_THRESHOLD
        else 0.0
    )
    return DividendCalculation(
        shares=shares_value,
        lots=shares_value / SHARES_PER_LOT,
        cash_dividend_per_share=cash_per_share,
        gross_cash_dividend=gross,
        estimated_income_tax=income_tax,
        estimated_nhi_premium=nhi,
        estimated_net_dividend=max(0.0, gross - income_tax - nhi),
        stock_dividend_new_shares=shares_value * stock_rate,
        yield_on_cost=cash_per_share / cost if cost > 0 else 0.0,
        current_yield=cash_per_share / price if price > 0 else 0.0,
        quarterly_average=gross / 4,
        monthly_average=gross / 12,
    )


def simulate_reinvestment(
    initial_shares: object,
    initial_price: object,
    annual_dividend_per_share: object,
    dividend_growth_rate: object,
    price_growth_rate: object,
    annual_contribution: object,
    years: int,
) -> pd.DataFrame:
    shares = max(0.0, safe_number(initial_shares))
    price = max(0.0, safe_number(initial_price))
    dividend = max(0.0, safe_number(annual_dividend_per_share))
    dividend_growth = max(-1.0, safe_number(dividend_growth_rate))
    price_growth = max(-1.0, safe_number(price_growth_rate))
    contribution = max(0.0, safe_number(annual_contribution))
    cumulative_cost = shares * price
    cumulative_dividend = 0.0
    rows: list[dict[str, float | int]] = []
    for year in range(1, max(0, int(years)) + 1):
        start_shares = shares
        cash_dividend = start_shares * dividend
        reinvestment_cash = cash_dividend + contribution
        added_shares = reinvestment_cash / price if price > 0 else 0.0
        shares += added_shares
        cumulative_cost += contribution
        cumulative_dividend += cash_dividend
        rows.append({
            "年度": year,
            "年初持股股數": start_shares,
            "當年度每股股利": dividend,
            "當年度現金股息": cash_dividend,
            "額外投入金額": contribution,
            "可再投入股數": added_shares,
            "年末總持股": shares,
            "累積投入成本": cumulative_cost,
            "累積收到股息": cumulative_dividend,
            "預估持股市值": shares * price,
            "預估股價": price,
        })
        dividend *= 1 + dividend_growth
        price *= 1 + price_growth
    return pd.DataFrame(rows)


def build_dividend_history(dividends: pd.Series, prices: pd.DataFrame) -> pd.DataFrame:
    """Build annual cash-dividend history and fill-right observations."""
    if dividends is None or dividends.empty:
        return pd.DataFrame()
    series = pd.to_numeric(dividends, errors="coerce").dropna()
    series = series[series > 0]
    if series.empty:
        return pd.DataFrame()
    index = pd.to_datetime(series.index, errors="coerce")
    if getattr(index, "tz", None) is not None:
        index = index.tz_localize(None)
    index = index.normalize()
    events = pd.DataFrame({"除息日期": index, "每股現金股利": series.to_numpy()})
    clean_prices = prices.copy()
    clean_prices["trade_date"] = pd.to_datetime(clean_prices["trade_date"], errors="coerce").dt.normalize()
    clean_prices["close"] = pd.to_numeric(clean_prices["close"], errors="coerce")
    clean_prices = clean_prices.dropna(subset=["trade_date", "close"]).sort_values("trade_date")
    rows = []
    for _, event in events.iterrows():
        ex_date = event["除息日期"]
        before = clean_prices[clean_prices["trade_date"] < ex_date]
        after = clean_prices[clean_prices["trade_date"] >= ex_date]
        reference = float(before.iloc[-1]["close"]) if not before.empty else 0.0
        filled = after[after["close"] >= reference] if reference > 0 else pd.DataFrame()
        fill_date = filled.iloc[0]["trade_date"] if not filled.empty else pd.NaT
        rows.append({
            "年度": int(ex_date.year),
            "除息日期": ex_date,
            "發放日期": pd.NaT,
            "每股現金股利": float(event["每股現金股利"]),
            "股票股利": pd.NA,
            "除息前參考價": reference if reference > 0 else pd.NA,
            "現金殖利率": float(event["每股現金股利"]) / reference if reference > 0 else pd.NA,
            "填息日期": fill_date,
            "填息天數": int((fill_date - ex_date).days) if pd.notna(fill_date) else pd.NA,
            "是否完成填息": "是" if pd.notna(fill_date) else "否",
        })
    return pd.DataFrame(rows).sort_values("除息日期", ascending=False).reset_index(drop=True)


def calculation_as_dict(result: DividendCalculation) -> dict[str, float]:
    return asdict(result)
