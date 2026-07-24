"""Safe scheduled/manual update pipeline with status persistence and locking."""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from typing import Callable
from zoneinfo import ZoneInfo

from config.settings import PROJECT_ROOT, get_settings
from utils.logging_config import configure_logging


TAIPEI = ZoneInfo("Asia/Taipei")
STATUS_PATH = PROJECT_ROOT / "logs" / "update_status.json"
LOCK_PATH = PROJECT_ROOT / "logs" / "update.lock"


@dataclass
class StepResult:
    name: str
    status: str
    message: str


@dataclass
class UpdateResult:
    started_at: str
    finished_at: str
    trigger: str
    status: str
    host: str
    steps: list[dict[str, str]]


class UpdateAlreadyRunning(RuntimeError):
    pass


class UpdateLock:
    def __enter__(self) -> "UpdateLock":
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        _remove_stale_lock()
        try:
            descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise UpdateAlreadyRunning("另一個更新程序正在執行，請稍後再試。") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} started_at={datetime.now(TAIPEI).isoformat()}")
        return self

    def __exit__(self, *_: object) -> None:
        LOCK_PATH.unlink(missing_ok=True)


def _remove_stale_lock() -> None:
    """Remove a lock left by a terminated process or an overlong cloud run."""
    if not LOCK_PATH.exists():
        return
    try:
        content = LOCK_PATH.read_text(encoding="utf-8")
        parts = dict(item.split("=", 1) for item in content.split() if "=" in item)
        pid = int(parts.get("pid", "0"))
        started = datetime.fromisoformat(parts["started_at"])
        age_seconds = (datetime.now(TAIPEI) - started).total_seconds()
    except (OSError, ValueError, KeyError):
        LOCK_PATH.unlink(missing_ok=True)
        return
    process_alive = True
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        process_alive = False
    if not process_alive or age_seconds > 2 * 60 * 60:
        LOCK_PATH.unlink(missing_ok=True)


