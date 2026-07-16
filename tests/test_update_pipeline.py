import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update_daily_data


class UpdatePipelineTests(unittest.TestCase):
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

