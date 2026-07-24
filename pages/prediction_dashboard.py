"""Model prediction dashboard; never creates or displays fabricated forecasts."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pandas as pd
import streamlit as st

from config.color_config import COLORS
from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from database.sqlite_repository import SQLiteRepository
from models.research_forecaster import forecast_from_price_history
from pages.chart_factory import prediction_chart
from pages.glossary import prediction_legend_items, render_chart_with_legend, render_glossary
from pages.stock_analysis import _sort_stocks_by_popularity

PREDICTION_PATH = PROJECT_ROOT / "data" / "processed" / "latest_prediction.csv"
CHART_COLUMNS = {"trade_date", "actual_price", "predicted_price", "prediction_upper", "prediction_lower"}


@st.cache_data(ttl=600, show_spinner=False)
def _cached_research_forecast(symbol: str) -> dict[str, object]:
    path = PROJECT_ROOT / "data" / "raw" / "tw" / f"{symbol.replace('.', '_')}.csv"
    return forecast_from_price_history(path)


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
    frame["trade_date"] = pd.to_datetime(
        frame["trade_date"], format="mixed", errors="coerce"
    )
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
    category = st.selectbox(
        "選擇預測標的類別",
        ("全部個股與ETF（100檔）", "臺灣50成分股（50檔）", "臺灣市場熱門ETF（50檔）"),
        accept_new_options=False,
        filter_mode=None,
    )
    stocks = _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
    etfs = load_popular_etfs()
    if category == "全部個股與ETF（100檔）":
        universe = {**stocks, **etfs}
    elif category == "臺灣50成分股（50檔）":
        universe = stocks
    else:
        universe = etfs
    labels = {
        f"{name}（{symbol.removesuffix('.TW')}）": symbol
        for symbol, name in universe.items()
    }
    selected_label = st.selectbox(
        "選擇個股或ETF查看預測",
        list(labels),
        accept_new_options=False,
        filter_mode=None,
    )
    selected_symbol = labels[selected_label]
    _render_research_forecast(selected_symbol)
    with st.expander("Logistic Regression與XGBoost開發狀態"):
        st.info("⏳ 正在訓練與進行時間序列驗證；完成未來資料防護與回測後才會顯示上漲機率。")


def _render_research_forecast(symbol: str) -> None:
    st.divider()
    st.subheader("第一階段研究預測｜歷史相似情境")
    st.caption("1日、5日、20日使用不同輸入視窗、盤整門檻與歷史情境，不共用完全相同規則。")
    try:
        result = _cached_research_forecast(symbol)
    except ValueError as exc:
        st.warning(f"目前無法產生研究預測：{exc}")
        return
    if not result["formal_training_ready"]:
        st.warning(
            f"目前有效歷史約 {result['history_years']:.1f} 年，未達正式模型最低5年要求；"
            "以下只列為研究結果，不視為已完成模型。"
        )
    st.caption(
        f"資料截至：{result['data_date']:%Y/%m/%d}｜最新收盤 {result['latest_close']:,.2f}｜"
        f"20日支撐 {result['support_20']:,.2f}｜20日壓力 {result['resistance_20']:,.2f}"
    )
    inventory = _data_inventory(symbol)
    st.markdown("#### 歷史資料完整度")
    st.dataframe(
        pd.DataFrame(inventory),
        hide_index=True,
        width="stretch",
        column_config={
            "資料類別": st.column_config.TextColumn("資料類別"),
            "筆數": st.column_config.NumberColumn("有效筆數", format="%d"),
            "起始日期": st.column_config.TextColumn("起始日期"),
            "最新日期": st.column_config.TextColumn("最新日期"),
            "使用狀態": st.column_config.TextColumn("使用狀態"),
            "說明": st.column_config.TextColumn("資料用途與限制"),
        },
    )
    stage_columns = st.columns(4)
    for column, (stage, available) in zip(stage_columns, result["stage_availability"].items()):
        with column:
            unavailable = "尚待正式公告資料" if "基本面" in stage else "尚未接入"
            st.metric(stage, "已接入" if available else unavailable)
    cards = st.columns(3)
    for column, forecast in zip(cards, result["forecasts"]):
        with column:
            st.markdown(f"#### 未來{forecast.horizon}日")
            st.write(
                f"上漲 {forecast.probability_up:.1%}｜"
                f"盤整 {forecast.probability_sideways:.1%}｜"
                f"下跌 {forecast.probability_down:.1%}"
            )
            st.metric("預期報酬", f"{forecast.expected_return:+.2%}")
            st.write(
                f"報酬區間：{forecast.return_lower:+.2%}～{forecast.return_upper:+.2%}\n\n"
                f"價格區間：{forecast.price_lower:,.2f}～{forecast.price_upper:,.2f}\n\n"
                f"年化波動：{forecast.volatility:.1%}｜風險：{forecast.risk_level}"
            )
            st.write(
                f"突破壓力機率：{forecast.probability_break_resistance:.1%}\n\n"
                f"跌破支撐機率：{forecast.probability_break_support:.1%}"
            )
            cost_text = "高於" if forecast.expected_return_above_cost else "未高於"
            st.write(f"預期報酬{cost_text}預設交易成本0.585%")
            st.caption(f"輸入視窗：{forecast.input_window}日｜相似樣本：{forecast.analogue_count}筆")
    with st.expander("目前六大類資料完整度與後續接入順序", expanded=False):
        stages = result["stage_availability"]
        st.dataframe(pd.DataFrame([
            {"資料類別": "價格、成交量與技術指標", "目前狀態": "已使用", "內容": "OHLC、成交量、報酬、波動、均線、RSI、KD、MACD、布林"},
            {"資料類別": "大盤、產業與前一晚美股", "目前狀態": "已使用", "內容": "台股、美股、費半、VIX、ADR、匯率、美債已用嚴格前一交易日對齊"},
            {"資料類別": "法人、籌碼與衍生品", "目前狀態": "已接入" if stages["第二階段｜法人籌碼與衍生品"] else "資料不足", "內容": "已使用三大法人、融資券與借券；期權、主力與集保仍需其他授權來源"},
            {
                "資料類別": "基本面與估值",
                "目前狀態": "已接入最近一次資料" if stages["第三階段｜基本面估值與產業"] else "尚待正式公告資料",
                "內容": (
                    "使用預測日以前最近一次已公告的月營收、財報、PER、PBR與殖利率；每日排程更新，舊日期不會使用後來才公布的資料"
                    if stages["第三階段｜基本面估值與產業"]
                    else "等待附公告時間的基本面與估值資料；未取得前不以事後資料替代"
                ),
            },
            {"資料類別": "總體經濟", "目前狀態": "已接入", "內容": "FRED／ALFRED點時資料已包含美債、匯率、VIX、CPI、PPI、GDP與失業率"},
            {"資料類別": "新聞、事件與情緒", "目前狀態": "已接入" if stages["第四階段｜新聞情緒與事件"] else "資料不足", "內容": "已依公開時間轉成台股有效交易日，並計算5日情緒與20日事件風險"},
            {"資料類別": "逐筆、大單小單與週轉率", "目前狀態": "資料來源不足", "內容": "目前日線來源沒有逐筆成交與完整流通股數"},
        ]), hide_index=True, width="stretch")
    st.info(
        "研究模型使用當時以前的歷史列尋找相似情境，未使用未來資料；"
        "正式上線仍需補足5年以上歷史、Walk-forward回測與交易成本驗證。"
    )


@st.cache_data(ttl=600, show_spinner=False)
def _data_inventory(symbol: str) -> list[dict[str, object]]:
    database = PROJECT_ROOT / "data" / "stock_predictor.db"
    stock_id = symbol.removesuffix(".TW")
    rows: list[dict[str, object]] = []
    if not database.exists():
        return [{
            "資料類別": "後台資料庫", "筆數": 0, "起始日期": "—", "最新日期": "—",
            "使用狀態": "資料庫不存在", "說明": "請先執行系統更新",
        }]
    SQLiteRepository(database).initialize()
    definitions = [
        (
            "個股價格與成交量", "tw_stock_daily", "trade_date",
            "REPLACE(UPPER(stock_id), '.TW', '') = ?", (stock_id,),
            "已使用", "OHLC、成交量、還原價格與技術指標",
        ),
        (
            "法人與籌碼", "institutional_trading", "trade_date",
            "REPLACE(UPPER(stock_id), '.TW', '') = ?", (stock_id,),
            "已使用", "外資、投信、自營商、融資券與借券",
        ),
        (
            "總體經濟", "macro_observation", "observation_date",
            "1 = 1", (),
            "已使用", "FRED／ALFRED點時歷史，不使用事後不可得數值",
        ),
        (
            "新聞與事件", "financial_event", "tw_effective_trade_date",
            "tw_effective_trade_date IS NOT NULL", (),
            "已使用", "依公開時間對齊下一個可使用的台股交易日",
        ),
        (
            "基本面與估值", "financial_statement", "effective_trade_date",
            "REPLACE(UPPER(stock_id), '.TW', '') = ?", (stock_id,),
            "已使用最近一次資料", "依公告或蒐集時間，使用當時最近一次月營收、財報、PER、PBR與殖利率",
        ),
    ]
    with sqlite3.connect(database) as connection:
        for label, table, date_column, condition, parameters, state, note in definitions:
            count, earliest, latest = connection.execute(
                f"SELECT COUNT(*), MIN({date_column}), MAX({date_column}) "
                f"FROM {table} WHERE {condition}",
                parameters,
            ).fetchone()
            rows.append({
                "資料類別": label,
                "筆數": int(count or 0),
                "起始日期": str(earliest or "—")[:10],
                "最新日期": str(latest or "—")[:10],
                "使用狀態": state if count else "目前無資料",
                "說明": note,
            })
    return rows
