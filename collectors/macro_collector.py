"""FRED/ALFRED point-in-time macroeconomic history collector."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_VINTAGES_URL = "https://api.stlouisfed.org/fred/series/vintagedates"
DEFAULT_SERIES = {
    "FEDFUNDS": "聯邦基金利率", "DGS2": "美國2年期公債殖利率", "DGS10": "美國10年期公債殖利率",
    "CPIAUCSL": "美國消費者物價指數", "PPIACO": "美國生產者物價指數",
    "UNRATE": "美國失業率", "GDP": "美國國內生產毛額", "DTWEXBGS": "美元廣義指數",
    "DEXTAUS": "美元兌新台幣匯率", "VIXCLS": "VIX恐慌指數", "DCOILWTICO": "WTI原油價格",
    "NASDAQQGLDI": "Credit Suisse NASDAQ 黃金指數",
}


def collect_macro_history(
    output_dir: Path, api_key: str, series: dict[str, str] | None = None,
    observation_start: str = "1950-01-01", session: requests.Session | None = None,
) -> dict[str, object]:
    if not api_key:
        raise RuntimeError("FRED_API_KEY is required")
    output_dir.mkdir(parents=True, exist_ok=True)
    client, completed, failed = session or requests.Session(), [], {}
    for series_id, name in (series or DEFAULT_SERIES).items():
        try:
            records = _fetch_observations(client, api_key, series_id, observation_start)
            frame = pd.DataFrame(records)
            if frame.empty:
                raise RuntimeError("no observations")
            frame = frame.rename(columns={
                "date": "observation_date", "realtime_start": "vintage_start_date",
                "realtime_end": "vintage_end_date",
            })
            frame.insert(0, "series_id", series_id)
            frame.insert(1, "series_name", name)
            frame["value"] = pd.to_numeric(frame["value"].replace(".", pd.NA), errors="coerce")
            frame["data_available_date"] = frame["vintage_start_date"]
            frame["updated_at"] = pd.Timestamp.now(tz="UTC").isoformat()
            _merge_macro(frame, output_dir / f"{series_id}.csv")
            completed.append(series_id)
        except Exception as exc:
            failed[series_id] = str(exc)
    if not completed:
        raise RuntimeError(f"FRED/ALFRED collection failed: {failed}")
    return {"completed": completed, "failed": failed}


def _fetch_observations(session, api_key: str, series_id: str, observation_start: str) -> list[dict]:
    base = {
        "series_id": series_id, "api_key": api_key, "file_type": "json",
        "observation_start": observation_start, "output_type": 1, "limit": 100000,
    }
    payload = _json_request(session, FRED_URL, {
        **base, "realtime_start": "1776-07-04", "realtime_end": "9999-12-31",
    }, allow_vintage_limit=True)
    if payload is not None:
        return payload.get("observations", [])
    vintage_payload = _json_request(session, FRED_VINTAGES_URL, {
        "series_id": series_id, "api_key": api_key, "file_type": "json", "limit": 10000,
    })
    vintages = vintage_payload.get("vintage_dates", [])
    records: list[dict] = []
    for start in range(0, len(vintages), 1900):
        chunk = vintages[start:start + 1900]
        payload = _json_request(session, FRED_URL, {
            **base, "realtime_start": chunk[0], "realtime_end": chunk[-1],
        })
        records.extend(payload.get("observations", []))
    return records


def _json_request(session, url: str, params: dict, allow_vintage_limit: bool = False) -> dict | None:
    response = session.get(url, params=params, timeout=120)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"FRED HTTP {response.status_code}: invalid JSON response") from exc
    error = str(payload.get("error_message", ""))
    if allow_vintage_limit and response.status_code == 400:
        if "vintage dates" in error:
            return None
        if "does not exist in ALFRED" in error:
            current = dict(params)
            current.pop("realtime_start", None)
            current.pop("realtime_end", None)
            return _json_request(session, url, current)
    if response.status_code >= 400 or error:
        # Never include response.url because it contains the API key.
        raise RuntimeError(f"FRED HTTP {response.status_code}: {error or 'request failed'}")
    return payload


def _merge_macro(frame: pd.DataFrame, target: Path) -> None:
    keys = ["series_id", "observation_date", "vintage_start_date"]
    if target.exists():
        frame = pd.concat([pd.read_csv(target), frame], ignore_index=True)
    frame = frame.drop_duplicates(keys, keep="last").sort_values(keys)
    temporary = target.with_suffix(".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(target)
