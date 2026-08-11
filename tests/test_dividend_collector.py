from pathlib import Path

import pandas as pd

from collectors.dividend_collector import (
    collect_dividend_announcements,
    normalize_dividend_announcements,
)
from services.dividend_service import build_announced_dividend_history


SAMPLE = {
    "date": "2026-07-20",
    "stock_id": "2330",
    "year": "115年第1季",
    "StockEarningsDistribution": 1.0,
    "StockStatutorySurplus": 0.5,
    "StockExDividendTradingDate": "2026-08-10",
    "CashEarningsDistribution": 5.0,
    "CashStatutorySurplus": 1.0,
    "CashExDividendTradingDate": "2026-08-10",
    "CashDividendPaymentDate": "2026-09-10",
    "AnnouncementDate": "2026-07-15",
    "AnnouncementTime": "18:30:00",
}


class _Response:
    status_code = 200

    def json(self):
        return {"status": 200, "data": [SAMPLE]}


class _Session:
    def get(self, *_args, **_kwargs):
        return _Response()


def test_normalizes_latest_announcement_dates_and_stock_dividend_rate():
    frame = normalize_dividend_announcements([SAMPLE], "2330")
    row = frame.iloc[0]
    assert row["cash_dividend"] == 6
    assert row["stock_dividend_value"] == 1.5
    assert row["stock_dividend_rate"] == 0.15
    assert str(row["cash_payment_date"].date()) == "2026-09-10"
    assert str(row["announcement_datetime"]) == "2026-07-15 18:30:00"


def test_collector_writes_incremental_cache(tmp_path: Path):
    result = collect_dividend_announcements(
        tmp_path, "token", ["2330"], start_date="2026-01-01", session=_Session()
    )
    assert result["completed"] == ["2330"]
    assert not result["failed"]
    assert (tmp_path / "2330.csv").exists()


def test_repeated_collection_does_not_duplicate_same_dividend_event(tmp_path: Path):
    for _ in range(2):
        collect_dividend_announcements(
            tmp_path, "token", ["0056"], start_date="2026-01-01", session=_Session()
        )
    cached = pd.read_csv(tmp_path / "0056.csv", dtype={"stock_id": "string"})
    assert len(cached) == 1
    assert cached.iloc[0]["stock_id"] == "0056"


def test_announced_history_prefers_exact_payment_and_stock_dates():
    announcements = normalize_dividend_announcements([SAMPLE], "2330")
    prices = pd.DataFrame({
        "trade_date": ["2026-08-07", "2026-08-10", "2026-08-11"],
        "close": [100, 95, 101],
    })
    history = build_announced_dividend_history(announcements, prices)
    row = history.iloc[0]
    assert row["股票股利"] == 1.5
    assert row["股票股利配股率"] == 0.15
    assert str(row["發放日期"].date()) == "2026-09-10"
    assert row["填息天數"] == 1
