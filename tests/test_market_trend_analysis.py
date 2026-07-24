from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from features.market_trend_analysis import analyze_market_and_news


def _write_market(path: Path, date_column: str, growth: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range(end=datetime.now(ZoneInfo("Asia/Taipei")).date(), periods=90)
    prices = pd.Series([100 * (1 + growth) ** index for index in range(len(dates))])
    pd.DataFrame({date_column: dates, "close": prices}).to_csv(path, index=False)


def test_analysis_produces_short_medium_long_and_regional_text(tmp_path: Path):
    raw = tmp_path / "raw"
    _write_market(raw / "tw" / "INDEX_TWII.csv", "trade_date", 0.001)
    _write_market(raw / "us" / "INDEX_GSPC.csv", "us_trade_date", 0.0008)
    _write_market(raw / "us" / "INDEX_NDX.csv", "us_trade_date", 0.0012)
    _write_market(raw / "us" / "INDEX_SOX.csv", "us_trade_date", 0.0015)
    _write_market(raw / "us" / "INDEX_VIX.csv", "us_trade_date", -0.0005)
    news = {
        "updated_at": "2026-07-24T01:00:00+00:00",
        "items": [
            {"title": "台股獲利成長", "summary": "需求強勁", "category": "台股市場"},
            {"title": "國際市場風險升溫", "summary": "不確定因素增加", "category": "美股國際"},
        ],
    }
    result = analyze_market_and_news(raw, news)

    assert [trend.name for trend in result["trends"]] == ["短程", "中程", "遠程"]
    assert [trend.trading_days for trend in result["trends"]] == [5, 20, 60]
    assert "台灣新聞共" in result["taiwan"]
    assert "全球新聞共" in result["global"]
    assert len(result["plan"]) == 4
    assert result["news_count"] == 2


def test_analysis_drops_market_rows_after_today(tmp_path: Path):
    raw = tmp_path / "raw"
    path = raw / "tw" / "INDEX_TWII.csv"
    path.parent.mkdir(parents=True)
    today = pd.Timestamp(datetime.now(ZoneInfo("Asia/Taipei")).date())
    dates = list(pd.date_range(end=today, periods=70)) + [today.to_pydatetime() + timedelta(days=1)]
    closes = list(range(100, 170)) + [99999]
    pd.DataFrame({"trade_date": dates, "close": closes}).to_csv(path, index=False)

    result = analyze_market_and_news(raw, {"updated_at": "", "items": []})
    assert result["market_as_of"] == today.strftime("%Y/%m/%d")
    assert all("99999" not in trend.narrative for trend in result["trends"])
