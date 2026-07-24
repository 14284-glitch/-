"""Model prediction dashboard; never creates or displays fabricated forecasts."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config.color_config import COLORS
from config.settings import PROJECT_ROOT
from config.universe import TAIWAN_50_CONSTITUENTS, load_popular_etfs
from models.price_average_estimator import RANGE_PERCENT, estimate_universe
from models.research_forecaster import forecast_from_price_history
from pages.chart_factory import prediction_chart
from pages.glossary import prediction_legend_items, render_chart_with_legend, render_glossary
from pages.stock_analysis import _sort_stocks_by_popularity

PREDICTION_PATH = PROJECT_ROOT / "data" / "processed" / "latest_prediction.csv"
CHART_COLUMNS = {"trade_date", "actual_price", "predicted_price", "prediction_upper", "prediction_lower"}


@st.cache_data(ttl=600, show_spinner=False)
def _cached_average_estimates(universe_items: tuple[tuple[str, str], ...]) -> pd.DataFrame:
    return estimate_universe(dict(universe_items), PROJECT_ROOT / "data" / "raw" / "tw")


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
    st.subheader("3、7、14日平均價區間估算")
    st.caption(
        "依截至資料日最近3、7、14個交易日收盤平均價計算；"
        f"下界＝平均價的 {1 - RANGE_PERCENT:.0%}，上界＝平均價的 {1 + RANGE_PERCENT:.0%}。"
    )
    category = st.selectbox(
        "選擇估算標的類別",
        ("全部個股與ETF（100檔）", "臺灣50成分股（50檔）", "臺灣市場熱門ETF（50檔）"),
        accept_new_options=False,
        filter_mode=None,
    )
    stocks = _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
    etfs = load_popular_etfs()
    if category == "全部個股與ETF（100檔）":
        universe = {**stocks, **etfs}
    elif category == "臺灣50成分股（50檔）":
        universe = _sort_stocks_by_popularity(TAIWAN_50_CONSTITUENTS)
    else:
        universe = etfs
    estimates = _cached_average_estimates(tuple(universe.items()))
    if estimates.empty:
        st.warning("目前沒有足夠14個交易日的行情資料可供估算，請先更新資料。")
        return

    labels = {
        f"{row['name']}（{row['symbol']}）": row["symbol"]
        for _, row in estimates.iterrows()
    }
    selected_label = st.selectbox(
        "選擇個股或ETF查看估算",
        list(labels),
        accept_new_options=False,
        filter_mode=None,
    )
    selected_symbol = labels[selected_label]
    selected = estimates[estimates["symbol"] == selected_symbol].iloc[0]
    st.caption(f"資料截至：{selected['data_date']:%Y/%m/%d}｜目前類別可估算 {len(estimates)} 檔")
    columns = st.columns(4)
    specs = (
        ("最新收盤價", "latest_close"),
        ("3日平均價", "average_3d"),
        ("7日平均價", "average_7d"),
        ("14日平均價", "average_14d"),
    )
    for column, (label, field) in zip(columns, specs):
        with column:
            st.metric(label, f"{selected[field]:,.2f}")
    st.markdown("#### 三種平均期間的±80%估算")
    detail = pd.DataFrame([
        {
            "平均期間": f"{window}個交易日",
            "平均價": selected[f"average_{window}d"],
            "下界（平均價−80%）": selected[f"lower_{window}d"],
            "上界（平均價＋80%）": selected[f"upper_{window}d"],
        }
        for window in (3, 7, 14)
    ])
    st.dataframe(
        detail.style.format({column: "{:,.2f}" for column in detail.columns[1:]}),
        hide_index=True,
        width="stretch",
    )
    st.info(
        f"三個平均值綜合估算：中心價 {selected['estimated_price']:,.2f}，"
        f"區間 {selected['estimated_lower']:,.2f}～{selected['estimated_upper']:,.2f}。"
    )
    _render_research_forecast(selected_symbol)

    with st.expander(f"查看{category}全部估算", expanded=False):
        display = estimates[[
            "symbol", "name", "data_date", "latest_close", "average_3d", "average_7d", "average_14d",
            "estimated_price", "estimated_lower", "estimated_upper",
        ]].rename(columns={
            "symbol": "代號", "name": "名稱", "data_date": "資料日期", "latest_close": "最新收盤價",
            "average_3d": "3日平均", "average_7d": "7日平均", "average_14d": "14日平均",
            "estimated_price": "綜合中心價", "estimated_lower": "估算下界", "estimated_upper": "估算上界",
        })
        st.dataframe(display, hide_index=True, width="stretch")
    st.warning(
        "±80%是使用者指定的極寬統計範圍，不代表價格有80%機率落在區間內。"
        "此功能不是已驗證的機器學習預測，也不構成買賣建議。"
    )
    with st.expander("Logistic Regression與XGBoost開發狀態"):
        st.info("⏳ 正在訓練與進行時間序列驗證；完成未來資料防護與回測後才會顯示上漲機率。")


def _render_research_forecast(symbol: str) -> None:
    st.divider()
    st.subheader("第一階段研究預測｜歷史相似情境")
    st.caption("1日、5日、20日使用不同輸入視窗、盤整門檻與歷史情境，不共用完全相同規則。")
    try:
        result = _cached_research_forecast(f"{symbol}.TW")
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
        st.dataframe(pd.DataFrame([
            {"資料類別": "價格、成交量與技術指標", "目前狀態": "已使用", "內容": "OHLC、成交量、報酬、波動、均線、RSI、KD、MACD、布林"},
            {"資料類別": "大盤、產業與前一晚美股", "目前狀態": "部分完成", "內容": "已蒐集台股、美股、費半、VIX、ADR、匯率、美債；待正式點時對齊模型"},
            {"資料類別": "法人、籌碼與衍生品", "目前狀態": "尚未接入模型", "內容": "三大法人、融資券、借券、期權、主力與集保"},
            {"資料類別": "基本面與估值", "目前狀態": "尚未接入模型", "內容": "營收、財報、現金流、ROE、估值與產業供需"},
            {"資料類別": "總體經濟", "目前狀態": "部分蒐集", "內容": "美債、匯率、VIX已蒐集；CPI、PMI、GDP等待點時資料庫"},
            {"資料類別": "新聞、事件與情緒", "目前狀態": "已有新聞，尚未接入價格模型", "內容": "需先完成去重、來源可信度與事件時間標記"},
            {"資料類別": "逐筆、大單小單與週轉率", "目前狀態": "資料來源不足", "內容": "目前日線來源沒有逐筆成交與完整流通股數"},
        ]), hide_index=True, width="stretch")
    st.info(
        "研究模型使用當時以前的歷史列尋找相似情境，未使用未來資料；"
        "正式上線仍需補足5年以上歷史、Walk-forward回測與交易成本驗證。"
    )
