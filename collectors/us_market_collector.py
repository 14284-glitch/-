"""US stocks, indices, FX and yield collection for the version-one universe."""

from pathlib import Path

import pandas as pd
import yfinance as yf

from config.universe import US_SYMBOLS


def collect_us_market(output_dir: Path, period: str = "2y") -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    completed: list[str] = []
    failed: dict[str, str] = {}
    for symbol in US_SYMBOLS:
        try:
            frame = yf.download(symbol, period=period, auto_adjust=False, progress=False, threads=False)
            if frame.empty:
                raise ValueError("資料來源回傳空資料")
            if isinstance(frame.columns, pd.MultiIndex):
                frame.columns = frame.columns.get_level_values(0)
            frame = frame.reset_index().rename(columns={"Date": "us_trade_date", "Adj Close": "adjusted_close"})
            frame.columns = [str(column).strip().lower().replace(" ", "_") for column in frame.columns]
            frame.insert(0, "ticker", symbol)
            frame["return_1d"] = frame["close"].pct_change()
            frame["updated_at"] = pd.Timestamp.now(tz="Asia/Taipei").isoformat()
            target = output_dir / f"{symbol.replace('^', 'INDEX_').replace('=', '_').replace('.', '_')}.csv"
            temporary = target.with_suffix(".tmp")
            frame.to_csv(temporary, index=False, encoding="utf-8-sig")
            temporary.replace(target)
            completed.append(symbol)
        except Exception as exc:
            failed[symbol] = str(exc)
    if not completed:
        raise RuntimeError(f"美股與國際市場資料全部更新失敗：{failed}")
    return {"completed": completed, "failed": failed, "rows": len(completed)}

