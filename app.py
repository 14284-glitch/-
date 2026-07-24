"""Streamlit web entry point for the Taiwan stock prediction platform."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from config.color_config import COLORS
from config.settings import get_settings
from pages import backtest_dashboard, financial_news, market_overview, prediction_dashboard, stock_analysis
from scripts.update_daily_data import UpdateAlreadyRunning, read_last_status, run_update


def render_system_status() -> None:
    st.header("系統與資料更新")
    st.info("系統每天於台北時間 07:00、14:00、21:00 自動更新，也可隨時手動更新。")
    if st.button("🔄 立即更新所有資料", type="primary", width="stretch"):
        try:
            with st.spinner("正在更新資料，請勿重複按下按鈕……"):
                result = run_update(trigger="manual")
            st.success("更新完成。") if result.status == "success" else st.error("部分更新失敗，請查看下方紀錄。")
        except UpdateAlreadyRunning as exc:
            st.warning(str(exc))
        st.rerun()
    status = read_last_status()
    if not status:
        st.warning("尚無更新紀錄。")
        return
    color = COLORS["signal"]["strong_buy"] if status["status"] == "success" else COLORS["signal"]["high_risk"]
    st.markdown(f"<div style='border-left:5px solid {color};padding:.7rem 1rem'>"
                f"最後完成：{datetime.fromisoformat(str(status['finished_at'])):%Y-%m-%d %H:%M:%S}（台北時間）"
                f"</div>", unsafe_allow_html=True)
    for step in status.get("steps", []):
        st.write(f"{'✅' if step['status'] == 'success' else '❌'} {step['name']}：{step['message']}")


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
        ("財經新聞", "市場總覽", "個股分析", "模型預測", "策略回測", "系統狀態"),
        help="切換財經新聞首頁、市場行情、個股技術分析、模型預測、策略回測或系統更新狀態。",
    )
    renderers = {
        "財經新聞": financial_news.render, "市場總覽": market_overview.render,
        "個股分析": stock_analysis.render,
        "模型預測": prediction_dashboard.render, "策略回測": backtest_dashboard.render,
        "系統狀態": render_system_status,
    }
    renderers[page]()
    sidebar_descriptions = {
        "財經新聞": "瀏覽最新財經新聞，可依分類、來源或關鍵字篩選。",
        "市場總覽": "比較台股與主要美國市場的相對走勢。",
        "個股分析": "查看K線、均線、成交量與技術指標。",
        "模型預測": "查看已驗證模型產生的預測與不確定區間。",
        "策略回測": "檢查策略的歷史績效與風險。",
        "系統狀態": "查看資料更新時間、執行結果及手動更新功能。",
    }
    st.sidebar.info(sidebar_descriptions[page])
    st.sidebar.divider()
    st.sidebar.caption(f"目前台北時間：{datetime.now(ZoneInfo('Asia/Taipei')):%Y-%m-%d %H:%M:%S}")
    st.sidebar.caption("本系統僅供研究，不構成投資建議。")
    st.sidebar.caption("介面版本：2026.07.24-34")


if __name__ == "__main__":
    main()
