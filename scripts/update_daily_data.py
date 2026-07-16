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

    return [
        ("更新財經新聞", lambda: collect_financial_news(PROJECT_ROOT / "data" / "processed" / "financial_news.json")),
        ("更新ETF熱門成交排行", lambda: collect_popular_etfs(PROJECT_ROOT / "data" / "processed" / "popular_etfs.json")),
        ("更新台股行情", lambda: collect_tw_market(raw_dir / "tw")),
        ("更新美股與國際市場", lambda: collect_us_market(raw_dir / "us")),
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
