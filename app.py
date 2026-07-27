"""Streamlit web entry point for the Taiwan stock prediction platform."""

from datetime import datetime
import json
import os
import sqlite3
from zoneinfo import ZoneInfo

import streamlit as st

from config.color_config import COLORS
from config.settings import PROJECT_ROOT, get_settings
from pages import (
    backtest_dashboard,
    dividend_dashboard,
    financial_news,
    market_overview,
    prediction_dashboard,
    stock_analysis,
)


def _read_update_status_safely() -> dict:
    """Read update status without importing the optional update backend."""
    status_path = PROJECT_ROOT / "logs" / "update_status.json"
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


@st.fragment(run_every="15s")
def render_system_status() -> None:
    st.header("系統與資料更新")
    st.info(
        "更新由網路上的 Streamlit 伺服器執行，不依賴家中電腦。"
        "系統每天於台北時間 07:00、14:00、21:00 自動更新，也可隨時手動更新。"
    )
    status = _read_update_status_safely()
    is_running = status.get("status") == "running"
    if st.button(
        "🔄 正在更新資料…" if is_running else "🔄 立即更新所有資料",
        type="primary",
        width="stretch",
        disabled=is_running,
    ):
        try:
            # Load the update backend only when requested. An optional cloud
            # dependency must not prevent the rest of the dashboard from opening.
            from scripts.update_daily_data import start_background_update

            start_background_update(trigger="manual")
            st.session_state["manual_update_started"] = True
        except Exception as exc:
            if exc.__class__.__name__ == "UpdateAlreadyRunning":
                st.warning(str(exc))
            else:
                st.error("手動更新服務目前無法啟動，但其他頁面仍可正常使用。請稍後再試。")
                st.caption(f"系統診斷：{exc.__class__.__name__}: {exc}")
        st.rerun()
    if st.session_state.pop("manual_update_started", False):
        st.success("手動更新已在背景啟動。可繼續瀏覽頁面，稍後按下方按鈕查看結果。")
    if st.button("查看最新更新進度", width="stretch"):
        st.rerun()
    if not status:
        st.warning("尚無更新紀錄。")
        return
    try:
        finished_at = datetime.fromisoformat(str(status["finished_at"]))
        started_at = datetime.fromisoformat(str(status["started_at"]))
    except (KeyError, TypeError, ValueError):
        st.warning("更新紀錄格式異常，請重新執行手動更新。")
        return
    elapsed_seconds = max(0, int((finished_at - started_at).total_seconds()))
    status_label = {
        "running": "正在更新",
        "success": "正常",
        "warning": "完成，部分沿用快取",
        "failed": "需要檢查",
    }.get(str(status["status"]), "需要檢查")
    status_color = (
        COLORS["signal"]["strong_buy"]
        if status["status"] == "success"
        else (
            COLORS["signal"]["bullish"]
            if status["status"] in {"warning", "running"}
            else COLORS["signal"]["high_risk"]
        )
    )
    status_columns = st.columns(4)
    status_columns[0].metric("系統狀態", status_label)
    status_columns[1].metric(
        "開始時間" if is_running else "最後更新",
        started_at.strftime("%Y/%m/%d %H:%M") if is_running else finished_at.strftime("%Y/%m/%d %H:%M"),
    )
    if is_running:
        elapsed_seconds = max(
            0,
            int((datetime.now(ZoneInfo("Asia/Taipei")) - started_at).total_seconds()),
        )
    status_columns[2].metric("目前耗時" if is_running else "更新耗時", f"{elapsed_seconds // 60}分 {elapsed_seconds % 60}秒")
    status_columns[3].metric("觸發方式", {"manual": "手動", "schedule": "排程", "github": "GitHub"}.get(status["trigger"], status["trigger"]))

    settings = get_settings()
    st.subheader("資料庫狀態")
    cloud_state = "已連線" if settings.gcp_project_id else "尚未設定"
    cloud_mode = "免費沙盒模式" if os.getenv("BIGQUERY_SANDBOX_MODE", "false").lower() == "true" else "正式分區模式"
    database_columns = st.columns(3)
    database_columns[0].metric("BigQuery", cloud_state)
    database_columns[1].metric("雲端資料集", settings.bigquery_dataset)
    database_columns[2].metric("儲存模式", cloud_mode)
    if settings.gcp_project_id:
        st.caption(
            f"Google Cloud 專案：{settings.gcp_project_id}｜"
            f"地區：{settings.bigquery_location}｜憑證存放於本機安全目錄，不會顯示或上傳。"
        )

    table_labels = {
        "tw_stock_daily": "台股行情",
        "institutional_trading": "法人籌碼",
        "macro_observation": "總體歷史",
        "financial_event": "財經事件",
    }
    database_path = PROJECT_ROOT / "data" / "stock_predictor.db"
    if database_path.exists():
        with sqlite3.connect(database_path) as connection:
            counts = {
                label: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table, label in table_labels.items()
            }
        count_columns = st.columns(len(counts))
        for column, (label, count) in zip(count_columns, counts.items()):
            column.metric(label, f"{count:,} 筆")

    st.subheader("目前更新進度" if is_running else "最近一次更新流程")
    st.markdown(f"<div style='border-left:5px solid {status_color};padding:.7rem 1rem'>"
                f"最後完成：{finished_at:%Y/%m/%d %H:%M:%S}（台北時間）"
                f"</div>", unsafe_allow_html=True)
    for step in status.get("steps", []):
        icon = {"running": "🔄", "success": "✅", "warning": "⚠️", "failed": "❌"}.get(step["status"], "ℹ️")
        st.write(f"{icon} {step['name']}：{step['message']}")
    if is_running and isinstance(status.get("previous"), dict):
        previous = status["previous"]
        st.subheader("上一次完成的更新內容")
        try:
            previous_finished = datetime.fromisoformat(str(previous["finished_at"]))
            st.caption(f"完成時間：{previous_finished:%Y/%m/%d %H:%M:%S}（台北時間）")
        except (KeyError, TypeError, ValueError):
            pass
        for step in previous.get("steps", []):
            icon = {"success": "✅", "warning": "⚠️", "failed": "❌"}.get(step.get("status"), "ℹ️")
            st.write(f"{icon} {step.get('name', '更新項目')}：{step.get('message', '')}")


