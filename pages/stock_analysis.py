"""Single-stock analysis page with separated, color-consistent technical charts."""

from pathlib import Path

import pandas as pd
import streamlit as st

from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
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
    frame = pd.read_csv(path, parse_dates=["trade_date"])
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
    render_chart_with_legend(price_chart(frame, stock_name), price_legend_items(), f"{symbol}_price")
    render_glossary(("KLINE", "MA5", "MA10", "MA20", "MA60", "MA120", "MA240", "BOLLINGER"))
    render_chart_with_legend(volume_chart(frame), volume_legend_items(), f"{symbol}_volume")
    render_glossary(("VOLUME", "VOLUME_MA20"))
    render_chart_with_legend(kd_chart(frame), kd_legend_items(), f"{symbol}_kd")
    render_glossary(("KD", "K", "D"))
    render_chart_with_legend(rsi_chart(frame), rsi_legend_items(), f"{symbol}_rsi")
    render_glossary(("RSI",))
    render_chart_with_legend(macd_chart(frame), macd_legend_items(), f"{symbol}_macd")
    render_glossary(("MACD", "DIF", "SIGNAL"))


def _sort_stocks_by_popularity(universe: dict[str, str]) -> dict[str, str]:
    scores: list[tuple[float, str, str]] = []
    for symbol, name in universe.items():
        path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
        score = 0.0
        if path.exists():
            try:
                recent = pd.read_csv(path, usecols=["close", "volume"]).tail(20)
                score = float((recent["close"] * recent["volume"]).mean())
            except (OSError, ValueError, KeyError):
                score = 0.0
        scores.append((score, symbol, name))
    scores.sort(reverse=True)
    return {symbol: name for _, symbol, name in scores}
