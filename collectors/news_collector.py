"""Collect public financial-news RSS headlines with a durable local fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import html
import json
from pathlib import Path
import re
from typing import Iterable
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus

import requests

def _google_news(query: str) -> str:
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


DEFAULT_FEEDS = (
    ("中央社產經證券", "台股市場", "https://feeds.feedburner.com/rsscna/finance"),
    ("中央社科技", "產業科技", "https://feeds.feedburner.com/rsscna/technology"),
    ("中央社國際", "美股國際", "https://feeds.feedburner.com/rsscna/intworld"),
    ("自由財經", "台股市場", "https://news.ltn.com.tw/rss/business.xml"),
    ("經濟日報", "台股市場", _google_news("site:money.udn.com 台股 OR 財經")),
    ("工商時報", "台股市場", _google_news("site:ctee.com.tw 台股 OR 財經")),
    ("聯合新聞網", "台股市場", _google_news("site:udn.com 台股 OR 投資 OR 財經")),
    ("MoneyDJ理財網", "台股市場", _google_news("site:moneydj.com 台股 OR 美股 OR ETF")),
    ("鉅亨網", "台股市場", _google_news("site:news.cnyes.com 台股 OR 美股 OR 財經")),
    ("ETtoday財經雲", "台股市場", _google_news("site:finance.ettoday.net 台股 OR 財經")),
    ("Yahoo股市", "台股市場", _google_news("site:tw.stock.yahoo.com 台股 OR 美股 OR 財經")),
    ("今周刊", "投資理財", _google_news("site:businesstoday.com.tw 股票 OR ETF OR 投資")),
    ("商業周刊", "投資理財", _google_news("site:businessweekly.com.tw 股票 OR 產業 OR 投資")),
    ("財訊", "投資理財", _google_news("site:wealth.com.tw 股票 OR 產業 OR 投資")),
    ("Google 新聞－股魚", "投資人－股魚", _google_news('股魚 股票 OR 投資')),
    ("Google 新聞－陳重銘", "投資人－陳重銘", _google_news('陳重銘 股票 OR 投資 OR ETF')),
    ("Google 新聞－施昇輝", "投資人－施昇輝", _google_news('施昇輝 股票 OR 投資 OR ETF')),
    ("Google 新聞－華倫老師", "投資人－華倫老師（周文偉）", _google_news('華倫老師 OR 周文偉 股票 投資')),
)
NEWS_CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "processed" / "financial_news.json"
EXCLUDED_TERMS = ("彩券", "樂透", "威力彩", "大樂透", "今彩539", "雙贏彩", "開獎號碼", "對獎")


def _plain_text(value: str | None) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(value or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_rss(xml_text: str, source: str, category: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    items = []
    for node in root.findall(".//item"):
        title, link = _plain_text(node.findtext("title")), (node.findtext("link") or "").strip()
        summary = _plain_text(node.findtext("description"))[:360]
        if (not title or not link.startswith(("https://", "http://"))
                or any(term in f"{title} {summary}" for term in EXCLUDED_TERMS)):
            continue
        published = node.findtext("pubDate") or ""
        try:
            parsed = parsedate_to_datetime(published)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            published = parsed.isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
        items.append({"title": title, "link": link,
                      "summary": summary,
                      "published_at": published, "source": source, "category": category})
    return items


def load_news_cache(path: Path = NEWS_CACHE_PATH) -> dict[str, object]:
    if not path.exists():
        return {"updated_at": "", "items": [], "errors": []}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {"updated_at": "", "items": [], "errors": []}
    except (OSError, json.JSONDecodeError):
        return {"updated_at": "", "items": [], "errors": ["本機新聞快取無法讀取"]}


def collect_financial_news(output_path: Path = NEWS_CACHE_PATH,
                           feeds: Iterable[tuple[str, str, str]] = DEFAULT_FEEDS,
                           timeout: float = 8.0) -> dict[str, object]:
    items, errors = [], []
    for source, category, url in feeds:
        try:
            response = requests.get(url, headers={"User-Agent": "TaiwanStockResearchDashboard/1.0"}, timeout=timeout)
            response.raise_for_status()
            # Keep sources balanced so one high-volume publisher cannot hide all others.
            items.extend(parse_rss(response.text, source, category)[:40])
        except (requests.RequestException, ET.ParseError) as exc:
            errors.append(f"{source}：{type(exc).__name__}")
    if not items:
        cached = load_news_cache(output_path)
        if cached.get("items"):
            cached.update({"errors": errors, "using_cache": True})
            return cached
    unique = {item["link"]: item for item in items
              if not any(term in f"{item.get('title', '')} {item.get('summary', '')}" for term in EXCLUDED_TERMS)}
    ordered = sorted(unique.values(), key=lambda item: item.get("published_at", ""), reverse=True)
    payload = {"updated_at": datetime.now(timezone.utc).isoformat(), "items": ordered[:700],
               "errors": errors, "using_cache": False}
    if ordered:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output_path)
    return payload
