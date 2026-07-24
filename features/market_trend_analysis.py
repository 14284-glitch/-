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
INDUSTRY_EXPLANATIONS = {
    "AI與半導體": (
        "主要受AI伺服器投資、先進製程、記憶體循環與美國科技股資本支出影響",
        "接下來要確認大型雲端業者資本支出、晶片交期、庫存與終端需求是否同步改善",
    ),
    "金融與利率": (
        "主要受中央銀行政策、存放款利差、債券評價與市場資金成本影響",
        "接下來要觀察利率方向、殖利率曲線、逾期放款與保險業避險成本",
    ),
    "能源與原物料": (
        "主要受供需缺口、地緣政治、美元走勢與運輸成本影響",
        "接下來要觀察油價與金屬價格是否持續、企業能否轉嫁成本，以及庫存變化",
    ),
    "電子與科技": (
        "主要受企業換機需求、雲端投資、消費電子庫存與新產品週期影響",
        "接下來要確認營收是否跟上題材、毛利率是否改善，以及供應鏈訂單能見度",
    ),
    "航運與供應鏈": (
        "主要受運價、港口效率、航線安全、旺季需求與全球貿易量影響",
        "接下來要觀察運價能否維持、塞港是否惡化，以及新增運力是否壓低報價",
    ),
    "消費與零售": (
        "主要受家庭所得、通膨、就業、利率與消費信心影響",
        "接下來要觀察同店銷售、客單價、庫存折價與民眾實質購買力",
    ),
    "生技醫療": (
        "主要受新藥進度、臨床結果、法規審查、授權合作與健保政策影響",
        "接下來要確認研發里程碑、現金可支應期間，以及產品是否真正開始貢獻收入",
    ),
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

    taiwan_detail = _regional_analysis(
        "台灣", markets, items, ("台股市場", "產業科技"),
        ("台灣加權指數", "SOX"),
    )
    global_detail = _regional_analysis(
        "全球", markets, items, ("美股國際",),
        ("S&P 500", "Nasdaq 100", "SOX"),
    )
    latest_dates = [frame["date"].max() for frame in markets.values() if not frame.empty]
    market_as_of = max(latest_dates).strftime("%Y/%m/%d") if latest_dates else "無可用日期"
    return {
        "trends": trends,
        "taiwan": taiwan_detail["narrative"],
        "global": global_detail["narrative"],
        "taiwan_detail": taiwan_detail,
        "global_detail": global_detail,
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
        "date": pd.to_datetime(
            frame[date_column], format="mixed", errors="coerce"
        ).dt.tz_localize(None),
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


def _regional_analysis(
    region: str,
    markets: dict[str, pd.DataFrame],
    items: list[dict[str, object]],
    categories: tuple[str, ...],
    market_names: tuple[str, ...],
) -> dict[str, object]:
    regional_items = [item for item in items if item.get("category") in categories]
    score, positive, negative = _news_tone(regional_items)
    returns = {
        name: _period_return(markets[name]["close"], 20)
        for name in market_names if name in markets and name != "VIX"
    }
    valid_returns = {name: value for name, value in returns.items() if pd.notna(value)}
    mean_return = float(np.mean(list(valid_returns.values()))) if valid_returns else 0.0
    combined_score = float(np.clip(mean_return * 5 + score * 0.25, -100, 100))
    direction = _direction(combined_score)
    if mean_return > 2:
        price_reason = "主要市場仍維持向上結構，代表資金尚未全面撤離"
    elif mean_return < -2:
        price_reason = "主要市場近期同步回落，代表投資人正降低風險部位"
    else:
        price_reason = "主要市場漲跌幅度不大，表示資金仍在等待更明確的方向"
    if negative > positive:
        news_reason = "近期消息較集中在政策、利率、成本或地緣政治風險"
    elif positive > negative:
        news_reason = "近期消息較集中在需求、訂單、獲利或資金回流"
    else:
        news_reason = "近期正面與風險消息大致相當，尚未形成一致預期"
    if region == "台灣":
        structure = (
            "台灣股市受電子與半導體權值股影響很大，因此美國科技股、費城半導體指數、"
            "新台幣匯率與外資動向，通常會比單一公司消息更快改變大盤方向。"
        )
        outlook = (
            "接下來若外資由賣轉買、成交量回升且半導體指數止穩，台股較有機會先整理再反彈；"
            "若新台幣持續走弱、國際科技股再下跌或市場量能萎縮，整理時間可能延長。"
        )
    else:
        structure = (
            "全球市場同時受到通膨、利率、能源價格、企業獲利與地緣政治影響。"
            "大型科技股雖能支撐指數，但若公債殖利率與能源成本同時上升，估值壓力會快速增加。"
        )
        outlook = (
            "接下來若通膨降溫、債券殖利率回落且企業財測穩定，全球風險資產可望逐步恢復；"
            "若油價、美元與市場波動率同步升高，資金可能繼續轉向現金、債券或防禦型產業。"
        )
    metrics: list[dict[str, str]] = [
        {"指標": "綜合判斷", "數值": direction, "用途": "整合價格結構與公開消息後的方向"},
        {"指標": "20日市場平均變化", "數值": f"{mean_return:+.2f}%", "用途": "確認近期價格實際方向"},
        {"指標": "正向訊號", "數值": f"{positive:,}", "用途": "需求、獲利、訂單及資金改善訊號"},
        {"指標": "風險訊號", "數值": f"{negative:,}", "用途": "政策、成本、利率及不確定性訊號"},
        {"指標": "納入消息", "數值": f"{len(regional_items):,} 則", "用途": "本次分析涵蓋的公開資訊量"},
    ]
    for market_name, value in valid_returns.items():
        metrics.append({
            "指標": f"{market_name} 20日變化",
            "數值": f"{value:+.2f}%",
            "用途": "比較各市場近期價格變化",
        })
    return {
        "direction": direction,
        "score": round(combined_score, 1),
        "current": f"{price_reason}；{news_reason}。",
        "reason": structure,
        "outlook": outlook,
        "metrics": metrics,
        "narrative": f"目前判斷為「{direction}」。{price_reason}；{news_reason}。{structure} {outlook}",
    }


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
            tone = "目前支持性消息較多，但價格上漲是否能延續，仍需由營收、訂單與成交量確認"
        elif negative > positive:
            tone = "目前風險消息較多，短期容易出現較大波動，不宜只因價格下跌就認定已經便宜"
        else:
            tone = "目前好壞消息接近，市場尚未形成共識，價格可能維持區間整理"
        cause, watch = INDUSTRY_EXPLANATIONS[industry]
        results.append(
            f"**{industry}**：{tone}。形成原因是{cause}。{watch}。"
            f"本次納入 {count} 則相關公開資訊，應搭配實際財報與價格走勢交叉確認。"
        )
    return results


def _planning_text(trends: list[TrendResult], negative: int, positive: int) -> list[str]:
    short, medium, long = trends
    return [
        f"**短程（約5個交易日）**：目前為「{short.direction}」。短線最容易被消息與資金流向影響，"
        "應先確認價格方向是否有成交量支持，並觀察外資買賣、VIX與美股前一晚表現。若只有單日急漲、"
        "但量能與國際市場沒有同步改善，先視為反彈而不是趨勢反轉。",
        f"**中程（約20個交易日）**：目前為「{medium.direction}」。中程需要確認月營收、法人連續買賣、"
        "匯率與產業訂單是否朝同一方向發展。研究時採分批觀察，每週重新檢查原本理由是否仍成立，"
        "不要因短期獲利或虧損就任意改變評估標準。",
        f"**遠程（約60個交易日以上）**：目前為「{long.direction}」。長期方向應以產業競爭力、自由現金流、"
        "資產負債與合理估值為核心；短期新聞只能作為風險提醒，不能代替公司基本面的持續改善。",
        "**每日資料工作**：每天核對台股、美股、法人、匯率、利率、總體與新聞的最新日期、筆數及失敗紀錄。"
        "任何必要欄位缺漏時，保留上一版結果並標示資料日期，不產生新的正式判斷。",
        "**模型研究工作**：1日、5日與20日分開訓練、校準與評估。逐步加入價量、法人、總體、基本面及事件資料，"
        "每加入一類資料都要比較樣本外表現，確認它真的改善結果，而不是只讓訓練資料看起來更漂亮。",
        "**三種市場情境**：偏多情境需要價格、成交量、法人與國際市場多數同步改善；盤整情境代表訊號互相矛盾，"
        "以等待與控制部位為主；偏空情境則要預先設定風險上限、失效條件與停止研究條件。",
        "**績效與風險追蹤**：使用Walk-forward回測，完整扣除手續費、交易稅與滑價。若最近30日與90日命中率下降、"
        "最大回撤擴大或機率校準失真，降低模型權重、檢查資料漂移，必要時停止發布該模型結果。",
    ]
