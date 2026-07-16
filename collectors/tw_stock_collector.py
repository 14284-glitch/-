"""Taiwan stock and index price collection for the version-one universe."""

from pathlib import Path

import pandas as pd
import yfinance as yf

from config.universe import load_tw_symbols


def collect_tw_market(output_dir: Path, period: str = "2y") -> dict[str, object]:
    """Download adjusted daily OHLCV data and atomically refresh local CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    completed: list[str] = []
    failed: dict[str, str] = {}
    for symbol in load_tw_symbols():
        try:
            frame = yf.download(symbol, period=period, auto_adjust=False, progress=False, threads=False)
            if frame.empty:
                raise ValueError("資料來源回傳空資料")
            frame = _normalize(frame, symbol)
            _atomic_csv(frame, output_dir / f"{symbol.replace('^', 'INDEX_').replace('.', '_')}.csv")
            completed.append(symbol)
        except Exception as exc:  # one symbol must not abort all updates
            failed[symbol] = str(exc)
    if not completed:
        raise RuntimeError(f"台股資料全部更新失敗：{failed}")
    return {"completed": completed, "failed": failed, "rows": len(completed)}


def _normalize(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.reset_index().rename(columns={"Date": "trade_date", "Adj Close": "adjusted_close"})
    frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
    frame.insert(0, "stock_id", symbol)
    frame["updated_at"] = pd.Timestamp.now(tz="Asia/Taipei").isoformat()
    return frame


def _atomic_csv(frame: pd.DataFrame, target: Path) -> None:
    temporary = target.with_suffix(".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(target)
