"""Safe scheduled/manual update pipeline with status persistence and locking."""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import socket
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
        try:
            descriptor = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise UpdateAlreadyRunning("另一個更新程序正在執行，請稍後再試。") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} started_at={datetime.now(TAIPEI).isoformat()}")
        return self

    def __exit__(self, *_: object) -> None:
        LOCK_PATH.unlink(missing_ok=True)


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
                results.append(StepResult(name, "success", _short_message(detail)))
                logger.info("Step succeeded: %s", name)
            except Exception as exc:
                results.append(StepResult(name, "failed", str(exc)))
                logger.exception("Step failed: %s", name)
        overall = "success" if all(item.status == "success" for item in results) else "failed"
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
        )

    def bigquery_update() -> object:
        if not settings.gcp_project_id:
            return {"skipped": "GCP_PROJECT_ID not configured"}
        from scripts.sync_bigquery import sync_all
        return sync_all()

    return [
        ("更新財經新聞", lambda: collect_financial_news(PROJECT_ROOT / "data" / "processed" / "financial_news.json")),
        ("更新ETF熱門成交排行", lambda: collect_popular_etfs(PROJECT_ROOT / "data" / "processed" / "popular_etfs.json")),
        ("更新台股行情", lambda: collect_tw_market(raw_dir / "tw")),
        ("更新美股與國際市場", lambda: collect_us_market(raw_dir / "us")),
        ("更新法人與籌碼資料", institutional_update),
        ("更新最近一次基本面與估值", fundamental_update),
        ("更新FRED與ALFRED總體資料", macro_update),
        ("同步後台歷史資料庫", lambda: SQLiteRepository().sync_project_data(raw_dir, PROJECT_ROOT / "data" / "processed" / "financial_news.json")),
        ("同步BigQuery雲端資料庫", bigquery_update),
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
        completed = detail.get("completed", [])
        failed = detail.get("failed", {})
        return f"成功 {len(completed)} 項，失敗 {len(failed)} 項"
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
