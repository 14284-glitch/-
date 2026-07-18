import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from scripts import update_daily_data


class UpdatePipelineTests(unittest.TestCase):
    def test_market_open_check_uses_taiwan_exchange_calendar(self) -> None:
        taipei = ZoneInfo("Asia/Taipei")
        self.assertTrue(update_daily_data.is_tw_market_open(datetime(2026, 7, 20, 9, 3, tzinfo=taipei)))
        self.assertFalse(update_daily_data.is_tw_market_open(datetime(2026, 7, 20, 14, 0, tzinfo=taipei)))
        self.assertFalse(update_daily_data.is_tw_market_open(datetime(2026, 7, 19, 10, 0, tzinfo=taipei)))

    def test_successful_steps_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(update_daily_data, "STATUS_PATH", root / "status.json"), patch.object(
                update_daily_data, "LOCK_PATH", root / "update.lock"
            ):
                result = update_daily_data.run_update(
                    "manual", steps=[("測試更新", lambda: {"completed": ["2330.TW"], "failed": {}})]
                )
        self.assertEqual(result.status, "success")
        self.assertEqual(result.steps[0]["status"], "success")

    def test_failed_step_does_not_crash_status_writer(self) -> None:
        def fail() -> None:
            raise RuntimeError("API unavailable")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(update_daily_data, "STATUS_PATH", root / "status.json"), patch.object(
                update_daily_data, "LOCK_PATH", root / "update.lock"
            ):
                result = update_daily_data.run_update("schedule", steps=[("測試失敗", fail)])
                self.assertTrue((root / "status.json").exists())
        self.assertEqual(result.status, "failed")


if __name__ == "__main__":
    unittest.main()
