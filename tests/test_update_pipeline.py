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

    def test_stale_lock_is_removed_before_update(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "update.lock"
            lock.write_text(
                "pid=99999999 started_at=2026-01-01T00:00:00+08:00",
                encoding="utf-8",
            )
            with patch.object(update_daily_data, "STATUS_PATH", root / "status.json"), patch.object(
                update_daily_data, "LOCK_PATH", lock
            ):
                result = update_daily_data.run_update(
                    "manual", steps=[("測試更新", lambda: {"completed": [], "failed": {}})]
                )
        self.assertEqual(result.status, "success")

    def test_background_update_starts_without_blocking_streamlit(self) -> None:
        fake_process = type("Process", (), {"pid": 4321})()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(update_daily_data, "LOCK_PATH", root / "update.lock"), patch.object(
                update_daily_data.subprocess, "Popen", return_value=fake_process
            ) as popen:
                pid = update_daily_data.start_background_update("manual")
        self.assertEqual(pid, 4321)
        popen.assert_called_once()

    def test_warning_step_completes_without_red_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(update_daily_data, "STATUS_PATH", root / "status.json"), patch.object(
                update_daily_data, "LOCK_PATH", root / "update.lock"
            ):
                result = update_daily_data.run_update(
                    "manual",
                    steps=[("使用快取", lambda: {"warning": "來源暫時無法連線，沿用快取"})],
                )
        self.assertEqual(result.status, "warning")
        self.assertEqual(result.steps[0]["status"], "warning")

    def test_partial_symbol_results_are_yellow_warning_not_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(update_daily_data, "STATUS_PATH", root / "status.json"), patch.object(
                update_daily_data, "LOCK_PATH", root / "update.lock"
            ):
                result = update_daily_data.run_update(
                    "manual",
                    steps=[(
                        "基本面",
                        lambda: {"completed": ["2330"], "failed": {"0050": "no data"}},
                    )],
                )
        self.assertEqual(result.status, "warning")
        self.assertIn("保留最近成功資料", result.steps[0]["message"])


if __name__ == "__main__":
    unittest.main()
