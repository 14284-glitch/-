import unittest
from pathlib import Path

from config.settings import Settings
from database.bigquery_client import BigQueryRepository
from database.schemas import TABLE_SPECS


class FakeBigQueryClient:
    def __init__(self, errors=None) -> None:
        self.errors = errors or []
        self.calls = []

    def insert_rows_json(self, table_id, rows):
        self.calls.append((table_id, rows))
        return self.errors


class DatabaseSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(gcp_project_id="test-project", bigquery_dataset="stocks_test")

    def test_all_required_tables_are_defined_in_schema_and_sql(self) -> None:
        expected = {
            "stock_master", "tw_stock_daily", "us_market_daily", "us_stock_daily",
            "institutional_trading", "financial_statement", "technical_features",
            "prediction_target", "model_prediction", "model_registry",
        }
        self.assertEqual(set(TABLE_SPECS), expected)
        sql = (Path(__file__).parents[1] / "database" / "create_tables.sql").read_text(encoding="utf-8")
        for table_name in expected:
            self.assertIn(f"DATASET_ID.{table_name}", sql)

    def test_point_in_time_fields_exist_for_cross_market_and_financial_data(self) -> None:
        us_fields = {item.name for item in TABLE_SPECS["us_market_daily"].fields}
        financial_fields = {item.name for item in TABLE_SPECS["financial_statement"].fields}
        self.assertIn("data_available_datetime", us_fields)
        self.assertIn("tw_effective_trade_date", us_fields)
        self.assertIn("announcement_datetime", financial_fields)
        self.assertIn("effective_trade_date", financial_fields)

    def test_valid_rows_can_be_sent_to_bigquery(self) -> None:
        client = FakeBigQueryClient()
        repository = BigQueryRepository(self.settings, client=client)
        count = repository.insert_rows("stock_master", [{
            "stock_id": "2330", "stock_name": "TSMC", "market": "TWSE",
            "currency": "TWD", "updated_at": "2026-07-16T14:00:00+08:00",
        }])
        self.assertEqual(count, 1)
        self.assertEqual(client.calls[0][0], "test-project.stocks_test.stock_master")

    def test_duplicate_logical_keys_are_rejected_before_write(self) -> None:
        repository = BigQueryRepository(self.settings, client=FakeBigQueryClient())
        row = {
            "stock_id": "2330", "trade_date": "2026-07-16", "updated_at": "2026-07-16T14:00:00+08:00"
        }
        with self.assertRaisesRegex(ValueError, "duplicate logical primary key"):
            repository.insert_rows("tw_stock_daily", [row, row])

    def test_bigquery_insert_errors_are_not_silenced(self) -> None:
        repository = BigQueryRepository(self.settings, client=FakeBigQueryClient(errors=[{"index": 0}]))
        with self.assertRaisesRegex(RuntimeError, "BigQuery insert failed"):
            repository.insert_rows("stock_master", [{
                "stock_id": "2330", "stock_name": "TSMC", "market": "TWSE",
                "currency": "TWD", "updated_at": "2026-07-16T14:00:00+08:00",
            }])


if __name__ == "__main__":
    unittest.main()

