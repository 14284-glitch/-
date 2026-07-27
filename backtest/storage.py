"""JSON strategy storage service, isolated from Streamlit UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def load_strategies(path: Path) -> list[dict]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def save_strategy(path: Path, strategy: dict) -> list[dict]:
    items = load_strategies(path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {**strategy, "updated_at": now}
    record.setdefault("created_at", now)
    items = [item for item in items if item.get("name") != record.get("name")]
    items.append(record)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items


def delete_strategy(path: Path, name: str) -> list[dict]:
    items = [item for item in load_strategies(path) if item.get("name") != name]
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return items
