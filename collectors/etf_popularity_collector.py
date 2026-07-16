"""Official TWSE ETF popularity ranking based on latest daily traded value."""

from datetime import datetime
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import requests


TWSE_DAILY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?type=ALLBUT0999&response=json"


def collect_popular_etfs(output_path: Path, limit: int = 50) -> dict[str, object]:
    response = requests.get(TWSE_DAILY_URL, timeout=30, headers={"User-Agent": "stock-predictor-research/1.0"})
    response.raise_for_status()
    payload = response.json()
    ranked: list[dict[str, object]] = []
    source_date = ""
    for table in payload.get("tables", []):
        fields = table.get("fields", [])
        if not {"證券代號", "證券名稱", "成交金額"}.issubset(fields):
            continue
        code_index, name_index, value_index = (fields.index("證券代號"), fields.index("證券名稱"), fields.index("成交金額"))
        source_date = table.get("title", "")
        for row in table.get("data", []):
            code = row[code_index].strip()
            if not re.fullmatch(r"00[0-9A-Z]{2,4}", code):
                continue
            try:
                traded_value = int(row[value_index].replace(",", ""))
            except (TypeError, ValueError):
                traded_value = 0
            ranked.append({"code": code, "name": row[name_index].strip(), "traded_value": traded_value})
    if len(ranked) < limit:
        raise RuntimeError(f"TWSE ETF candidates insufficient: {len(ranked)}")
    ranked.sort(key=lambda item: int(item["traded_value"]), reverse=True)
    items = ranked[:limit]
    document = {
        "ranking_method": "latest_daily_traded_value", "source": TWSE_DAILY_URL,
        "source_date": source_date, "updated_at": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(), "items": items,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(output_path)
    return {"completed": [item["code"] for item in items], "failed": {}, "rows": len(items)}
