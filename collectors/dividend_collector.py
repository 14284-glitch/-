"""FinMind dividend announcement collector with incremental durable caches."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import requests

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

OUTPUT_COLUMNS = (
    "stock_id", "year", "record_date", "announcement_datetime",
    "cash_dividend", "stock_dividend_value", "stock_dividend_rate",
    "cash_ex_dividend_date", "stock_ex_right_date", "cash_payment_date", "updated_at",
)


def collect_dividend_announcements(
    output_dir: Path,
    token: str,
    stock_ids: list[str],
    start_date: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, object]:
    if not token:
        raise RuntimeError("FINMIND_API_TOKEN is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    client = session or requests.Session()
    start = start_date or f"{date.today().year - 2}-01-01"
    completed, failed = [], {}
    for stock_id in stock_ids:
        try:
            response = client.get(
                FINMIND_URL,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "dataset": "TaiwanStockDividend",
                    "data_id": stock_id,
                    "start_date": start,
                },
                timeout=30,
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(f"FinMind HTTP {response.status_code}: invalid JSON") from exc
            if response.status_code != 200 or payload.get("status") != 200:
                raise RuntimeError(payload.get("msg", f"FinMind HTTP {response.status_code}"))
            normalized = normalize_dividend_announcements(payload.get("data", []), stock_id)
            _merge_cache(output_dir / f"{stock_id}.csv", normalized)
            completed.append(stock_id)
        except Exception as exc:
            failed[stock_id] = str(exc)
    return {"completed": completed, "failed": failed}


def normalize_dividend_announcements(rows: list[dict[str, object]], stock_id: str) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)
    cash = _numeric(frame, "CashEarningsDistribution") + _numeric(frame, "CashStatutorySurplus")
    stock_value = _numeric(frame, "StockEarningsDistribution") + _numeric(frame, "StockStatutorySurplus")
    announcement_date = pd.to_datetime(_column(frame, "AnnouncementDate"), errors="coerce")
    announcement_time = frame.get("AnnouncementTime", pd.Series("", index=frame.index)).fillna("").astype(str)
    announcement = pd.to_datetime(
        announcement_date.dt.strftime("%Y-%m-%d") + " " + announcement_time,
        errors="coerce",
    )
    result = pd.DataFrame({
        "stock_id": str(stock_id),
        "year": frame.get("year", ""),
        "record_date": pd.to_datetime(_column(frame, "date"), errors="coerce"),
        "announcement_datetime": announcement,
        "cash_dividend": cash,
        "stock_dividend_value": stock_value,
        # A NT$1 stock dividend corresponds to 0.1 new share per existing share.
        "stock_dividend_rate": stock_value / 10,
        "cash_ex_dividend_date": pd.to_datetime(_column(frame, "CashExDividendTradingDate"), errors="coerce"),
        "stock_ex_right_date": pd.to_datetime(_column(frame, "StockExDividendTradingDate"), errors="coerce"),
        "cash_payment_date": pd.to_datetime(_column(frame, "CashDividendPaymentDate"), errors="coerce"),
        "updated_at": pd.Timestamp.now(tz="Asia/Taipei").isoformat(),
    })
    result = result[(result["cash_dividend"] > 0) | (result["stock_dividend_value"] > 0)]
    return result.loc[:, OUTPUT_COLUMNS].reset_index(drop=True)


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame:
        return pd.Series(pd.NaT, index=frame.index)
    return frame[column]


def _merge_cache(path: Path, incoming: pd.DataFrame) -> None:
    existing = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=OUTPUT_COLUMNS)
    frames = [frame for frame in (existing, incoming) if not frame.empty]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=OUTPUT_COLUMNS)
    if combined.empty:
        combined = pd.DataFrame(columns=OUTPUT_COLUMNS)
    else:
        combined = combined.drop_duplicates(
            ["stock_id", "year", "record_date", "announcement_datetime"], keep="last"
        ).sort_values(["announcement_datetime", "record_date"])
    temporary = path.with_suffix(".tmp")
    combined.to_csv(temporary, index=False)
    temporary.replace(path)
