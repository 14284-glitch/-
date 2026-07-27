"""Standalone dividend analysis page reusing the existing calculator and data flow."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from pages import dividend_analysis
from pages.stock_analysis import _load_price_history, _sort_stocks_by_popularity


def render() -> None:
    st.header("股息分析與試算")
    st.caption("選擇股票或ETF後，查看最新公告、歷年股息、填息情形，並即時計算預估實領股息。")

    category = st.selectbox(
        "第一步：選擇標的類別",
        ("臺灣50成分股（50檔）", "臺灣市場熱門ETF（50檔）"),
        key="dividend_category",
    )
    universe = (
        _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
        if category == "臺灣50成分股（50檔）"
        else load_popular_etfs()
    )
    labels = {
        f"{rank:02d}｜{name}（{symbol.removesuffix('.TW')}）": symbol
        for rank, (symbol, name) in enumerate(universe.items(), start=1)
    }
    previous = st.session_state.get("selected_stock_symbol")
    default_index = next(
        (index for index, symbol in enumerate(labels.values()) if symbol == previous),
        0,
    )
    selected = st.selectbox(
        "第二步：選擇股息分析標的",
        list(labels),
        index=default_index,
        key="dividend_symbol",
        help="選擇後會自動帶入最新股價、最近公告的現金股利及股票股利。",
    )
    symbol = labels[selected]
    stock_name = universe[symbol]
    st.session_state["selected_stock_symbol"] = symbol
    st.session_state["selected_stock_name"] = stock_name

    path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
    if not path.exists():
        st.warning("尚無此標的行情資料，請到「系統狀態」執行資料更新。")
        return
    try:
        frame = _load_price_history(path)
    except (OSError, ValueError) as exc:
        st.error(f"行情資料格式異常，無法載入：{exc}")
        return
    if frame.empty:
        st.warning("目前沒有可用的價格資料，請先更新資料。")
        return

    latest_date = pd.to_datetime(frame["trade_date"]).max()
    st.success(
        f"目前標的：{stock_name}（{symbol.removesuffix('.TW')}）"
        f"｜最新行情日期：{latest_date:%Y-%m-%d}"
    )
    dividend_analysis.render(symbol, stock_name, frame)

