"""Point-in-time feature joins for staged chip, fundamental and news data."""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3

import pandas as pd


STAGE2_COLUMNS = ("foreign_net_5d", "institutional_net_5d", "margin_change_5d", "short_change_5d")
STAGE3_COLUMNS = (
    "revenue_yoy", "revenue_mom", "gross_margin", "operating_margin",
    "eps", "roe", "debt_ratio", "free_cash_flow",
    "pe_ratio", "pb_ratio", "dividend_yield",
)
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
    if data.empty:
        data = _read_institutional_database(path.parent.parent / "stock_predictor.db", stock_id)
    if data.empty:
        raw_path = (
            path.parent.parent / "raw" / "institutional"
            / f"{stock_id.upper().removesuffix('.TW')}.csv"
        )
        if raw_path.exists():
            try:
                data = pd.read_csv(raw_path)
            except (OSError, pd.errors.ParserError, UnicodeDecodeError):
                data = pd.DataFrame()
    required = {"trade_date", "foreign_net", "institutional_net", "margin_change", "short_change"}
    if data.empty or not required.issubset(data.columns):
        return _with_defaults(frame, STAGE2_COLUMNS), False
    data["trade_date"] = pd.to_datetime(
        data["trade_date"], format="mixed", errors="coerce"
    ).dt.tz_localize(None)
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
    legacy_required = {
        "revenue_yoy", "gross_margin", "eps", "roe",
        "debt_ratio", "free_cash_flow",
    }
    if (
        data.empty
        or "effective_trade_date" not in data
        or not legacy_required.issubset(data.columns)
    ):
        return _with_defaults(frame, STAGE3_COLUMNS), False
    for column in STAGE3_COLUMNS:
        if column not in data:
            data[column] = 0.0
    data["effective_trade_date"] = pd.to_datetime(
        data["effective_trade_date"], format="mixed", errors="coerce"
    ).dt.tz_localize(None)
    data = (
        data.dropna(subset=["effective_trade_date"])
        .sort_values("effective_trade_date")
        .drop_duplicates("effective_trade_date", keep="last")
    )
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
    if data.empty:
        data = _read_news_database(path.parent.parent / "stock_predictor.db")
    if data.empty:
        data = _read_news_cache(path.parent / "financial_news.json")
    required = {"tw_effective_trade_date", "sentiment_score", "news_count", "event_risk"}
    if data.empty or not required.issubset(data.columns):
        return _with_defaults(frame, STAGE4_COLUMNS), False
    data["tw_effective_trade_date"] = pd.to_datetime(
        data["tw_effective_trade_date"], format="mixed", errors="coerce"
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


def _read_institutional_database(path: Path, stock_id: str) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    target = stock_id.upper().removesuffix(".TW")
    query = """
        SELECT trade_date, foreign_net, institutional_net,
               margin_change, short_change
        FROM institutional_trading
        WHERE REPLACE(UPPER(stock_id), '.TW', '') = ?
        ORDER BY trade_date
    """
    try:
        with sqlite3.connect(path) as connection:
            return pd.read_sql_query(query, connection, params=(target,))
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame()


def _read_news_database(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    query = """
        SELECT tw_effective_trade_date, title, summary
        FROM financial_event
        WHERE tw_effective_trade_date IS NOT NULL
        ORDER BY tw_effective_trade_date
    """
    try:
        with sqlite3.connect(path) as connection:
            data = pd.read_sql_query(query, connection)
    except (sqlite3.Error, pd.errors.DatabaseError):
        return pd.DataFrame()
    return _score_news_rows(data)


def _read_news_cache(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return pd.DataFrame()
    data = pd.DataFrame(
        item for item in payload.get("items", []) if isinstance(item, dict)
    )
    if data.empty or "published_at" not in data:
        return pd.DataFrame()
    published = pd.to_datetime(
        data["published_at"], format="mixed", errors="coerce", utc=True
    ).dt.tz_convert("Asia/Taipei")
    # A news item is usable from the next Taiwan calendar day; the later
    # as-of merge prevents it from entering any earlier model row.
    data["tw_effective_trade_date"] = (
        published.dt.tz_localize(None).dt.normalize() + pd.Timedelta(days=1)
    )
    return _score_news_rows(data)


def _score_news_rows(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    positive_terms = ("成長", "上漲", "回升", "獲利", "買超", "突破", "需求強勁")
    risk_terms = ("下跌", "重挫", "風險", "升息", "通膨", "戰爭", "賣超", "不確定")
    text = (data["title"].fillna("") + " " + data["summary"].fillna("")).astype(str)
    positive = text.map(lambda value: sum(term in value for term in positive_terms))
    negative = text.map(lambda value: sum(term in value for term in risk_terms))
    denominator = (positive + negative).clip(lower=1)
    data["sentiment_score"] = (positive - negative) / denominator
    data["news_count"] = 1.0
    data["event_risk"] = (negative > positive).astype(float)
    data["stock_id"] = "MARKET"
    return data
