"""Collect latest point-in-time fundamentals and valuation data from FinMind."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import exchange_calendars as xcals
import numpy as np
import pandas as pd
import requests

from collectors.institutional_collector import _merge_csv, _request


TW_CALENDAR = xcals.get_calendar("XTAI")
OUTPUT_COLUMNS = (
    "stock_id", "report_period", "announcement_datetime", "effective_trade_date",
    "revenue", "revenue_yoy", "revenue_mom", "gross_margin",
    "operating_margin", "eps", "roe", "debt_ratio", "free_cash_flow",
    "pe_ratio", "pb_ratio", "dividend_yield", "updated_at",
)


def collect_latest_fundamentals(
    output_path: Path,
    token: str,
    stock_ids: list[str],
    session: requests.Session | None = None,
    today: date | None = None,
) -> dict[str, object]:
    """Append the latest safely available snapshot for every requested symbol."""
    if not token:
        raise RuntimeError("FINMIND_API_TOKEN is required")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    run_day = today or pd.Timestamp.now(tz="Asia/Taipei").date()
    completed: list[str] = []
    failed: dict[str, str] = {}
    snapshots: list[dict[str, object]] = []
    for stock_id in stock_ids:
        try:
            snapshot = _collect_symbol(client, token, stock_id, run_day)
            if snapshot is None:
                failed[stock_id] = "沒有可用的基本面或估值資料"
            else:
                snapshots.append(snapshot)
                completed.append(stock_id)
        except Exception as exc:
            failed[stock_id] = str(exc)
    if snapshots:
        frame = pd.DataFrame(snapshots).reindex(columns=OUTPUT_COLUMNS)
        _merge_csv(frame, output_path, ["stock_id", "effective_trade_date"])
    if not completed:
        raise RuntimeError(f"FinMind fundamental collection failed: {failed}")
    return {
        "completed": completed,
        "failed": failed,
        "output": str(output_path),
        "latest_effective_trade_date": max(
            row["effective_trade_date"] for row in snapshots
        ),
    }


def _collect_symbol(
    client: requests.Session, token: str, stock_id: str, run_day: date
) -> dict[str, object] | None:
    recent = (run_day - timedelta(days=550)).isoformat()
    end = run_day.isoformat()
    revenue = _request(client, token, "TaiwanStockMonthRevenue", stock_id, recent, end)
    valuation = _request(
        client, token, "TaiwanStockPER", stock_id,
        (run_day - timedelta(days=45)).isoformat(), end,
    )
    statements = _optional_request(
        client, token, "TaiwanStockFinancialStatements", stock_id, recent, end
    )
    balance = _optional_request(
        client, token, "TaiwanStockBalanceSheet", stock_id, recent, end
    )
    cashflow = _optional_request(
        client, token, "TaiwanStockCashFlowsStatement", stock_id, recent, end
    )
    if revenue.empty and valuation.empty and statements.empty:
        return None

    now = pd.Timestamp.now(tz="Asia/Taipei")
    result: dict[str, object] = {
        "stock_id": stock_id,
        "report_period": run_day.isoformat(),
        "announcement_datetime": now.isoformat(),
        "effective_trade_date": _next_tw_session(pd.Timestamp(run_day)),
        "updated_at": now.isoformat(),
    }
    result.update(_latest_revenue(revenue))
    result.update(_latest_valuation(valuation))
    result.update(_latest_statements(statements, balance, cashflow))

    # Only explicit FinMind create_time is trusted as a historical publication
    # timestamp. Otherwise the row is first usable after this collection run.
    availability = [pd.Timestamp(run_day)]
    for data in (revenue, statements, balance, cashflow):
        if not data.empty and "create_time" in data:
            created = pd.to_datetime(data["create_time"], errors="coerce").dropna()
            if not created.empty:
                availability.append(created.max())
    if not valuation.empty and "date" in valuation:
        valued = pd.to_datetime(valuation["date"], errors="coerce").dropna()
        if not valued.empty:
            availability.append(valued.max())
    available_at = max(availability)
    result["announcement_datetime"] = available_at.isoformat()
    result["effective_trade_date"] = _next_tw_session(available_at)
    return result


def _optional_request(*args: object) -> pd.DataFrame:
    try:
        return _request(*args)
    except Exception:
        return pd.DataFrame()


def _latest_revenue(data: pd.DataFrame) -> dict[str, object]:
    if data.empty or not {"revenue", "date"}.issubset(data.columns):
        return {}
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["revenue"] = pd.to_numeric(frame["revenue"], errors="coerce")
    frame = frame.dropna(subset=["date", "revenue"]).sort_values("date")
    if frame.empty:
        return {}
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]["revenue"] if len(frame) >= 2 else np.nan
    year_ago = frame.iloc[-13]["revenue"] if len(frame) >= 13 else np.nan
    return {
        "report_period": latest["date"].date().isoformat(),
        "revenue": float(latest["revenue"]),
        "revenue_mom": _safe_change(latest["revenue"], previous),
        "revenue_yoy": _safe_change(latest["revenue"], year_ago),
    }


def _latest_valuation(data: pd.DataFrame) -> dict[str, object]:
    if data.empty or "date" not in data:
        return {}
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if frame.empty:
        return {}
    latest = frame.iloc[-1]
    return {
        "pe_ratio": _number(latest.get("PER")),
        "pb_ratio": _number(latest.get("PBR")),
        "dividend_yield": _number(latest.get("dividend_yield")),
    }


def _latest_statements(
    income: pd.DataFrame, balance: pd.DataFrame, cashflow: pd.DataFrame
) -> dict[str, object]:
    values = _latest_type_values(income)
    balance_values = _latest_type_values(balance)
    cash_values = _latest_type_values(cashflow)
    revenue = _first(values, "Revenue", "OperatingRevenue", "TotalRevenue")
    gross_profit = _first(values, "GrossProfit", "GrossProfitLoss")
    operating_income = _first(values, "OperatingIncome", "OperatingIncomeLoss")
    net_income = _first(values, "IncomeAfterTaxes", "NetIncome")
    equity = _first(balance_values, "Equity", "TotalEquity")
    assets = _first(balance_values, "Assets", "TotalAssets")
    liabilities = _first(balance_values, "Liabilities", "TotalLiabilities")
    operating_cash = _first(cash_values, "CashFlowsFromOperatingActivities")
    capex = _first(cash_values, "PropertyPlantAndEquipment")
    return {
        "gross_margin": _safe_ratio(gross_profit, revenue),
        "operating_margin": _safe_ratio(operating_income, revenue),
        "eps": _first(values, "EPS", "BasicEarningsPerShare"),
        "roe": _safe_ratio(net_income, equity),
        "debt_ratio": _safe_ratio(liabilities, assets),
        "free_cash_flow": (
            operating_cash - abs(capex)
            if np.isfinite(operating_cash) and np.isfinite(capex) else np.nan
        ),
    }


def _latest_type_values(data: pd.DataFrame) -> dict[str, float]:
    if data.empty or not {"date", "type", "value"}.issubset(data.columns):
        return {}
    frame = data.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
    frame = frame.dropna(subset=["date", "type", "value"])
    if frame.empty:
        return {}
    latest_date = frame["date"].max()
    return frame[frame["date"] == latest_date].groupby("type")["value"].last().to_dict()


def _first(values: dict[str, float], *names: str) -> float:
    for name in names:
        value = _number(values.get(name))
        if np.isfinite(value):
            return value
    return np.nan


def _number(value: object) -> float:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if pd.notna(number) else np.nan


def _safe_ratio(numerator: object, denominator: object) -> float:
    left, right = _number(numerator), _number(denominator)
    return left / right if np.isfinite(left) and np.isfinite(right) and right else np.nan


def _safe_change(current: object, previous: object) -> float:
    left, right = _number(current), _number(previous)
    return left / right - 1 if np.isfinite(left) and np.isfinite(right) and right else np.nan


def _next_tw_session(value: pd.Timestamp) -> str:
    day = pd.Timestamp(value).tz_localize(None).normalize()
    if TW_CALENDAR.is_session(day):
        day = pd.Timestamp(TW_CALENDAR.next_session(day))
    else:
        day = pd.Timestamp(TW_CALENDAR.date_to_session(day, direction="next"))
    return day.strftime("%Y-%m-%d")
