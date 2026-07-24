from pathlib import Path

import pandas as pd

from features.point_in_time_integrator import attach_point_in_time_features


def test_staged_features_never_join_before_effective_date(tmp_path: Path):
    processed = tmp_path / "processed"
    processed.mkdir()
    dates = pd.date_range("2026-01-05", periods=6, freq="D")
    frame = pd.DataFrame({"trade_date": dates, "close": range(100, 106)})

    pd.DataFrame({
        "stock_id": ["2330"] * 6,
        "trade_date": dates,
        "foreign_net": range(1, 7),
        "institutional_net": range(2, 8),
        "margin_change": range(3, 9),
        "short_change": range(4, 10),
    }).to_csv(processed / "institutional_features.csv", index=False)
    pd.DataFrame({
        "stock_id": ["2330", "2330"],
        "effective_trade_date": ["2026-01-06", "2026-01-10"],
        "revenue_yoy": [10, 999],
        "gross_margin": [20, 999],
        "eps": [3, 999],
        "roe": [4, 999],
        "debt_ratio": [5, 999],
        "free_cash_flow": [6, 999],
    }).to_csv(processed / "financial_features.csv", index=False)
    pd.DataFrame({
        "stock_id": ["2330", "2330"],
        "tw_effective_trade_date": ["2026-01-07", "2026-01-10"],
        "sentiment_score": [0.2, 99],
        "news_count": [2, 99],
        "event_risk": [0.3, 99],
    }).to_csv(processed / "news_features.csv", index=False)

    joined, stages = attach_point_in_time_features(frame, "2330.TW", processed)

    row_before_financial = joined[joined["trade_date"] == pd.Timestamp("2026-01-05")].iloc[0]
    row_before_news = joined[joined["trade_date"] == pd.Timestamp("2026-01-06")].iloc[0]
    row_before_future_revision = joined[joined["trade_date"] == pd.Timestamp("2026-01-09")].iloc[0]
    assert row_before_financial["revenue_yoy"] == 0
    assert row_before_news["news_sentiment_5d"] == 0
    assert row_before_future_revision["revenue_yoy"] == 10
    assert row_before_future_revision["news_sentiment_5d"] == 0.2
    assert all(stages.values())


def test_missing_stage_files_are_reported_and_do_not_crash(tmp_path: Path):
    frame = pd.DataFrame({
        "trade_date": pd.date_range("2026-01-01", periods=3),
        "close": [100, 101, 102],
    })
    joined, stages = attach_point_in_time_features(frame, "2330.TW", tmp_path)

    assert stages["第一階段｜價量技術與國際市場"] is True
    assert stages["第二階段｜法人籌碼與衍生品"] is False
    assert stages["第三階段｜基本面估值與產業"] is False
    assert stages["第四階段｜新聞情緒與事件"] is False
    assert joined["foreign_net_5d"].eq(0).all()
    assert joined["revenue_yoy"].eq(0).all()
    assert joined["news_sentiment_5d"].eq(0).all()
