import json
from pathlib import Path

import pandas as pd

from database.sqlite_repository import SQLiteRepository, _tw_effective_date


def test_sqlite_backend_upserts_market_and_event_history(tmp_path: Path):
    raw = tmp_path / "raw"
    (raw / "tw").mkdir(parents=True)
    (raw / "us").mkdir(parents=True)
    pd.DataFrame({
        "stock_id": ["2330.TW", "2330.TW"],
        "trade_date": ["2026-07-23", "2026-07-24"],
        "open": [100, 101], "high": [102, 103], "low": [99, 100], "close": [101, 102],
        "adjusted_close": [101, 102], "volume": [1000, 1100], "updated_at": ["x", "x"],
    }).to_csv(raw / "tw" / "2330_TW.csv", index=False)
    pd.DataFrame({
        "ticker": ["TSM"], "us_trade_date": ["2026-07-23"],
        "open": [200], "high": [202], "low": [198], "close": [201],
        "adjusted_close": [201], "volume": [2000], "return_1d": [0.01], "updated_at": ["x"],
    }).to_csv(raw / "us" / "TSM.csv", index=False)
    news = tmp_path / "news.json"
    news.write_text(json.dumps({
        "items": [{
            "title": "測試事件", "link": "https://example.com/event", "summary": "摘要",
            "source": "測試", "category": "台股市場", "published_at": "2026-07-24T00:30:00+08:00",
        }]
    }, ensure_ascii=False), encoding="utf-8")
    repository = SQLiteRepository(tmp_path / "stock.db")

    first = repository.sync_project_data(raw, news, trigger="test")
    second = repository.sync_project_data(raw, news, trigger="test")
    counts = repository.table_counts()

    assert first == second == {
        "tw_rows": 2, "us_rows": 1, "event_rows": 1,
        "institutional_rows": 0, "macro_rows": 0, "financial_rows": 0,
    }
    assert counts["tw_stock_daily"] == 2
    assert counts["us_market_daily"] == 1
    assert counts["financial_event"] == 1
    assert counts["ingestion_run"] == 2


def test_event_effective_date_respects_taiwan_session_time():
    before_open = pd.Timestamp("2026-07-24 08:30", tz="Asia/Taipei")
    after_open = pd.Timestamp("2026-07-24 10:30", tz="Asia/Taipei")
    weekend = pd.Timestamp("2026-07-25 10:30", tz="Asia/Taipei")

    assert _tw_effective_date(before_open) == "2026-07-24"
    assert _tw_effective_date(after_open) == "2026-07-27"
    assert _tw_effective_date(weekend) == "2026-07-27"
