"""Market overview with normalized, colorblind-friendly cross-market lines."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.color_config import COLORS, LINE_STYLES
from config.settings import PROJECT_ROOT
from collectors.news_collector import load_news_cache
from features.market_trend_analysis import analyze_market_and_news
from pages.chart_factory import add_attention_trace, apply_chart_layout
from pages.glossary import market_legend_items, render_chart_with_legend, render_glossary


SERIES = {
    "台灣加權指數": ("tw/INDEX_TWII.csv", "twii"),
    "S&P 500｜標普500指數": ("us/INDEX_GSPC.csv", "sp500"),
    "Nasdaq 100｜那斯達克100指數": ("us/INDEX_NDX.csv", "nasdaq100"),
    "SOX｜費城半導體指數": ("us/INDEX_SOX.csv", "sox"),
}


def render() -> None:
    st.header("市場總覽")
    figure = go.Figure()
    for label, (relative_path, style_key) in SERIES.items():
        path = PROJECT_ROOT / "data" / "raw" / relative_path
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        date_column = "trade_date" if "trade_date" in frame else "us_trade_date"
        frame[date_column] = pd.to_datetime(
            frame[date_column], format="mixed", errors="coerce"
        )
        frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
        frame = frame.dropna(subset=[date_column, "close"]).sort_values(date_column)
        if frame.empty:
            continue
        frame = frame.tail(252)
        normalized = frame["close"] / frame["close"].iloc[0] * 100
        figure.add_trace(go.Scatter(
            x=frame[date_column], y=normalized, name=label, mode="lines",
            line=dict(color=COLORS["market"][style_key], width=3 if style_key == "twii" else 2,
                      dash=LINE_STYLES["market"][style_key]),
            hovertemplate=f"{label}：%{{y:.2f}}<extra></extra>",
        ))
    if not figure.data:
        st.warning("尚無市場資料，請先執行更新。")
        return
    first_trace = figure.data[0]
    attention_notes = pd.Series("比較臺灣加權指數與美股指數的相對強弱；若走勢明顯分歧，注意隔日連動風險。", index=range(len(first_trace.x)))
    add_attention_trace(figure, pd.Series(first_trace.x), pd.Series(first_trace.y), attention_notes)
    render_chart_with_legend(
        apply_chart_layout(figure, "主要市場近一年相對走勢（起點＝100）", "指數化價格", True),
        market_legend_items(),
        "market_overview",
        default_period="3個月",
        dynamic_title_prefix="主要市場相對走勢",
    )
    render_glossary(("SP500", "NASDAQ100", "SOX"))
    _render_ai_trend_summary()


def _render_ai_trend_summary() -> None:
    st.divider()
    st.subheader("目前台灣與全球財經趨勢")
    st.caption("整合目前可取得的市場價格與公開資訊；數據獨立列示，正文以白話說明現況、原因與可能發展。")
    try:
        analysis = analyze_market_and_news(PROJECT_ROOT / "data" / "raw", load_news_cache())
    except Exception as exc:
        st.warning(f"目前無法產生綜合趨勢：{exc}")
        return
    columns = st.columns(3)
    for column, trend in zip(columns, analysis["trends"]):
        with column:
            st.markdown(f"#### {trend.name}趨勢｜{trend.trading_days}日")
            st.metric("綜合方向", trend.direction, f"評分 {trend.score:+.1f}")
            st.write(trend.narrative)
    _render_regional_trend(
        "目前台灣財經趨勢", analysis["taiwan_detail"], analysis["taiwan_industries"]
    )
    _render_regional_trend(
        "目前全球財經趨勢", analysis["global_detail"], analysis["global_industries"]
    )
    st.markdown("#### 未來方向與研究規劃")
    st.write(
        "研究重點不是猜一個確定答案，而是持續確認哪些條件正在改善、哪些風險正在升高，"
        "並讓每個判斷都有可檢查的資料、時間範圍與失效條件。"
    )
    for item in analysis["plan"]:
        st.markdown(f"- {item}")
    st.caption(
        f"市場資料截止：{analysis['market_as_of']}｜新聞 {analysis['news_count']} 則｜"
        f"市場序列 {analysis['market_count']} 組｜新聞快取時間：{analysis['news_as_of']}"
    )
    st.info("本區為可解釋的統計與文字綜合分析，只供研究；不是保證預測、買賣指示或個人化投資建議。")


def _render_regional_trend(
    title: str, detail: dict[str, object], industries: list[str]
) -> None:
    st.markdown(f"#### {title}")
    st.markdown("##### 現在的情況")
    st.write(detail["current"])
    st.markdown("##### 形成原因")
    st.write(detail["reason"])
    st.markdown("##### 接下來可能怎麼發展")
    st.write(detail["outlook"])
    st.markdown("##### 觀察數據")
    st.dataframe(
        pd.DataFrame(detail["metrics"]),
        width="stretch",
        hide_index=True,
        column_config={
            "指標": st.column_config.TextColumn("指標"),
            "數值": st.column_config.TextColumn("目前數值"),
            "用途": st.column_config.TextColumn("觀看重點"),
        },
    )
    st.markdown("##### 產業趨勢")
    for item in industries:
        st.markdown(f"- {item}")