def main() -> None:
    settings = get_settings()
    st.set_page_config(
        page_title=settings.app_name,
        page_icon="📈",
        layout="wide",
        menu_items={"Get Help": None, "Report a bug": None, "About": "台股智慧預測與分析系統｜僅供資料分析與研究使用。"},
    )
    st.markdown(
        """
        <style>
        /* Phone and tablet layout: preserve readable controls and full-width charts. */
        [data-testid="stAppViewContainer"] .main .block-container {
            max-width: 1500px; padding-top: 1.25rem; padding-bottom: 2rem;
        }
        [data-testid="stPlotlyChart"] { width: 100% !important; }
        [data-testid="stMetric"] { min-width: 0; }
        [data-testid="stMetricValue"] { font-size: clamp(1.15rem, 4vw, 2rem); }
        .mobile-chart-hint { display: none; }
        @media (max-width: 768px) {
            [data-testid="stAppViewContainer"] .main .block-container {
                padding-left: .75rem; padding-right: .75rem; padding-top: .75rem;
            }
            h1 { font-size: 1.65rem !important; line-height: 1.25 !important; }
            h2 { font-size: 1.35rem !important; }
            h3 { font-size: 1.12rem !important; }
            [data-testid="stHorizontalBlock"] { gap: .5rem; }
            [data-testid="column"] { min-width: 100% !important; flex: 1 1 100% !important; }
            .stButton > button { min-height: 44px; width: 100%; }
            [data-baseweb="select"] { min-height: 44px; }
            [data-testid="stDataFrame"] { overflow-x: auto; }
            /* Fit every chart to the phone screen without widening the whole page. */
            [data-testid="stPlotlyChart"] {
                width: 100% !important; max-width: 100% !important; overflow: hidden;
                border: 1px solid rgba(127,127,127,.18);
                border-radius: .4rem;
            }
            [data-testid="stPlotlyChart"] > div,
            [data-testid="stPlotlyChart"] .js-plotly-plot {
                min-width: 0 !important; width: 100% !important; max-width: 100% !important;
            }
            /* On phones the chart never captures pinch/drag zoom; only vertical page scrolling remains. */
            [data-testid="stPlotlyChart"],
            [data-testid="stPlotlyChart"] .js-plotly-plot,
            [data-testid="stPlotlyChart"] .draglayer,
            [data-testid="stPlotlyChart"] .nsewdrag {
                touch-action: pan-y !important;
            }
            .mobile-chart-hint {
                display: block; margin: .25rem 0 .4rem; padding: .4rem .6rem;
                background: rgba(31,119,180,.08); border-radius: .35rem;
                font-size: .9rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.title("台股智慧預測與分析系統")
    st.caption("本系統僅供資料分析與研究，模型結果不代表或保證任何投資獲利。")
    st.sidebar.title("功能導覽")
    st.sidebar.caption("請選擇要查看的功能頁面")
    page = st.sidebar.radio(
        "功能選單",
        ("財經新聞", "市場總覽", "個股分析", "股息分析", "模型預測", "策略回測", "系統狀態"),
        help="切換財經新聞、市場行情、個股技術分析、股息分析與試算、模型預測、策略回測或系統更新狀態。",
    )
    renderers = {
        "財經新聞": financial_news.render, "市場總覽": market_overview.render,
        "個股分析": stock_analysis.render,
        "股息分析": dividend_dashboard.render,
        "模型預測": prediction_dashboard.render, "策略回測": backtest_dashboard.render,
        "系統狀態": render_system_status,
    }
    renderers[page]()
    sidebar_descriptions = {
        "財經新聞": "瀏覽最新財經新聞，可使用固定的分類與新聞來源選單篩選。",
        "市場總覽": "比較台股與主要美國市場的相對走勢。",
        "個股分析": "查看K線、均線、成交量與技術指標。",
        "股息分析": "查看最新與歷年股息、填息狀態，並使用可操作的股息試算機。",
        "模型預測": "查看已驗證模型產生的預測與不確定區間。",
        "策略回測": "檢查策略的歷史績效與風險。",
        "系統狀態": "查看資料更新時間、執行結果及手動更新功能。",
    }
    st.sidebar.info(sidebar_descriptions[page])
    st.sidebar.divider()
    st.sidebar.caption(f"目前台北時間：{datetime.now(ZoneInfo('Asia/Taipei')):%Y-%m-%d %H:%M:%S}")
    st.sidebar.caption("本系統僅供研究，不構成投資建議。")
    st.sidebar.caption("介面版本：2026.07.27-48（預測方向彩色提示版）")


if __name__ == "__main__":
    main()
