"""FinMind institutional and margin history with durable incremental files."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"


def collect_institutional_history(
    output_dir: Path, token: str, stock_ids: list[str], start_date: str = "2016-01-01",
    end_date: str | None = None, session: requests.Session | None = None,
) -> dict[str, object]:
    if not token:
        raise RuntimeError("FINMIND_API_TOKEN is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    completed, failed = [], {}
    for stock_id in stock_ids:
        try:
            institutional = _request(client, token, "TaiwanStockInstitutionalInvestorsBuySell", stock_id, start_date, end_date)
            margin = _request(client, token, "TaiwanStockMarginPurchaseShortSale", stock_id, start_date, end_date)
            frame = _combine(stock_id, institutional, margin)
            _merge_csv(frame, output_dir / f"{stock_id}.csv", ["stock_id", "trade_date"])
            completed.append(stock_id)
        except Exception as exc:
            failed[stock_id] = str(exc)
    if not completed:
        raise RuntimeError(f"FinMind institutional collection failed: {failed}")
    return {"completed": completed, "failed": failed}


def _request(session, token, dataset, stock_id, start_date, end_date):
    params = {"dataset": dataset, "data_id": stock_id, "start_date": start_date, "token": token}
    if end_date:
        params["end_date"] = end_date
    response = session.get(FINMIND_URL, params=params, timeout=60)
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != 200:
        raise RuntimeError(payload.get("msg", f"FinMind status {payload.get('status')}"))
    return pd.DataFrame(payload.get("data", []))


def _combine(stock_id: str, institutional: pd.DataFrame, margin: pd.DataFrame) -> pd.DataFrame:
    base = pd.DataFrame(columns=["trade_date"])
    if not institutional.empty:
        inst = institutional.copy()
        inst["net"] = pd.to_numeric(inst.get("buy"), errors="coerce").fillna(0) - pd.to_numeric(inst.get("sell"), errors="coerce").fillna(0)
        names = inst.get("name", pd.Series("", index=inst.index)).astype(str)
        inst["kind"] = "dealer"
        inst.loc[names.str.contains("Foreign|外資", case=False), "kind"] = "foreign"
        inst.loc[names.str.contains("Investment_Trust|投信", case=False), "kind"] = "trust"
        pivot = inst.pivot_table(index="date", columns="kind", values="net", aggfunc="sum", fill_value=0)
        base = pivot.rename_axis("trade_date").reset_index().rename(columns={
            "foreign": "foreign_net", "trust": "investment_trust_net", "dealer": "dealer_net"
        })
    for column in ("foreign_net", "investment_trust_net", "dealer_net"):
        if column not in base:
            base[column] = 0
    base["institutional_net"] = base[["foreign_net", "investment_trust_net", "dealer_net"]].sum(axis=1)
    if not margin.empty:
        rename = {
            "date": "trade_date", "MarginPurchaseTodayBalance": "margin_balance",
            "ShortSaleTodayBalance": "short_balance", "SBLShortSalesTodayBalance": "securities_lending",
        }
        selected = margin.rename(columns=rename)
        keep = ["trade_date"] + [column for column in rename.values() if column != "trade_date" and column in selected]
        base = base.merge(selected[keep], on="trade_date", how="outer")
    base.insert(0, "stock_id", stock_id)
    base = base.sort_values("trade_date")
    for balance, change in (("margin_balance", "margin_change"), ("short_balance", "short_change")):
        if balance not in base:
            base[balance] = pd.NA
        base[change] = pd.to_numeric(base[balance], errors="coerce").diff()
    if "securities_lending" not in base:
        base["securities_lending"] = pd.NA
    base["updated_at"] = pd.Timestamp.now(tz="Asia/Taipei").isoformat()
    return base


def _merge_csv(frame: pd.DataFrame, target: Path, keys: list[str]) -> None:
    if target.exists():
        frame = pd.concat([pd.read_csv(target), frame], ignore_index=True)
    frame = frame.drop_duplicates(keys, keep="last").sort_values(keys)
    temporary = target.with_suffix(".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(target)
