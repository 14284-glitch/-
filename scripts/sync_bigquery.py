"""Initialize BigQuery and idempotently synchronize durable SQLite tables."""

from __future__ import annotations

import argparse
import sqlite3

import pandas as pd

from database.bigquery_client import BigQueryRepository
from database.sqlite_repository import DEFAULT_DATABASE_PATH
from database.schemas import TABLE_SPECS

SYNC_TABLES = (
    "tw_stock_daily", "institutional_trading", "macro_observation",
    "financial_event", "financial_statement",
)


def sync_all(batch_size: int = 5000) -> dict[str, int]:
    """Synchronize complete durable tables using Sandbox-compatible load jobs.

    ``batch_size`` is retained for CLI compatibility. Full replacement is
    intentional: it is idempotent and does not require billing-enabled DML.
    """
    repository = BigQueryRepository()
    repository.initialize()
    totals = {}
    with sqlite3.connect(DEFAULT_DATABASE_PATH) as connection:
        for table in SYNC_TABLES:
            columns = {field.name for field in TABLE_SPECS[table].fields}
            available = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            selected = [field.name for field in TABLE_SPECS[table].fields if field.name in available]
            if not selected:
                continue
            frame = pd.read_sql_query(f"SELECT {','.join(selected)} FROM {table}", connection)
            frame = frame.astype(object).where(pd.notna(frame), None)
            totals[table] = repository.replace_dataframe(table, frame)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=5000)
    args = parser.parse_args()
    print(sync_all(args.batch_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
