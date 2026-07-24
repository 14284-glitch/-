"""Single-stock analysis page with separated, color-consistent technical charts."""

from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from collectors.news_collector import load_news_cache
from features.technical_indicators import add_technical_indicators
from pages.chart_factory import kd_chart, macd_chart, price_chart, rsi_chart, volume_chart
from pages.glossary import (
    kd_legend_items, macd_legend_items, price_legend_items, render_chart_with_legend,
    render_glossary, rsi_legend_items, volume_legend_items,
)


def render() -> None:
    st.header("個股技術分析")
    category = st.selectbox(
        "第一步：選擇標的類別",
        ("臺灣50成分股（50檔）", "臺灣市場熱門ETF（50檔）"),
        help="切換後，下方標的選單會顯示該類別的50檔商品。",
    )
    if category == "臺灣50成分股（50檔）":
        universe = _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
        ranking_note = "依最近20個交易日平均成交金額排序"
    else:
        universe = load_popular_etfs()
        ranking_note = "依證交所最新交易日成交金額排序"
    st.success(f"目前類別：{category}｜已載入 {len(universe)} 檔")
    label_to_symbol = {
        f"{rank:02d}｜{name}（{symbol.removesuffix('.TW')}）": symbol
        for rank, (symbol, name) in enumerate(universe.items(), start=1)
    }
    st.caption(f"熱門度排序方式：{ranking_note}")
    selected = st.selectbox(
        "第二步：選擇分析標的",
        list(label_to_symbol),
        help="臺灣50成分股按近20日平均成交金額排序；ETF按證交所最新交易日成交金額排序。",
    )
    with st.expander(f"查看{category}完整名單", expanded=False):
        st.dataframe(
            pd.DataFrame([
                {"熱門排名": rank, "代號": symbol.removesuffix(".TW"), "名稱": name}
                for rank, (symbol, name) in enumerate(universe.items(), start=1)
            ]),
            hide_index=True,
            width="stretch",
        )
    symbol = label_to_symbol[selected]
    path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
    if not path.exists():
        st.warning("尚無行情資料，請先回到系統狀態頁執行更新。")
        return
    try:
        frame = _load_price_history(path)
    except (OSError, ValueError) as exc:
        st.error(f"行情資料格式異常，無法載入：{exc}")
        return
    if frame.empty:
        st.warning("行情資料沒有可用的日期或價格，請回到系統狀態頁重新更新。")
        return
    frame = add_technical_indicators(frame)
    minimum, maximum = frame["trade_date"].min().date(), frame["trade_date"].max().date()
    default_start = max(minimum, (pd.Timestamp(maximum) - pd.DateOffset(years=1)).date())
    start, end = st.date_input("顯示日期範圍", value=(default_start, maximum),
                               min_value=minimum, max_value=maximum)
    frame = frame[(frame["trade_date"].dt.date >= start) & (frame["trade_date"].dt.date <= end)]
    if frame.empty:
        st.info("所選日期範圍沒有交易資料。")
        return
    stock_name = universe[symbol]
    render_chart_with_legend(
        price_chart(frame, stock_name), price_legend_items(), f"{symbol}_price", default_period="7天"
    )
    render_glossary(("KLINE", "MA5", "MA10", "MA20", "MA60", "MA120", "MA240", "BOLLINGER"))
    render_chart_with_legend(
        volume_chart(frame), volume_legend_items(), f"{symbol}_volume", default_period="7天"
    )
    render_glossary(("VOLUME", "VOLUME_MA20"))
    render_chart_with_legend(
        kd_chart(frame), kd_legend_items(), f"{symbol}_kd", default_period="7天"
    )
    render_glossary(("KD", "K", "D"))
    render_chart_with_legend(
        rsi_chart(frame), rsi_legend_items(), f"{symbol}_rsi", default_period="7天"
    )
    render_glossary(("RSI",))
    render_chart_with_legend(
        macd_chart(frame), macd_legend_items(), f"{symbol}_macd", default_period="7天"
    )
    render_glossary(("MACD", "DIF", "SIGNAL"))
    _render_related_news(symbol, stock_name)


def _sort_stocks_by_popularity(universe: dict[str, str]) -> dict[str, str]:
    scores: list[tuple[float, str, str]] = []
    for symbol, name in universe.items():
        path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
        score = 0.0
        if path.exists():
            try:
                recent = pd.read_csv(path, usecols=["close", "volume"]).tail(20)
                recent["close"] = pd.to_numeric(recent["close"], errors="coerce")
                recent["volume"] = pd.to_numeric(recent["volume"], errors="coerce")
                score = float((recent["close"] * recent["volume"]).mean())
            except (OSError, ValueError, KeyError):
                score = 0.0
        scores.append((score, symbol, name))
    scores.sort(reverse=True)
    return {symbol: name for _, symbol, name in scores}


def _load_price_history(path: Path) -> pd.DataFrame:
    """Load mixed ISO dates safely and reject unusable market rows."""
    frame = pd.read_csv(path)
    required = {"trade_date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"缺少必要欄位：{', '.join(sorted(missing))}")
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], format="mixed", errors="coerce"
    )
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(
        subset=["trade_date", "open", "high", "low", "close", "volume"]
    )
    return (
        frame.sort_values("trade_date")
        .drop_duplicates("trade_date", keep="last")
        .reset_index(drop=True)
    )


@st.cache_data(ttl=600, show_spinner=False)
def _related_news(symbol: str, stock_name: str) -> list[dict[str, object]]:
    payload = load_news_cache()
    code = symbol.removesuffix(".TW")
    name_terms = {
        stock_name.strip(),
        stock_name.replace("元大", "").replace("富邦", "").replace("國泰", "").strip(),
    }
    name_terms = {term for term in name_terms if len(term) >= 2}
    matches: list[dict[str, object]] = []
    for item in payload.get("items", []):
        if not isinstance(item, dict):
            continue
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        code_hit = code in text and any(marker in text for marker in (f"（{code}）", f"({code})", f" {code}"))
        if code_hit or any(term in text for term in name_terms):
            matches.append(item)
    matches.sort(key=lambda item: str(item.get("published_at", "")), reverse=True)
    return matches[:12]


def _render_related_news(symbol: str, stock_name: str) -> None:
    st.divider()
    st.subheader(f"{stock_name}（{symbol.removesuffix('.TW')}）相關新聞")
    st.caption("依目前選擇的股票或ETF名稱與代碼，自公開新聞快取篩選；點選標題可查看原始來源。")
    try:
        items = _related_news(symbol, stock_name)
    except Exception as exc:
        st.warning(f"相關新聞暫時無法載入：{exc}")
        return
    if not items:
        st.info("目前新聞資料中沒有明確提及此標的；系統不會用產業新聞冒充個股新聞。")
        return
    for item in items:
        published = pd.to_datetime(
            item.get("published_at"), format="mixed", errors="coerce", utc=True
        )
        published_text = (
            published.tz_convert("Asia/Taipei").strftime("%Y/%m/%d %H:%M")
            if pd.notna(published)
            else "時間未提供"
        )
        st.markdown(f"#### [{item.get('title', '未命名新聞')}]({item.get('link', '#')})")
        st.caption(
            f"{item.get('source', '來源未提供')}｜"
            f"{item.get('category', '其他')}｜{published_text}"
        )
        if item.get("summary"):
            st.write(str(item["summary"]))
