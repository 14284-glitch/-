"""Model prediction dashboard; never creates or displays fabricated forecasts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config.color_config import COLORS
from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from pages.chart_factory import prediction_chart
from pages.glossary import prediction_legend_items, render_chart_with_legend, render_glossary
from pages.stock_analysis import _sort_stocks_by_popularity

PREDICTION_PATH = PROJECT_ROOT / "data" / "processed" / "latest_prediction.csv"
CHART_COLUMNS = {"trade_date", "actual_price", "predicted_price", "prediction_upper", "prediction_lower"}


def load_prediction_data(path: Path = PREDICTION_PATH) -> tuple[pd.DataFrame, str | None]:
    if not path.exists():
        return pd.DataFrame(), "尚未產生模型預測檔案"
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, UnicodeDecodeError) as exc:
        return pd.DataFrame(), f"預測檔案無法讀取：{exc}"
    if frame.empty:
        return frame, "預測檔案目前沒有資料"
    if "trade_date" not in frame.columns:
        return pd.DataFrame(), "預測資料缺少交易日期欄位 trade_date"
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date")
    if frame.empty:
        return frame, "預測資料沒有有效的交易日期"
    return frame, None


def _metric(label: str, row: pd.Series, column: str, percent: bool = True) -> None:
    value = pd.to_numeric(row.get(column), errors="coerce")
    if pd.isna(value):
        st.metric(label, "尚無資料")
    else:
        st.metric(label, f"{value:.1%}" if percent else f"{value:,.2f}")


def _empty_state(message: str) -> None:
    st.warning(message)
    st.markdown(
        """
        #### 目前狀態

        - 尚未完成可供正式展示的模型訓練與預測輸出。
        - 系統不會以隨機數、示範值或未驗證資料冒充預測。
        - 完成時間序列切割、無未來資料檢查及模型驗證後，才會顯示上漲機率與預期報酬。
        """
    )
    with st.expander("完成模型後，本頁會顯示哪些內容？"):
        st.write("1日、5日及20日上漲機率、預期報酬、訊號、信心水準、風險等級、預測區間及主要影響特徵。")


def render() -> None:
    st.header("模型預測")
    st.info("⏳ 正在訓練模型中")
    st.caption("模型完成時間序列驗證與未來資料防護測試後，才會開放正式預測結果。")
    st.progress(45, text="目前進度：技術特徵、預測目標與 Logistic Regression 建置中")
    st.warning("訓練完成前不顯示示範值或未驗證的預測，避免造成誤解。")
    return

    category = st.selectbox(
        "第一步：選擇預測標的類別",
        ("臺灣50成分股（50檔）", "臺灣市場熱門ETF（50檔）"),
        help="兩組名單與個股分析頁相同，並依目前熱門度排列。",
    )
    if category == "臺灣50成分股（50檔）":
        universe = _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
        ranking_note = "依最近20個交易日平均成交金額排序"
    else:
        universe = load_popular_etfs()
        ranking_note = "依證交所最新交易日成交金額排序"
    labels = {
        f"{rank:02d}｜{name}（{symbol.removesuffix('.TW')}）": symbol
        for rank, (symbol, name) in enumerate(universe.items(), start=1)
    }
    selected_label = st.selectbox("第二步：選擇預測標的", list(labels))
    selected_symbol = labels[selected_label]
    st.caption(f"目前類別：{category}｜共 {len(universe)} 檔｜{ranking_note}")

    frame, error = load_prediction_data()
    if error:
        _empty_state(error)
        return

    if "stock_id" in frame.columns:
        normalized = frame["stock_id"].astype(str).str.upper().str.replace(".TW", "", regex=False)
        frame = frame[normalized == selected_symbol.removesuffix(".TW")].copy()
        if frame.empty:
            _empty_state(f"{selected_label} 尚未產生已驗證的模型預測")
            return

    latest = frame.iloc[-1]
    st.caption(f"資料截至：{latest['trade_date']:%Y/%m/%d}｜共 {len(frame):,} 筆預測紀錄")
    cols = st.columns(6)
    metric_specs = (
        ("1日上漲機率", "probability_up_1d"), ("5日上漲機率", "probability_up_5d"),
        ("20日上漲機率", "probability_up_20d"), ("1日預期報酬", "predicted_return_1d"),
        ("5日預期報酬", "predicted_return_5d"), ("20日預期報酬", "predicted_return_20d"),
    )
    for column, (label, field) in zip(cols, metric_specs):
        with column:
            _metric(label, latest, field)

    signal = str(latest.get("signal", "尚無訊號"))
    risk = str(latest.get("risk_level", "尚無風險評級"))
    confidence = str(latest.get("confidence_level", "尚無信心水準"))
    signal_color = COLORS["signal"]["neutral"]
    st.markdown(
        f"<div style='border-left:6px solid {signal_color};padding:.8rem 1rem;background:rgba(128,128,128,.08)'>"
        f"<b>模型訊號：</b>{signal}　｜　<b>信心水準：</b>{confidence}　｜　<b>風險等級：</b>{risk}</div>",
        unsafe_allow_html=True,
    )

    if CHART_COLUMNS.issubset(frame.columns):
        render_chart_with_legend(prediction_chart(frame), prediction_legend_items(), "prediction")
        render_glossary(("ACTUAL_PRICE", "PREDICTED_PRICE", "PREDICTION_INTERVAL"))
    else:
        missing = "、".join(sorted(CHART_COLUMNS - set(frame.columns)))
        st.info(f"機率資料已載入，但價格預測圖尚缺少欄位：{missing}")

    with st.expander("查看最新預測原始資料"):
        st.dataframe(frame.tail(50), width="stretch", hide_index=True)

    st.info("模型輸出僅供研究，請搭配技術面、籌碼面、風險承受度及資金管理判斷。")
