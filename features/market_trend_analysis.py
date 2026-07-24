"""Explainable market/news trend synthesis without future-data leakage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


TAIPEI = ZoneInfo("Asia/Taipei")
POSITIVE_TERMS = (
    "成長", "上漲", "創高", "回升", "擴張", "優於預期", "獲利", "買超",
    "降息", "復甦", "突破", "訂單增加", "需求強勁",
)
NEGATIVE_TERMS = (
    "下跌", "重挫", "衰退", "風險", "升息", "通膨", "戰爭", "制裁",
    "虧損", "賣超", "裁員", "違約", "升溫", "疲弱", "不確定",
)
HORIZONS = (("短程", 5), ("中程", 20), ("遠程", 60))
INDUSTRIES = {
    "AI與半導體": ("AI", "人工智慧", "半導體", "晶片", "晶圓", "伺服器"),
    "金融與利率": ("金融", "銀行", "保險", "利率", "降息", "升息", "債券"),
    "能源與原物料": ("能源", "原油", "油價", "天然氣", "黃金", "原物料"),
    "電子與科技": ("電子", "科技", "雲端", "軟體", "手機", "電腦"),
    "航運與供應鏈": ("航運", "運價", "供應鏈", "紅海", "物流"),
    "消費與零售": ("消費", "零售", "觀光", "餐飲", "汽車"),
    "生技醫療": ("生技", "醫療", "製藥", "藥品"),
}


@dataclass(frozen=True)
class TrendResult:
    name: str
    trading_days: int
    direction: str
    score: float
    narrative: str


def analyze_market_and_news(raw_root: Path, news_payload: dict[str, object]) -> dict[str, object]:
    """Combine only currently available market rows and cached news into text trends."""
    today = pd.Timestamp(datetime.now(TAIPEI).date())
    markets = {
        "台灣加權指數": _read_market(raw_root / "tw" / "INDEX_TWII.csv", today),
        "S&P 500": _read_market(raw_root / "us" / "INDEX_GSPC.csv", today),
        "Nasdaq 100": _read_market(raw_root / "us" / "INDEX_NDX.csv", today),
        "SOX": _read_market(raw_root / "us" / "INDEX_SOX.csv", today),
        "VIX": _read_market(raw_root / "us" / "INDEX_VIX.csv", today),
    }
    markets = {name: frame for name, frame in markets.items() if not frame.empty}
    items = [item for item in news_payload.get("items", []) if isinstance(item, dict)]
    news_score, positive_count, negative_count = _news_tone(items)

    trends = []
    for name, days in HORIZONS:
        returns = {
            market: _period_return(frame["close"], days)
            for market, frame in markets.items()
            if market != "VIX" and len(frame) > days
        }
        vix_change = _period_return(markets["VIX"]["close"], days) if "VIX" in markets else np.nan
        market_return = float(np.nanmean(list(returns.values()))) if returns else 0.0
        risk_adjustment = -float(vix_change) * 0.25 if pd.notna(vix_change) else 0.0
        market_score = float(np.tanh((market_return + risk_adjustment) / 5) * 100)
        # Long horizons rely more on observed price structure and less on short-lived headlines.
        news_weight = {5: 0.30, 20: 0.20, 60: 0.10}[days]
        score = market_score * (1 - news_weight) + news_score * news_weight
        direction = _direction(score)
        leaders = _leaders_text(returns)
        narrative = (
            f"{direction}。主要市場平均報酬約 {market_return:+.2f}%；{leaders}。"
            f"新聞語氣正向 {positive_count} 項、風險 {negative_count} 項，"
            f"{'VIX變化已納入風險扣分。' if pd.notna(vix_change) else 'VIX資料不足，未納入風險調整。'} "
            f"白話解讀：{_plain_language(direction, name)}"
        )
        trends.append(TrendResult(name, days, direction, round(score, 1), narrative))

    taiwan = _regional_text("台灣", markets, items, ("台股市場", "產業科技"), ("台灣加權指數", "SOX"))
    global_text = _regional_text("全球", markets, items, ("美股國際",), ("S&P 500", "Nasdaq 100", "VIX"))
    latest_dates = [frame["date"].max() for frame in markets.values() if not frame.empty]
    market_as_of = max(latest_dates).strftime("%Y/%m/%d") if latest_dates else "無可用日期"
    return {
        "trends": trends,
        "taiwan": taiwan,
        "global": global_text,
        "taiwan_industries": _industry_trends(items, ("台股市場", "產業科技", "投資理財"), "台灣"),
        "global_industries": _industry_trends(items, ("美股國際", "產業科技"), "全球"),
        "plan": _planning_text(trends, negative_count, positive_count),
        "market_as_of": market_as_of,
        "news_as_of": str(news_payload.get("updated_at", "未提供")),
        "news_count": len(items),
        "market_count": len(markets),
    }


def _read_market(path: Path, today: pd.Timestamp) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["date", "close"])
    frame = pd.read_csv(path)
    date_column = "trade_date" if "trade_date" in frame else "us_trade_date"
    if date_column not in frame or "close" not in frame:
        return pd.DataFrame(columns=["date", "close"])
    result = pd.DataFrame({
        "date": pd.to_datetime(frame[date_column], errors="coerce").dt.tz_localize(None),
        "close": pd.to_numeric(frame["close"], errors="coerce"),
    }).dropna()
    return result[result["date"] <= today].sort_values("date").drop_duplicates("date", keep="last")


def _period_return(close: pd.Series, days: int) -> float:
    if len(close) <= days or close.iloc[-days - 1] == 0:
        return float("nan")
    return float((close.iloc[-1] / close.iloc[-days - 1] - 1) * 100)


def _news_tone(items: list[dict[str, object]]) -> tuple[float, int, int]:
    positive = negative = 0
    for item in items:
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        positive += sum(term in text for term in POSITIVE_TERMS)
        negative += sum(term in text for term in NEGATIVE_TERMS)
    total = positive + negative
    score = 0.0 if total == 0 else (positive - negative) / total * 100
    return float(score), positive, negative


def _direction(score: float) -> str:
    if score >= 25:
        return "偏多但仍需確認"
    if score >= 8:
        return "溫和偏多"
    if score <= -25:
        return "偏空且風險較高"
    if score <= -8:
        return "溫和偏空"
    return "中性震盪"


def _plain_language(direction: str, horizon: str) -> str:
    if "偏多" in direction:
        return f"{horizon}走勢有向上力量，但不是一路上漲；若成交量跟不上或風險消息增加，仍可能拉回。"
    if "偏空" in direction:
        return f"{horizon}壓力較大，市場容易因壞消息放大波動；先重視風險與資金配置，不急著追價。"
    return f"{horizon}多空力量接近，較可能反覆震盪；等待價格、成交量與消息方向更一致再判斷。"


def _leaders_text(returns: dict[str, float]) -> str:
    valid = {name: value for name, value in returns.items() if pd.notna(value)}
    if not valid:
        return "市場資料不足"
    strongest = max(valid, key=valid.get)
    weakest = min(valid, key=valid.get)
    return f"相對較強為 {strongest}（{valid[strongest]:+.2f}%），較弱為 {weakest}（{valid[weakest]:+.2f}%）"


def _regional_text(
    region: str,
    markets: dict[str, pd.DataFrame],
    items: list[dict[str, object]],
    categories: tuple[str, ...],
    market_names: tuple[str, ...],
) -> str:
    regional_items = [item for item in items if item.get("category") in categories]
    score, positive, negative = _news_tone(regional_items)
    returns = {
        name: _period_return(markets[name]["close"], 20)
        for name in market_names if name in markets and name != "VIX"
    }
    direction = _direction(score)
    return (
        f"{region}新聞共 {len(regional_items)} 則，文字語氣為{direction}"
        f"（正向詞 {positive}、風險詞 {negative}）。{_leaders_text(returns)}。"
        f"白話來說，目前{region}市場的好消息與風險正在拉鋸，"
        "觀察時要同時確認成交量、利率、匯率與政策變化，不要只看單一新聞標題。"
    )


def _industry_trends(
    items: list[dict[str, object]], categories: tuple[str, ...], region: str
) -> list[str]:
    regional_items = [item for item in items if item.get("category") in categories]
    ranked: list[tuple[int, str, int, int]] = []
    for industry, keywords in INDUSTRIES.items():
        matched = [
            item for item in regional_items
            if any(keyword in f"{item.get('title', '')} {item.get('summary', '')}" for keyword in keywords)
        ]
        if not matched:
            continue
        _, positive, negative = _news_tone(matched)
        ranked.append((len(matched), industry, positive, negative))
    ranked.sort(reverse=True)
    if not ranked:
        return [f"{region}產業新聞樣本不足，目前無法形成可靠的產業排序。"]
    results = []
    for count, industry, positive, negative in ranked[:4]:
        if positive > negative:
            tone = "消息面較正向，但仍需確認實際營收與訂單"
        elif negative > positive:
            tone = "風險消息較多，宜留意成本、需求或政策壓力"
        else:
            tone = "好壞消息接近，產業方向仍在整理"
        results.append(f"{industry}：相關新聞 {count} 則，{tone}。")
    return results


def _planning_text(trends: list[TrendResult], negative: int, positive: int) -> list[str]:
    short, medium, long = trends
    return [
        f"短程（5日）：目前為「{short.direction}」，先追蹤量價、VIX及外資動向，不追逐單日急漲急跌。",
        f"中程（20日）：目前為「{medium.direction}」，採分批研究與定期檢視，設定可承受風險及最大部位。",
        f"遠程（60日）：目前為「{long.direction}」，以產業競爭力、現金流與估值為主，避免用短期新聞取代基本面。",
        f"情境規劃：新聞風險詞 {negative}、正向詞 {positive}；準備偏多、盤整、偏空三種方案與退出條件。",
    ]