def start_background_update(trigger: str = "manual") -> int:
    """Start the long update outside Streamlit's request/rerun lifecycle."""
    _remove_stale_lock()
    if LOCK_PATH.exists():
        raise UpdateAlreadyRunning("另一個更新程序正在執行，請稍後再試。")
    command = [
        sys.executable,
        "-m",
        "scripts.update_daily_data",
        "--trigger",
        trigger,
    ]
    options: dict[str, object] = {
        "cwd": str(PROJECT_ROOT),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NO_WINDOW
    else:
        options["start_new_session"] = True
    process = subprocess.Popen(command, **options)
    return int(process.pid)


def run_update(trigger: str = "manual", steps: list[tuple[str, Callable[[], object]]] | None = None) -> UpdateResult:
    settings = get_settings()
    logger = configure_logging(PROJECT_ROOT / "logs", settings.log_level)
    started = datetime.now(TAIPEI)
    raw_dir = PROJECT_ROOT / "data" / "raw"
    pipeline = steps or _default_pipeline(raw_dir)
    results: list[StepResult] = []
    with UpdateLock():
        logger.info("Update started trigger=%s", trigger)
        for name, operation in pipeline:
            try:
                detail = operation()
                step_status = (
                    "warning"
                    if isinstance(detail, dict) and (
                        detail.get("warning") or detail.get("failed")
                    )
                    else "success"
                )
                results.append(StepResult(name, step_status, _short_message(detail)))
                logger.info("Step %s: %s", step_status, name)
            except Exception as exc:
                results.append(StepResult(name, "failed", str(exc)))
                logger.exception("Step failed: %s", name)
        overall = "failed" if any(item.status == "failed" for item in results) else (
            "warning" if any(item.status == "warning" for item in results) else "success"
        )
        finished = datetime.now(TAIPEI)
        result = UpdateResult(
            started_at=started.isoformat(), finished_at=finished.isoformat(), trigger=trigger,
            status=overall, host=socket.gethostname(), steps=[asdict(item) for item in results],
        )
        _write_status(result)
        logger.info("Update finished status=%s", overall)
        return result


def _default_pipeline(raw_dir: Path) -> list[tuple[str, Callable[[], object]]]:
    # Lazy imports keep status inspection and unit tests available before optional data packages are installed.
    from collectors.tw_stock_collector import collect_tw_market
    from collectors.us_market_collector import collect_us_market
    from collectors.etf_popularity_collector import collect_popular_etfs
    from collectors.news_collector import collect_financial_news
    from database.sqlite_repository import SQLiteRepository
    from collectors.institutional_collector import collect_institutional_history
    from collectors.fundamental_collector import collect_latest_fundamentals
    from collectors.macro_collector import collect_macro_history
    from config.universe import load_tw_symbols

    settings = get_settings()
    stock_ids = sorted({
        symbol.split(".")[0] for symbol in load_tw_symbols()
        if symbol.endswith((".TW", ".TWO")) and symbol.split(".")[0].isdigit()
    })

    def institutional_update() -> object:
        if not settings.finmind_api_token:
            return {"skipped": "FINMIND_API_TOKEN not configured"}
        return collect_institutional_history(
            raw_dir / "institutional", settings.finmind_api_token, stock_ids,
            start_date=(datetime.now(TAIPEI).date().replace(day=1)).isoformat(),
        )

    def macro_update() -> object:
        if not settings.fred_api_key:
            return {"skipped": "FRED_API_KEY not configured"}
        return collect_macro_history(raw_dir / "macro", settings.fred_api_key, observation_start="2020-01-01")

    def fundamental_update() -> object:
        if not settings.finmind_api_token:
            return {"skipped": "FINMIND_API_TOKEN not configured"}
        return collect_latest_fundamentals(
            PROJECT_ROOT / "data" / "processed" / "financial_features.csv",
            settings.finmind_api_token,
            stock_ids,
            include_statements=False,
        )

    def bigquery_update() -> object:
        if not settings.gcp_project_id:
            return {"skipped": "GCP_PROJECT_ID not configured"}
        from scripts.sync_bigquery import sync_all
        return sync_all()

    def cached(operation: Callable[[], object], *paths: Path) -> Callable[[], object]:
        def execute() -> object:
            try:
                return operation()
            except Exception as exc:
                available = [
                    path for path in paths
                    if path.exists() and (
                        path.is_file() and path.stat().st_size > 0
                        or path.is_dir() and any(path.glob("*.csv"))
                    )
                ]
                if not available:
                    raise
                return {
                    "warning": f"即時來源暫時無法連線，沿用最近成功資料：{exc}",
                    "cache": [str(path) for path in available],
                }
        return execute

    return [
        ("更新財經新聞", cached(
            lambda: collect_financial_news(PROJECT_ROOT / "data" / "processed" / "financial_news.json"),
            PROJECT_ROOT / "data" / "processed" / "financial_news.json",
        )),
        ("更新ETF熱門成交排行", cached(
            lambda: collect_popular_etfs(PROJECT_ROOT / "data" / "processed" / "popular_etfs.json"),
            PROJECT_ROOT / "data" / "processed" / "popular_etfs.json",
        )),
        ("更新台股行情", cached(lambda: collect_tw_market(raw_dir / "tw"), raw_dir / "tw")),
        ("更新美股與國際市場", cached(lambda: collect_us_market(raw_dir / "us"), raw_dir / "us")),
        ("更新法人與籌碼資料", cached(institutional_update, raw_dir / "institutional")),
        ("更新最近一次基本面與估值", cached(
            fundamental_update, PROJECT_ROOT / "data" / "processed" / "financial_features.csv"
        )),
        ("更新FRED與ALFRED總體資料", cached(macro_update, raw_dir / "macro")),
        ("同步後台歷史資料庫", lambda: SQLiteRepository().sync_project_data(raw_dir, PROJECT_ROOT / "data" / "processed" / "financial_news.json")),
        ("同步BigQuery雲端資料庫", cached(
            bigquery_update, PROJECT_ROOT / "data" / "stock_predictor.db"
        )),
    ]


def read_last_status() -> dict[str, object] | None:
    if not STATUS_PATH.exists():
        return None
    try:
        return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_status(result: UpdateResult) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(STATUS_PATH)


def _short_message(detail: object) -> str:
    if isinstance(detail, dict):
        if detail.get("warning"):
            return str(detail["warning"])
        if detail.get("skipped"):
            return f"略過：{detail['skipped']}"
        completed = detail.get("completed", [])
        failed = detail.get("failed", {})
        if failed:
            return (
                f"成功更新 {len(completed)} 項；"
                f"{len(failed)} 個標的暫無新資料，已保留最近成功資料"
            )
        return f"成功 {len(completed)} 項，失敗 0 項"
    return str(detail)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trigger", default="manual", choices=("manual", "schedule", "github"))
    args = parser.parse_args()
    try:
        result = run_update(args.trigger)
    except UpdateAlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    return 0 if result.status == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
