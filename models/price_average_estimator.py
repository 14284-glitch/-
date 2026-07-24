"""Deterministic 3/7/14-session price-average estimator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


TAIPEI = ZoneInfo("Asia/Taipei")
WINDOWS = (3, 7, 14)
RANGE_PERCENT = 0.80


def estimate_symbol_price(
    path: Path,
    symbol: str,
    name: str,
    as_of: datetime | pd.Timestamp | None = None,
) -> dict[str, object] | None:
    """Estimate price ranges using only rows available on or before as_of."""
    if not path.exists():
        return None
    try:
        frame = pd.read_csv(path, usecols=["trade_date", "close"])
    except (OSError, ValueError, pd.errors.ParserError):
        return None
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce").dt.tz_localize(None)
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna().sort_values("trade_date").drop_duplicates("trade_date", keep="last")
    cutoff = pd.Timestamp(as_of or datetime.now(TAIPEI)).tz_localize(None).normalize()
    frame = frame[frame["trade_date"] <= cutoff]
    if len(frame) < max(WINDOWS):
        return None

    result: dict[str, object] = {
        "symbol": symbol.removesuffix(".TW"),
        "name": name,
        "data_date": frame.iloc[-1]["trade_date"],
        "latest_close": float(frame.iloc[-1]["close"]),
    }
    averages = []
    for window in WINDOWS:
        average = float(frame["close"].tail(window).mean())
        averages.append(average)
        result[f"average_{window}d"] = average
        result[f"lower_{window}d"] = max(0.0, average * (1 - RANGE_PERCENT))
        result[f"upper_{window}d"] = average * (1 + RANGE_PERCENT)
    combined = sum(averages) / len(averages)
    result.update({
        "estimated_price": combined,
        "estimated_lower": max(0.0, combined * (1 - RANGE_PERCENT)),
        "estimated_upper": combined * (1 + RANGE_PERCENT),
    })
    return result


def estimate_universe(
    universe: dict[str, str],
    raw_tw_path: Path,
    as_of: datetime | pd.Timestamp | None = None,
) -> pd.DataFrame:
    rows = []
    for symbol, name in universe.items():
        filename = f"{symbol.replace('.', '_')}.csv"
        estimate = estimate_symbol_price(raw_tw_path / filename, symbol, name, as_of)
        if estimate is not None:
            rows.append(estimate)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["name", "symbol"]).reset_index(drop=True)
