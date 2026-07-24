"""Durable local SQLite backend for historical market and event data."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import exchange_calendars as xcals
import pandas as pd

from config.settings import PROJECT_ROOT


DEFAULT_DATABASE_PATH = PROJECT_ROOT / "data" / "stock_predictor.db"
TW_CALENDAR = xcals.get_calendar("XTAI")

SCHEMA = """
CREATE TABLE IF NOT EXISTS tw_stock_daily (
    stock_id TEXT NOT NULL, trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adjusted_close REAL,
    volume INTEGER, turnover REAL, updated_at TEXT,
    PRIMARY KEY (stock_id, trade_date)
);
CREATE TABLE IF NOT EXISTS us_market_daily (
    ticker TEXT NOT NULL, us_trade_date TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, adjusted_close REAL,
    volume INTEGER, return_1d REAL, updated_at TEXT,
    PRIMARY KEY (ticker, us_trade_date)
);
CREATE TABLE IF NOT EXISTS financial_event (
    event_id TEXT PRIMARY KEY, title TEXT NOT NULL, link TEXT NOT NULL,
    summary TEXT, source TEXT, category TEXT, published_at TEXT,
    data_available_datetime TEXT, tw_effective_trade_date TEXT,
    first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS institutional_trading (
    stock_id TEXT NOT NULL, trade_date TEXT NOT NULL,
    foreign_net REAL, investment_trust_net REAL, dealer_net REAL, institutional_net REAL,
    margin_balance REAL, margin_change REAL, short_balance REAL, short_change REAL,
    securities_lending REAL, updated_at TEXT,
    PRIMARY KEY (stock_id, trade_date)
);
CREATE TABLE IF NOT EXISTS financial_statement (
    stock_id TEXT NOT NULL, report_period TEXT NOT NULL,
    announcement_datetime TEXT NOT NULL, effective_trade_date TEXT NOT NULL,
    revenue REAL, revenue_yoy REAL, revenue_mom REAL,
    gross_profit REAL, gross_margin REAL, operating_income REAL,
    operating_margin REAL, net_income REAL, eps REAL, roe REAL,
    debt_ratio REAL, free_cash_flow REAL,
    pe_ratio REAL, pb_ratio REAL, dividend_yield REAL, updated_at TEXT,
    PRIMARY KEY (stock_id, report_period, announcement_datetime)
);
CREATE TABLE IF NOT EXISTS macro_observation (
    series_id TEXT NOT NULL, series_name TEXT, observation_date TEXT NOT NULL,
    vintage_start_date TEXT NOT NULL, vintage_end_date TEXT, data_available_date TEXT NOT NULL,
    value REAL, updated_at TEXT,
    PRIMARY KEY (series_id, observation_date, vintage_start_date)
);
CREATE TABLE IF NOT EXISTS ingestion_run (
    run_id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
    trigger TEXT NOT NULL, status TEXT NOT NULL, detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_tw_trade_date ON tw_stock_daily(trade_date);
CREATE INDEX IF NOT EXISTS idx_us_trade_date ON us_market_daily(us_trade_date);
CREATE INDEX IF NOT EXISTS idx_event_effective_date ON financial_event(tw_effective_trade_date);
CREATE INDEX IF NOT EXISTS idx_macro_available ON macro_observation(data_available_date);
CREATE INDEX IF NOT EXISTS idx_financial_effective ON financial_statement(stock_id, effective_trade_date);
"""


class SQLiteRepository:
    def __init__(self, path: Path = DEFAULT_DATABASE_PATH) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)

    def sync_project_data(
        self,
        raw_root: Path | None = None,
        news_path: Path | None = None,
        trigger: str = "schedule",
    ) -> dict[str, int]:
        self.initialize()
        raw_root = raw_root or PROJECT_ROOT / "data" / "raw"
        news_path = news_path or PROJECT_ROOT / "data" / "processed" / "financial_news.json"
        started = pd.Timestamp.now(tz="Asia/Taipei")
        counts = {"tw_rows": 0, "us_rows": 0, "event_rows": 0, "institutional_rows": 0, "macro_rows": 0, "financial_rows": 0}
        with self._connect() as connection:
            for path in (raw_root / "tw").glob("*.csv"):
                counts["tw_rows"] += self._upsert_market_csv(
                    connection, path, "tw_stock_daily", "stock_id", "trade_date"
                )
            for path in (raw_root / "us").glob("*.csv"):
                counts["us_rows"] += self._upsert_market_csv(
                    connection, path, "us_market_daily", "ticker", "us_trade_date"
                )
            for path in (raw_root / "institutional").glob("*.csv"):
                counts["institutional_rows"] += self._upsert_generic_csv(
                    connection, path, "institutional_trading", ["stock_id", "trade_date"]
                )
            for path in (raw_root / "macro").glob("*.csv"):
                counts["macro_rows"] += self._upsert_generic_csv(
                    connection, path, "macro_observation",
                    ["series_id", "observation_date", "vintage_start_date"],
                )
            financial_path = PROJECT_ROOT / "data" / "processed" / "financial_features.csv"
            if financial_path.exists():
                counts["financial_rows"] = self._upsert_generic_csv(
                    connection, financial_path, "financial_statement",
                    ["stock_id", "report_period", "announcement_datetime"],
                )
            counts["event_rows"] = self._upsert_news(connection, news_path)
            finished = pd.Timestamp.now(tz="Asia/Taipei")
            connection.execute(
                "INSERT INTO ingestion_run(started_at,finished_at,trigger,status,detail) VALUES(?,?,?,?,?)",
                (started.isoformat(), finished.isoformat(), trigger, "success", json.dumps(counts)),
            )
        return counts

    def table_counts(self) -> dict[str, int]:
        self.initialize()
        with self._connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in (
                    "tw_stock_daily", "us_market_daily", "financial_event",
                    "institutional_trading", "macro_observation", "ingestion_run",
                    "financial_statement",
                )
            }

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def _upsert_market_csv(
        self,
        connection: sqlite3.Connection,
        path: Path,
        table: str,
        symbol_column: str,
        date_column: str,
    ) -> int:
        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            return 0
        required = {symbol_column, date_column, "close"}
        if frame.empty or not required.issubset(frame.columns):
            return 0
        columns = (
            [symbol_column, date_column, "open", "high", "low", "close", "adjusted_close", "volume"]
            + (["turnover"] if table == "tw_stock_daily" else ["return_1d"])
            + ["updated_at"]
        )
        for column in columns:
            if column not in frame:
                frame[column] = None
        frame[date_column] = pd.to_datetime(frame[date_column], errors="coerce").dt.strftime("%Y-%m-%d")
        frame = frame.dropna(subset=[symbol_column, date_column]).replace({pd.NA: None, float("nan"): None})
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(f"{column}=excluded.{column}" for column in columns if column not in {symbol_column, date_column})
        sql = (
            f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders}) "
            f"ON CONFLICT({symbol_column},{date_column}) DO UPDATE SET {updates}"
        )
        records = [tuple(_sqlite_value(value) for value in row) for row in frame[columns].itertuples(index=False, name=None)]
        connection.executemany(sql, records)
        return len(records)

    def _upsert_generic_csv(
        self, connection: sqlite3.Connection, path: Path, table: str, keys: list[str]
    ) -> int:
        try:
            frame = pd.read_csv(path)
        except (OSError, pd.errors.ParserError, UnicodeDecodeError):
            return 0
        columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
        if frame.empty or not set(keys).issubset(frame.columns):
            return 0
        for column in columns:
            if column not in frame:
                frame[column] = None
        frame = frame[columns].dropna(subset=keys)
        placeholders = ",".join("?" for _ in columns)
        updates = ",".join(f"{column}=excluded.{column}" for column in columns if column not in keys)
        sql = (
            f"INSERT INTO {table}({','.join(columns)}) VALUES({placeholders}) "
            f"ON CONFLICT({','.join(keys)}) DO UPDATE SET {updates}"
        )
        records = [tuple(_sqlite_value(value) for value in row) for row in frame.itertuples(index=False, name=None)]
        connection.executemany(sql, records)
        return len(records)

    def _upsert_news(self, connection: sqlite3.Connection, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return 0
        now = pd.Timestamp.now(tz="Asia/Taipei").isoformat()
        rows = []
        for item in payload.get("items", []):
            link = str(item.get("link", "")).strip()
            title = str(item.get("title", "")).strip()
            if not link or not title:
                continue
            published = pd.to_datetime(item.get("published_at"), errors="coerce", utc=True)
            available = published.tz_convert("Asia/Taipei") if pd.notna(published) else pd.NaT
            effective = _tw_effective_date(available) if pd.notna(available) else None
            event_id = _stable_event_id(link)
            rows.append((
                event_id, title, link, item.get("summary"), item.get("source"), item.get("category"),
                published.isoformat() if pd.notna(published) else None,
                available.isoformat() if pd.notna(available) else None,
                effective, now, now,
            ))
        connection.executemany(
            """
            INSERT INTO financial_event(
                event_id,title,link,summary,source,category,published_at,
                data_available_datetime,tw_effective_trade_date,first_seen_at,last_seen_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(event_id) DO UPDATE SET
                title=excluded.title, summary=excluded.summary, source=excluded.source,
                category=excluded.category, published_at=excluded.published_at,
                data_available_datetime=excluded.data_available_datetime,
                tw_effective_trade_date=excluded.tw_effective_trade_date,
                last_seen_at=excluded.last_seen_at
            """,
            rows,
        )
        return len(rows)


def _tw_effective_date(available: pd.Timestamp) -> str:
    local = available.tz_convert("Asia/Taipei")
    date = pd.Timestamp(local.date())
    if TW_CALENDAR.is_session(date) and local.hour < 9:
        return date.strftime("%Y-%m-%d")
    if TW_CALENDAR.is_session(date):
        session = TW_CALENDAR.next_session(date)
    else:
        session = TW_CALENDAR.date_to_session(date, direction="next")
    return pd.Timestamp(session).strftime("%Y-%m-%d")


def _stable_event_id(link: str) -> str:
    import hashlib

    return hashlib.sha256(link.encode("utf-8")).hexdigest()


def _sqlite_value(value: object) -> object:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value
