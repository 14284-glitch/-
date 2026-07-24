"""Point-in-time feature joins for staged chip, fundamental and news data."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


STAGE2_COLUMNS = ("foreign_net_5d", "institutional_net_5d", "margin_change_5d", "short_change_5d")
STAGE3_COLUMNS = ("revenue_yoy", "gross_margin", "eps", "roe", "debt_ratio", "free_cash_flow")
STAGE4_COLUMNS = ("news_sentiment_5d", "news_count_5d", "event_risk_20d")


def attach_point_in_time_features(
    frame: pd.DataFrame,
    stock_id: str,
    processed_root: Path,
) -> tuple[pd.DataFrame, dict[str, bool]]:
    result = frame.sort_values("trade_date").copy()
    result, stage2 = _attach_institutional(
        result, processed_root / "institutional_features.csv", stock_id
    )
    result, stage3 = _attach_fundamental(
        result, processed_root / "financial_features.csv", stock_id
    )
    result, stage4 = _attach_news(
        result, processed_root / "news_features.csv", stock_id
    )
    return result, {
        "第一階段｜價量技術與國際市場": True,
        "第二階段｜法人籌碼與衍生品": stage2,
        "第三階段｜基本面估值與產業": stage3,
        "第四階段｜新聞情緒與事件": stage4,
    }


def _attach_institutional(
    frame: pd.DataFrame, path: Path, stock_id: str
) -> tuple[pd.DataFrame, bool]:
    data = _read_stock_file(path, stock_id)
    required = {"trade_date", "foreign_net", "institutional_net", "margin_change", "short_change"}
    if data.empty or not required.issubset(data.columns):
        return _with_defaults(frame, STAGE2_COLUMNS), False
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce").dt.tz_localize(None)
    data = data.dropna(subset=["trade_date"]).sort_values("trade_date")
    for source, output in (
        ("foreign_net", "foreign_net_5d"),
        ("institutional_net", "institutional_net_5d"),
        ("margin_change", "margin_change_5d"),
        ("short_change", "short_change_5d"),
    ):
        data[source] = pd.to_numeric(data[source], errors="coerce")
        data[output] = data[source].rolling(5, min_periods=1).sum()
    joined = frame.merge(data[["trade_date", *STAGE2_COLUMNS]], on="trade_date", how="left")
    joined[list(STAGE2_COLUMNS)] = joined[list(STAGE2_COLUMNS)].fillna(0.0)
    return joined, True


def _attach_fundamental(
    frame: pd.DataFrame, path: Path, stock_id: str
) -> tuple[pd.DataFrame, bool]:
    data = _read_stock_file(path, stock_id)
    if data.empty or "effective_trade_date" not in data or not set(STAGE3_COLUMNS).issubset(data.columns):
        return _with_defaults(frame, STAGE3_COLUMNS), False
    data["effective_trade_date"] = pd.to_datetime(
        data["effective_trade_date"], errors="coerce"
    ).dt.tz_localize(None)
    data = data.dropna(subset=["effective_trade_date"]).sort_values("effective_trade_date")
    for column in STAGE3_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    joined = pd.merge_asof(
        frame.sort_values("trade_date"),
        data[["effective_trade_date", *STAGE3_COLUMNS]],
        left_on="trade_date",
        right_on="effective_trade_date",
        direction="backward",
        allow_exact_matches=True,
    ).drop(columns="effective_trade_date")
    joined[list(STAGE3_COLUMNS)] = joined[list(STAGE3_COLUMNS)].fillna(0.0)
    return joined, True


def _attach_news(
    frame: pd.DataFrame, path: Path, stock_id: str
) -> tuple[pd.DataFrame, bool]:
    data = _read_stock_file(path, stock_id, allow_market_rows=True)
    required = {"tw_effective_trade_date", "sentiment_score", "news_count", "event_risk"}
    if data.empty or not required.issubset(data.columns):
        return _with_defaults(frame, STAGE4_COLUMNS), False
    data["tw_effective_trade_date"] = pd.to_datetime(
        data["tw_effective_trade_date"], errors="coerce"
    ).dt.tz_localize(None)
    data = data.dropna(subset=["tw_effective_trade_date"]).sort_values("tw_effective_trade_date")
    daily = data.groupby("tw_effective_trade_date", as_index=False).agg(
        sentiment_score=("sentiment_score", "mean"),
        news_count=("news_count", "sum"),
        event_risk=("event_risk", "max"),
    )
    daily["news_sentiment_5d"] = daily["sentiment_score"].rolling(5, min_periods=1).mean()
    daily["news_count_5d"] = daily["news_count"].rolling(5, min_periods=1).sum()
    daily["event_risk_20d"] = daily["event_risk"].rolling(20, min_periods=1).max()
    joined = pd.merge_asof(
        frame.sort_values("trade_date"),
        daily[["tw_effective_trade_date", *STAGE4_COLUMNS]].sort_values("tw_effective_trade_date"),
        left_on="trade_date",
        right_on="tw_effective_trade_date",
        direction="backward",
        allow_exact_matches=True,
    ).drop(columns="tw_effective_trade_date")
    joined[list(STAGE4_COLUMNS)] = joined[list(STAGE4_COLUMNS)].fillna(0.0)
    return joined, True


def _read_stock_file(
    path: Path, stock_id: str, allow_market_rows: bool = False
) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        data = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError):
        return pd.DataFrame()
    if "stock_id" not in data:
        return data if allow_market_rows else pd.DataFrame()
    normalized = data["stock_id"].astype(str).str.upper().str.replace(".TW", "", regex=False)
    target = stock_id.upper().removesuffix(".TW")
    if allow_market_rows:
        return data[(normalized == target) | normalized.isin({"MARKET", "ALL"})].copy()
    return data[normalized == target].copy()


def _with_defaults(frame: pd.DataFrame, columns: tuple[str, ...]) -> pd.DataFrame:
    result = frame.copy()
    for column in columns:
        result[column] = 0.0
    return result
