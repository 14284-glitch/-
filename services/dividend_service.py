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


def build_announced_dividend_history(announcements: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Use announced FinMind dates and values, then observe fill-right from prices."""
    if announcements is None or announcements.empty:
        return pd.DataFrame()
    announcements = _deduplicate_announcements(announcements)
    clean_prices = prices.copy()
    clean_prices["trade_date"] = pd.to_datetime(clean_prices["trade_date"], errors="coerce").dt.normalize()
    clean_prices["close"] = pd.to_numeric(clean_prices["close"], errors="coerce")
    clean_prices = clean_prices.dropna(subset=["trade_date", "close"]).sort_values("trade_date")
    rows: list[dict[str, object]] = []
    for _, item in announcements.iterrows():
        ex_date = pd.to_datetime(item.get("cash_ex_dividend_date"), errors="coerce")
        stock_ex_date = pd.to_datetime(item.get("stock_ex_right_date"), errors="coerce")
        effective_ex_date = ex_date if pd.notna(ex_date) else stock_ex_date
        if pd.isna(effective_ex_date):
            continue
        effective_ex_date = effective_ex_date.normalize()
        before = clean_prices[clean_prices["trade_date"] < effective_ex_date]
        after = clean_prices[clean_prices["trade_date"] >= effective_ex_date]
        reference = float(before.iloc[-1]["close"]) if not before.empty else 0.0
        filled = after[after["close"] >= reference] if reference > 0 else pd.DataFrame()
        fill_date = filled.iloc[0]["trade_date"] if not filled.empty else pd.NaT
        cash = max(0.0, safe_number(item.get("cash_dividend")))
        stock_value = max(0.0, safe_number(item.get("stock_dividend_value")))
        year_text = str(item.get("year", ""))
        gregorian_year = _dividend_year(year_text, effective_ex_date.year)
        rows.append({
            "年度": gregorian_year,
            "股利所屬年度": year_text or str(gregorian_year),
            "公告時間": pd.to_datetime(item.get("announcement_datetime"), errors="coerce"),
            "除息日期": ex_date,
            "除權日期": stock_ex_date,
            "發放日期": pd.to_datetime(item.get("cash_payment_date"), errors="coerce"),
            "每股現金股利": cash,
            "股票股利": stock_value,
            "股票股利配股率": max(0.0, safe_number(item.get("stock_dividend_rate"))),
            "除息前參考價": reference if reference > 0 else pd.NA,
            "現金殖利率": cash / reference if reference > 0 else pd.NA,
            "填息日期": fill_date,
            "填息天數": int((fill_date - effective_ex_date).days) if pd.notna(fill_date) else pd.NA,
            "是否完成填息": "是" if pd.notna(fill_date) else "否",
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(
        ["公告時間", "除息日期"], ascending=False, na_position="last"
    ).reset_index(drop=True)


def summarize_cash_payment_frequency(
    history: pd.DataFrame, as_of: object | None = None
) -> dict[str, object]:
    """Summarize unique cash-payment events without counting duplicate announcements.

    Frequency is based on the latest completed calendar year, so a partially elapsed
    current year cannot incorrectly turn a quarterly payer into a semiannual payer.
    Only rows with a positive cash dividend are considered. Exact payment dates are
    used for paid counts; ex-dividend dates are only a fallback for frequency when an
    issuer has not supplied payment dates.
    """
    empty = {
        "reference_year": None,
        "frequency_count": 0,
        "frequency_text": "目前無現金配息資料",
        "current_year": pd.Timestamp(as_of or pd.Timestamp.now()).year,
        "current_announced_count": 0,
        "current_paid_count": 0,
        "basis": "目前無資料",
    }
    if history is None or history.empty or "每股現金股利" not in history:
        return empty

    cutoff = pd.Timestamp(as_of or pd.Timestamp.now()).tz_localize(None).normalize()
    cash = history[pd.to_numeric(history["每股現金股利"], errors="coerce").fillna(0) > 0].copy()
    if cash.empty:
        return empty
    payment = pd.to_datetime(cash.get("發放日期"), errors="coerce").dt.normalize()
    ex_date = pd.to_datetime(cash.get("除息日期"), errors="coerce").dt.normalize()
    cash["_payment_date"] = payment
    cash["_event_date"] = payment.fillna(ex_date)
    cash = cash.dropna(subset=["_event_date"])
    if cash.empty:
        return empty

    cash = cash.drop_duplicates(subset=["_event_date"])
    completed = cash[cash["_event_date"].dt.year < cutoff.year]
    reference_year = (
        int(completed["_event_date"].dt.year.max()) if not completed.empty else None
    )
    completed_year_count = (
        int(completed.loc[
            completed["_event_date"].dt.year == reference_year, "_event_date"
        ].nunique()) if reference_year is not None else 0
    )
    # Determine the recurring schedule from recent intervals. This remains accurate
    # when the first event of a calendar year is absent from a partial API backfill,
    # or when a newly listed ETF has not yet completed its first full year.
    recent_dates = cash["_event_date"].sort_values().drop_duplicates().tail(8)
    intervals = recent_dates.diff().dt.days.dropna()
    typical_days = float(intervals.median()) if not intervals.empty else float("nan")
    if pd.notna(typical_days):
        if typical_days <= 45:
            frequency_count = 12
        elif typical_days <= 120:
            frequency_count = 4
        elif typical_days <= 220:
            frequency_count = 2
        else:
            frequency_count = 1
    else:
        frequency_count = completed_year_count or 1
    labels = {1: "每年一次", 2: "每半年", 4: "每季", 12: "每月"}
    frequency_text = labels.get(
        frequency_count,
        f"每年約{frequency_count}次" if frequency_count else "尚無完整年度資料",
    )
    current = cash[cash["_event_date"].dt.year == cutoff.year]
    paid = cash[
        cash["_payment_date"].notna()
        & (cash["_payment_date"].dt.year == cutoff.year)
        & (cash["_payment_date"] <= cutoff)
    ]
    return {
        "reference_year": reference_year,
        "frequency_count": frequency_count,
        "frequency_text": frequency_text,
        "current_year": cutoff.year,
        "current_announced_count": int(current["_event_date"].nunique()),
        "current_paid_count": int(paid["_payment_date"].nunique()),
        "completed_year_count": completed_year_count,
        "basis": "唯一現金股利發放日" if payment.notna().any() else "唯一除息日（發放日未提供）",
    }


def _deduplicate_announcements(announcements: pd.DataFrame) -> pd.DataFrame:
    """Keep one row per economic dividend event across repeated daily downloads."""
    clean = announcements.copy()
    date_keys = [
        column for column in (
            "cash_ex_dividend_date", "stock_ex_right_date", "cash_payment_date", "record_date",
        ) if column in clean.columns
    ]
    for column in date_keys:
        # CSV updates may represent the same day as either YYYY-MM-DD or with 00:00:00.
        clean[column] = pd.to_datetime(clean[column], errors="coerce").dt.normalize()
    if not date_keys and "year" not in clean.columns:
        return clean
    if date_keys:
        clean["_event_identity"] = pd.NaT
        for column in date_keys:
            clean["_event_identity"] = clean["_event_identity"].fillna(clean[column])
        keys = ["_event_identity"]
    else:
        keys = ["year"]
    if "updated_at" in clean:
        clean = clean.sort_values("updated_at", na_position="first")
    return clean.drop_duplicates(subset=keys, keep="last").drop(
        columns=["_event_identity"], errors="ignore"
    ).reset_index(drop=True)


def _dividend_year(text: str, fallback: int) -> int:
    digits = "".join(character for character in text.split("年", 1)[0] if character.isdigit())
    if not digits:
        return fallback
    value = int(digits)
    return value + 1911 if value < 1911 else value


def calculation_as_dict(result: DividendCalculation) -> dict[str, float]:
    return asdict(result)
